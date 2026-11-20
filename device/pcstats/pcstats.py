#!/usr/bin/env python3
"""PC stats service for the SmallTV desk display (Windows).

Samples CPU, RAM, GPU memory, GPU temperature and uptime once per second and
serves the latest values as JSON at GET /stats. Stdlib only: Windows system
calls go through ctypes, and the GPU numbers come from nvidia-smi.

Runs under pythonw, so every subprocess is started with no console window.
If nvidia-smi fails, the GPU keys go null or zero and the other keys still work.
"""
import argparse
import ctypes
import json
import subprocess
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_AGE_S = 5.0
MB = 1024 * 1024
NVIDIA_SMI_CMD = [
    "nvidia-smi",
    "--query-gpu=memory.used,memory.total,temperature.gpu",
    "--format=csv,noheader,nounits",
]


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


def _filetime_to_int(ft: FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def cpu_percent(prev: tuple[int, int], cur: tuple[int, int]) -> float:
    """Busy percent between two samples, clamped to 0..100; 0 when counters did not advance."""
    d_total = cur[1] - prev[1]
    d_idle = cur[0] - prev[0]
    if d_total <= 0:
        return 0.0
    busy = 100.0 * (d_total - d_idle) / d_total
    return round(min(100.0, max(0.0, busy)), 1)


def parse_nvidia_smi(text: str) -> tuple[int, int, float] | None:
    """Return (used_mb, total_mb, temp_c) from the first GPU line, or None if it cannot be read."""
    lines = text.splitlines()
    if not lines:
        return None
    parts = [p.strip() for p in lines[0].split(",")]
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), float(parts[2])
    except ValueError:  # for example "[N/A]" when the GPU does not report a value
        return None


def build_stats(
    cpu: float,
    ram: tuple[int, int],
    gpu: tuple[int, int, float] | None,
    uptime_s: int,
) -> dict:
    """Assemble the JSON the display reads. A missing GPU gives null VRAM and temperature, never a fake 0."""
    ram_used_mb, ram_total_mb = ram
    if gpu is None:
        vram, vram_used_mb, vram_total_mb, temp_c = None, 0, 0, None
    else:
        vram_used_mb, vram_total_mb, temp_c = gpu
        vram = round(100.0 * vram_used_mb / vram_total_mb, 1) if vram_total_mb else 0.0
    return {
        "cpu": round(cpu, 1),
        "ram": round(100.0 * ram_used_mb / ram_total_mb, 1) if ram_total_mb else 0.0,
        "ram_used_mb": ram_used_mb,
        "ram_total_mb": ram_total_mb,
        "vram": vram,
        "vram_used_mb": vram_used_mb,
        "vram_total_mb": vram_total_mb,
        "temp_c": temp_c,
        "uptime_s": uptime_s,
    }


def read_cpu_times() -> tuple[int, int]:
    """Return (idle, total) from Windows. Kernel time already includes idle, so total is kernel + user."""
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        raise OSError("GetSystemTimes failed")
    return _filetime_to_int(idle), _filetime_to_int(kernel) + _filetime_to_int(user)


def read_memory() -> tuple[int, int]:
    """Return (used_mb, total_mb) of physical RAM."""
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)  # Windows needs this set before the call
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    used = status.ullTotalPhys - status.ullAvailPhys
    return used // MB, status.ullTotalPhys // MB


def read_gpu(run=subprocess.run) -> str | None:
    """Ask nvidia-smi for GPU memory and temperature. Return its text, or None if it fails or times out."""
    try:
        result = run(
            NVIDIA_SMI_CMD,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,  # no console flash under pythonw
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _uptime_s() -> int:
    get_tick = ctypes.windll.kernel32.GetTickCount64
    get_tick.restype = ctypes.c_uint64  # it returns a 64-bit value; the default 32-bit int wraps after about 24.8 days
    return get_tick() // 1000


def is_fresh(sample_ts: float | None, now: float) -> bool:
    """True when a sample exists and is at most MAX_AGE_S old (monotonic seconds)."""
    return sample_ts is not None and now - sample_ts <= MAX_AGE_S


class Sampler:
    """Background thread that keeps the latest stats dict."""

    def __init__(
        self,
        read_cpu=read_cpu_times,
        read_mem=read_memory,
        read_gpu=read_gpu,
        clock=time.monotonic,
        uptime=_uptime_s,
    ) -> None:
        self._read_cpu = read_cpu
        self._read_mem = read_mem
        self._read_gpu = read_gpu
        self._clock = clock
        self._uptime = uptime
        self._lock = threading.Lock()
        self._latest: dict = {}
        self._ts: float | None = None
        self._prev = self._read_cpu()

    def sample(self) -> None:
        cur = self._read_cpu()
        cpu = cpu_percent(self._prev, cur)
        self._prev = cur
        ram = self._read_mem()
        gpu_text = self._read_gpu()
        gpu = parse_nvidia_smi(gpu_text) if gpu_text is not None else None
        stats = build_stats(cpu, ram, gpu, self._uptime())
        with self._lock:
            self._latest = stats
            self._ts = self._clock()

    def latest(self) -> tuple[dict, float | None]:
        """Return (stats, monotonic time of that sample, or None before the first one)."""
        with self._lock:
            return dict(self._latest), self._ts

    def run(self) -> None:
        while True:
            time.sleep(1.0)
            try:
                self.sample()
            except Exception as exc:  # keep serving the last good values
                print(f"[pcstats] sample failed: {exc}", flush=True)


def make_handler(sampler: Sampler):
    class Handler(BaseHTTPRequestHandler):
        timeout = 5  # seconds; a client that connects and sends nothing must not hold a thread forever

        def do_GET(self) -> None:
            if self.path.split("?")[0] != "/stats":
                self.send_error(404)
                return
            stats, ts = sampler.latest()
            if not is_fresh(ts, time.monotonic()):
                # Sampler stalled: say so, so the screen greys out instead of showing frozen values.
                self.send_error(503, "stats are stale")
                return
            body = json.dumps(stats).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # one request every 2 s; keep the log quiet
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9101)
    args = parser.parse_args()
    sampler = Sampler()
    time.sleep(1.0)
    sampler.sample()
    threading.Thread(target=sampler.run, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(sampler))
    print(f"[pcstats] serving /stats on :{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
