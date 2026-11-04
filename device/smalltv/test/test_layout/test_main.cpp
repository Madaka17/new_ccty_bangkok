#include <unity.h>
#include "layout.h"
#include "stats.h"
#include <stdio.h>
#include <string.h>

static const char* GOOD =
    "{\"v\":1,\"c\":[65535,33808,2016,65504,63488,8452],\"w\":{"
    "\"cpu_value\":[140,38,90,26,4,1],"
    "\"cpu_bar\":[10,68,220,10,0,1],"
    "\"ram_value\":[140,86,90,26,4,1],"
    "\"ram_bar\":[10,116,220,10,0,1],"
    "\"power\":[12,164,108,26,4,1],"
    "\"temp\":[134,164,96,26,4,1],"
    "\"footer\":[120,228,110,12,1,1],"
    "\"status\":[120,226,110,14,2,1]}}";

// Copies src into out with the first occurrence of from replaced by to.
static void replaceOnce(char* out, size_t cap, const char* src, const char* from, const char* to) {
    const char* hit = strstr(src, from);
    TEST_ASSERT_NOT_NULL(hit);
    size_t head = (size_t)(hit - src);
    snprintf(out, cap, "%.*s%s%s", (int)head, src, to, hit + strlen(from));
}

static Layout sentinel() {
    Layout l;
    defaultLayout(l);
    l.text = 1; l.muted = 2; l.ok = 3; l.warn = 4; l.critical = 5; l.track = 6;
    l.w[W_CPU_VALUE].x = 77;
    return l;
}

static void expectSentinel(const Layout& l) {
    TEST_ASSERT_EQUAL_UINT16(1, l.text);
    TEST_ASSERT_EQUAL_UINT16(6, l.track);
    TEST_ASSERT_EQUAL_INT16(77, l.w[W_CPU_VALUE].x);
}

void setUp() {}
void tearDown() {}

void test_default_layout_matches_draw_positions() {
    Layout l;
    defaultLayout(l);
    TEST_ASSERT_EQUAL_INT16(140, l.w[W_CPU_VALUE].x);    // right edge 230, pad 90
    TEST_ASSERT_EQUAL_INT16(38, l.w[W_CPU_VALUE].y);
    TEST_ASSERT_EQUAL_INT16(90, l.w[W_CPU_VALUE].w);
    TEST_ASSERT_EQUAL_UINT8(4, l.w[W_CPU_VALUE].font);
    TEST_ASSERT_TRUE(l.w[W_CPU_VALUE].visible);
    TEST_ASSERT_EQUAL_INT16(10, l.w[W_CPU_BAR].x);
    TEST_ASSERT_EQUAL_INT16(68, l.w[W_CPU_BAR].y);
    TEST_ASSERT_EQUAL_INT16(220, l.w[W_CPU_BAR].w);
    TEST_ASSERT_EQUAL_INT16(10, l.w[W_CPU_BAR].h);
    TEST_ASSERT_EQUAL_UINT8(0, l.w[W_CPU_BAR].font);
    TEST_ASSERT_EQUAL_INT16(86, l.w[W_RAM_VALUE].y);
    TEST_ASSERT_EQUAL_INT16(116, l.w[W_RAM_BAR].y);
    TEST_ASSERT_EQUAL_INT16(12, l.w[W_POWER].x);         // right edge 120, pad 108
    TEST_ASSERT_EQUAL_INT16(164, l.w[W_POWER].y);
    TEST_ASSERT_EQUAL_INT16(108, l.w[W_POWER].w);
    TEST_ASSERT_EQUAL_INT16(134, l.w[W_TEMP].x);         // right edge 230, pad 96
    TEST_ASSERT_EQUAL_INT16(96, l.w[W_TEMP].w);
    TEST_ASSERT_EQUAL_INT16(120, l.w[W_FOOTER].x);       // right edge 230, font 1 bottom at 238
    TEST_ASSERT_EQUAL_INT16(230, l.w[W_FOOTER].y);
    TEST_ASSERT_EQUAL_INT16(8, l.w[W_FOOTER].h);
    TEST_ASSERT_EQUAL_UINT8(1, l.w[W_FOOTER].font);
    TEST_ASSERT_EQUAL_INT16(120, l.w[W_STATUS].x);       // right edge 230, font 2 bottom at 238
    TEST_ASSERT_EQUAL_INT16(222, l.w[W_STATUS].y);
    TEST_ASSERT_EQUAL_INT16(16, l.w[W_STATUS].h);
    TEST_ASSERT_EQUAL_UINT8(2, l.w[W_STATUS].font);
    TEST_ASSERT_EQUAL_UINT16(0xFFFF, l.text);
    TEST_ASSERT_EQUAL_UINT16(0x8410, l.muted);
    TEST_ASSERT_EQUAL_UINT16(0x07E0, l.ok);
    TEST_ASSERT_EQUAL_UINT16(0xFFE0, l.warn);
    TEST_ASSERT_EQUAL_UINT16(0xF800, l.critical);
    TEST_ASSERT_EQUAL_UINT16(0x2104, l.track);
}

