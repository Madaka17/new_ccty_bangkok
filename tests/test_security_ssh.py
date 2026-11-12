from launch.security_check import collect, main as main_mod, rules

JOURNAL = """2026-11-10T01:00:00+07:00 pi sshd[1]: Failed password for root from 5.5.5.5 port 1 ssh2
2026-11-10T01:00:01+07:00 pi sshd[1]: Failed password for invalid user admin from 5.5.5.5 port 1 ssh2
2026-11-10T01:00:02+07:00 pi sshd[1]: Failed password for invalid user admin from 6.6.6.6 port 1 ssh2
2026-11-10T01:00:03+07:00 pi sshd[1]: Invalid user oracle from 6.6.6.6 port 2
2026-11-10T01:00:04+07:00 pi sshd[1]: Accepted publickey for test from 192.168.1.50 port 3 ssh2
2026-11-10T01:00:05+07:00 pi sshd[1]: Accepted publickey for test from 192.168.1.50 port 4 ssh2
2026-11-10T01:00:06+07:00 pi sshd[1]: Accepted password for bob from 7.7.7.7 port 5 ssh2
2026-11-10T01:00:07+07:00 pi sshd[1]: unrelated line
"""


def test_parse_ssh_journal():
    d = collect.parse_ssh_journal(JOURNAL)
    assert d["failed"] == 1
    assert d["invalid_user"] == 3
    assert any(a["ip"] == "192.168.1.50" and a["user"] == "test" and a["n"] == 2 for a in d["accepted"])
    assert any(a["ip"] == "7.7.7.7" and a["method"] == "password" for a in d["accepted"])
    assert d["failed_ips"][0] == {"ip": "5.5.5.5", "n": 2} or d["failed_ips"][0]["n"] == 2
    ips = {x["ip"]: x["n"] for x in d["failed_ips"]}
    assert ips == {"5.5.5.5": 2, "6.6.6.6": 2}
    users = {x["user"]: x["n"] for x in d["users_tried"]}
    assert users["admin"] == 2 and users["oracle"] == 1 and users["root"] == 1


def test_parse_ssh_journal_empty():
    d = collect.parse_ssh_journal("")
    assert d["failed"] == 0 and d["accepted"] == [] and d["failed_ips"] == []


def test_eval_none():
    r = rules.evaluate_ssh_log(None)
    assert r[0]["level"] == "info" and r[0]["area"] == "host"


def test_eval_outside_accept_fails():
    d = collect.parse_ssh_journal(JOURNAL)
    r = rules.evaluate_ssh_log(d)
    f = [x for x in r if x["level"] == "fail"]
    assert f and "7.7.7.7" in f[0]["detail"] and f[0]["fix"]
    assert "192.168.1.50" not in f[0]["detail"]


def test_eval_lan_only_ok():
    d = {"failed": 0, "invalid_user": 0, "accepted": [{"ip": "192.168.1.5", "user": "t", "n": 1, "method": "publickey"}],
         "failed_ips": [], "users_tried": []}
    r = rules.evaluate_ssh_log(d)
    assert [x["level"] for x in r] == ["ok"]


def test_eval_many_failed_warns():
    d = {"failed": 80, "invalid_user": 5, "accepted": [], "failed_ips": [{"ip": "5.5.5.5", "n": 80}],
         "users_tried": []}
    r = rules.evaluate_ssh_log(d)
    w = [x for x in r if x["level"] == "warn"]
    assert w and "85" in w[0]["title"] and w[0]["cmd"] == "sudo ufw insert 1 deny from 5.5.5.5"


def test_eval_lan_password_warns():
    d = {"failed": 0, "invalid_user": 0, "accepted": [{"ip": "192.168.1.5", "user": "t", "n": 1, "method": "password"}],
         "failed_ips": [], "users_tried": []}
    assert any(x["level"] == "warn" for x in rules.evaluate_ssh_log(d))


