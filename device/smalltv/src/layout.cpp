#include "layout.h"
#include <ArduinoJson.h>
#include <string.h>

static const int SCREEN_PX = 240;
static const int ANIM_HEADER_BYTES = 48;

void defaultLayout(Layout& out) {
    out.w[W_CPU_VALUE] = {140, 38, 90, 26, 4, true};
    out.w[W_CPU_BAR] = {10, 68, 220, 10, 0, true};
    out.w[W_RAM_VALUE] = {140, 86, 90, 26, 4, true};
    out.w[W_RAM_BAR] = {10, 116, 220, 10, 0, true};
    out.w[W_POWER] = {12, 164, 108, 26, 4, true};
    out.w[W_TEMP] = {134, 164, 96, 26, 4, true};
    out.w[W_FOOTER] = {120, 230, 110, 8, 1, true};   // drawn bottom-aligned at y 238: font 1 is 8 px tall
    out.w[W_STATUS] = {120, 222, 110, 16, 2, true};  // font 2 is 16 px tall
    out.text = 0xFFFF;
    out.muted = 0x8410;
    out.ok = 0x07E0;
    out.warn = 0xFFE0;
    out.critical = 0xF800;
    out.track = 0x2104;
}

static const char* const WIDGET_KEYS[W_COUNT] = {
    "cpu_value", "cpu_bar", "ram_value", "ram_bar", "power", "temp", "footer", "status"};

static bool isBar(int id) { return id == W_CPU_BAR || id == W_RAM_BAR; }

static bool parseColor(JsonVariantConst v, uint16_t& out) {
    if (!v.is<int>()) return false;
    int c = v.as<int>();
    if (c < 0 || c > 65535) return false;
    out = (uint16_t)c;
    return true;
}

// Reads [x,y,w,h,font,visible]. Values are checked, then clamped onto the screen.
static bool parseRect(JsonVariantConst v, bool bar, Rect& out) {
    if (!v.is<JsonArrayConst>()) return false;
    JsonArrayConst a = v.as<JsonArrayConst>();
    if (a.size() != 6) return false;
    int f[6];
    for (int i = 0; i < 6; i++) {
        if (!a[i].is<int>()) return false;
        f[i] = a[i].as<int>();
    }
    if (bar ? f[4] != 0 : (f[4] != 1 && f[4] != 2 && f[4] != 4)) return false;
    if (f[5] != 0 && f[5] != 1) return false;
    int x = f[0] < 0 ? 0 : (f[0] > SCREEN_PX - 1 ? SCREEN_PX - 1 : f[0]);
    int y = f[1] < 0 ? 0 : (f[1] > SCREEN_PX - 1 ? SCREEN_PX - 1 : f[1]);
    int w = f[2] < 1 ? 1 : (f[2] > SCREEN_PX ? SCREEN_PX : f[2]);
    int h = f[3] < 1 ? 1 : (f[3] > SCREEN_PX ? SCREEN_PX : f[3]);
    if (x + w > SCREEN_PX) w = SCREEN_PX - x;
    if (y + h > SCREEN_PX) h = SCREEN_PX - y;
    out = {(int16_t)x, (int16_t)y, (int16_t)w, (int16_t)h, (uint8_t)f[4], f[5] == 1};
    return true;
}

bool parseLayout(const char* json, Layout& out) {
    JsonDocument doc;
    if (deserializeJson(doc, json)) return false;
    if (!doc["v"].is<int>() || doc["v"].as<int>() != 1) return false;

    JsonArrayConst colors = doc["c"].as<JsonArrayConst>();
    if (colors.size() != 6) return false;
    Layout l;
    uint16_t* slots[6] = {&l.text, &l.muted, &l.ok, &l.warn, &l.critical, &l.track};
    for (int i = 0; i < 6; i++) {
        if (!parseColor(colors[i], *slots[i])) return false;
    }

    bool seen[W_COUNT] = {};
    for (JsonPairConst kv : doc["w"].as<JsonObjectConst>()) {
        int id = -1;
        for (int i = 0; i < W_COUNT; i++) {
            if (strcmp(kv.key().c_str(), WIDGET_KEYS[i]) == 0) id = i;
        }
        if (id < 0 || seen[id]) return false;
        if (!parseRect(kv.value(), isBar(id), l.w[id])) return false;
        seen[id] = true;
    }
    for (int i = 0; i < W_COUNT; i++) {
        if (!seen[i]) return false;
    }
    out = l;
    return true;
}

bool designSafeAfterReset(uint32_t reason) {
    const uint32_t HARDWARE_WDT = 1, EXCEPTION = 2, SOFTWARE_WDT = 3;  // ESP8266 REASON_*_RST values
    return reason != HARDWARE_WDT && reason != EXCEPTION && reason != SOFTWARE_WDT;
}

uint16_t levelColorOf(const Layout& l, float pct) {
    if (pct < 60.0f) return l.ok;
    if (pct < 85.0f) return l.warn;
    return l.critical;
}

uint8_t changedWidgets(const Screen& a, const Screen& b) {
    const bool stale = a.stale != b.stale;
    const bool wifi = a.wifiDown != b.wifiDown;
    const bool cpu = a.cpu != b.cpu || stale;
    const bool ram = a.ram != b.ram || stale;
    const bool power = a.watts10 != b.watts10 || stale;
    const bool temp = a.temp != b.temp || stale;
    const bool footer = a.ramUsedMb != b.ramUsedMb || a.ramTotalMb != b.ramTotalMb || stale || wifi;
    const bool status = stale || wifi;

    uint8_t bits = 0;
    if (cpu) bits |= (1u << W_CPU_VALUE) | (1u << W_CPU_BAR);
    if (ram) bits |= (1u << W_RAM_VALUE) | (1u << W_RAM_BAR);
    if (power) bits |= 1u << W_POWER;
    if (temp) bits |= 1u << W_TEMP;
    if (footer) bits |= 1u << W_FOOTER;
    if (status) bits |= 1u << W_STATUS;
    return bits;
}

bool validAnim(const uint8_t* b, uint32_t len) {
    if (len < (uint32_t)ANIM_HEADER_BYTES) return false;
    if (b[0] != 2) return false;
    const uint32_t w = b[1], h = b[2], scale = b[3];
    const uint32_t x = (uint32_t)b[4] << 8 | b[5];
    const uint32_t y = (uint32_t)b[6] << 8 | b[7];
    const uint32_t fps = b[8], n = b[9];
    if (w < 1 || w > 32 || h < 1 || h > 32) return false;
    if (scale < 1 || scale > 8) return false;
    if (x + w * scale > (uint32_t)SCREEN_PX || y + h * scale > (uint32_t)SCREEN_PX) return false;
    if (fps > 30) return false;
    if (n < 1 || n > 16) return false;
    if (n * w * h > 4096) return false;
    if (len != (uint32_t)ANIM_HEADER_BYTES + n * w * h) return false;
    for (uint32_t i = ANIM_HEADER_BYTES; i < len; i++) {
        if (b[i] > 15) return false;
    }
    return true;
}
