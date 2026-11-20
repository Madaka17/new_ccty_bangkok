#include <unity.h>
#include "stats.h"
#include <math.h>
#include <string.h>

// The contract example from the PC stats server (device/pcstats).
static const char* GOOD =
    "{\"cpu\": 12.5, \"ram\": 41.0, \"ram_used_mb\": 13420, \"ram_total_mb\": 32684,"
    " \"vram\": 85.8, \"vram_used_mb\": 8789, \"vram_total_mb\": 10240,"
    " \"temp_c\": 55.0, \"uptime_s\": 12345}";

static Stats sentinel() {
    Stats s;
    s.cpu = 1; s.ram = 2; s.vram = 3; s.tempC = 4;
    s.ramUsedMb = 5; s.ramTotalMb = 6; s.vramUsedMb = 7; s.vramTotalMb = 8;
    return s;
}

void setUp() {}
void tearDown() {}

void test_parse_ok() {
    Stats s = sentinel();
    TEST_ASSERT_TRUE(parseStats(GOOD, s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 12.5, s.cpu);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 41.0, s.ram);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 55.0, s.tempC);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 85.8, s.vram);
    TEST_ASSERT_EQUAL_INT(13420, s.ramUsedMb);
    TEST_ASSERT_EQUAL_INT(32684, s.ramTotalMb);
    TEST_ASSERT_EQUAL_INT(8789, s.vramUsedMb);
    TEST_ASSERT_EQUAL_INT(10240, s.vramTotalMb);
}

void test_parse_rejects_bad_json() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("<html>", s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 1, s.cpu);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 3, s.vram);
}

void test_parse_rejects_missing_field() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("{\"cpu\": 12.5, \"ram\": 34.0, \"ram_used_mb\": 1,"
                                 " \"ram_total_mb\": 2, \"temp_c\": 40}", s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 1, s.cpu);
}

void test_parse_rejects_missing_vram() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("{\"cpu\": 12.5, \"ram\": 41.0, \"ram_used_mb\": 13420,"
                                 " \"ram_total_mb\": 32684, \"vram_used_mb\": 8789,"
                                 " \"vram_total_mb\": 10240, \"temp_c\": 55.0}", s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 1, s.cpu);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 3, s.vram);
}

void test_parse_vram_null() {
    // The GPU read failed: the server sends vram null with zero MB counts.
    Stats s = sentinel();
    TEST_ASSERT_TRUE(parseStats("{\"cpu\": 1, \"ram\": 2, \"ram_used_mb\": 3, \"ram_total_mb\": 4,"
                                " \"vram\": null, \"vram_used_mb\": 0, \"vram_total_mb\": 0,"
                                " \"temp_c\": 40}", s));
    TEST_ASSERT_TRUE(isnan(s.vram));
    TEST_ASSERT_EQUAL_INT(0, s.vramTotalMb);
}

void test_bar_width_clamps() {
    TEST_ASSERT_EQUAL_INT(200, barWidth(130, 200));
    TEST_ASSERT_EQUAL_INT(0, barWidth(-5, 200));
    TEST_ASSERT_EQUAL_INT(100, barWidth(50, 200));
}

void test_bar_width_nan_is_zero() {
    TEST_ASSERT_EQUAL_INT(0, barWidth(NAN, 200));
}

void test_level_color() {
    TEST_ASSERT_EQUAL_HEX16(0x07E0, levelColor(59.9f));
    TEST_ASSERT_EQUAL_HEX16(0xFFE0, levelColor(60.0f));
    TEST_ASSERT_EQUAL_HEX16(0xF800, levelColor(85.0f));
}

void test_is_stale_after_10s() {
    TEST_ASSERT_TRUE(isStale(10001, 0));
    TEST_ASSERT_FALSE(isStale(10000, 0));
    TEST_ASSERT_FALSE(isStale(5, 4294967290u));
}