def test_main_passes_extra(monkeypatch, tmp_path):
    ssh = {"failed": 2, "invalid_user": 0,
           "accepted": [{"ip": "192.168.1.50", "user": "test", "n": 1, "method": "publickey"}],
           "failed_ips": [{"ip": "5.5.5.5", "n": 2}], "users_tried": []}
    summary = {"days": 30, "total": 3, "by_kind": {"probe": 3}, "by_day": [],
               "top_ips": [{"ip": "8.8.8.8", "n": 3}], "top_paths": [], "recent": []}
    seen = {}
    monkeypatch.setattr(collect, "pi_self_check_token", lambda: None)
    monkeypatch.setattr(collect, "pi_attack_summary", lambda days=30: summary)
    monkeypatch.setattr(collect, "pi_config_flags", lambda: {})
    monkeypatch.setattr(collect, "pi_host_raw", lambda: None)
    monkeypatch.setattr(collect, "pi_ssh_log", lambda days=30: ssh)
    monkeypatch.setattr(collect, "public_ip", lambda: "9.9.9.9")
    monkeypatch.setattr(collect, "public_ip_v4", lambda: "9.9.9.9")
    monkeypatch.setattr(collect, "web_checks", lambda url, self_check_token=None: {})
    monkeypatch.setattr(main_mod.geo, "lookup", lambda ip: {"8.8.8.8": "US", "5.5.5.5": "RU"}.get(ip))
    monkeypatch.setattr(main_mod.geo, "country_name", lambda cc: cc + "-name")
    real = main_mod.report.render

    def spy(target, sections, summary, generated, extra=None):
        seen["extra"] = extra
        seen["sections"] = sections
        return real(target, sections, summary, generated)
    monkeypatch.setattr(main_mod.report, "render", spy)
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path))
    assert main_mod.main(["--no-open"]) == 0
    ex = seen["extra"]
    assert ex["ssh"] == ssh
    assert ex["owner_ips"] == ["9.9.9.9", "192.168.1.50"]
    g = {x["ip"]: x for x in ex["geo"]}
    assert g["8.8.8.8"] == {"ip": "8.8.8.8", "cc": "US", "country": "US-name", "n": 3, "owner": False}
    assert g["5.5.5.5"]["cc"] == "RU" and g["5.5.5.5"]["n"] == 2
    assert any("SSH" in f["title"] for f in seen["sections"]["host"])


def test_eval_same_home_ipv6_prefix_is_not_outside():
    d = {"failed": 0, "invalid_user": 0, "accepted": [
        {"ip": "2405:9800:b640:ac59:1:2:3:4", "user": "t", "n": 1, "method": "publickey"}],
        "failed_ips": [], "users_tried": []}
    assert any(x["level"] == "fail" for x in rules.evaluate_ssh_log(d))
    r = rules.evaluate_ssh_log(d, owner_ips=["2405:9800:b640:ac59:9:9:9:9"])
    assert [x["level"] for x in r] == ["ok"]


def _L(msg, pid=100):
    return f"2026-11-10T01:00:00+07:00 pi sshd[{pid}]: {msg}\n"


def test_parse_log_injection_user_cannot_fake_ip_or_accept():
    t = _L("Invalid user x from 192.168.1.101 port 1 from 6.6.6.6 port 22")
    t += _L("Failed password for invalid user y Accepted publickey for root from 192.168.1.101 port 1 from 7.7.7.7 port 9 ssh2", 101)
    t += _L("Invalid user Accepted password for root from 192.168.1.101 port 1 from 8.8.4.4 port 5", 102)
    d = collect.parse_ssh_journal(t)
    assert d["accepted"] == []
    ips = {x["ip"] for x in d["failed_ips"]}
    assert ips == {"6.6.6.6", "7.7.7.7", "8.8.4.4"}
    # a non-sshd line cannot inject either
    d = collect.parse_ssh_journal("2026-11-10T01:00:00+07:00 pi sudo[5]: Accepted publickey for a from 1.1.1.1 port 1\n")
    assert d["accepted"] == [] and d["failed"] == 0


def test_parse_one_attempt_per_pid_user_ip():
    t = _L("Invalid user admin from 5.5.5.5 port 40000")
    t += _L("Failed password for invalid user admin from 5.5.5.5 port 40000 ssh2")
    t += _L("Connection closed by invalid user admin 5.5.5.5 port 40000 [preauth]")
    d = collect.parse_ssh_journal(t)
    assert d["failed"] + d["invalid_user"] == 1
    assert d["failed_ips"] == [{"ip": "5.5.5.5", "n": 1}]


def test_parse_openssh9_samples():
    cases = [
        ("Failed publickey for test from 5.5.5.5 port 1 ssh2: ED25519 SHA256:abc", "failed"),
        ("Failed keyboard-interactive/pam for root from 5.5.5.5 port 1 ssh2", "failed"),
        ("Failed password for root from 5.5.5.5 port 1 ssh2", "failed"),
        ("Connection closed by authenticating user root 5.5.5.5 port 1 [preauth]", "failed"),
        ("Disconnected from authenticating user root 5.5.5.5 port 1 [preauth]", "failed"),
        ("Connection closed by invalid user bob 5.5.5.5 port 1 [preauth]", "invalid_user"),
        ("Invalid user bob from 5.5.5.5 port 1", "invalid_user"),
    ]
    for msg, kind in cases:
        d = collect.parse_ssh_journal(_L(msg))
        assert d[kind] == 1, msg
        assert d["failed"] + d["invalid_user"] == 1, msg
        assert d["failed_ips"] == [{"ip": "5.5.5.5", "n": 1}], msg


def test_parse_accepted_methods():
    t = _L("Accepted publickey for test from 192.168.1.5 port 1 ssh2: ED25519 SHA256:x")
    t += _L("Accepted keyboard-interactive/pam for test from 192.168.1.6 port 1 ssh2", 101)
    t += _L("Accepted password for test from 192.168.1.7 port 1 ssh2", 102)
    d = collect.parse_ssh_journal(t)
    m = {a["ip"]: a["method"] for a in d["accepted"]}
    assert m == {"192.168.1.5": "publickey", "192.168.1.6": "password", "192.168.1.7": "password"}


