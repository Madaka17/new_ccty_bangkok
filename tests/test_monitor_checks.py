import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_checks as mc  # noqa: E402

HEALTH = {"ok": True, "uptime_s": 7200, "gpu": {"name": None, "used_mb": 2048, "total_mb": 10240},
          "data_disk": {"path": "E:\\data", "free_gb": 120.0, "total_gb": 900.0}}


def patch(monkeypatch, up=(), stopped=(), ok_health=True, tunnel=True, watchdog_age=lambda: 30.0,
          public_status=lambda: (200, 200)):
    monkeypatch.setattr(mc, "stopped", lambda port: port in stopped)

    def health(port):
        if port not in up:
            raise urllib.error.URLError("refused")
        return {**HEALTH, "ok": ok_health}
    monkeypatch.setattr(mc, "health", health)
    monkeypatch.setattr(mc, "http_up", lambda port: port in up)
    monkeypatch.setattr(mc, "tunnel_running", lambda: tunnel)
    monkeypatch.setattr(mc, "camera_age", lambda: 60.0)
    monkeypatch.setattr(mc, "watchdog_age", watchdog_age)
    monkeypatch.setattr(mc, "public_status", public_status)
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


def test_camera_check(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050})
    monkeypatch.setattr(mc, "camera_age", lambda: 120.0)
    assert by_key(mc.run_round(gateway_due=False))["service:camera"]["state"] == "ok"
    monkeypatch.setattr(mc, "camera_age", lambda: 3600.0)
    assert by_key(mc.run_round(gateway_due=False))["service:camera"]["state"] == "fail"
    monkeypatch.setattr(mc, "camera_age", lambda: None)
    patch(monkeypatch, up=set(), stopped={8000, 8001, 5050})
    monkeypatch.setattr(mc, "camera_age", lambda: None)
    assert by_key(mc.run_round(gateway_due=False))["service:camera"]["state"] == "stopped"


def test_camera_idle_when_production_down_not_stopped(monkeypatch):
    patch(monkeypatch, up=set(), stopped={8001, 5050})
    monkeypatch.setattr(mc, "camera_age", lambda: 3600.0)
    row = by_key(mc.run_round(gateway_due=False))["service:camera"]
    assert row["state"] == "idle" and row["detail"] == "waiting for production"


def test_labels_for_new_services():
    assert mc.LABELS["watchdog"] == "Watchdog" and mc.LABELS["disk"] == "Data disk"
    assert mc.LABELS["public"] == "Public site"


def test_watchdog_heartbeat_ok_old_missing(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, watchdog_age=lambda: 100.0)
    row = by_key(mc.run_round(gateway_due=False))["service:watchdog"]
    assert row["state"] == "ok" and row["detail"] == "last run 100 s ago" and row["target"] == "watchdog"
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, watchdog_age=lambda: 360.0)
    row = by_key(mc.run_round(gateway_due=False))["service:watchdog"]
    assert row["state"] == "fail"
    assert row["detail"] == "no run for 6 min (scheduled task 'BKK StreetSmart watchdog')"
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, watchdog_age=lambda: None)
    row = by_key(mc.run_round(gateway_due=False))["service:watchdog"]
    assert row["state"] == "fail" and row["detail"] == "no heartbeat file"


def test_watchdog_age_reads_heartbeat_mtime(monkeypatch, tmp_path):
    import os
    import time
    monkeypatch.setattr(mc, "STATE_DIR", tmp_path)
    assert mc.watchdog_age() is None
    hb = tmp_path / "heartbeat"
    hb.write_text("x", encoding="utf-8")
    os.utime(hb, (time.time() - 50, time.time() - 50))
    assert 45 <= mc.watchdog_age() <= 80


def test_disk_ok_warn_fail(monkeypatch):
    def with_free(free):
        h = {**HEALTH, "data_disk": {"path": "E:\data", "free_gb": free, "total_gb": 900.0}}
        patch(monkeypatch, up={8000}, stopped={8001, 5050})
        monkeypatch.setattr(mc, "health", lambda port: h if port == 8000 else (_ for _ in ()).throw(urllib.error.URLError("x")))
        return by_key(mc.run_round(gateway_due=False))["service:disk"]
    row = with_free(120.0)
    assert row["state"] == "ok" and row["target"] == "disk"
    assert row["detail"] == "120.0 GB free of 900.0 GB (E:\data)"
    assert with_free(20.0)["state"] == "ok"
    assert with_free(19.9)["state"] == "warn"
    assert with_free(10.0)["state"] == "warn"
    assert with_free(5.0)["state"] == "warn"
    assert with_free(4.9)["state"] == "fail"
    assert with_free(2.0)["state"] == "fail"


def test_no_disk_row_when_production_down(monkeypatch):
    patch(monkeypatch, up=set(), stopped={8000, 8001, 5050})
    assert "service:disk" not in by_key(mc.run_round(gateway_due=False))


def test_public_only_when_gateway_due(monkeypatch):
    calls = []
    patch(monkeypatch, up={8000}, stopped={8001, 5050},
          public_status=lambda: calls.append(1) or (200, 200))
    assert "service:public" not in by_key(mc.run_round(gateway_due=False))
    assert calls == []
    row = by_key(mc.run_round(gateway_due=True))["service:public"]
    assert row["state"] == "ok" and row["target"] == "public"
    assert row["detail"] == "bkksmartstreet.com 200 · /enviro/ 200"
    assert calls == [1]


def test_public_fail_522_names_origin(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, public_status=lambda: (522, 200))
    row = by_key(mc.run_round(gateway_due=True))["service:public"]
    assert row["state"] == "fail" and "origin" in row["detail"] and "522" in row["detail"]


def test_public_no_answer_is_zero(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, public_status=lambda: (0, 200))
    row = by_key(mc.run_round(gateway_due=True))["service:public"]
    assert row["state"] == "fail" and "no answer" in row["detail"]


def test_public_enviro_stopped_on_purpose_judges_main_only(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, public_status=lambda: (200, 502))
    assert by_key(mc.run_round(gateway_due=True))["service:public"]["state"] == "ok"


def test_public_enviro_fails_when_not_stopped(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001}, public_status=lambda: (200, 502))
    assert by_key(mc.run_round(gateway_due=True))["service:public"]["state"] == "fail"


def test_public_probe_crash_becomes_fail_row(monkeypatch):
    def boom():
        raise RuntimeError("dns down")
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, public_status=boom)
    row = by_key(mc.run_round(gateway_due=True))["service:public"]
    assert row["state"] == "fail" and "dns down" in row["detail"]


def test_public_status_codes(monkeypatch):
    import io
    seen = []

    def fake_urlopen(url, timeout):
        seen.append((url, timeout))
        if "enviro" in url:
            raise urllib.error.HTTPError(url, 522, "x", None, io.BytesIO(b""))
        raise urllib.error.URLError("no route")
    monkeypatch.setattr(mc.urllib.request, "urlopen", fake_urlopen)
    assert mc.public_status() == (0, 522)
    assert seen == [("https://bkksmartstreet.com/", 20), ("https://bkksmartstreet.com/enviro/", 20)]
