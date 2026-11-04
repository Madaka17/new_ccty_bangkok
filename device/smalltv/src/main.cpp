// SmallTV Ultra desk display: shows the Raspberry Pi's CPU, RAM, estimated power and temperature.
// Polls the Pi stats service (STATS_URL) every POLL_MS and keeps /update for WiFi firmware updates.
// A design uploaded to /design/* (kept in LittleFS) replaces the built-in look; device/README.md has the rules.
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPUpdateServer.h>
#include <WiFiManager.h>
#include <TFT_eSPI.h>
#include <EEPROM.h>
#include <LittleFS.h>
#include <math.h>

#include "config.h"
#include "layout.h"
#include "stats.h"

static const uint16_t GREY = 0x8410;
static const uint16_t DIM = 0x2104;
static const int BAR_X = 10, BAR_W = 220, BAR_H = 10;

TFT_eSPI tft;
ESP8266WebServer server(80);
ESP8266HTTPUpdateServer updater;

Stats stats = {0, 0, 0, 0, 0, 0};
bool haveStats = false;
uint32_t lastOkMs = 0;
uint32_t lastPollMs = 0;
uint32_t lastWifiOkMs = 0;
uint32_t lastKickMs = 0;
String lastResult = "not fetched yet";
char statsUrl[STATS_URL_MAX + 1] = STATS_URL;
Screen shown;
bool shownValid = false;  // false: the next drawStats must redraw

// EEPROM layout: byte 0 = URL_MAGIC when a URL set through /set is stored, then the URL with its 0.
static const uint8_t URL_MAGIC = 0xA5;

static void loadStatsUrl() {
    EEPROM.begin(STATS_URL_MAX + 2);
    if (EEPROM.read(0) != URL_MAGIC) return;
    char buf[STATS_URL_MAX + 1];
    for (int i = 0; i <= STATS_URL_MAX; i++) buf[i] = (char)EEPROM.read(1 + i);
    buf[STATS_URL_MAX] = 0;
    if (validStatsUrl(buf)) strcpy(statsUrl, buf);
}

static void saveStatsUrl(const char* url, bool custom) {
    EEPROM.write(0, custom ? URL_MAGIC : 0);
    for (int i = 0; i <= STATS_URL_MAX; i++) EEPROM.write(1 + i, custom && i <= (int)strlen(url) ? url[i] : 0);
    EEPROM.commit();
    strcpy(statsUrl, url);
}

static void backlight(int level) {
    analogWriteRange(1023);
    analogWrite(PIN_BL, 1023 - level);  // inverted
}

