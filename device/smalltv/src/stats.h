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
