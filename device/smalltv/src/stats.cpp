#include "stats.h"
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>

static const uint32_t STALE_MS = 10000;

bool parseStats(const char* json, Stats& out) {
    JsonDocument doc;
    if (deserializeJson(doc, json)) return false;
    const char* numbers[] = {"cpu", "ram", "watts", "ram_used_mb", "ram_total_mb"};
    for (const char* key : numbers) {
        if (!doc[key].is<float>()) return false;
    }
    bool tempNull = false;  // key present with value null (a missing key still fails)
    for (JsonPairConst kv : doc.as<JsonObjectConst>()) {
        if (strcmp(kv.key().c_str(), "temp_c") == 0) tempNull = kv.value().isNull();
    }
    if (!tempNull && !doc["temp_c"].is<float>()) return false;
    Stats s;
    s.cpu = doc["cpu"].as<float>();
    s.ram = doc["ram"].as<float>();
    s.tempC = tempNull ? NAN : doc["temp_c"].as<float>();
    s.watts = doc["watts"].as<float>();
    s.ramUsedMb = doc["ram_used_mb"].as<int>();
    s.ramTotalMb = doc["ram_total_mb"].as<int>();
    out = s;
    return true;
}

int barWidth(float pct, int maxW) {
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
    out.watts10 = roundInt(s.watts * 10.0f);
    out.temp = isnan(s.tempC) ? SCREEN_NO_TEMP : roundInt(s.tempC);
    out.ramUsedMb = s.ramUsedMb;
    out.ramTotalMb = s.ramTotalMb;
    out.stale = stale;
    out.wifiDown = wifiDown;
    return out;
}

bool sameScreen(const Screen& a, const Screen& b) {
    return a.cpu == b.cpu && a.ram == b.ram && a.watts10 == b.watts10 && a.temp == b.temp &&
           a.ramUsedMb == b.ramUsedMb && a.ramTotalMb == b.ramTotalMb && a.stale == b.stale &&
           a.wifiDown == b.wifiDown;
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
