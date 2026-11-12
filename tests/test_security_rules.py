import json

from launch.security_check.rules import (
    evaluate_attacks, evaluate_web, evaluate_config, evaluate_host, overall,
)


def _levels(fs):
    return [f["level"] for f in fs]


def test_attacks_none_is_info():
    assert evaluate_attacks(None)[0]["level"] == "info"


def test_attacks_zero_is_ok():
    f = evaluate_attacks({"total": 0, "by_kind": {}, "top_ips": [], "top_paths": [], "recent": []})
    assert f[0]["level"] == "ok"


def test_many_probes_warns():
    f = evaluate_attacks({"days": 7, "total": 150, "by_kind": {"probe": 150},
                          "top_ips": [{"ip": "1.1.1.1", "n": 10}], "top_paths": [], "recent": []})
    assert any(x["level"] == "warn" and "ช่องโหว่" in x["title"] for x in f)


def test_one_ip_dominates_warns():
    f = evaluate_attacks({"days": 7, "total": 80, "by_kind": {"bad_path": 80},
                          "top_ips": [{"ip": "9.9.9.9", "n": 60}, {"ip": "8.8.8.8", "n": 20}],
                          "top_paths": [], "recent": []})
    assert any(x["level"] == "warn" and "9.9.9.9" in x["title"] + x["detail"] for x in f)


def test_one_ip_small_total_no_warn():
    f = evaluate_attacks({"days": 7, "total": 30, "by_kind": {"bad_path": 30},
                          "top_ips": [{"ip": "9.9.9.9", "n": 30}], "top_paths": [], "recent": []})
    assert "warn" not in _levels(f)


def test_rate_limited_warns_and_dropped_info():
    f = evaluate_attacks({"days": 7, "total": 600, "by_kind": {"rate_limited": 300, "chat_limited": 200, "dropped": 3},
                          "top_ips": [], "top_paths": [], "recent": []})
    assert "warn" in _levels(f)
    assert any("นับไม่ทัน" in x["title"] + x["detail"] for x in f)


