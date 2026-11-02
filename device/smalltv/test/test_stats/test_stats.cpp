#include <unity.h>
#include "stats.h"

static const char* GOOD =
    "{\"cpu\": 12.5, \"ram\": 34.0, \"ram_used_mb\": 2660, \"ram_total_mb\": 7820,"
    " \"temp_c\": 48.2, \"watts\": 4.2, \"watts_est\": true, \"uptime_s\": 100}";

static Stats sentinel() {
    Stats s;
    s.cpu = 1; s.ram = 2; s.tempC = 3; s.watts = 4; s.ramUsedMb = 5; s.ramTotalMb = 6;
    return s;
}

void setUp() {}
void tearDown() {}

void test_parse_ok() {
    Stats s = sentinel();
    TEST_ASSERT_TRUE(parseStats(GOOD, s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 12.5, s.cpu);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 34.0, s.ram);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 48.2, s.tempC);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 4.2, s.watts);
    TEST_ASSERT_EQUAL_INT(2660, s.ramUsedMb);
    TEST_ASSERT_EQUAL_INT(7820, s.ramTotalMb);
}

void test_parse_rejects_bad_json() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("<html>", s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 1, s.cpu);
    TEST_ASSERT_FLOAT_WITHIN(0.01, 4, s.watts);
}

void test_parse_rejects_missing_field() {
    Stats s = sentinel();
    TEST_ASSERT_FALSE(parseStats("{\"cpu\": 12.5, \"ram\": 34.0, \"ram_used_mb\": 1,"
                                 " \"ram_total_mb\": 2, \"temp_c\": 40}", s));
    TEST_ASSERT_FLOAT_WITHIN(0.01, 1, s.cpu);
}

void test_bar_width_clamps() {
    TEST_ASSERT_EQUAL_INT(200, barWidth(130, 200));
    TEST_ASSERT_EQUAL_INT(0, barWidth(-5, 200));
    TEST_ASSERT_EQUAL_INT(100, barWidth(50, 200));
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

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_parse_ok);
    RUN_TEST(test_parse_rejects_bad_json);
    RUN_TEST(test_parse_rejects_missing_field);
    RUN_TEST(test_bar_width_clamps);
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
    return UNITY_END();
}
