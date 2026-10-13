"""While YOLO is off: no cloud calls from the helmet patrol, check_now says so, live frames stay plain."""
import numpy as np
import pytest
import ultralytics

from backend.vision import helmet_service, wrongway_service
from backend.vision.yolo_switch import YoloOff


class Vision:
    provider, client = "fake", object()


class OffScanner:
    cameras = [{"camid": "1", "title": "t"}]
    infer_lock = __import__("threading").Lock()

    class session:
        @staticmethod
        def fetch_snapshot(camid, timeout=0):
            import cv2
            return cv2.imencode(".jpg", np.zeros((64, 64, 3), np.uint8))[1].tobytes()

    @staticmethod
    def _detect(img):
        raise YoloOff("off")


def _patrol(monkeypatch, tmp_path, mod, cls, load_models=False, **kw):
    for attr in ("CACHE_DIR", "EVIDENCE_DIR", "ARCHIVE_DIR"):
        if hasattr(mod, attr):
            monkeypatch.setattr(mod, attr, str(tmp_path / attr))
    return cls(str(tmp_path / "v.db"), load_models=load_models, **kw)


def _pending_row(p, hid="h1"):
    p._insert((hid, 1, "1", "t", "d", "[0,0,1,1]", "pending", None, None, None, None, "wait", None))


def test_helmet_analyse_auto_while_off_makes_no_agent_call(monkeypatch, tmp_path):
    p = _patrol(monkeypatch, tmp_path, helmet_service, helmet_service.HelmetPatrol, vision=Vision())
    calls = []
    monkeypatch.setattr(p, "_ask", lambda jpeg, ctx: calls.append(1) or '{"riders":1,"no_helmet":0,"confidence":0.9,"note_th":"x"}')
    _pending_row(p)
    crop = np.zeros((40, 40, 3), np.uint8)
    p._analyse("h1", "1", {"camid": "1"}, crop, crop, agent="auto")
    assert calls == []
    assert p._row("h1")["verdict"] == "pending"


def test_helmet_analyse_auto_after_load_calls_agent_again(monkeypatch, tmp_path):
    monkeypatch.setattr(ultralytics, "YOLO", lambda path: (_ for _ in ()).throw(RuntimeError("no weights")))
    p = _patrol(monkeypatch, tmp_path, helmet_service, helmet_service.HelmetPatrol, vision=Vision())
    calls = []
    monkeypatch.setattr(p, "_ask", lambda jpeg, ctx: calls.append(1) or '{"riders":1,"no_helmet":0,"confidence":0.9,"note_th":"x"}')
    p.load_models()
    _pending_row(p)
    crop = np.zeros((40, 40, 3), np.uint8)
    p._analyse("h1", "1", {"camid": "1"}, crop, crop, agent="auto")
    assert calls == [1]


def test_helmet_explicit_cloud_still_works_while_off(monkeypatch, tmp_path):
    p = _patrol(monkeypatch, tmp_path, helmet_service, helmet_service.HelmetPatrol, vision=Vision())
    calls = []
    monkeypatch.setattr(p, "_ask", lambda jpeg, ctx: calls.append(1) or '{"riders":1,"no_helmet":0,"confidence":0.9,"note_th":"x"}')
    _pending_row(p)
    crop = np.zeros((40, 40, 3), np.uint8)
    p._analyse("h1", "1", {"camid": "1"}, crop, crop, agent="cloud")
    assert calls == [1]


def test_helmet_unload_sets_switched_off(monkeypatch, tmp_path):
    p = _patrol(monkeypatch, tmp_path, helmet_service, helmet_service.HelmetPatrol, load_models=True)
    p.unload_models()
    assert p._switched_off is True


def test_helmet_check_now_while_off(monkeypatch, tmp_path):
    p = _patrol(monkeypatch, tmp_path, helmet_service, helmet_service.HelmetPatrol, scanner=OffScanner())
    assert p.check_now("1") == {"ok": False, "error": "YOLO ปิดอยู่"}


def test_wrongway_check_now_while_off(monkeypatch, tmp_path):
    p = _patrol(monkeypatch, tmp_path, wrongway_service, wrongway_service.WrongWayPatrol, scanner=OffScanner())
    p.cls = object()     # a loaded classifier, so observe() asks the scanner's detector
    monkeypatch.setattr(p, "enabled", lambda: True)
    assert p.check_now("1") == {"ok": False, "error": "YOLO ปิดอยู่"}