void test_layout_parses_good_file() {
    Layout l = sentinel();
    TEST_ASSERT_TRUE(parseLayout(GOOD, l));
    TEST_ASSERT_EQUAL_INT16(140, l.w[W_CPU_VALUE].x);
    TEST_ASSERT_EQUAL_INT16(26, l.w[W_CPU_VALUE].h);
    TEST_ASSERT_EQUAL_UINT8(2, l.w[W_STATUS].font);
    TEST_ASSERT_TRUE(l.w[W_FOOTER].visible);
    TEST_ASSERT_EQUAL_UINT16(65535, l.text);
    TEST_ASSERT_EQUAL_UINT16(33808, l.muted);
    TEST_ASSERT_EQUAL_UINT16(8452, l.track);
}

void test_layout_rejects_bad_json() {
    Layout l = sentinel();
    TEST_ASSERT_FALSE(parseLayout("{\"v\":1,", l));
    expectSentinel(l);
}

void test_layout_rejects_missing_widget() {
    Layout l = sentinel();
    const char* json =
        "{\"v\":1,\"c\":[65535,33808,2016,65504,63488,8452],\"w\":{"
        "\"cpu_value\":[140,38,90,26,4,1],"
        "\"cpu_bar\":[10,68,220,10,0,1],"
        "\"ram_value\":[140,86,90,26,4,1],"
        "\"ram_bar\":[10,116,220,10,0,1],"
        "\"power\":[12,164,108,26,4,1],"
        "\"temp\":[134,164,96,26,4,1],"
        "\"footer\":[120,228,110,12,1,1]}}";
    TEST_ASSERT_FALSE(parseLayout(json, l));
    expectSentinel(l);
}

void test_layout_rejects_wrong_version() {
    Layout l = sentinel();
    char json[512];
    snprintf(json, sizeof(json), "%s", GOOD);
    char* v = strstr(json, "\"v\":1");
    v[4] = '2';
    TEST_ASSERT_FALSE(parseLayout(json, l));
    expectSentinel(l);
}

void test_layout_clamps_rects() {
    Layout l;
    const char* json =
        "{\"v\":1,\"c\":[1,2,3,4,5,6],\"w\":{"
        "\"cpu_value\":[-5,-3,500,0,4,1],"
        "\"cpu_bar\":[300,239,50,50,0,1],"
        "\"ram_value\":[140,86,90,26,4,1],"
        "\"ram_bar\":[10,116,220,10,0,1],"
        "\"power\":[12,164,108,26,4,1],"
        "\"temp\":[134,164,96,26,4,1],"
        "\"footer\":[120,228,110,12,1,1],"
        "\"status\":[120,226,110,14,2,1]}}";
    TEST_ASSERT_TRUE(parseLayout(json, l));
    TEST_ASSERT_EQUAL_INT16(0, l.w[W_CPU_VALUE].x);
    TEST_ASSERT_EQUAL_INT16(0, l.w[W_CPU_VALUE].y);
    TEST_ASSERT_EQUAL_INT16(240, l.w[W_CPU_VALUE].w);     // 500 clamps to 240, then fits x=0
    TEST_ASSERT_EQUAL_INT16(1, l.w[W_CPU_VALUE].h);       // 0 clamps to 1
    TEST_ASSERT_EQUAL_INT16(239, l.w[W_CPU_BAR].x);
    TEST_ASSERT_EQUAL_INT16(239, l.w[W_CPU_BAR].y);
    TEST_ASSERT_EQUAL_INT16(1, l.w[W_CPU_BAR].w);         // shrunk so x+w <= 240
    TEST_ASSERT_EQUAL_INT16(1, l.w[W_CPU_BAR].h);         // shrunk so y+h <= 240
}

