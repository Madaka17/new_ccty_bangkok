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
    assert d["failed"] == 3
    assert d["invalid_user"] == 1
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
    assert w and "85" in w[0]["title"] and "ufw insert 1 deny from" in w[0]["fix"]


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
