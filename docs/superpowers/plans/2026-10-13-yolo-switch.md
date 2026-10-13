# YOLO On/Off Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Desktop icon "BKK YOLO On-Off" that shows whether YOLO is on and flips it. Off stops all YOLO work and returns the GPU memory (VRAM). The state survives a server restart.

**Architecture:** A small `YoloSwitch` (new `backend/vision/yolo_switch.py`) owns the on/off state (a JSON file in the instance cache) and a list of "model holders". Holders are the four objects that load YOLO weights: the vehicle detector, the helmet patrol, the wrong-way patrol and the violation monitor. Each holder gets `load_models()` / `unload_models()` / `models_loaded()`. While the vehicle detector is unloaded, its `infer()` raises `YoloOff`. Every caller already loops per frame: it catches `YoloOff` and idles instead of writing zero counts. The server exposes `GET/POST /api/ai/yolo`. That path is operator-only through the existing access guard, since `/api/ai/` is not a public write prefix. A console script `launch/yolo_switch.py` (with a `.bat` and the Desktop shortcut) calls the endpoint.

**Tech Stack:** Python 3.14, FastAPI, ultralytics YOLO, torch CUDA, pytest; React + vitest for the dashboard fallback; Windows `.bat` + `WScript.Shell` shortcut.

**Spec:** the user's decisions of 2026-10-13 (no separate spec file):
- **Off:** stop all YOLO work and free VRAM.
- **Scope:** every YOLO model (vehicle counting on the live camera and the count workers and the survey, the BMA scanner, the helmet check, the wrong-way check).
- **Icon:** one Desktop icon that toggles. It shows the state and asks Y/N.
- **Restart:** off stays off after a server restart.
- **States:** two only (GPU on / off). No CPU mode.

## Global Constraints

- Off must free VRAM: drop every model reference, then `gc.collect()` and `torch.cuda.empty_cache()`. Verified on production with `nvidia-smi` in Task 8.
- While off, no component may write vehicle counts of 0 as if they were measured. Counts keep their last values. Pages must not show a "free flow" made from missing data.
- While off, the BMA scanner keeps fetching snapshots, because the flood camera watch (Qwen vision) still needs them. Only the YOLO step and the count write are skipped.
- State file: `<DATA_DIR>/cache/yolo_switch.json`, `{"enabled": bool, "changed_at": int}`. If the file is missing or unreadable, YOLO is on.
- `POST /api/ai/yolo` stays operator-only. Do not add it to `PUBLIC_WRITE_PREFIXES`.
- Tests never load real YOLO weights and never import the real `backend.services`. Monkeypatch `YOLO` with a fake class. Route tests use the stub-services pattern in `tests/test_api_micro_cache.py`.
- All user-visible text is short, plain Thai (project rule). Code, comments, commits and docs are in English.
- Run tests with `.venv/Scripts/python.exe -m pytest -q tests`. Run web tests with `npm test` in `web/`. The Python suite has 282 passed before this plan.
- Commit trailer: `Co-Authored-By:` naming the model that wrote the commit.

## Review Focus

1. **Flip while a frame is being processed.** `unload_models()` must take the holder's model lock, so it never drops a model mid-inference. An inference that starts after the drop raises `YoloOff`. It never hits an `AttributeError` on `None`. Task 2 has a test.
2. **Double flip / concurrent POSTs.** Two "off" requests at once, or "on" while "off" is still unloading, run one after the other under the switch lock. The state file ends with the last requested value. Task 1 has a test.
3. **A holder fails to load** (missing `.pt`, CUDA OOM when turning on). The switch still reports which holders loaded. One failure does not stop the others. The state still says "on", so a later retry can load the rest. Task 1 has a test.
4. **Restart while off.** The constructors get `load_models=False` from the saved state, so no weights touch the GPU at startup. Tasks 2, 3 and 5 have tests.
5. **Dashboard while off.** The BMA camera summary must count as not online, so the dashboard uses Longdo (the fallback from commit 613a2b6). Task 6 has a test.

---

## File Structure

