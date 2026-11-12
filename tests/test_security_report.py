import json

from launch.security_check import collect, main as main_mod
from launch.security_check.collect import parse_host_output, local_config_flags
from launch.security_check.report import render

import pytest


@pytest.fixture(autouse=True)
def _no_network_public_ip(monkeypatch):
    monkeypatch.setattr(collect, "public_ip", lambda: None)
    monkeypatch.setattr(collect, "public_ip_v4", lambda: None)

HOST_TEXT = """@@listen
LISTEN 0 128 0.0.0.0:22 0.0.0.0:*
LISTEN 0 4096 127.0.0.1:8000 0.0.0.0:*
LISTEN 0 5 0.0.0.0:5900 0.0.0.0:*
@@sshd
passwordauthentication no
permitrootlogin prohibit-password
kbdinteractiveauthentication no
@@ufw
Status: inactive
@@upgradable
12
@@unattended
yes
@@reboot
@@fail2ban
inactive
"""


def test_parse_host_output():
    r = parse_host_output(HOST_TEXT)
    assert r["listen"] == ["0.0.0.0:22", "127.0.0.1:8000", "0.0.0.0:5900"]
    assert r["sshd"]["passwordauthentication"] == "no"
    assert r["firewall"] == "inactive"
    assert r["upgradable"] == 12
    assert r["unattended"] is True
    assert r["reboot_required"] is False
    assert r["fail2ban"] is False


def test_parse_host_output_garbage_is_safe():
    assert isinstance(parse_host_output("nonsense"), dict)


def _f(level, title="x"):
    return {"area": "web", "level": level, "title": title, "detail": "d", "fix": "f"}


def test_render_escapes_and_shows_verdict():
    html = render("production", {"web": [_f("fail", "<script>")]}, None, "2026-11-12 10:00")
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "ต้องแก้" in html


def test_render_without_summary():
    html = render("production", {"attack": [_f("info")]}, None, "now")
    assert "ต่อ Pi ไม่ได้" in html or "ยังไม่มีข้อมูล" in html


def test_render_with_summary():
    s = {"days": 2, "total": 5, "by_kind": {"probe": 5}, "by_day": [{"day": "2026-11-11", "n": 2}, {"day": "2026-11-12", "n": 3}],
         "top_ips": [{"ip": "1.2.3.4", "n": 5}], "top_paths": [{"path": "/.env", "n": 5}], "recent": []}
    html = render("production", {"attack": [_f("ok")]}, s, "now")
    assert "1.2.3.4" in html and "/.env" in html and "สแกนหาช่องโหว่" in html


def test_main_pi_unreachable(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "ssh", lambda cmd, timeout=20: None)
    monkeypatch.setattr(collect, "web_checks", lambda url, self_check_token=None: {})
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path / "reports"))
    assert main_mod.main(["--no-open"]) == 0
    files = list((tmp_path / "reports").glob("security-production-*.html"))
    assert len(files) == 1
    assert "ต่อ Pi ไม่ได้" in files[0].read_text(encoding="utf-8")


def test_main_pi_not_deployed(monkeypatch, tmp_path):
    def fake_ssh(cmd, timeout=20):
        return "" if "security_log" in cmd else "ok"
    monkeypatch.setattr(collect, "ssh", fake_ssh)
    monkeypatch.setattr(collect, "web_checks", lambda url, self_check_token=None: {})
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path))
    assert collect.pi_attack_summary() == {"_error": "not_deployed"}
    assert main_mod.main(["--no-open"]) == 0


def test_local_config_flags_never_returns_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ADMIN_TOKEN=supersecretvalue123\nAPI_SESSION=0\n", encoding="utf-8")
    r = local_config_flags(str(env))
    assert "supersecret" not in json.dumps(r)
    assert r["admin_token_len"] == len("supersecretvalue123")
    assert r["api_session"] is False and r["api_browser_only"] is True
    assert r["general_rate_per_min"] == 600 and r["chat_rate_per_day"] == 60


def test_parse_host_output_denied():
    r = parse_host_output("@@sshd\nDENIED\n@@ufw\ndenied\n")
    assert r["sshd"] == {"_denied": True} and r["firewall"] == "denied"