void test_boot_wifi_connected() {
    TEST_ASSERT_EQUAL_INT(BOOT_CONNECTED, bootWifiAction(true, true, false, 5000));
}

void test_boot_wifi_no_saved_network_opens_portal() {
    TEST_ASSERT_EQUAL_INT(BOOT_PORTAL, bootWifiAction(false, false, false, 0));
}

void test_boot_wifi_router_slow_keeps_waiting() {
    // Power cut: the display boots before the router. Never open the open AP for that.
    TEST_ASSERT_EQUAL_INT(BOOT_WAIT, bootWifiAction(true, false, false, 179999));
}

void test_boot_wifi_gives_up_with_restart() {
    TEST_ASSERT_EQUAL_INT(BOOT_RESTART, bootWifiAction(true, false, false, 180000));
}

void test_boot_wifi_wrong_password_opens_portal() {
    TEST_ASSERT_EQUAL_INT(BOOT_PORTAL, bootWifiAction(true, false, true, 3000));
}

void test_run_wifi_short_drop_waits() {
    TEST_ASSERT_EQUAL_INT(RUN_WAIT, runWifiAction(29999, 0, 0));
}

void test_run_wifi_kicks_reconnect_every_30s() {
    TEST_ASSERT_EQUAL_INT(RUN_RECONNECT, runWifiAction(30000, 0, 0));
    TEST_ASSERT_EQUAL_INT(RUN_WAIT, runWifiAction(40000, 0, 30000));
    TEST_ASSERT_EQUAL_INT(RUN_RECONNECT, runWifiAction(60000, 0, 30000));
}

void test_run_wifi_restarts_after_5_min() {
    TEST_ASSERT_EQUAL_INT(RUN_RESTART, runWifiAction(300000, 0, 270000));
}

void test_run_wifi_safe_across_wrap() {
    TEST_ASSERT_EQUAL_INT(RUN_WAIT, runWifiAction(5, 4294967290u, 4294967290u));
}

void test_parse_null_temp_is_nan() {
    // The PC server sends null when it has no temperature reading.
    Stats s = sentinel();
    TEST_ASSERT_TRUE(parseStats("{\"cpu\": 1, \"ram\": 2, \"ram_used_mb\": 3, \"ram_total_mb\": 4,"
                                " \"vram\": 5, \"vram_used_mb\": 6, \"vram_total_mb\": 7,"
                                " \"temp_c\": null}", s));
    TEST_ASSERT_TRUE(isnan(s.tempC));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 5, s.vram);
}

void test_parse_rejects_string_values() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("{\"cpu\": \"12\", \"ram\": 2, \"ram_used_mb\": 3, \"ram_total_mb\": 4,"
                                 " \"vram\": 5, \"vram_used_mb\": 6, \"vram_total_mb\": 7,"
                                 " \"temp_c\": 40}", s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 1, s.cpu);
}

void test_parse_rejects_null_cpu() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("{\"cpu\": null, \"ram\": 2, \"ram_used_mb\": 3, \"ram_total_mb\": 4,"
                                 " \"vram\": 5, \"vram_used_mb\": 6, \"vram_total_mb\": 7,"
                                 " \"temp_c\": 40}", s));
}

void test_same_screen_ignores_changes_below_display_precision() {
    Stats a = sentinel(), b = sentinel();
    a.cpu = 12.2f; b.cpu = 12.4f;        // both show 12%
    TEST_ASSERT_TRUE(sameScreen(screenOf(a, false, false), screenOf(b, false, false)));
}

