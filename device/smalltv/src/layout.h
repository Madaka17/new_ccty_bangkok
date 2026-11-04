#pragma once
#include <stdint.h>
#include "stats.h"

// One widget's box on the 240x240 screen. font 0 is the bar (drawn as a rectangle).
struct Rect {
    int16_t x, y, w, h;
    uint8_t font;
    bool visible;
};

enum WidgetId { W_CPU_VALUE, W_CPU_BAR, W_RAM_VALUE, W_RAM_BAR, W_POWER, W_TEMP, W_FOOTER, W_STATUS, W_COUNT };

// Screen layout and palette. Colours are RGB565.
struct Layout {
    Rect w[W_COUNT];
    uint16_t text, muted, ok, warn, critical, track;
};

// The positions and colours the firmware used before layouts could be stored.
void defaultLayout(Layout& out);

// Layout file: {"v":1,"c":[text,muted,ok,warn,critical,track],"w":{"cpu_value":[x,y,w,h,font,visible],...}}
// Every widget id must be present and no other keys are allowed. Rects are clamped to the screen.
// False on any error; out is left unchanged on false.
bool parseLayout(const char* json, Layout& out);

// False when the last reset was a crash or watchdog (ESP8266 reason 1 hardware WDT, 2 exception,
// 3 software WDT): that boot then skips the stored design, so a design that crashes cannot loop the display.
bool designSafeAfterReset(uint32_t reason);

// Bar colour for a percentage: under 60 ok, under 85 warn, else critical.
uint16_t levelColorOf(const Layout& l, float pct);

// One bit per WidgetId (bit n is WidgetId n) for each widget that a change from a to b redraws.
uint8_t changedWidgets(const Screen& a, const Screen& b);

// True for a valid v2 animation: 48-byte header, then one palette-index byte per cell.
bool validAnim(const uint8_t* b, uint32_t len);
