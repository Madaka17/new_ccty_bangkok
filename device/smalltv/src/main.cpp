// SmallTV Ultra desk display: shows the Raspberry Pi's CPU, RAM, estimated power and temperature.
// Polls the Pi stats service (STATS_URL) every POLL_MS and keeps /update for WiFi firmware updates.
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPUpdateServer.h>
#include <WiFiManager.h>
#include <TFT_eSPI.h>
#include <EEPROM.h>
#include <math.h>

#include "config.h"
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

static void drawStats(bool stale, bool wifiDown) {
    Screen now = screenOf(stats, stale, wifiDown);
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

void setup() {
    backlight(BL_LEVEL);
    loadStatsUrl();
    tft.init();
    tft.setRotation(0);
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
    updater.setup(&server, "/update");
    server.begin();

    drawFrame();
    shownValid = false;
    drawStats(true, false);
}

void loop() {
    server.handleClient();
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
