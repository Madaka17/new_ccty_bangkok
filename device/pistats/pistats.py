#!/usr/bin/env python3
"""Pi stats service for the SmallTV desk display.

Samples CPU, RAM, temperature and uptime once per second and serves the latest
values as JSON at GET /stats. Stdlib only, so it runs on the Pi system Python.

The Pi 4 has no power sensor: "watts" is an estimate from CPU load
(idle about 2.7 W, about 6.4 W at full load, plus about 1.0 W for the USB SSD).
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IDLE_W = 2.7
LOAD_W = 3.7
SSD_W = 1.0
MAX_AGE_S = 5.0


def parse_proc_stat(text: str) -> tuple[int, int]:
    """Return (idle, total) jiffies from the aggregate 'cpu ' line; idle includes iowait.

    Only the first 8 fields count: guest and guest_nice are already inside user and nice."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            values = [int(v) for v in line.split()[1:9]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return idle, sum(values)
    raise ValueError("no aggregate cpu line")


def cpu_percent(prev: tuple[int, int], cur: tuple[int, int]) -> float:
    """Busy percent between two samples, clamped to 0..100; 0 when counters did not advance."""
    d_total = cur[1] - prev[1]
    d_idle = cur[0] - prev[0]
    if d_total <= 0:
        return 0.0
    busy = 100.0 * (d_total - d_idle) / d_total
    return round(min(100.0, max(0.0, busy)), 1)


def parse_meminfo(text: str) -> tuple[int, int]:
    """Return (used_mb, total_mb) where used = MemTotal - MemAvailable."""
    kb = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if rest:
            kb[name.strip()] = int(rest.split()[0])
    total = kb["MemTotal"]
    used = total - kb["MemAvailable"]
    return used // 1024, total // 1024


def estimate_watts(cpu: float) -> float:
    cpu = min(100.0, max(0.0, cpu))
    return round(IDLE_W + LOAD_W * cpu / 100.0 + SSD_W, 1)


def is_fresh(sample_ts: float | None, now: float) -> bool:
    """True when a sample exists and is at most MAX_AGE_S old (monotonic seconds)."""
    return sample_ts is not None and now - sample_ts <= MAX_AGE_S


def _read(path: str) -> str:
    with open(path, encoding="ascii") as f:
        return f.read()


class Sampler:
    """Background thread that keeps the latest stats dict."""

    def __init__(self, read=None, clock=time.monotonic) -> None:
        self._read = read or _read
        self._clock = clock
        self._lock = threading.Lock()
        self._latest: dict = {}
        self._ts: float | None = None
        self._prev = parse_proc_stat(self._read("/proc/stat"))

    def sample(self) -> None:
        cur = parse_proc_stat(self._read("/proc/stat"))
        cpu = cpu_percent(self._prev, cur)
        self._prev = cur
        used_mb, total_mb = parse_meminfo(self._read("/proc/meminfo"))
        try:
            temp_c = round(int(self._read("/sys/class/thermal/thermal_zone0/temp")) / 1000.0, 1)
        except (OSError, ValueError):
            temp_c = None  # no sensor reading: the screen shows "--", never a fake 0
        uptime_s = int(float(self._read("/proc/uptime").split()[0]))
        stats = {
            "cpu": cpu,
            "ram": round(100.0 * used_mb / total_mb, 1) if total_mb else 0.0,
            "ram_used_mb": used_mb,
            "ram_total_mb": total_mb,
            "temp_c": temp_c,
            "watts": estimate_watts(cpu),
            "watts_est": True,
            "uptime_s": uptime_s,
        }
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
                print(f"[pistats] sample failed: {exc}", flush=True)


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

        def log_message(self, *args) -> None:  # one request every 2 s; keep the journal quiet
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
    print(f"[pistats] serving /stats on :{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
