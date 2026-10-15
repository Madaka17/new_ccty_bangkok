import importlib.util
import io
import json
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("yolo_status_mod", ROOT / "launch" / "yolo_status.py")
ys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ys)

HEALTH = {"ok": True, "uptime_s": 600, "gpu": {"name": None, "used_mb": 2000, "total_mb": 10240},
          "scan": {"cycle": 5, "age_s": 60, "running": False}, "bma_source": {"frames_ok": 500, "frames_new": 20, "state": "ok"}}


def fake_fetch(resp):
    def fetch(port, path):
        val = resp[path]
        if isinstance(val, Exception):
            raise val
        return val
    return fetch


def base(**over):
    resp = {"/api/health": HEALTH,
            "/api/ai/yolo": {"enabled": True, "vram": {"used_mb": 2000, "total_mb": 10240}},
            "/api/ai/stats": {"active": False, "model": "YOLO26x"},
            "/api/helmet/status": {"enabled": True, "last_check": time.time() - 30, "local_detector": "helmet_det",
                                   "calls_last_hour": 10, "queue": 0, "today": {}},
            "/api/wrongway/status": {"enabled": True, "frames_seen": 100, "detector": "wrongway_det",
                                     "cameras_learned": 3, "cameras_seen": 9, "today": {}}}
    resp.update(over)
    return resp


def test_all_working():
    out = ys.check_yolo(8000, fetch=fake_fetch(base()))
    states = {r["name"]: r["state"] for r in out["rows"]}
    assert states["YOLO switch"] == "ok"
    assert states["YOLO26x  BMA camera scan"] == "ok"
    assert states["YOLO26x  live AI camera"] == "idle"
    assert states["helmet  helmet_det"] == "ok"
    assert states["wrong-way  wrongway_det"] == "ok"
    assert out["server"]["uptime_s"] == 600


def test_switch_off_is_idle():
    out = ys.check_yolo(8000, fetch=fake_fetch(base(**{"/api/ai/yolo": {"enabled": False, "vram": None}})))
    sw = next(r for r in out["rows"] if r["name"] == "YOLO switch")
    assert sw["state"] == "idle" and "off" in sw["detail"]


def test_stale_scan_fails():
    h = {**HEALTH, "ok": False, "scan": {"cycle": 5, "age_s": 3600, "running": False}}
    out = ys.check_yolo(8000, fetch=fake_fetch(base(**{"/api/health": h})))
    scan = next(r for r in out["rows"] if r["name"] == "YOLO26x  BMA camera scan")
    assert scan["state"] == "fail"


def test_health_503_returns_body():
    body = json.dumps({**HEALTH, "ok": False}).encode()

    def fetch(port, path):
        raise urllib.error.HTTPError("http://x/api/health", 503, "Service Unavailable", {}, io.BytesIO(body))
    h = ys.get_health(8000, fetch=fetch)
    assert h["ok"] is False and h["uptime_s"] == 600


def test_health_refused_raises():
    def fetch(port, path):
        raise urllib.error.URLError("refused")
    try:
        ys.get_health(8000, fetch=fetch)
    except urllib.error.URLError:
        return
    raise AssertionError("expected URLError")
