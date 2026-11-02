"""YOLO holders on the Pi: with AI_WORKER_URL set they load a RemoteYolo, skip CUDA and warm-up, and
treat a worker that is down as YOLO off."""
import importlib

import numpy as np
import pytest

from backend.vision import yolo_detector
from backend.vision.yolo_switch import YoloOff, YoloSwitch


class FakeRemote:
    remote = True

    def __init__(self, path, names=None, fail=False):
        self.path = path
        self.names_ = names or {0: "helmet", 1: "no_helmet"}
        self.fail = fail
        self.calls = []
        self.moved = False

    @property
    def names(self):
        if self.fail:
            raise YoloOff("AI worker offline")
        return self.names_

    def to(self, *_):
        self.moved = True
        return self

    def __call__(self, source, **kw):
        self.calls.append(kw)
        raise YoloOff("AI worker offline")


@pytest.fixture
def pi_env(monkeypatch):
    monkeypatch.setenv("AI_WORKER_URL", "http://pc:8100")
    monkeypatch.setenv("AI_WORKER_TOKEN", "t")
    monkeypatch.setenv("YOLO_ALLOWED", "0")


def test_detector_loads_remote_without_cuda_or_warmup(pi_env, monkeypatch):
    made = []
    monkeypatch.setattr(yolo_detector, "load_yolo", lambda p, **kw: made.append(FakeRemote(p)) or made[-1])
    d = yolo_detector.VehicleDetectorYOLO11x(model_path="yolo26x.pt")
    assert d.models_loaded()
    assert made[0].calls == [] and made[0].moved is False


def test_detector_infer_raises_yolo_off_when_worker_down(pi_env, monkeypatch):
    monkeypatch.setattr(yolo_detector, "load_yolo", lambda p, **kw: FakeRemote(p, names={2: "car"}))
    d = yolo_detector.VehicleDetectorYOLO11x(model_path="yolo26x.pt")
    with pytest.raises(YoloOff):
        d.detect_boxes(np.zeros((720, 1280, 3), dtype=np.uint8), tiled=False)
    with pytest.raises(YoloOff):
        d.detect_boxes(np.zeros((360, 640, 3), dtype=np.uint8), tiled=True)


@pytest.mark.parametrize("module_name,cls_name,attr,loaded_attr", [
    ("backend.vision.helmet_service", "HelmetPatrol", "LOCAL_DET_PATH", "local_det"),
    ("backend.vision.wrongway_service", "WrongWayPatrol", "CLS_PATH", "cls"),
    ("backend.vision.violation_service", "ViolationMonitor", "HELMET_CLS_PATH", "helmet_cls"),
])
def test_patrol_loads_remote_when_file_missing_on_pi(pi_env, monkeypatch, tmp_path, module_name, cls_name,
                                                     attr, loaded_attr):
    mod = importlib.import_module(module_name)
    made = []
    monkeypatch.setattr(mod, "load_yolo", lambda p, **kw: made.append(FakeRemote(p)) or made[-1])
    monkeypatch.setattr(mod, "weights_available", lambda p: True)   # the worker has it
    monkeypatch.setattr(mod, attr, str(tmp_path / "not_on_the_pi.pt"))
    for a in ("CACHE_DIR", "EVIDENCE_DIR", "ARCHIVE_DIR"):
        if hasattr(mod, a):
            monkeypatch.setattr(mod, a, str(tmp_path / a))
    p = getattr(mod, cls_name)(str(tmp_path / "v.db"))
    assert p.models_loaded() is True
    assert getattr(p, loaded_attr) is made[0]
    assert made[0].calls == []          # no warm-up over the network


def test_patrol_stays_unloaded_when_worker_down_at_load(pi_env, monkeypatch, tmp_path):
    mod = importlib.import_module("backend.vision.violation_service")
    monkeypatch.setattr(mod, "load_yolo", lambda p, **kw: FakeRemote(p, fail=True))
    monkeypatch.setattr(mod, "weights_available", lambda p: True)
    p = mod.ViolationMonitor(str(tmp_path / "v.db"))
    assert p.models_loaded() is False


class Holder:
    def __init__(self, loaded, fail=False):
        self.loaded, self.fail, self.loads = loaded, fail, 0

    def load_models(self):
        self.loads += 1
        if self.fail:
            raise RuntimeError("worker down")
        self.loaded = True

    def unload_models(self):
        self.loaded = False

    def models_loaded(self):
        return self.loaded


def test_retry_missing_loads_only_missing_holders(tmp_path):
    sw = YoloSwitch(str(tmp_path / "s.json"), cuda=None)
    a, b = Holder(True), Holder(False)
    sw.register("a", a)
    sw.register("b", b)
    assert sw.retry_missing() == ["b"]
    assert a.loads == 0 and b.loads == 1 and b.loaded


def test_retry_missing_noop_when_off(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"enabled": false}')
    sw = YoloSwitch(str(p), cuda=None)
    h = Holder(False)
    sw.register("h", h)
    assert sw.retry_missing() == []
    assert h.loads == 0


def test_retry_missing_survives_holder_error(tmp_path):
    sw = YoloSwitch(str(tmp_path / "s.json"), cuda=None)
    bad, good = Holder(False, fail=True), Holder(False)
    sw.register("bad", bad)
    sw.register("good", good)
    assert sw.retry_missing() == ["good"]
    assert good.loaded and not bad.loaded


def test_patrol_off_when_worker_lacks_the_weights(pi_env, monkeypatch, tmp_path):
    mod = importlib.import_module("backend.vision.violation_service")
    made = []
    monkeypatch.setattr(mod, "load_yolo", lambda p, **kw: made.append(FakeRemote(p)) or made[-1])
    monkeypatch.setattr(mod, "weights_available", lambda p: False)
    p = mod.ViolationMonitor(str(tmp_path / "v.db"))
    assert p.models_loaded() is False and made == []


def test_helmet_check_stays_pending_when_worker_down(pi_env, monkeypatch, tmp_path):
    # A PC reboot must not turn queued helmet checks into saved "error" rows: they stay pending, like YOLO off.
    mod = importlib.import_module("backend.vision.helmet_service")
    monkeypatch.setattr(mod, "load_yolo", lambda p, **kw: FakeRemote(p))
    monkeypatch.setattr(mod, "weights_available", lambda p: True)
    for a in ("CACHE_DIR", "EVIDENCE_DIR", "ARCHIVE_DIR"):
        if hasattr(mod, a):
            monkeypatch.setattr(mod, a, str(tmp_path / a))
    p = mod.HelmetPatrol(str(tmp_path / "v.db"))
    updates = []
    monkeypatch.setattr(p, "_update", lambda hid, **kw: updates.append(kw))
    p._analyse(1, "7", {"camid": "7"}, np.zeros((64, 64, 3), dtype=np.uint8), None)
    assert updates == []