- Create `backend/vision/yolo_switch.py`: `YoloOff` exception, `YoloSwitch` class (state file, holders, `set()`, `status()`, VRAM figures).
- Modify `backend/vision/yolo_detector.py`: holder methods; `infer()` raises `YoloOff` when unloaded; live `_process_loop` idles on `YoloOff`.
- Modify `backend/vision/count_workers.py`, `backend/vision/survey.py`: catch `YoloOff`.
- Modify `backend/vision/helmet_service.py`, `backend/vision/wrongway_service.py`, `backend/vision/violation_service.py`: holder methods + `load_models` constructor kwarg.
- Modify `backend/bma/bma_service.py`: skip YOLO + count write on `YoloOff`; `get_analytics` reports `scan_status.yolo_enabled` and no online cameras while off.
- Modify `backend/services.py`: build the switch first, pass `load_models=`, register holders.
- Modify `backend/api/live_ai.py`: `GET /api/ai/yolo`, `POST /api/ai/yolo`.
- Modify `web/src/lib/trafficSummary.js` + `web/src/components/DashboardPage.jsx`: BMA summary is offline while YOLO is off.
- Create `launch/yolo_switch.py`, `launch/yolo_switch.bat`.
- Tests: `tests/test_yolo_switch.py`, `tests/test_yolo_holders.py`, `tests/test_bma_yolo_off.py`, `tests/test_yolo_api.py`, `tests/test_yolo_switch_cli.py`, `web/src/lib/trafficSummary.test.js` (extend).

---

### Task 1: The switch

**Files:** Create `backend/vision/yolo_switch.py`; Test `tests/test_yolo_switch.py`

**Interfaces — Produces:**
- `class YoloOff(RuntimeError)`
- `class YoloSwitch(state_path: str, cuda=None)`. `cuda` is injectable for tests; the default is `torch.cuda` when torch imports, else `None`.
  - `.enabled -> bool` (the saved state, read at construction)
  - `.register(name: str, holder)`. A holder has `load_models()`, `unload_models()`, `models_loaded() -> bool`.
  - `.set(enabled: bool) -> dict` (the same shape as `status()`, plus `"errors": {name: message}`)
  - `.status() -> dict`: `{"enabled", "changed_at", "holders": {name: bool}, "vram": {"used_mb", "total_mb"} | None}`

- [ ] **Step 1: Write the failing tests** (`tests/test_yolo_switch.py`)

```python
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
```

- [ ] **Step 2: Run, expect** collection error `ModuleNotFoundError: backend.vision.yolo_switch`.

- [ ] **Step 3: Implement** `backend/vision/yolo_switch.py`:

```python
"""
YOLO on/off (launch\\yolo_switch.bat, the "BKK YOLO On-Off" Desktop icon).

Off drops every YOLO model from the GPU: the vehicle detector (live camera, count workers, survey and
the BMA scanner share it), the helmet patrol, the wrong-way patrol and the violation monitor. Callers of
the detector get YoloOff while it is off and idle instead of writing counts of 0. The state is saved in
the instance cache, so a restart while off starts with no weights on the GPU.
"""
import gc
import json
import os
import threading
import time


class YoloOff(RuntimeError):
    """YOLO is switched off: no model to run."""


def _default_cuda():
    try:
        import torch
        return torch.cuda
    except Exception:  # noqa: BLE001 - no torch: no VRAM figures
        return None


class YoloSwitch:
    def __init__(self, state_path, cuda=_default_cuda):
        self.state_path = state_path
        self.cuda = cuda() if callable(cuda) and cuda is _default_cuda else cuda
        self.lock = threading.Lock()     # one flip at a time
        self.holders = {}                # name -> holder, in registration order
        self.enabled, self.changed_at = True, 0
        try:
            with open(state_path, encoding="utf-8") as f:
                saved = json.load(f)
            self.enabled = bool(saved.get("enabled", True))
            self.changed_at = int(saved.get("changed_at") or 0)
        except (OSError, ValueError):
            pass

    def register(self, name, holder):
        self.holders[name] = holder

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"enabled": self.enabled, "changed_at": self.changed_at}, f)
        os.replace(tmp, self.state_path)

    def _free_cache(self):
        gc.collect()
        try:
            if self.cuda is not None and self.cuda.is_available():
                self.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def set(self, enabled):
        enabled = bool(enabled)
        errors = {}
        with self.lock:
            self.enabled, self.changed_at = enabled, int(time.time())
            self._save()
            for name, holder in self.holders.items():
                try:
                    holder.load_models() if enabled else holder.unload_models()
                except Exception as e:  # noqa: BLE001 - one holder must not stop the others
                    errors[name] = str(e)[:200]
                    print(f"[YOLO] {name}: {'load' if enabled else 'unload'} failed: {e}")
            if not enabled:
                self._free_cache()
            out = self._status()
        out["errors"] = errors
        print(f"[YOLO] switched {'on' if enabled else 'off'}: {out['holders']}")
        return out

    def _vram(self):
        try:
            if self.cuda is None or not self.cuda.is_available():
                return None
            free, total = self.cuda.mem_get_info()
            return {"used_mb": int((total - free) / 2**20), "total_mb": int(total / 2**20)}
        except Exception:  # noqa: BLE001
            return None

    def _status(self):
        holders = {}
        for name, holder in self.holders.items():
            try:
                holders[name] = bool(holder.models_loaded())
            except Exception:  # noqa: BLE001
                holders[name] = False
        return {"enabled": self.enabled, "changed_at": self.changed_at, "holders": holders, "vram": self._vram()}

    def status(self):
        return self._status()
```

- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest -q tests/test_yolo_switch.py`. Expect 6 passed. Then run the full suite and expect 288 passed.
- [ ] **Step 5: Commit** `feat(vision): YOLO switch with saved state and model holders`.

---

### Task 2: Vehicle detector as a holder; callers idle while off

**Files:** Modify `backend/vision/yolo_detector.py`, `backend/vision/count_workers.py`, `backend/vision/survey.py`; Test `tests/test_yolo_holders.py`

**Interfaces:**
- Consumes `YoloOff` (Task 1).
- Produces:
  - `VehicleDetectorYOLO11x(..., load_models=True)`
  - `.load_models()`, `.unload_models()`, `.models_loaded()`
  - `infer()` / `detect_boxes()` raise `YoloOff` when unloaded

Changes:
1. In `__init__`, keep `self.model_path = model_path`. Move the block from `self.model = YOLO(model_path)` through the warm-up into `load_models()`. That is: YOLO load, `.to('cuda').half()` when CUDA is available, and the dummy warm-up. Create `self.model_lock` before it, and set `self.model = None` first. Call `self.load_models()` only when `load_models` is true. Keep `model_name` computed from the path as today.
2. `load_models()`: if a model is already loaded, return. Otherwise build it outside the lock, then assign it under `self.model_lock`.
3. `unload_models()`: under `self.model_lock`, set `self.model = None`.
4. `models_loaded()`: return `self.model is not None`.
5. `infer()`: inside each `with self.model_lock:` block, read `model = self.model`. If it is `None`, raise `YoloOff("YOLO ปิดอยู่")`. Use `model(...)` inside the block. The tiled branch also uses `model.names` (read it inside the lock) in place of `self.model.names`.
6. `_process_loop` (live camera): wrap the per-frame inference path in `except YoloOff:`. That sets `self.latest_stats.update(active=False, stream_error='yolo_off')` under `self.lock`, then `stop_event.wait(2.0)` and `continue`. Find where `self.infer(` or `self.detect_boxes(` is called in the loop.
7. `count_workers.py`: around `result = self.detector.infer(frame)`, add `except YoloOff:`. That sets `status.update(active=False, error='YOLO ปิดอยู่')`, then `stop.wait(10.0)` and `continue`. No count is recorded.
8. `survey.py`: around `result = self.detector.infer(frame)`, add `except YoloOff:` that `return`s from the sample without saving it. Read the surrounding function: it must not record a sample with 0 vehicles.

- [ ] **Step 1: Tests** (`tests/test_yolo_holders.py`; this file grows in Task 3)

```python
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
```

Adjust the fake's result shape only if `infer()` needs more attributes. Read `infer()` first; the untiled path indexes `[0]` and then reads `result.boxes`.

- [ ] **Step 2: Run them** and expect failures: `TypeError: unexpected keyword 'load_models'` / missing methods.
- [ ] **Step 3: Implement** changes 1-8.
- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest -q tests/test_yolo_holders.py`, then the full suite. Expect 292 passed.
- [ ] **Step 5: Commit** `feat(vision): vehicle detector unloads on the YOLO switch; counters idle while off`.

---

### Task 3: Helmet, wrong-way and violation models as holders

**Files:** Modify `backend/vision/helmet_service.py` (`HelmetPatrol`), `backend/vision/wrongway_service.py` (`WrongWayPatrol`), `backend/vision/violation_service.py` (`ViolationMonitor`); Test `tests/test_yolo_holders.py` (append)

**Interfaces:** Each class gets the constructor kwarg `load_models=True` and the methods `load_models()`, `unload_models()`, `models_loaded()`.

For each class, move the existing model-loading block from `__init__` into `load_models()` unchanged. The blocks are:
- `HelmetPatrol`: `local_det`
- `WrongWayPatrol`: `cls`, falling back to `det` + `det_names`
- `ViolationMonitor`: `helmet_cls`

In `__init__`, set the attributes to `None` and create the lock first, then call `load_models()` only when the kwarg is true.
- `unload_models()` sets the model attributes to `None` under the existing model lock (`_det_lock` / `_det_lock` / `_cls_lock`).
- `models_loaded()` returns whether any of that class's model attributes is not `None`.
- Every place that runs a model must read the attribute once into a local under its lock and handle `None`. Helmet `local_det` at line ~286 already returns early when it is `None`. Check the wrong-way `cls`/`det` uses (~316, ~327) and violation `helmet_cls` (~429), and add the `None` guard where one is missing.

- [ ] **Step 1: Tests** (append). Each class's constructor needs a db path and starts daemon threads. Use `tmp_path / "v.db"`. Monkeypatch `ultralytics.YOLO` (the classes do `from ultralytics import YOLO` inside the method) with `FakeYOLO`. Monkeypatch the class module's path constant (`LOCAL_DET_PATH`, `CLS_PATH` / `DET_PATH`, `HELMET_CLS_PATH`) to a file you create in `tmp_path`, so `os.path.exists` is true.

```python
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
    cls = getattr(mod, cls_name)
    off = cls(str(tmp_path / "v.db"), load_models=False)
    assert off.models_loaded() is False
    off.load_models()
    assert off.models_loaded() is True
    off.unload_models()
    assert off.models_loaded() is False
```

If a constructor needs more arguments or touches other directories (e.g. `CACHE_DIR`, `EVIDENCE_DIR`), monkeypatch those module constants into `tmp_path` in the same test. Never write into `instances/`.

- [ ] **Step 2: Run them** and expect failures on the `load_models` kwarg.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the file, then the full suite. Expect 295 passed.
- [ ] **Step 5: Commit** `feat(vision): helmet, wrong-way and violation models follow the YOLO switch`.

---

### Task 4: BMA scanner while YOLO is off

**Files:** Modify `backend/bma/bma_service.py`; Test `tests/test_bma_yolo_off.py`

**Interfaces:**
- Consumes `YoloOff` and `detector.models_loaded()`.
- Produces `get_analytics()["scan_status"]["yolo_enabled"]` as a bool.

Changes:
1. In `_run_scan_cycle`'s `process_camera`, the block starting `# YOLO Inference` calls `self._detect(img)` under `self.infer_lock`. Catch `YoloOff` there. On `YoloOff`, `return` from `process_camera` after the flood observe, which already ran above. Do not call `update_camera_count` and do not run the helmet/wrong-way observe. Snapshots, `note_frame`, `save_raw_frame` and flood keep working.
2. Add `def yolo_enabled(self): return bool(self.detector is None or getattr(self.detector, "models_loaded", lambda: True)())`.
3. `_build_analytics()`: when `not self.yolo_enabled()`, set `online_cams = []`. Reuse the branch the site-down case uses. Add `"yolo_enabled": self.yolo_enabled()` to the returned `scan_status` dict. Read the existing `scan_status` construction and add the key there.

- [ ] **Step 1: Tests.** Build the scanner the way `tests/test_bma_analytics.py` does: `BmaScanner.__new__(BmaScanner)` and set the attributes the method reads. Read that file and reuse its helper if it has one. Test:
  - a) with a detector whose `models_loaded()` is False, `_build_analytics()` gives `scan_status.yolo_enabled is False` and `summary.online_cameras == 0`, even when the db's latest rows are fresh and online;
  - b) with `models_loaded()` True, `yolo_enabled is True`.
  Use a fake `db` object with `get_all_latest()` returning one fresh online camera (`ts=now`, `status="online"`, `total=5`) and `get_history_summary()` returning `[]`. Set `self.source = {"state": "live"}`, `self.cameras = [...]`, and whatever else the method reads, which you will find by reading it.
