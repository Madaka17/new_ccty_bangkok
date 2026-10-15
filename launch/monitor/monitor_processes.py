r"""
BKK Monitor: whether each hidden server runs, from launch\logs\<name>.json (written by launch\run_hidden.py),
and the tail of its log launch\logs\<name>.log. The collector never reads these; only the monitor window does.

Liveness uses OpenProcess + GetExitCodeProcess, never os.kill (on Windows os.kill(pid, 0) terminates the process).
"""
import ctypes
import json
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NAMES = ("production", "test", "enviro", "camera")
LABELS = {"production": "Production", "test": "Test", "enviro": "ENVIRO", "camera": "Camera status"}
LOG_DIR = ROOT / "launch" / "logs"

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)
STILL_ACTIVE = 259


def alive(pid):
    if not pid or not isinstance(pid, int) or pid < 0 or pid > 0xFFFFFFFF:
        return False
    h = _k32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        _k32.CloseHandle(h)


def _dir(log_dir):
    # resolved at call time so a test can point LOG_DIR somewhere else
    return LOG_DIR if log_dir is None else Path(log_dir)


def _state(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):   # missing, or read while run_hidden is rewriting it
        return None
    return data if isinstance(data, dict) else None


def info(name, log_dir=None, alive=alive, now=time.time):
    d = _dir(log_dir)
    log = d / f"{name}.log"
    try:
        log_size = log.stat().st_size
    except OSError:
        log_size = 0
    st = _state(d / f"{name}.json") or {}
    started = st.get("started_at")
    running = bool(st) and "exited_at" not in st and alive(st.get("runner_pid")) and alive(st.get("child_pid"))
    return {"name": name, "label": LABELS.get(name, name), "running": running,
            "pid": st.get("child_pid"), "started_at": started,
            "uptime_s": int(now() - started) if running and started is not None else None,
            "exit_code": st.get("exit_code"), "exited_at": st.get("exited_at"),
            "log": str(log), "log_size": log_size}


def tail(name, offset=None, log_dir=None, first_bytes=65536, max_bytes=262144):
    """offset None: the last first_bytes. Otherwise the bytes after offset (at most max_bytes), whole lines only.
    A file shorter than offset was rotated: read from 0 and say so with reset."""
    path = _dir(log_dir) / f"{name}.log"
    try:
        size = path.stat().st_size
    except OSError:
        return {"lines": [], "offset": 0, "reset": offset is not None and offset > 0}
    reset = False
    if offset is None:
        start, n = max(0, size - first_bytes), first_bytes
    elif offset > size:
        start, n, reset = 0, min(size, max_bytes), True
    else:
        start, n = offset, min(size - offset, max_bytes)
    with open(path, "rb") as f:
        f.seek(start)
        buf = f.read(n)
    base = start
    if offset is None and start > 0:              # cut in the middle of a line: drop the partial head
        nl = buf.find(b"\n")
        if nl < 0:
            return {"lines": [], "offset": size, "reset": reset}
        base, buf = base + nl + 1, buf[nl + 1:]
    end = buf.rfind(b"\n")
    if end < 0:
        if offset is None or len(buf) < max_bytes:
            return {"lines": [], "offset": base, "reset": reset}
        end = len(buf) - 1                         # one line longer than max_bytes: take it whole
    text = buf[:end + 1].decode("utf-8", "replace")
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return {"lines": [ln.rstrip("\r") for ln in lines], "offset": base + end + 1, "reset": reset}
