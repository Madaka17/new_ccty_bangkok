#include "stats.h"
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>

static const uint32_t STALE_MS = 10000;

// Reads a key that must be present and hold a number or null. null gives NAN. A missing key fails.
static bool numberOrNull(JsonDocument& doc, const char* key, float& out) {
    bool present = false, isNull = false;
    for (JsonPairConst kv : doc.as<JsonObjectConst>()) {
        if (strcmp(kv.key().c_str(), key) == 0) {
            present = true;
            isNull = kv.value().isNull();
        }
    }
    if (!present) return false;
    if (isNull) {
        out = NAN;
        return true;
    }
    if (!doc[key].is<float>()) return false;
    out = doc[key].as<float>();
    return true;
}

bool parseStats(const char* json, Stats& out) {
    JsonDocument doc;
    if (deserializeJson(doc, json)) return false;
    const char* numbers[] = {"cpu", "ram", "ram_used_mb", "ram_total_mb", "vram_used_mb", "vram_total_mb"};
    for (const char* key : numbers) {
        if (!doc[key].is<float>()) return false;
    }
    Stats s;
    if (!numberOrNull(doc, "vram", s.vram) || !numberOrNull(doc, "temp_c", s.tempC)) return false;
    s.cpu = doc["cpu"].as<float>();
    s.ram = doc["ram"].as<float>();
    s.ramUsedMb = doc["ram_used_mb"].as<int>();
    s.ramTotalMb = doc["ram_total_mb"].as<int>();
    s.vramUsedMb = doc["vram_used_mb"].as<int>();
    s.vramTotalMb = doc["vram_total_mb"].as<int>();
    out = s;
    return true;
}

int barWidth(float pct, int maxW) {
    if (isnan(pct)) return 0;
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    return (int)(pct * maxW / 100.0f + 0.5f);
}

uint16_t levelColor(float pct) {
    if (pct < 60.0f) return 0x07E0;
    if (pct < 85.0f) return 0xFFE0;
    return 0xF800;
}

bool isStale(uint32_t nowMs, uint32_t lastOkMs) {
    return (uint32_t)(nowMs - lastOkMs) > STALE_MS;
}

BootWifi bootWifiAction(bool haveSavedSsid, bool connected, bool wrongPassword, uint32_t elapsedMs) {
    if (connected) return BOOT_CONNECTED;
    if (!haveSavedSsid || wrongPassword) return BOOT_PORTAL;
    if (elapsedMs >= BOOT_GIVE_UP_MS) return BOOT_RESTART;
    return BOOT_WAIT;
}

RunWifi runWifiAction(uint32_t nowMs, uint32_t lastWifiOkMs, uint32_t lastKickMs) {
    if ((uint32_t)(nowMs - lastWifiOkMs) >= RUN_RESTART_MS) return RUN_RESTART;
    if ((uint32_t)(nowMs - lastWifiOkMs) >= RUN_KICK_MS && (uint32_t)(nowMs - lastKickMs) >= RUN_KICK_MS)
        return RUN_RECONNECT;
    return RUN_WAIT;
}

static int roundInt(float v) { return (int)floorf(v + 0.5f); }

Screen screenOf(const Stats& s, bool stale, bool wifiDown) {
    Screen out;
    out.cpu = roundInt(s.cpu);
    out.ram = roundInt(s.ram);
    out.vram = isnan(s.vram) ? SCREEN_NONE : roundInt(s.vram);
    out.temp = isnan(s.tempC) ? SCREEN_NONE : roundInt(s.tempC);
    out.ramUsedMb = s.ramUsedMb;
    out.ramTotalMb = s.ramTotalMb;
    out.vramUsedMb = s.vramUsedMb;
    out.vramTotalMb = s.vramTotalMb;
    out.stale = stale;
    out.wifiDown = wifiDown;
    return out;
}

bool sameScreen(const Screen& a, const Screen& b) {
    return a.cpu == b.cpu && a.ram == b.ram && a.vram == b.vram && a.temp == b.temp &&
           a.ramUsedMb == b.ramUsedMb && a.ramTotalMb == b.ramTotalMb && a.vramUsedMb == b.vramUsedMb &&
           a.vramTotalMb == b.vramTotalMb && a.stale == b.stale && a.wifiDown == b.wifiDown;
}

bool validStatsUrl(const char* url) {
    size_t n = strlen(url);
    if (n > (size_t)STATS_URL_MAX || strncmp(url, "http://", 7) != 0) return false;
    if (n == 7 || url[7] == '/' || url[7] == ':') return false;  // no host
    for (size_t i = 0; i < n; i++) {
        if (url[i] <= ' ' || url[i] > '~') return false;
    }
    return true;
}