def test_main_test_target_trusted_origin(monkeypatch, tmp_path):
    seen = {}
    def fake_web(url, self_check_token=None):
        return {"headers": {}, "status": {"/openapi.json": (200, "application/json", "{}")}}
    monkeypatch.setattr(collect, "web_checks", fake_web)
    monkeypatch.setattr(collect, "local_attack_summary", lambda d, days=30: None)
    monkeypatch.setattr(collect, "local_config_flags", lambda p: {})
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path))
    assert main_mod.main(["--target", "test", "--no-open"]) == 0
    html = next(tmp_path.glob("security-test-*.html")).read_text(encoding="utf-8")
    assert "openapi.json" not in html
    assert "เลยตรวจรั้วกันคนนอกไม่ได้" in html


def test_pi_config_flags_uses_stdin_no_tempfile(monkeypatch):
    cmds = []
    monkeypatch.setattr(collect, "ssh", lambda cmd, timeout=20: cmds.append(cmd) or None)
    collect.pi_config_flags()
    assert "/tmp" not in cmds[0] and "rm " not in cmds[0] and "python -" in cmds[0]


def test_web_checks_sends_self_check_header(monkeypatch):
    import urllib.request
    seen = []

    def fake_urlopen(req, timeout=None):
        seen.append({k.lower(): v for k, v in req.header_items()})
        raise OSError("no network")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    collect.web_checks("http://example.invalid", self_check_token="a" * 32)
    assert seen and all(h.get("x-bkk-self-check") == "a" * 32 for h in seen)
    seen.clear()
    collect.web_checks("http://example.invalid")
    assert seen and all("x-bkk-self-check" not in h for h in seen)


def test_main_no_token_adds_info(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "pi_self_check_token", lambda: None)
    monkeypatch.setattr(collect, "pi_attack_summary", lambda days=30: None)
    monkeypatch.setattr(collect, "pi_config_flags", lambda: {})
    monkeypatch.setattr(collect, "pi_host_raw", lambda: None)
    monkeypatch.setattr(collect, "web_checks", lambda url, self_check_token=None: {})
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path))
    assert main_mod.main(["--no-open"]) == 0
    html = next(tmp_path.glob("security-production-*.html")).read_text(encoding="utf-8")
    assert "ส่งรหัสตรวจตัวเองไม่ได้ รอบนี้จะถูกนับเป็นการโจมตี" in html


def test_report_shows_self_check_line():
    s = {"days": 30, "total": 1, "self_checks": 4, "by_kind": {"probe": 1},
         "by_day": [{"day": "2026-11-01", "n": 1}], "top_ips": [], "top_paths": [], "recent": []}
    assert "ไม่นับการตรวจของโปรแกรมนี้เอง 4 ครั้ง" in render("production", {"attack": []}, s, "now")


def test_host_script_finds_ufw_outside_path():
    # ssh without a login shell has no /usr/sbin in PATH; ufw lives there on Debian
    from launch.security_check import collect
    import base64, inspect
    src = inspect.getsource(collect)
    assert "/usr/sbin/ufw" in src


def _extra(**kw):
    e = {"ssh": {"failed": 40, "invalid_user": 5, "accepted": [], "failed_ips": [{"ip": "9.9.9.9", "n": 30}],
                 "users_tried": [{"user": "<b>root</b>", "n": 20}]},
         "owner_ips": ["7.7.7.7"],
         "geo": [{"ip": "9.9.9.9", "cc": "CN", "country": "China", "n": 30, "owner": False},
                 {"ip": "7.7.7.7", "cc": "TH", "country": "Thailand", "n": 3, "owner": True}]}
    e.update(kw)
    return e


def _summ():
    return {"days": 30, "total": 50, "by_kind": {"probe": 50}, "by_day": [{"day": "2026-11-12", "n": 50}],
            "top_ips": [{"ip": "<i>1.1.1.1</i>", "n": 40}, {"ip": "7.7.7.7", "n": 3}],
            "top_paths": [{"path": "/<script>x", "n": 9}], "recent": []}