void test_same_screen_sees_value_change() {
    Stats a = sentinel(), b = sentinel();
    a.cpu = 12.2f; b.cpu = 13.0f;
    TEST_ASSERT_FALSE(sameScreen(screenOf(a, false, false), screenOf(b, false, false)));
    a = sentinel(); b = sentinel();
    a.vram = 85.4f; b.vram = 85.6f;      // 85% vs 86%
    TEST_ASSERT_FALSE(sameScreen(screenOf(a, false, false), screenOf(b, false, false)));
    a = sentinel(); b = sentinel();
    a.vramUsedMb = 8789; b.vramUsedMb = 8790;   // the VRAM detail line shows MB
    TEST_ASSERT_FALSE(sameScreen(screenOf(a, false, false), screenOf(b, false, false)));
}

void test_same_screen_sees_state_change() {
    Stats a = sentinel();
    TEST_ASSERT_FALSE(sameScreen(screenOf(a, false, false), screenOf(a, true, false)));
    TEST_ASSERT_FALSE(sameScreen(screenOf(a, true, false), screenOf(a, true, true)));
}

void test_same_screen_nan_temp_equals_itself() {
    Stats a = sentinel();
    a.tempC = NAN;
    TEST_ASSERT_TRUE(sameScreen(screenOf(a, false, false), screenOf(a, false, false)));
}

void test_screen_vram_none() {
    Stats a = sentinel();
    a.vram = NAN;
    TEST_ASSERT_EQUAL_INT(SCREEN_NONE, screenOf(a, false, false).vram);
    TEST_ASSERT_EQUAL_INT(4, screenOf(a, false, false).temp);   // temp is unaffected by a missing vram
}

void test_valid_stats_url() {
    TEST_ASSERT_TRUE(validStatsUrl("http://192.168.1.109:9101/stats"));
    TEST_ASSERT_TRUE(validStatsUrl("http://raspberrypi.local:9101/stats"));
    TEST_ASSERT_FALSE(validStatsUrl("https://x/stats"));   // no TLS on this firmware
    TEST_ASSERT_FALSE(validStatsUrl("http://"));
    TEST_ASSERT_FALSE(validStatsUrl("http://a b/stats"));
    TEST_ASSERT_FALSE(validStatsUrl(""));
    char longUrl[200];
    memset(longUrl, 'a', sizeof(longUrl));
    memcpy(longUrl, "http://", 7);
    longUrl[199] = 0;
    TEST_ASSERT_FALSE(validStatsUrl(longUrl));               // longer than STATS_URL_MAX
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_parse_ok);
    RUN_TEST(test_parse_rejects_bad_json);
    RUN_TEST(test_parse_rejects_missing_field);
    RUN_TEST(test_parse_rejects_missing_vram);
    RUN_TEST(test_parse_vram_null);
    RUN_TEST(test_bar_width_clamps);
    RUN_TEST(test_bar_width_nan_is_zero);
    RUN_TEST(test_level_color);
    RUN_TEST(test_is_stale_after_10s);
    RUN_TEST(test_boot_wifi_connected);
    RUN_TEST(test_boot_wifi_no_saved_network_opens_portal);
    RUN_TEST(test_boot_wifi_router_slow_keeps_waiting);
    RUN_TEST(test_boot_wifi_gives_up_with_restart);
    RUN_TEST(test_boot_wifi_wrong_password_opens_portal);
    RUN_TEST(test_run_wifi_short_drop_waits);
    RUN_TEST(test_run_wifi_kicks_reconnect_every_30s);
    RUN_TEST(test_run_wifi_restarts_after_5_min);
    RUN_TEST(test_run_wifi_safe_across_wrap);
    RUN_TEST(test_parse_null_temp_is_nan);
    RUN_TEST(test_parse_rejects_string_values);
    RUN_TEST(test_parse_rejects_null_cpu);
    RUN_TEST(test_same_screen_ignores_changes_below_display_precision);
    RUN_TEST(test_same_screen_sees_value_change);
    RUN_TEST(test_same_screen_sees_state_change);
    RUN_TEST(test_same_screen_nan_temp_equals_itself);
    RUN_TEST(test_screen_vram_none);
    RUN_TEST(test_valid_stats_url);
    return UNITY_END();
}