void test_layout_rejects_bad_font() {
    Layout l = sentinel();
    const char* json =
        "{\"v\":1,\"c\":[1,2,3,4,5,6],\"w\":{"
        "\"cpu_value\":[140,38,90,26,7,1],"
        "\"cpu_bar\":[10,68,220,10,0,1],"
        "\"ram_value\":[140,86,90,26,4,1],"
        "\"ram_bar\":[10,116,220,10,0,1],"
        "\"power\":[12,164,108,26,4,1],"
        "\"temp\":[134,164,96,26,4,1],"
        "\"footer\":[120,228,110,12,1,1],"
        "\"status\":[120,226,110,14,2,1]}}";
    TEST_ASSERT_FALSE(parseLayout(json, l));              // font 7 is not allowed
    expectSentinel(l);
}

void test_layout_bars_need_font_0_and_only_bars_may_use_it() {
    Layout l = sentinel();
    char json[512];
    replaceOnce(json, sizeof(json), GOOD, "\"cpu_bar\":[10,68,220,10,0,1]",
                "\"cpu_bar\":[10,68,220,10,2,1]");        // bar with font 2
    TEST_ASSERT_FALSE(parseLayout(json, l));
    replaceOnce(json, sizeof(json), GOOD, "\"cpu_value\":[140,38,90,26,4,1]",
                "\"cpu_value\":[140,38,90,26,0,1]");      // value with font 0
    TEST_ASSERT_FALSE(parseLayout(json, l));
    expectSentinel(l);
}

void test_layout_rejects_bad_visible_color_key_and_fraction() {
    Layout l = sentinel();
    char json[512];
    replaceOnce(json, sizeof(json), GOOD, "\"status\":[120,226,110,14,2,1]",
                "\"status\":[120,226,110,14,2,2]");       // visible must be 0 or 1
    TEST_ASSERT_FALSE(parseLayout(json, l));

    replaceOnce(json, sizeof(json), GOOD, "65535,33808", "65536,33808");  // colour out of range
    TEST_ASSERT_FALSE(parseLayout(json, l));

    replaceOnce(json, sizeof(json), GOOD, "\"status\":", "\"statuz\":");   // unknown widget key
    TEST_ASSERT_FALSE(parseLayout(json, l));

    replaceOnce(json, sizeof(json), GOOD, "\"cpu_value\":[140,", "\"cpu_value\":[140.5,");  // fraction
    TEST_ASSERT_FALSE(parseLayout(json, l));
    expectSentinel(l);
}

void test_level_color_uses_layout() {
    Layout l;
    defaultLayout(l);
    l.ok = 1111; l.warn = 2222; l.critical = 3333;
    TEST_ASSERT_EQUAL_UINT16(1111, levelColorOf(l, 0));
    TEST_ASSERT_EQUAL_UINT16(1111, levelColorOf(l, 59.9f));
    TEST_ASSERT_EQUAL_UINT16(2222, levelColorOf(l, 60));
    TEST_ASSERT_EQUAL_UINT16(2222, levelColorOf(l, 84.9f));
    TEST_ASSERT_EQUAL_UINT16(3333, levelColorOf(l, 85));
    TEST_ASSERT_EQUAL_UINT16(3333, levelColorOf(l, 100));
}

static Screen base() {
    Screen s = {12, 34, 40, 48, 2660, 7820, false, false};
    return s;
}

void test_changed_widgets_only_flags_changes() {
    Screen a = base();
    TEST_ASSERT_EQUAL_HEX8(0x00, changedWidgets(a, a));

    Screen b = base();
    b.cpu = 13;
    TEST_ASSERT_EQUAL_HEX8((1 << W_CPU_VALUE) | (1 << W_CPU_BAR), changedWidgets(a, b));

    b = base();
    b.ram = 35;
    TEST_ASSERT_EQUAL_HEX8((1 << W_RAM_VALUE) | (1 << W_RAM_BAR), changedWidgets(a, b));

    b = base();
    b.watts10 = 41;
    TEST_ASSERT_EQUAL_HEX8(1 << W_POWER, changedWidgets(a, b));

    b = base();
    b.temp = 49;
    TEST_ASSERT_EQUAL_HEX8(1 << W_TEMP, changedWidgets(a, b));

    b = base();
    b.ramUsedMb = 2661;
    TEST_ASSERT_EQUAL_HEX8(1 << W_FOOTER, changedWidgets(a, b));

    b = base();
    b.ramTotalMb = 7821;
    TEST_ASSERT_EQUAL_HEX8(1 << W_FOOTER, changedWidgets(a, b));

    b = base();
    b.wifiDown = true;
    TEST_ASSERT_EQUAL_HEX8((1 << W_FOOTER) | (1 << W_STATUS), changedWidgets(a, b));

    b = base();
    b.stale = true;
    TEST_ASSERT_EQUAL_HEX8(0xFF, changedWidgets(a, b));

    Screen staleA = base(), staleB = base();
    staleA.stale = staleB.stale = true;
    staleB.cpu = 13;                                       // stale on both sides: only the value changed
    TEST_ASSERT_EQUAL_HEX8((1 << W_CPU_VALUE) | (1 << W_CPU_BAR), changedWidgets(staleA, staleB));
}