- [ ] **Step 2: Run them** and expect RED (no `yolo_enabled` key).
- [ ] **Step 3: Implement** 1-3. Change 1 has no unit test, because it sits inside a nested scan closure. Keep it minimal and say so in the report.
- [ ] **Step 4: Run** the file, then the full suite. Expect 297 passed.
- [ ] **Step 5: Commit** `feat(bma): scanner skips counting while YOLO is off and reports it`.

---

### Task 5: Wire the switch into the server; the API

**Files:** Modify `backend/services.py`, `backend/api/live_ai.py`; Test `tests/test_yolo_api.py`

**Interfaces:**
- `services.yolo` is a `YoloSwitch`.
- `GET /api/ai/yolo` returns `yolo.status()`.
- `POST /api/ai/yolo` takes the body `{"enabled": bool}` and returns `yolo.set(enabled)`. It answers 400 when `enabled` is not a bool.

1. `backend/services.py`: before `detector = VehicleDetectorYOLO11x(...)`, add `yolo = YoloSwitch(os.path.join(DATA_DIR, "cache", "yolo_switch.json"))` and the import. Pass `load_models=yolo.enabled` to `VehicleDetectorYOLO11x`, `ViolationMonitor`, `HelmetPatrol` and `WrongWayPatrol`. After `wrongway` is built, register them: `yolo.register("detector", detector)`, `yolo.register("helmet", helmet)`, `yolo.register("wrongway", wrongway)`, `yolo.register("violations", violations)`. If `yolo.enabled` is False at startup, print `[YOLO] off (saved state): no models loaded`.
2. `backend/api/live_ai.py`: add `yolo` to the `from backend.services import ...` line, and add:

