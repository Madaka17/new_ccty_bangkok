import json

from launch.security_check import collect, main as main_mod
from launch.security_check.collect import parse_host_output, local_config_flags
from launch.security_check.report import render

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
    monkeypatch.setattr(collect, "web_checks", lambda url: {})
    monkeypatch.setattr(main_mod, "REPORTS_DIR", str(tmp_path / "reports"))
    assert main_mod.main(["--no-open"]) == 0
    files = list((tmp_path / "reports").glob("security-production-*.html"))
    assert len(files) == 1
    assert "ต่อ Pi ไม่ได้" in files[0].read_text(encoding="utf-8")


def test_main_pi_not_deployed(monkeypatch, tmp_path):
    def fake_ssh(cmd, timeout=20):
        return "" if "security_log" in cmd else "ok"
    monkeypatch.setattr(collect, "ssh", fake_ssh)
    monkeypatch.setattr(collect, "web_checks", lambda url: {})
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
