"""WrongWayPatrol.observe: the heading classifier runs at most every CLS_EVERY s per camera, and on the biggest crops."""
import queue
import threading
from types import SimpleNamespace

import numpy as np

from backend.vision import wrongway_service as svc

DARK = np.zeros((360, 640, 3), np.uint8)
BRIGHT = np.full((360, 640, 3), 255, np.uint8)   # far from DARK in same_scene, so every frame is a new scene
CAR = 2


class FakeCls:
    """Stands in for the heading classifier: records each call's crops, always answers 'toward' at 95%."""

    def __init__(self):
        self.calls = []

    def __call__(self, crops, imgsz=None, verbose=False):
        self.calls.append(list(crops))
        return [SimpleNamespace(names=svc.HEADINGS, probs=SimpleNamespace(top1=0, top1conf=0.95)) for _ in crops]


def _patrol(monkeypatch, tmp_path, clock):
    """A patrol without __init__ (no threads, no sqlite, no model files): only what observe touches."""
    monkeypatch.setattr(svc, "FIELD_DIR", str(tmp_path / "heading"))
    monkeypatch.setattr(svc, "time", SimpleNamespace(time=lambda: clock["t"]))
    p = svc.WrongWayPatrol.__new__(svc.WrongWayPatrol)
    p.db_path = str(tmp_path / "ww.db")
    p.vision = None
    p.scanner = None
    p.lock = threading.Lock()
    p.fields = {}
    p._last_visit = {}
    p._last_frame = {}
    p._last_boxes = {}
    p._last_classify = {}
    p._calls = []
    p._queue = queue.Queue()
    p.last_check = 0
    p.agent_error = None
    p.frames_seen = 0
    p.det = None
    p.det_names = {}
    p.cls = FakeCls()
    p._det_lock = threading.Lock()
    return p


def _cam(camid):
    return {"camid": camid, "title": f"cam {camid}"}


BOXES = [(CAR, 0.9, 100, 100, 160, 180)]


def test_second_frame_within_interval_is_skipped(monkeypatch, tmp_path):
    clock = {"t": 1000.0}
    p = _patrol(monkeypatch, tmp_path, clock)
    p.observe(_cam(1), DARK, BOXES)
    clock["t"] += 60
    p.observe(_cam(1), BRIGHT, BOXES)
    assert len(p.cls.calls) == 1


def test_frame_after_interval_is_classified(monkeypatch, tmp_path):
    clock = {"t": 1000.0}
    p = _patrol(monkeypatch, tmp_path, clock)
    p.observe(_cam(1), DARK, BOXES)
    clock["t"] += 601
    p.observe(_cam(1), BRIGHT, BOXES)
    assert len(p.cls.calls) == 2


def test_force_ignores_interval(monkeypatch, tmp_path):
    clock = {"t": 1000.0}
    p = _patrol(monkeypatch, tmp_path, clock)
    p.observe(_cam(1), DARK, BOXES)
    clock["t"] += 60
    p.observe(_cam(1), BRIGHT, BOXES, force=True)
    assert len(p.cls.calls) == 2


def test_other_camera_not_throttled(monkeypatch, tmp_path):
    clock = {"t": 1000.0}
    p = _patrol(monkeypatch, tmp_path, clock)
    p.observe(_cam(1), DARK, BOXES)
    p.observe(_cam(2), DARK, BOXES)
    assert len(p.cls.calls) == 2


def test_crops_capped_biggest_first(monkeypatch, tmp_path):
    clock = {"t": 1000.0}
    p = _patrol(monkeypatch, tmp_path, clock)
    # box i grows with i: x2 = 10 + 5i, y2 = 12 + 3i, so area (and x2) is strictly increasing
    boxes = [(CAR, 0.9, 0, 0, 10 + 5 * i, 12 + 3 * i) for i in range(40)]
    out = p._classify_headings(DARK, boxes)
    assert len(p.cls.calls) == 1
    assert len(p.cls.calls[0]) == svc.CLS_MAX_CROPS == 24
    kept_x2 = sorted(o[5] for o in out)
    assert kept_x2 == sorted(10 + 5 * i for i in range(40 - 24, 40))
