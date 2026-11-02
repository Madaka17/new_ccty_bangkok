#pragma once
#include <stdint.h>

// Latest values from the Pi stats service (GET /stats on the Pi).
struct Stats {
    float cpu, ram, tempC, watts;
    int ramUsedMb, ramTotalMb;
};

// False on bad JSON or a missing key; out is left unchanged on false.
bool parseStats(const char* json, Stats& out);

// Clamps pct to 0..100 and returns the bar length 0..maxW.
int barWidth(float pct, int maxW);

// RGB565: under 60 green, under 85 yellow, else red.
uint16_t levelColor(float pct);

// True when more than 10 s passed since the last good fetch (safe across millis() wrap).
bool isStale(uint32_t nowMs, uint32_t lastOkMs);

// WiFi policy. Timings in ms.
const uint32_t BOOT_GIVE_UP_MS = 180000;   // saved network not seen for 3 min at boot: restart and try again
const uint32_t RUN_KICK_MS = 30000;        // WiFi down: call WiFi.reconnect() every 30 s
const uint32_t RUN_RESTART_MS = 300000;    // WiFi down for 5 min: restart

enum BootWifi { BOOT_CONNECTED, BOOT_WAIT, BOOT_PORTAL, BOOT_RESTART };
enum RunWifi { RUN_WAIT, RUN_RECONNECT, RUN_RESTART };

// What to do at boot. The setup portal (an open AP) opens only when no network is saved
// or the router rejected the password, never because the router is still booting.
BootWifi bootWifiAction(bool haveSavedSsid, bool connected, bool wrongPassword, uint32_t elapsedMs);

// What to do while WiFi is down after boot (safe across millis() wrap).
RunWifi runWifiAction(uint32_t nowMs, uint32_t lastWifiOkMs, uint32_t lastKickMs);
