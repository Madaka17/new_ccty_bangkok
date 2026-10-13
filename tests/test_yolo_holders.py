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
