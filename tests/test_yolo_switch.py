"""YoloSwitch: saved on/off state, holders loaded and unloaded in turn, VRAM figures."""
import json
import threading
import time

from backend.vision.yolo_switch import YoloSwitch


class Holder:
    def __init__(self, fail_load=False, slow=0.0):
        self.loaded = True
        self.fail_load = fail_load
        self.slow = slow
        self.calls = []

    def load_models(self):
        self.calls.append("load")
        time.sleep(self.slow)
        if self.fail_load:
            raise RuntimeError("CUDA out of memory")
        self.loaded = True

    def unload_models(self):
        self.calls.append("unload")
        time.sleep(self.slow)
        self.loaded = False

    def models_loaded(self):
        return self.loaded


class FakeCuda:
    def __init__(self):
        self.emptied = 0

    def is_available(self):
        return True

    def empty_cache(self):
        self.emptied += 1

    def mem_get_info(self):
        return (6 * 2**30, 10 * 2**30)   # free, total


def test_missing_state_file_means_on(tmp_path):
    assert YoloSwitch(str(tmp_path / "yolo_switch.json"), cuda=FakeCuda()).enabled is True


def test_off_unloads_every_holder_frees_cache_and_saves(tmp_path):
    path = tmp_path / "yolo_switch.json"
    cuda = FakeCuda()
    sw = YoloSwitch(str(path), cuda=cuda)
    a, b = Holder(), Holder()
    sw.register("detector", a)
    sw.register("helmet", b)
    out = sw.set(False)
    assert a.calls == ["unload"] and b.calls == ["unload"]
    assert cuda.emptied >= 1
    assert out["enabled"] is False and out["holders"] == {"detector": False, "helmet": False}
    assert json.loads(path.read_text(encoding="utf-8"))["enabled"] is False
    assert YoloSwitch(str(path), cuda=cuda).enabled is False   # survives a restart


def test_on_loads_every_holder_and_reports_failures(tmp_path):
    sw = YoloSwitch(str(tmp_path / "s.json"), cuda=FakeCuda())
    good, bad = Holder(), Holder(fail_load=True)
    good.loaded = bad.loaded = False
    sw.register("detector", good)
    sw.register("wrongway", bad)
    out = sw.set(True)
    assert out["enabled"] is True
    assert out["holders"] == {"detector": True, "wrongway": False}
    assert "out of memory" in out["errors"]["wrongway"]
    assert good.calls == ["load"]


def test_flips_run_one_at_a_time_and_last_one_wins(tmp_path):
    path = tmp_path / "s.json"
    sw = YoloSwitch(str(path), cuda=FakeCuda())
    h = Holder(slow=0.2)
    sw.register("detector", h)
    t = threading.Thread(target=sw.set, args=(False,))
    t.start()
    time.sleep(0.05)
    sw.set(True)
    t.join()
    assert h.calls == ["unload", "load"]
    assert json.loads(path.read_text(encoding="utf-8"))["enabled"] is True


def test_status_reports_vram(tmp_path):
    st = YoloSwitch(str(tmp_path / "s.json"), cuda=FakeCuda()).status()
    assert st["vram"] == {"used_mb": 4096, "total_mb": 10240}


def test_status_without_cuda(tmp_path):
    assert YoloSwitch(str(tmp_path / "s.json"), cuda=None).status()["vram"] is None
