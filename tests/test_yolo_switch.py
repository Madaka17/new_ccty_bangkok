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


# --- gpu_memory: no CUDA context created just to read VRAM ---
import subprocess

from backend.vision import yolo_switch as ysw


class UninitCuda:
    def __init__(self):
        self.mem_calls = 0

    def is_initialized(self):
        return False

    def mem_get_info(self):
        self.mem_calls += 1
        return (1, 2)


def _fresh_cache():
    ysw._gpu_cache.update(at=None, value=None)


def test_gpu_memory_uses_nvidia_smi_when_cuda_not_initialized():
    _fresh_cache()
    cuda, cmds = UninitCuda(), []

    def run(cmd, **kw):
        cmds.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout="1234, 10240\n", stderr="")

    out = ysw.gpu_memory(cuda=cuda, run=run, now=lambda: 100.0)
    assert out == {"used_mb": 1234, "total_mb": 10240}
    assert cuda.mem_calls == 0
    assert cmds[0][1]["timeout"] == 3 and cmds[0][1]["capture_output"] is True and cmds[0][1]["text"] is True


def test_gpu_memory_none_when_nvidia_smi_fails():
    _fresh_cache()

    def run(cmd, **kw):
        raise FileNotFoundError("nvidia-smi")

    assert ysw.gpu_memory(cuda=UninitCuda(), run=run, now=lambda: 100.0) is None


def test_gpu_memory_cached_for_five_seconds():
    _fresh_cache()
    calls = []

    def run(cmd, **kw):
        calls.append(1)
        return subprocess.CompletedProcess(cmd, 0, stdout="1, 2\n", stderr="")

    t = [100.0]
    ysw.gpu_memory(cuda=UninitCuda(), run=run, now=lambda: t[0])
    t[0] = 103.0
    ysw.gpu_memory(cuda=UninitCuda(), run=run, now=lambda: t[0])
    assert len(calls) == 1
    t[0] = 106.0
    ysw.gpu_memory(cuda=UninitCuda(), run=run, now=lambda: t[0])
    assert len(calls) == 2


def test_gpu_memory_initialized_cuda_uses_mem_get_info():
    _fresh_cache()

    class Init(UninitCuda):
        def is_initialized(self):
            return True

        def mem_get_info(self):
            return (6 * 2**30, 10 * 2**30)

    assert ysw.gpu_memory(cuda=Init(), run=None, now=lambda: 1.0) == {"used_mb": 4096, "total_mb": 10240}


def test_non_object_state_file_means_on(tmp_path):
    p = tmp_path / "s.json"
    for text in ("[]", "null", '"x"'):
        p.write_text(text, encoding="utf-8")
        assert YoloSwitch(str(p), cuda=FakeCuda()).enabled is True