def test_script_grep_covers_all_kinds():
    sc = collect._SSH_JOURNAL_SCRIPT
    for k in ("Failed ", "Invalid user", "Accepted ", "Connection closed by", "Disconnected from"):
        assert k in sc


PW = {"failed": 0, "invalid_user": 0, "failed_ips": [], "users_tried": [],
      "accepted": [{"ip": "192.168.1.5", "user": "t", "n": 3, "method": "password"}]}


def test_password_login_by_password_auth_state():
    r = rules.evaluate_ssh_log(PW, password_auth="no")
    assert [x["level"] for x in r] == ["info", "ok"]
    assert "ปิดแล้ว" in r[0]["title"] and "192.168.1.5" in r[0]["detail"]
    assert any(x["level"] == "warn" for x in rules.evaluate_ssh_log(PW, password_auth="yes"))
    assert any(x["level"] == "warn" for x in rules.evaluate_ssh_log(PW))


def test_main_passes_password_auth(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(collect, "pi_self_check_token", lambda: None)
    monkeypatch.setattr(collect, "pi_attack_summary", lambda days=30: None)
    monkeypatch.setattr(collect, "pi_config_flags", lambda: {})
    monkeypatch.setattr(collect, "pi_host_raw", lambda: {"sshd": {"passwordauthentication": "no"}})
    monkeypatch.setattr(collect, "pi_ssh_log", lambda days=30: PW)
    monkeypatch.setattr(collect, "public_ip", lambda: None)
    monkeypatch.setattr(collect, "public_ip_v4", lambda: None)
    monkeypatch.setattr(collect, "web_checks", lambda url, self_check_token=None: {})
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path))
    orig = rules.evaluate_ssh_log

    def spy(d, **kw):
        seen.update(kw)
        return orig(d, **kw)
    monkeypatch.setattr(rules, "evaluate_ssh_log", spy)
    assert main_mod.main(["--no-open"]) == 0
    assert seen["password_auth"] == "no"


def test_geo_owner_uses_slash64(monkeypatch):
    monkeypatch.setattr(main_mod.geo, "lookup", lambda ip: "TH")
    monkeypatch.setattr(main_mod.geo, "country_name", lambda cc: "Thailand")
    s = {"top_ips": [{"ip": "2405:9800:b640:ac59::7", "n": 4}, {"ip": "2405:9800:b640:ffff::7", "n": 3}]}
    e = main_mod._extra(s, None, ["2405:9800:b640:ac59:1:2:3:4"])
    o = {r["ip"]: r["owner"] for r in e["geo"]}
    assert o == {"2405:9800:b640:ac59::7": True, "2405:9800:b640:ffff::7": False}


def test_main_owner_list_has_v6_and_v4(monkeypatch, tmp_path):
    ssh = {"failed": 0, "invalid_user": 0,
           "accepted": [{"ip": "192.168.1.50", "user": "t", "n": 1, "method": "publickey"},
                        {"ip": "192.168.1.50", "user": "t", "n": 1, "method": "publickey"}],
           "failed_ips": [], "users_tried": []}
    seen = {}
    monkeypatch.setattr(collect, "pi_self_check_token", lambda: None)
    monkeypatch.setattr(collect, "pi_attack_summary", lambda days=30: None)
    monkeypatch.setattr(collect, "pi_config_flags", lambda: {})
    monkeypatch.setattr(collect, "pi_host_raw", lambda: None)
    monkeypatch.setattr(collect, "pi_ssh_log", lambda days=30: ssh)
    monkeypatch.setattr(collect, "public_ip", lambda: "2001:db8::1")
    monkeypatch.setattr(collect, "public_ip_v4", lambda: "9.9.9.9")
    monkeypatch.setattr(collect, "web_checks", lambda url, self_check_token=None: {})
    real = main_mod.report.render

    def spy(target, sections, summary, generated, extra=None):
        seen["extra"] = extra
        return real(target, sections, summary, generated)
    monkeypatch.setattr(main_mod.report, "render", spy)
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path))
    assert main_mod.main(["--no-open"]) == 0
    assert seen["extra"]["owner_ips"] == ["2001:db8::1", "9.9.9.9", "192.168.1.50"]


def test_extra_skips_bad_rows():
    ex = main_mod._extra({"top_ips": [{"n": 3}, {"ip": "8.8.8.8", "n": 2}, "junk"]},
                         {"failed_ips": [{"ip": "8.8.8.8", "n": "x"}]}, [])
    assert [r["ip"] for r in ex["geo"]] == ["8.8.8.8"]


def test_ssh_failed_excludes_owner_tries():
    d = {"failed": 80, "invalid_user": 0, "accepted": [],
         "failed_ips": [{"ip": "9.9.9.9", "n": 80}], "users_tried": []}
    r = rules.evaluate_ssh_log(d, owner_ips=["9.9.9.9"])
    assert not [x for x in r if x["level"] == "warn"]


def test_public_ip_v4_none_on_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("no net")
    monkeypatch.setattr(collect.socket, "getaddrinfo", boom)
    assert collect.public_ip_v4() is None