static uint8_t anim[4200];

// Fills a v2 header and n zeroed cells; returns the length to pass to validAnim.
static uint32_t makeAnim(uint8_t w, uint8_t h, uint8_t scale, uint16_t x, uint16_t y,
                         uint8_t fps, uint8_t n) {
    memset(anim, 0, sizeof(anim));
    anim[0] = 2;
    anim[1] = w;
    anim[2] = h;
    anim[3] = scale;
    anim[4] = x >> 8; anim[5] = x & 0xFF;
    anim[6] = y >> 8; anim[7] = y & 0xFF;
    anim[8] = fps;
    anim[9] = n;
    return 48 + (uint32_t)n * w * h;
}

void test_valid_anim_accepts_v2_and_rejects_limits() {
    uint32_t len = makeAnim(2, 2, 2, 200, 200, 30, 1);    // 200+4 <= 240
    TEST_ASSERT_TRUE(validAnim(anim, len));

    len = makeAnim(32, 32, 1, 0, 0, 30, 4);                // n*w*h = 4096 is the limit
    TEST_ASSERT_EQUAL_UINT32(48 + 4096, len);
    TEST_ASSERT_TRUE(validAnim(anim, len));

    len = makeAnim(2, 2, 2, 200, 200, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, 47));                // shorter than the header
    TEST_ASSERT_FALSE(validAnim(anim, len - 1));           // length mismatch
    TEST_ASSERT_FALSE(validAnim(anim, len + 1));

    len = makeAnim(2, 2, 2, 200, 200, 30, 1);
    anim[0] = 1;
    TEST_ASSERT_FALSE(validAnim(anim, len));               // v1 is not accepted here
    anim[0] = 2;

    len = makeAnim(0, 2, 2, 0, 0, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));
    len = makeAnim(33, 2, 2, 0, 0, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));
    len = makeAnim(2, 0, 2, 0, 0, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));
    len = makeAnim(2, 33, 1, 0, 0, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));

    len = makeAnim(2, 2, 0, 0, 0, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));
    len = makeAnim(2, 2, 9, 0, 0, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));

    len = makeAnim(2, 2, 2, 237, 0, 30, 1);                // 237+4 > 240
    TEST_ASSERT_FALSE(validAnim(anim, len));
    len = makeAnim(2, 2, 2, 0, 237, 30, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));

    len = makeAnim(2, 2, 2, 0, 0, 31, 1);
    TEST_ASSERT_FALSE(validAnim(anim, len));

    len = makeAnim(2, 2, 2, 0, 0, 30, 0);
    TEST_ASSERT_FALSE(validAnim(anim, len));
    len = makeAnim(2, 2, 2, 0, 0, 30, 17);
    TEST_ASSERT_FALSE(validAnim(anim, len));

    len = makeAnim(32, 32, 1, 0, 0, 30, 5);                // 5*1024 > 4096
    TEST_ASSERT_FALSE(validAnim(anim, len));

    len = makeAnim(2, 2, 2, 0, 0, 30, 1);
    anim[50] = 16;                                         // cell index must be 0..15
    TEST_ASSERT_FALSE(validAnim(anim, len));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_default_layout_matches_draw_positions);
    RUN_TEST(test_layout_parses_good_file);
    RUN_TEST(test_layout_rejects_bad_json);
    RUN_TEST(test_layout_rejects_missing_widget);
    RUN_TEST(test_layout_rejects_wrong_version);
    RUN_TEST(test_layout_clamps_rects);
    RUN_TEST(test_layout_rejects_bad_font);
    RUN_TEST(test_layout_bars_need_font_0_and_only_bars_may_use_it);
    RUN_TEST(test_layout_rejects_bad_visible_color_key_and_fraction);
    RUN_TEST(test_level_color_uses_layout);
    RUN_TEST(test_changed_widgets_only_flags_changes);
    RUN_TEST(test_valid_anim_accepts_v2_and_rejects_limits);
    return UNITY_END();
}
