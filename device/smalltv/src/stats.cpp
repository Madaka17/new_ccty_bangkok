#include "stats.h"
#include <ArduinoJson.h>

static const uint32_t STALE_MS = 10000;

bool parseStats(const char* json, Stats& out) {
    JsonDocument doc;
    if (deserializeJson(doc, json)) return false;
    const char* numbers[] = {"cpu", "ram", "temp_c", "watts", "ram_used_mb", "ram_total_mb"};
    for (const char* key : numbers) {
        if (!doc[key].is<float>()) return false;
    }
    Stats s;
    s.cpu = doc["cpu"].as<float>();
    s.ram = doc["ram"].as<float>();
    s.tempC = doc["temp_c"].as<float>();
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