static void splash(const char* line1, const char* line2) {
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(TC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("BKK Pi Monitor", 120, 60, 4);
    tft.setTextColor(GREY, TFT_BLACK);
    tft.drawString("fw " FW_VERSION, 120, 92, 2);
    tft.setTextColor(TFT_CYAN, TFT_BLACK);
    tft.drawString(line1, 120, 130, 2);
    tft.drawString(line2, 120, 150, 2);
}

static void drawFrame() {
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString("Raspberry Pi", 10, 6, 4);
    tft.setTextColor(GREY, TFT_BLACK);
    tft.drawString("CPU", 10, 44, 2);
    tft.drawString("RAM", 10, 92, 2);
    tft.drawString("PWR", 10, 142, 2);
    tft.drawString("TEMP", 130, 142, 2);
    tft.setTextDatum(BL_DATUM);
    tft.drawString(WiFi.localIP().toString(), 10, 238, 1);
}

static void drawBar(int y, float pct, bool stale) {
    int w = barWidth(pct, BAR_W);
    tft.fillRect(BAR_X, y, w, BAR_H, stale ? GREY : levelColor(pct));
    tft.fillRect(BAR_X + w, y, BAR_W - w, BAR_H, DIM);
}

static void drawValue(const String& text, int x, int y, int font, int pad, uint16_t color) {
    tft.setTextDatum(TR_DATUM);
    tft.setTextColor(color, TFT_BLACK);
    tft.setTextPadding(pad);
    tft.drawString(text, x, y, font);
    tft.setTextPadding(0);
}

// ---- stored design: /base.rgb (240x240 RGB565, big-endian), /layout.json, /anim.bin

static const uint32_t PANEL_PX = 240;
static const uint32_t BASE_BYTES = PANEL_PX * PANEL_PX * 2;
static const uint32_t LAYOUT_MAX = 2048;
static const uint32_t ANIM_HEADER = 48;
static const uint32_t ANIM_MAX = ANIM_HEADER + 4096;  // v2 header plus at most 4096 cells
static const uint8_t ALL_WIDGETS = (1u << W_COUNT) - 1;
static const char* const BASE_PATH = "/base.rgb";
static const char* const LAYOUT_PATH = "/layout.json";
static const char* const ANIM_PATH = "/anim.bin";

static bool fsOk = false;        // LittleFS mounted; without it there is no design and no upload
static bool designMode = false;  // base and layout are good: draw the stored design, not the built-in look
static Layout layout;            // the stored layout; used only in design mode
static bool animActive = false;  // animBuf holds a valid sprite and design mode is on
static uint8_t animBuf[ANIM_MAX];  // the active sprite
static uint8_t animLast[32 * 32];  // last drawn palette index per cell
static bool animForce = false;     // draw every cell on the next tick
static uint8_t animFrame = 0;
static uint32_t lastAnimMs = 0;

// Streams rows of /base.rgb to the panel. The bytes go out in file order (big-endian RGB565) because
// TFT_eSPI's pushImage keeps swapBytes false; the hardware check confirms the colours are not swapped.
static void pushBaseRows(File& base, int x, int y, int w, int h) {
    uint16_t row[PANEL_PX];  // 480 bytes on the stack
    for (int r = y; r < y + h; r++) {
        base.seek(((uint32_t)r * PANEL_PX + x) * 2);
        base.read((uint8_t*)row, w * 2);
        tft.pushImage(x, r, w, 1, row);
        yield();
    }
}

static void drawDesignBar(const Rect& r, float pct, bool stale) {
    const int w = barWidth(pct, r.w);
    tft.fillRect(r.x, r.y, w, r.h, stale ? layout.muted : levelColorOf(layout, pct));
    tft.fillRect(r.x + w, r.y, r.w - w, r.h, layout.track);
}

// Transparent text (one-argument setTextColor), right-aligned to the widget's right edge, top at y.
static void drawDesignText(const Rect& r, const String& text, uint16_t color) {
    tft.setTextDatum(TR_DATUM);
    tft.setTextColor(color);
    tft.drawString(text, r.x + r.w, r.y, r.font);
}

static void drawDesignWidget(int id, const Rect& r, const Screen& now) {
    const uint16_t value = now.stale ? layout.muted : layout.text;
    tft.setViewport(r.x, r.y, r.w, r.h, false);
    switch (id) {
        case W_CPU_VALUE: drawDesignText(r, String(now.cpu) + "%", value); break;
        case W_CPU_BAR: drawDesignBar(r, stats.cpu, now.stale); break;
        case W_RAM_VALUE: drawDesignText(r, String(now.ram) + "%", value); break;
        case W_RAM_BAR: drawDesignBar(r, stats.ram, now.stale); break;
        case W_POWER: {
            char text[24];
            snprintf(text, sizeof(text), "~%d.%d W", now.watts10 / 10, now.watts10 % 10);
            drawDesignText(r, text, value);
            break;
        }
        case W_TEMP:
            drawDesignText(r, now.temp == SCREEN_NO_TEMP ? String("-- C") : String(now.temp) + " C", value);
            break;
        case W_FOOTER:  // hidden while stale, as the built-in look does
            if (!now.stale) drawDesignText(r, String(now.ramUsedMb) + "/" + String(now.ramTotalMb) + " MB", layout.muted);
            break;
        case W_STATUS:
            if (now.stale) drawDesignText(r, now.wifiDown ? "No WiFi" : "Pi offline", layout.critical);
            break;
    }
    tft.resetViewport();
}

// Draws the stored design, redrawing only the widgets that changed. A full redraw (shownValid false)
// streams the whole base image first.
static void drawDesign(const Screen& now) {
    const bool full = !shownValid;
    const uint8_t bits = full ? ALL_WIDGETS : changedWidgets(shown, now);
    shown = now;
    shownValid = true;
    if (!bits) return;
    File base = LittleFS.open(BASE_PATH, "r");
    if (!base) {
        shownValid = false;  // try again on the next call
        return;
    }
    if (full) pushBaseRows(base, 0, 0, PANEL_PX, PANEL_PX);
    for (int i = 0; i < W_COUNT; i++) {
        const Rect& r = layout.w[i];
        if (!(bits & (1u << i)) || !r.visible) continue;
        if (!full) pushBaseRows(base, r.x, r.y, r.w, r.h);  // put back the base under the old value
        drawDesignWidget(i, r, now);
    }
    base.close();
    animForce = true;  // the sprite may sit under a widget that was just redrawn
}

static void drawStats(bool stale, bool wifiDown) {
    Screen now = screenOf(stats, stale, wifiDown);
    if (designMode) {
        drawDesign(now);
        return;
    }
    if (shownValid && sameScreen(now, shown)) return;  // nothing visible changed: no SPI traffic, no flicker
    shown = now;
    shownValid = true;
    uint16_t fg = stale ? GREY : TFT_WHITE;
    drawValue(String((int)(stats.cpu + 0.5f)) + "%", 230, 38, 4, 90, fg);
    drawBar(68, stats.cpu, stale);
    drawValue(String((int)(stats.ram + 0.5f)) + "%", 230, 86, 4, 90, fg);
    drawBar(116, stats.ram, stale);
    drawValue("~" + String(stats.watts, 1) + " W", 120, 164, 4, 108, fg);
    drawValue(isnan(stats.tempC) ? String("-- C") : String((int)(stats.tempC + 0.5f)) + " C", 230, 164, 4, 96, fg);
    tft.setTextDatum(BR_DATUM);
    tft.setTextPadding(110);
    if (stale) {
        tft.setTextColor(TFT_RED, TFT_BLACK);
        tft.drawString(wifiDown ? "No WiFi" : "Pi offline", 230, 238, 2);
    } else {
        tft.setTextColor(GREY, TFT_BLACK);
        tft.drawString(String(stats.ramUsedMb) + "/" + String(stats.ramTotalMb) + " MB", 230, 238, 1);
    }
    tft.setTextPadding(0);
}

static void poll() {
    WiFiClient client;
    HTTPClient http;
    http.setTimeout(1500);
    if (!http.begin(client, statsUrl)) {
        lastResult = "http begin failed";
        return;
    }
    int code = http.GET();
    if (code == HTTP_CODE_OK) {
        String body = http.getString();
        if (parseStats(body.c_str(), stats)) {
            haveStats = true;
            lastOkMs = millis();
            lastResult = "ok";
        } else {
            lastResult = "bad json";
        }
    } else {
        lastResult = "http " + String(code);
    }
    http.end();
}

static void handleSet() {
    String url = server.arg("url");
    if (url == "default") {
        saveStatsUrl(STATS_URL, false);
    } else if (validStatsUrl(url.c_str())) {
        saveStatsUrl(url.c_str(), true);
    } else {
        server.send(400, "text/plain", "bad url: use http://HOST[:PORT]/PATH, at most 120 characters\n");
        return;
    }
    haveStats = false;  // values from the old URL must not show as live
    shownValid = false;
    server.send(200, "text/plain", "stats url: " + String(statsUrl) + "\n");
}

static void handleRoot() {
    String text = "SmallTV Pi monitor fw " FW_VERSION "\n";
    text += "stats url: " + String(statsUrl) + "\n";
    text += "wifi: " + WiFi.SSID() + " rssi " + String(WiFi.RSSI()) + " dBm\n";
    text += "last fetch: " + lastResult + "\n";
    text += "seconds since good fetch: " + (haveStats ? String((millis() - lastOkMs) / 1000) : String("never")) + "\n";
    text += "change stats url: /set?url=http://HOST:9101/stats   (url=default goes back to " STATS_URL ")\n";
    text += "firmware update: /update\n";
    server.send(200, "text/plain", text);
}

// Parses the layout file at path into out. out is set only when the file is good.
static bool readLayout(const char* path, Layout& out) {
    File f = LittleFS.open(path, "r");
    if (!f) return false;
    const uint32_t len = f.size();
    if (len > LAYOUT_MAX) {
        f.close();
        return false;
    }
    char* text = (char*)malloc(LAYOUT_MAX + 1);
    bool ok = text && f.read((uint8_t*)text, len) == (int)len;
    f.close();
    if (ok) {
        text[len] = 0;
        ok = parseLayout(text, out);
    }
    free(text);
    return ok;
}

// Reads exactly len bytes of path into buf. False when the file is missing or too short.
static bool readFile(const char* path, uint8_t* buf, uint32_t len) {
    File f = LittleFS.open(path, "r");
    if (!f) return false;
    const bool ok = f.read(buf, len) == (int)len;
    f.close();
    return ok;
}

// Loads /anim.bin into animBuf. A missing or invalid file just means no sprite.
static void loadAnim() {
    animActive = false;
    File f = LittleFS.open(ANIM_PATH, "r");
    if (!f) return;
    const uint32_t len = f.size();
    f.close();
    if (len > ANIM_MAX || !readFile(ANIM_PATH, animBuf, len) || !validAnim(animBuf, len)) return;
    animActive = true;
    animForce = true;
    animFrame = 0;
    lastAnimMs = millis() - 1000UL;  // draw on the next tick
}

// Reads the design files and sets the mode. A missing or invalid file means the built-in look.
static void loadDesign() {
    designMode = false;
    animActive = false;
    defaultLayout(layout);
    if (!fsOk) return;
    bool baseOk = false;
    File base = LittleFS.open(BASE_PATH, "r");
    if (base) {
        baseOk = base.size() == BASE_BYTES;
        base.close();
    }
    if (!baseOk) return;
    designMode = readLayout(LAYOUT_PATH, layout);
    if (designMode) loadAnim();
}

enum DesignSlot { SLOT_NONE, SLOT_BASE, SLOT_LAYOUT, SLOT_ANIM };
enum UploadError { UPERR_NONE, UPERR_NO_STORAGE, UPERR_WRITE, UPERR_TOO_LARGE };
static DesignSlot upSlot = SLOT_NONE;  // the file the current upload is for
static UploadError upError = UPERR_NONE;
static uint32_t upBytes = 0;
static File upFile;

static DesignSlot slotForUri(const String& uri) {
    if (uri == "/design/base") return SLOT_BASE;
    if (uri == "/design/layout") return SLOT_LAYOUT;
    if (uri == "/design/anim") return SLOT_ANIM;
    return SLOT_NONE;
}

static const char* slotPath(DesignSlot s) {
    return s == SLOT_BASE ? BASE_PATH : (s == SLOT_LAYOUT ? LAYOUT_PATH : ANIM_PATH);
}

static uint32_t slotLimit(DesignSlot s) {
    return s == SLOT_BASE ? BASE_BYTES : (s == SLOT_LAYOUT ? LAYOUT_MAX : ANIM_MAX);
}

static String tmpPath(DesignSlot s) { return String(slotPath(s)) + ".tmp"; }

static void closeUploadFile() {
    if (upFile) {
        upFile.close();
        upFile = File();
    }
}

// Upload parts go to <name>.tmp. Nothing replaces the design file until the whole part checks out.
static void handleDesignUpload() {
    HTTPUpload& up = server.upload();
    switch (up.status) {
        case UPLOAD_FILE_START:
            closeUploadFile();
            upSlot = slotForUri(server.uri());
            upBytes = 0;
            upError = UPERR_NONE;
            if (upSlot == SLOT_NONE) break;
            if (!fsOk) {
                upError = UPERR_NO_STORAGE;
                break;
            }
            upFile = LittleFS.open(tmpPath(upSlot), "w");
            if (!upFile) upError = UPERR_WRITE;
            break;
        case UPLOAD_FILE_WRITE:
            if (upSlot == SLOT_NONE || upError != UPERR_NONE) break;  // after a problem the rest is dropped
            if (upBytes + up.currentSize > slotLimit(upSlot)) {
                upError = UPERR_TOO_LARGE;
                break;
            }
            if (upFile.write(up.buf, up.currentSize) != up.currentSize) {
                upError = UPERR_WRITE;
                break;
            }
            upBytes += up.currentSize;
            break;
        case UPLOAD_FILE_END:
            closeUploadFile();
            break;
        case UPLOAD_FILE_ABORTED:
            closeUploadFile();
            if (upSlot != SLOT_NONE && fsOk) LittleFS.remove(tmpPath(upSlot));
            upSlot = SLOT_NONE;
            break;
    }
}

// Moves from over to. LittleFS.rename does not overwrite, so an existing to is removed first.
// This short window is the only unsafe moment: a power cut there leaves the file missing, which
// falls back to the built-in look, and never leaves a half-written design file.
static bool replaceFile(const char* from, const char* to) {
    if (LittleFS.rename(from, to)) return true;
    if (!LittleFS.exists(to)) return false;
    LittleFS.remove(to);
    return LittleFS.rename(from, to);
}

// Checks the finished tmp file and moves it into place. nullptr on success, else the reason to send.
static const char* acceptUpload(DesignSlot slot, uint32_t bytes) {
    const String tmp = tmpPath(slot);
    if (slot == SLOT_BASE && bytes != BASE_BYTES) return "bad size";
    if (slot == SLOT_LAYOUT) {
        Layout check;
        if (!readLayout(tmp.c_str(), check)) return "bad layout";
    }
    if (slot == SLOT_ANIM) {
        if (bytes == 0) {  // an empty upload removes the sprite
            LittleFS.remove(ANIM_PATH);
            LittleFS.remove(tmp);
            return nullptr;
        }
        if (!readFile(tmp.c_str(), animBuf, bytes) || !validAnim(animBuf, bytes)) return "bad anim";
    }
    if (!replaceFile(tmp.c_str(), slotPath(slot))) return "write failed";
    return nullptr;
}

// Redraws for the current design files: the stored design, or the built-in look when there is none.
static void refreshScreen() {
    const bool wifiDown = WiFi.status() != WL_CONNECTED;
    const bool stale = wifiDown || !haveStats || isStale(millis(), lastOkMs);
    if (!designMode) drawFrame();
    shownValid = false;
    drawStats(stale, wifiDown);
}

static void handleDesignDone() {
    const DesignSlot slot = upSlot;
    const uint32_t bytes = upBytes;
    const UploadError err = upError;
    upSlot = SLOT_NONE;
    upBytes = 0;
    upError = UPERR_NONE;
    const char* reason = nullptr;
    if (slot == SLOT_NONE) reason = "no file";
    else if (err == UPERR_NO_STORAGE) reason = "no storage";
    else if (err == UPERR_TOO_LARGE) reason = "too large";
    else if (err == UPERR_WRITE) reason = "write failed";
    else reason = acceptUpload(slot, bytes);
    if (reason && slot != SLOT_NONE && fsOk) LittleFS.remove(tmpPath(slot));
    loadDesign();  // also restores the sprite if an upload just overwrote it
    if (reason) {
        server.send(400, "text/plain", String(reason) + "\n");
        return;
    }
    refreshScreen();
    server.send(200, "text/plain", "ok\n");
}

static void handleDesignReset() {
    if (fsOk) {
        LittleFS.remove(BASE_PATH);
        LittleFS.remove(LAYOUT_PATH);
        LittleFS.remove(ANIM_PATH);
    }
    loadDesign();
    refreshScreen();
    server.send(200, "text/plain", "ok\n");
}

// Steps the sprite when its frame is due. Draws nothing without a sprite, or when fps is 0.
static void animTick() {
    if (!animActive || animBuf[8] == 0) return;
    const uint32_t period = 1000UL / animBuf[8];
    if (millis() - lastAnimMs < period) return;
    lastAnimMs = millis();
    const uint8_t w = animBuf[1], h = animBuf[2], sc = animBuf[3], n = animBuf[9];
    const int x = (int)animBuf[4] << 8 | animBuf[5];
    const int y = (int)animBuf[6] << 8 | animBuf[7];
    uint16_t pal[16];
    for (int i = 0; i < 16; i++) pal[i] = (uint16_t)(animBuf[10 + 2 * i] << 8 | animBuf[11 + 2 * i]);
    const uint8_t* cells = animBuf + ANIM_HEADER + (uint32_t)animFrame * w * h;
    for (uint8_t cy = 0; cy < h; cy++) {
        for (uint8_t cx = 0; cx < w; cx++) {
            const uint16_t k = (uint16_t)cy * w + cx;
            const uint8_t idx = cells[k];
            if (animForce || animLast[k] != idx) {
                tft.fillRect(x + cx * sc, y + cy * sc, sc, sc, pal[idx]);
                animLast[k] = idx;
            }
        }
    }
    animForce = false;
    animFrame = (animFrame + 1) % n;
}

// Sized for the longest reply: about 170 bytes.
static void handleInfo() {
    FSInfo fs = {};
    const unsigned long fsFree = fsOk && LittleFS.info(fs) ? fs.totalBytes - fs.usedBytes : 0;
    char buf[320];
    snprintf(buf, sizeof(buf),
             "{\"model\":\"smalltv\",\"fw\":\"" FW_VERSION "\",\"design\":%s,\"ip\":\"%s\",\"uptime_s\":%lu,"
             "\"free_heap\":%lu,\"fs_free\":%lu,\"reset_reason\":\"%s\"}",
             designMode ? "true" : "false", WiFi.localIP().toString().c_str(), millis() / 1000UL,
             (unsigned long)ESP.getFreeHeap(), fsFree, ESP.getResetReason().c_str());
    server.send(200, "application/json", buf);
}

void setup() {
    backlight(BL_LEVEL);
    loadStatsUrl();
    tft.init();
    tft.setRotation(0);
    splash("Storage...", "");  // LittleFS.begin() can take a while on a blank chip; a failure is not fatal
    fsOk = LittleFS.begin();
    splash("WiFi...", "");

    WiFi.mode(WIFI_STA);
    WiFi.begin();  // credentials saved in flash by WiFiManager
    String ssid = WiFi.SSID();
    splash("WiFi...", ssid.c_str());
    uint32_t start = millis();
    for (;;) {
        wl_status_t st = WiFi.status();
        BootWifi action = bootWifiAction(ssid.length() > 0, st == WL_CONNECTED, st == WL_WRONG_PASSWORD,
                                         millis() - start);
        if (action == BOOT_CONNECTED) break;
        if (action == BOOT_RESTART) ESP.restart();
        if (action == BOOT_PORTAL) {
            splash("Join WiFi " AP_NAME, "open 192.168.4.1");
            WiFiManager wm;
            wm.setConfigPortalTimeout(300);
            if (!wm.autoConnect(AP_NAME)) ESP.restart();
            break;
        }
        delay(250);
    }
    WiFi.setAutoReconnect(true);
    lastWifiOkMs = lastKickMs = millis();

    server.on("/", handleRoot);
    server.on("/set", handleSet);
    server.on("/info", handleInfo);
    server.on("/design/base", HTTP_POST, handleDesignDone, handleDesignUpload);
    server.on("/design/layout", HTTP_POST, handleDesignDone, handleDesignUpload);
    server.on("/design/anim", HTTP_POST, handleDesignDone, handleDesignUpload);
    server.on("/design/reset", HTTP_POST, handleDesignReset);
    updater.setup(&server, "/update");
    server.begin();

    loadDesign();
    refreshScreen();
}

void loop() {
    server.handleClient();
    animTick();
    uint32_t now = millis();
    if (now - lastPollMs < POLL_MS) return;
    lastPollMs = now;
    bool wifiDown = WiFi.status() != WL_CONNECTED;
    if (!wifiDown) {
        lastWifiOkMs = lastKickMs = now;
        poll();
    } else {
        lastResult = "no wifi";
        RunWifi action = runWifiAction(now, lastWifiOkMs, lastKickMs);
        if (action == RUN_RESTART) ESP.restart();
        if (action == RUN_RECONNECT) {
            WiFi.reconnect();
            lastKickMs = now;
        }
    }
    bool stale = wifiDown || !haveStats || isStale(millis(), lastOkMs);
    drawStats(stale, wifiDown);
}
