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
import subprocess
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


_gpu_cache = {"at": None, "value": None}
_GPU_CACHE_S = 5.0


def _forget_gpu_memory():
    _gpu_cache["at"] = None   # a flip changes VRAM at once; the 5 s cache would report the old figure


def gpu_memory(cuda=_default_cuda, run=subprocess.run, now=time.monotonic):
    """{"used_mb", "total_mb"} or None. Never creates a CUDA context: with no context yet it asks
    nvidia-smi. Cached for 5 s so a public poll loop cannot spawn a process per request."""
    t = now()
    if _gpu_cache["at"] is not None and t - _gpu_cache["at"] < _GPU_CACHE_S:
        return _gpu_cache["value"]
    value = None
    try:
        c = cuda() if cuda is _default_cuda else cuda
        if c is not None and getattr(c, "is_initialized", lambda: False)():
            free, total = c.mem_get_info()
            value = {"used_mb": int((total - free) / 2**20), "total_mb": int(total / 2**20)}
        else:
            kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
            r = run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                    timeout=3, capture_output=True, text=True, **kw)
            used, total = r.stdout.splitlines()[0].split(",")
            value = {"used_mb": int(used.strip()), "total_mb": int(total.strip())}
    except Exception:  # noqa: BLE001 - no GPU / no nvidia-smi: no figures
        value = None
    _gpu_cache["at"], _gpu_cache["value"] = t, value
    return value


class YoloSwitch:
    def __init__(self, state_path, cuda=_default_cuda):
        self.state_path = state_path
        self._real_cuda = cuda is _default_cuda
        self.cuda = cuda() if callable(cuda) and cuda is _default_cuda else cuda
        self.lock = threading.Lock()     # one flip at a time
        self.holders = {}                # name -> holder, in registration order
        self.enabled, self.changed_at = True, 0
        try:
            with open(state_path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.enabled = bool(saved.get("enabled", True))
                self.changed_at = int(saved.get("changed_at") or 0)
        except (OSError, ValueError, TypeError):
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
            _forget_gpu_memory()
            out = self._status()
        out["errors"] = errors
        print(f"[YOLO] switched {'on' if enabled else 'off'}: {out['holders']}")
        return out

    def _vram(self):
        if self._real_cuda:
            return gpu_memory()
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