def test_web_missing_csp_fails():
    f = evaluate_web({"headers": {"strict-transport-security": "x", "x-frame-options": "DENY",
                                  "x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}})
    assert any(x["level"] == "fail" and "content-security-policy" in x["title"].lower() for x in f)


def test_web_env_html_fallback_is_ok():
    f = evaluate_web({"status": {"/.env": (200, "text/html; charset=utf-8", "<!doctype html>")}})
    assert all(x["level"] != "fail" for x in f)


def test_web_env_plain_text_fails():
    f = evaluate_web({"status": {"/.env": (200, "text/plain", "ADMIN_TOKEN=abc")}})
    assert any(x["level"] == "fail" and "ไฟล์ลับ" in x["title"] for x in f)


def test_web_docs_non_html_fails():
    f = evaluate_web({"status": {"/openapi.json": (200, "application/json", "{}")}})
    assert "fail" in _levels(f)


def test_web_api_without_cookie_warns():
    f = evaluate_web({"status": {"/api/traffic/summary": (200, "application/json", "{}")}})
    assert "warn" in _levels(f)


def test_web_cert():
    assert "warn" in _levels(evaluate_web({"cert_days_left": 10}))
    assert "fail" in _levels(evaluate_web({"cert_days_left": 2}))
    assert "warn" not in _levels(evaluate_web({"cert_days_left": 60}))


def test_web_server_version_info():
    f = evaluate_web({"headers": {"server": "nginx/1.18.0"}})
    assert any(x["level"] == "info" for x in f)


def test_web_missing_keys_skipped():
    assert evaluate_web({}) == [] or all(x["level"] in ("ok", "info") for x in evaluate_web({}))


def test_config_short_token_fails():
    f = evaluate_config({"admin_token_len": 10, "api_session": True, "api_browser_only": True,
                         "general_rate_per_min": 60, "chat_rate_per_day": 20})
    assert any(x["level"] == "fail" for x in f)


def test_config_unset_token_warns_and_flags():
    f = evaluate_config({"admin_token_len": 0, "api_session": False, "api_browser_only": False,
                         "general_rate_per_min": 0, "chat_rate_per_day": 0})
    assert _levels(f).count("warn") >= 5


def test_config_none_is_info():
    assert evaluate_config(None)[0]["level"] == "info"


def test_config_never_contains_secret_text():
    f = evaluate_config({"admin_token_len": 10, "api_session": True, "api_browser_only": True,
                         "general_rate_per_min": 60, "chat_rate_per_day": 20,
                         "admin_token": "supersecretvalue123"})
    assert "supersecretvalue123" not in json.dumps(f, ensure_ascii=False)


GOOD_HOST = {"listen": ["0.0.0.0:22", "*:8000"], "sshd": {"passwordauthentication": "no",
             "permitrootlogin": "prohibit-password", "kbdinteractiveauthentication": "no"},
             "firewall": "active", "upgradable": 0, "unattended": True,
             "reboot_required": False, "fail2ban": True}


def test_host_good_has_no_problems():
    assert set(_levels(evaluate_host(GOOD_HOST))) <= {"ok", "info"}


def test_host_password_ssh_fails():
    h = dict(GOOD_HOST, sshd={"passwordauthentication": "yes", "permitrootlogin": "no"})
    assert any(x["level"] == "fail" for x in evaluate_host(h))


def test_host_root_keys_only_alias_is_ok():
    # Debian's sshd -T prints the old name "without-password" for "prohibit-password" (root by key only)
    h = dict(GOOD_HOST, sshd={"passwordauthentication": "no", "permitrootlogin": "without-password"})
    assert set(_levels(evaluate_host(h))) <= {"ok", "info"}


def test_host_root_with_password_fails():
    h = dict(GOOD_HOST, sshd={"passwordauthentication": "no", "permitrootlogin": "yes"})
    assert any(x["level"] == "fail" and "root" in x["title"] for x in evaluate_host(h))


def test_host_unknown_port_warns():
    f = evaluate_host(dict(GOOD_HOST, listen=["0.0.0.0:3306"]))
    assert any(x["level"] == "warn" and "3306" in x["title"] + x["detail"] for x in f)


def test_host_loopback_ports_ignored():
    f = evaluate_host(dict(GOOD_HOST, listen=["127.0.0.1:8001", "127.0.0.2:8000"]))
    assert "warn" not in _levels(f)


def test_host_vnc_warns():
    f = evaluate_host(dict(GOOD_HOST, listen=["[::]:5900"]))
    assert any("VNC" in x["title"] for x in f)


def test_host_none_is_info():
    assert evaluate_host(None)[0]["level"] == "info"


def test_host_misc_warnings():
    f = evaluate_host(dict(GOOD_HOST, firewall="inactive", upgradable=25, reboot_required=True))
    assert _levels(f).count("warn") == 3


def test_overall():
    assert overall([]) == "ok"
    assert overall([{"level": "ok"}, {"level": "warn"}]) == "warn"
    assert overall([{"level": "warn"}, {"level": "fail"}]) == "fail"


def _port_warns(listen):
    return [x for x in evaluate_host(dict(GOOD_HOST, listen=listen)) if x["level"] == "warn"]


def test_host_lan_address_unknown_port_warns():
    f = _port_warns(["192.168.1.109:3306"])
    assert len(f) == 1 and "3306" in f[0]["title"]


def test_host_lan_address_known_port_ok():
    assert _port_warns(["192.168.1.109:22", "192.168.1.109:8000"]) == []


def test_host_loopback_variants_ignored():
    assert _port_warns(["127.0.0.2:8000", "127.0.0.1:8001", "[::1]:631", "::1:631"]) == []


def test_host_iface_suffix_and_dedup():
    f = _port_warns(["0.0.0.0%eth0:53", "[::]:53", "192.168.1.109:53"])
    assert len(f) == 1 and "53" in f[0]["title"]


def test_host_vnc_on_lan_address_warns():
    assert any("VNC" in x["title"] for x in _port_warns(["192.168.1.109:5900"]))


def test_trusted_origin_skips_path_checks():
    checks = {"headers": {"content-security-policy": "x", "strict-transport-security": "x", "x-frame-options": "x",
                          "x-content-type-options": "x", "referrer-policy": "x"},
              "status": {"/openapi.json": (200, "application/json", "{}"),
                         "/api/traffic/summary": (200, "application/json", "{}")}}
    assert evaluate_web(checks) != []
    assert evaluate_web(checks, trusted_origin=True) == []


def test_host_sudo_denied_is_info_not_pass_or_warn():
    f = evaluate_host({"sshd": {"_denied": True}, "firewall": "denied", "listen": []})
    assert [x["level"] for x in f] == ["info", "info"]
    assert any("SSH" in x["title"] for x in f) and any("ไฟร์วอลล์" in x["title"] for x in f)
