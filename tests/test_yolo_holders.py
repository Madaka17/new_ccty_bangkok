"""Model holders: load, unload, idle while off. A fake YOLO stands in for the real weights."""
import threading
import time

import numpy as np
import pytest

from backend.vision import yolo_detector
from backend.vision.yolo_switch import YoloOff


class FakeYOLO:
    loads = 0

    def __init__(self, path):
        FakeYOLO.loads += 1
        self.names = {2: "car", 3: "motorcycle"}

    def to(self, *_):
        return self

    def half(self):
        return self

    def __call__(self, frame, **kw):
        class R:
            boxes = []
        return [R()] if not isinstance(frame, list) else [R() for _ in frame]


@pytest.fixture
def fake_yolo(monkeypatch):
    FakeYOLO.loads = 0
    monkeypatch.setattr(yolo_detector, "YOLO", FakeYOLO)
    monkeypatch.setattr(yolo_detector.torch.cuda, "is_available", lambda: False)
    return FakeYOLO


def test_detector_built_off_loads_nothing(fake_yolo):
    d = yolo_detector.VehicleDetectorYOLO11x(model_path="yolo26x.pt", load_models=False)
    assert fake_yolo.loads == 0 and d.models_loaded() is False


def test_detector_infer_while_off_raises_yolo_off(fake_yolo):
    d = yolo_detector.VehicleDetectorYOLO11x(model_path="yolo26x.pt", load_models=False)
    with pytest.raises(YoloOff):
        d.infer(np.zeros((720, 1280, 3), dtype=np.uint8), tiled=False)


def test_detector_unload_and_load(fake_yolo):
    d = yolo_detector.VehicleDetectorYOLO11x(model_path="yolo26x.pt")
    assert d.models_loaded()
    d.unload_models()
    assert not d.models_loaded()
    d.load_models()
    d.load_models()   # loading twice keeps one model
    assert d.models_loaded() and fake_yolo.loads == 2


def test_unload_waits_for_a_running_inference(fake_yolo):
    d = yolo_detector.VehicleDetectorYOLO11x(model_path="yolo26x.pt")
    d.model_lock.acquire()          # an inference holds the model
    t = threading.Thread(target=d.unload_models)
    t.start()
    time.sleep(0.1)
    assert d.models_loaded()        # not dropped mid-inference
    d.model_lock.release()
    t.join(2)
    assert not d.models_loaded()


import ultralytics


@pytest.mark.parametrize("module_name,cls_name,path_attrs", [
    ("backend.vision.helmet_service", "HelmetPatrol", ["LOCAL_DET_PATH"]),
    ("backend.vision.wrongway_service", "WrongWayPatrol", ["CLS_PATH"]),
    ("backend.vision.violation_service", "ViolationMonitor", ["HELMET_CLS_PATH"]),
])
def test_patrol_models_follow_the_switch(monkeypatch, tmp_path, module_name, cls_name, path_attrs):
    import importlib
    mod = importlib.import_module(module_name)
    monkeypatch.setattr(ultralytics, "YOLO", FakeYOLO)
    for attr in path_attrs:
        weights = tmp_path / f"{attr}.pt"
        weights.write_bytes(b"x")
        monkeypatch.setattr(mod, attr, str(weights))
    for attr in ("CACHE_DIR", "EVIDENCE_DIR", "ARCHIVE_DIR"):
        if hasattr(mod, attr):
            monkeypatch.setattr(mod, attr, str(tmp_path / attr))
    cls = getattr(mod, cls_name)
    off = cls(str(tmp_path / "v.db"), load_models=False)
    assert off.models_loaded() is False
    off.load_models()
    assert off.models_loaded() is True
    off.load_models()   # no-op when loaded
    off.unload_models()
    assert off.models_loaded() is False