```python
@router.get("/api/ai/yolo")
def yolo_status():
    """YOLO on/off (launch\\yolo_switch.bat): saved state, which models are on the GPU, VRAM in use."""
    return yolo.status()


@router.post("/api/ai/yolo")
def yolo_set(payload: dict = Body(...)):
    """Switch every YOLO model on or off (operator only: the access guard keeps /api/ai/ POSTs local)."""
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return JSONResponse(status_code=400, content={"error": "enabled must be true or false"})
    return yolo.set(enabled)
```

- [ ] **Step 1: Tests** (`tests/test_yolo_api.py`). Use the stub-services pattern: copy the module-scoped `services_stub` fixture and `_router_client` helper from `tests/test_api_micro_cache.py`, or import them from there if they import cleanly. Monkeypatch `module.yolo` to a real `YoloSwitch(tmp_path/"s.json", cuda=None)` with one fake holder. Test:
  - GET returns `enabled` True;
  - POST `{"enabled": false}` makes the holder unloaded and GET then shows False;
  - POST `{"enabled": "no"}` answers 400.
  Add a guard test using `backend.core.access_guard` with the `_app()`-style client from `tests/test_access_guard.py`. A POST to a path under `/api/ai/` from the TestClient peer (not trusted) answers 403. If `tests/test_access_guard.py` already covers `/api/ai/set_fps`, note that this covers the new path's prefix and skip the duplicate.
- [ ] **Step 2: RED.** **Step 3: Implement.** **Step 4: Run** the full suite and expect about 300 passed. **Step 5: Commit** `feat(api): YOLO on/off endpoint wired to every model holder`.

---

### Task 6: Dashboard treats the BMA counts as offline while YOLO is off

**Files:** Modify `web/src/lib/trafficSummary.js`, `web/src/components/DashboardPage.jsx`; Test `web/src/lib/trafficSummary.test.js`

- Add `export function bmaCountsLive(scanStatus)` to `trafficSummary.js`. It returns `false` when `scanStatus?.yolo_enabled === false`, else `true`.
- In `DashboardPage.jsx`, build `bmaSummary` with `online: !siteDown && bmaCountsLive(bma?.scan_status)` and `flow_index: (siteDown || !bmaCountsLive(bma?.scan_status)) ? null : ...`. Keep everything else. `pickTrafficSummary` then falls back to Longdo by itself.
- Tests in `trafficSummary.test.js`: `bmaCountsLive({yolo_enabled: false}) === false`, `bmaCountsLive({yolo_enabled: true}) === true`, `bmaCountsLive(undefined) === true` (an older server without the key).
- RED (import fails), then GREEN with `npm test` in `web/`. Check that `npx vite build --outDir <scratch dir>` passes. Do not build into `instances/production`.
- Commit `feat(web): dashboard uses Longdo while YOLO is off`.

---

### Task 7: The console switch and the Desktop icon

**Files:** Create `launch/yolo_switch.py`, `launch/yolo_switch.bat`; Test `tests/test_yolo_switch_cli.py`

`launch/yolo_switch.py` (stdlib only):

