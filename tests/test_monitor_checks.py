import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_checks as mc  # noqa: E402

HEALTH = {"ok": True, "uptime_s": 7200, "gpu": {"name": None, "used_mb": 2048, "total_mb": 10240}}


def patch(monkeypatch, up=(), stopped=(), ok_health=True, tunnel=True):
    monkeypatch.setattr(mc, "stopped", lambda port: port in stopped)

    def health(port):
        if port not in up:
            raise urllib.error.URLError("refused")
        return {**HEALTH, "ok": ok_health}
    monkeypatch.setattr(mc, "health", health)
    monkeypatch.setattr(mc, "http_up", lambda port: port in up)
    monkeypatch.setattr(mc, "tunnel_running", lambda: tunnel)
    monkeypatch.setattr(mc, "gateway", lambda: (True, True, "200, qwen listed", "200 answered", 1.2))
    monkeypatch.setattr(mc, "agents", lambda port: {"summary": "s", "window": 60, "rows": [
        {"name": "Bangkok flood report", "state": "ok", "data": "1m", "analysis": "1m", "calls": 1, "fails": 0,
         "tokens": 10, "note": ""}]})
    monkeypatch.setattr(mc, "yolo", lambda port, h: {"server": {}, "rows": [
        {"name": "YOLO switch", "state": "ok", "detail": "on"}]})


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_production_up_test_stopped(monkeypatch):
    patch(monkeypatch, up={8000, 5050}, stopped={8001})
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["server:production"]["state"] == "ok"
    assert "up 2 h" in rows["server:production"]["detail"]
    assert rows["server:test"]["state"] == "stopped"
    assert "agent:production:Bangkok flood report" in rows
    assert "yolo:production:YOLO switch" in rows
    assert not any(k.startswith(("agent:test", "yolo:test")) for k in rows)
    assert rows["server:enviro"]["state"] == "ok"
    assert rows["service:tunnel"]["state"] == "ok"
    assert "service:gateway" not in rows


def test_down_without_marker_fails(monkeypatch):
    patch(monkeypatch, up=set(), stopped=set())
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["server:production"]["state"] == "fail"
    assert rows["server:enviro"]["state"] == "fail"


def test_health_503_is_warn_and_still_checks_agents(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, ok_health=False)
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["server:production"]["state"] == "warn"
    assert "agent:production:Bangkok flood report" in rows


def test_gateway_and_tunnel(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, tunnel=False)
    rows = by_key(mc.run_round(gateway_due=True))
    assert rows["service:gateway"]["state"] == "ok"
    assert rows["service:tunnel"]["state"] == "fail"


def test_agent_check_crash_becomes_fail_row(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050})

    def boom(port):
        raise RuntimeError("bad json")
    monkeypatch.setattr(mc, "agents", boom)
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["agent:production:checks"]["state"] == "fail"
    assert "bad json" in rows["agent:production:checks"]["detail"]


def test_server_status_carries_uptime(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050})
    assert by_key(mc.run_round(gateway_due=False))["server:production"]["uptime_s"] == 7200