def test_v2_escapes_everything():
    html = render("production", {"web": [_f("fail", "<script>alert(1)</script>")]}, _summ(), "now", _extra())
    for bad in ("<script>alert", "<i>1.1.1.1", "/<script>x", "<b>root</b>"):
        assert bad not in html
    assert "&lt;script&gt;alert(1)" in html


def test_v2_reduced_motion_and_no_network():
    import re
    html = render("production", {"web": [_f("warn")]}, _summ(), "now", _extra())
    assert "prefers-reduced-motion" in html
    assert not re.findall(r'(?:src|href)\s*=\s*["\']?https?:', html)
    assert "url(http" not in html and "@import" not in html


def test_v2_map_fallback_when_geo_empty():
    html = render("production", {"web": [_f("ok")]}, _summ(), "now",
                  {"ssh": None, "owner_ips": [], "geo": []})
    assert "ยังไม่มีฐานข้อมูล IP" in html


def test_v2_owner_chip_and_excluded_from_map():
    html = render("production", {"web": [_f("ok")]}, _summ(), "now", _extra())
    assert "7.7.7.7" in html and "เจ้าของ" in html
    assert 'data-cc="CN"' in html or "ไม่มีฐานข้อมูล" in html
    assert 'data-cc="TH"' not in html


def test_v2_copy_button_and_stats():
    html = render("production", {"host": [{"area": "host", "level": "fail", "title": "t", "detail": "d",
                                           "fix": "ทำตามนี้", "cmd": "sudo ufw deny from 1.2.3.4"}]}, _summ(), "now", _extra())
    assert "data-copy" in html and "<pre>sudo ufw deny from 1.2.3.4</pre>" in html
    assert 'aria-label="คัดลอกคำสั่ง: t"' in html and "ทำตามนี้" in html
    assert "ต้องแก้" in html and "45" in html


def test_v2_extra_none_ok():
    assert "<svg" in render("test", {"web": [_f("ok")]}, None, "now")


def test_fix_without_cmd_has_no_copy_box():
    html = render("production", {"host": [{"area": "host", "level": "warn", "title": "t", "detail": "d",
                                           "fix": "แก้ด้วยมือ"}]}, _summ(), "now", _extra())
    assert "แก้ด้วยมือ" in html and "<button" not in html and "<pre>" not in html


def test_owner_traffic_not_counted_in_cards():
    summ = {"days": 30, "total": 11, "by_kind": {"probe": 11}, "by_day": [{"day": "2026-11-12", "n": 11}],
            "top_ips": [{"ip": "7.7.7.7", "n": 11}], "top_paths": [], "recent": []}
    ssh = {"failed": 5, "invalid_user": 0, "accepted": [], "failed_ips": [{"ip": "7.7.7.7", "n": 5}], "users_tried": []}
    html = render("production", {"web": [_f("ok")]}, summ, "now", _extra(ssh=ssh))
    assert 'data-n="0">0</span>' in html
    assert html.count("(+11 ครั้งจากเจ้าของเครื่อง ไม่นับ)") == 1
    assert "(+5 ครั้งจากเจ้าของเครื่อง ไม่นับ)" in html
    assert "รวม 11 ครั้งจากเจ้าของเครื่อง" in html


def test_chip_wraps_and_csp_and_glow_scope():
    import re
    html = render("production", {"web": [_f("ok")]}, _summ(), "now", _extra())
    rule = re.search(r"\.chip\{[^}]*\}", html).group(0)
    assert "overflow-wrap:anywhere" in rule and "max-width:100%" in rule and "nowrap" not in rule
    assert 'http-equiv="Content-Security-Policy"' in html and "default-src 'none'" in html
    assert re.search(r"\.card\{[^}]*animation", html) is None
    assert 'class="bars" role="img" aria-label="ยอดบล็อกรายวัน' in html


def test_map_message_when_db_present(monkeypatch):
    from launch.security_check import geo
    monkeypatch.setattr(geo, "available", lambda: True)
    html = render("production", {"web": [_f("ok")]}, _summ(), "now", {"ssh": None, "owner_ips": [], "geo": []})
    assert "ยังไม่มีผู้โจมตีนอกบ้านให้แสดง" in html and "update_geo" not in html