```python
"""
YOLO on/off from the Desktop ("BKK YOLO On-Off" -> launch\\yolo_switch.bat).

Shows whether YOLO is on and how much GPU memory is in use, asks, then switches every YOLO model on or
off through the server's /api/ai/yolo (operator only: it answers this machine). The server keeps the
state across restarts.
Usage: yolo_switch.py [port] [--on | --off]   (no flag: ask)
"""
import json
import sys
import urllib.error
import urllib.request


def call(port, method="GET", body=None, timeout=120):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/ai/yolo", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def describe(st):
    state = "เปิด" if st.get("enabled") else "ปิด"
    vram = st.get("vram")
    mem = f" · GPU ใช้ {vram['used_mb'] / 1024:.1f} จาก {vram['total_mb'] / 1024:.1f} GB" if vram else ""
    loaded = [n for n, on in (st.get("holders") or {}).items() if on]
    return f"YOLO ตอนนี้: {state}{mem}" + (f"\nโมเดลที่อยู่บน GPU: {', '.join(loaded)}" if loaded else "")


def main(argv, ask=input):
    port = next((a for a in argv if a.isdigit()), "8000")
    try:
        st = call(port)
    except (urllib.error.URLError, OSError) as e:
        print(f"ต่อเซิร์ฟเวอร์ที่พอร์ต {port} ไม่ได้: {e}")
        return 1
    print(describe(st))
    if "--on" in argv or "--off" in argv:
        want = "--on" in argv
    else:
        want = not st.get("enabled")
        answer = ask(f"{'เปิด' if want else 'ปิด'} YOLO ไหม? (Y/N) ").strip().lower()
        if answer not in ("y", "yes", "ใช่"):
            print("ไม่เปลี่ยน")
            return 0
    print("กำลังเปิด YOLO (โหลดโมเดลราว 10-30 วินาที)..." if want else "กำลังปิด YOLO และคืน GPU...")
    out = call(port, "POST", {"enabled": want})
    print(describe(out))
    for name, err in (out.get("errors") or {}).items():
        print(f"  {name}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

`launch/yolo_switch.bat` follows `launch/yolo_status.bat`. It sets `chcp 65001`, `cd /d "%~dp0.."`, `title BKK StreetSmart - YOLO On-Off`, picks `.venv\Scripts\python.exe`, sets `PYTHONIOENCODING=utf-8`, runs `"%PY%" launch\yolo_switch.py %*`, then calls `pause` so the window stays open to read the result.

- [ ] **Step 1: Tests** (`tests/test_yolo_switch_cli.py`). Load the script with `importlib.util.spec_from_file_location("yolo_switch_cli", "launch/yolo_switch.py")` and monkeypatch its `call`. Test:
  - when the state is on and the user answers "y", it POSTs `{"enabled": False}`;
  - answering "n" makes no POST;
  - `--on` POSTs True without asking;
  - with the server down (`call` raises `urllib.error.URLError`), it returns 1;
  - `describe()` shows `ปิด` and `GPU ใช้ 3.7 จาก 10.0 GB` for `{"enabled": False, "vram": {"used_mb": 3789, "total_mb": 10240}, "holders": {}}`.
- [ ] **Step 2: RED. Step 3: Implement. Step 4: Run** the full suite. **Step 5: Commit** `feat(launch): YOLO on/off console switch`.

---

### Task 8 (controller, production): deploy and the Desktop icon

1. Restart production (`launch\production\restart.bat` in a new window). Wait for a new PID on :8000, for `/` to answer 200 and for the traffic summary to be ready.
2. Run `nvidia-smi --query-gpu=memory.used --format=csv,noheader` and record the figure. Run `launch\yolo_switch.bat 8000 --off`, then `nvidia-smi` again. VRAM must drop. Expect ~2-3 GB less.
3. Check the dashboard (Longdo fallback) and that `/api/bma/analytics` `scan_status.yolo_enabled` is false.
4. Restart production again. The startup log says `[YOLO] off (saved state)` and `nvidia-smi` stays low.
5. Run `launch\yolo_switch.bat 8000 --on`. VRAM goes back up, `/api/ai/yolo` holders are all true, and BMA counts resume within one scan cycle.
6. Create the Desktop shortcut "BKK YOLO On-Off.lnk". Its target is `E:\new_ccty_bangkok\launch\yolo_switch.bat`, working dir `E:\new_ccty_bangkok`, icon `%SystemRoot%\System32\shell32.dll,27`. Use PowerShell `WScript.Shell` `CreateShortcut`, in the same style as the existing `BKK YOLO Status.lnk`.
