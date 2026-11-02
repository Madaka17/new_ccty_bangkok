"""Pure-function tests for device/pistats/pistats.py (the Pi stats service for the desk display)."""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "device" / "pistats" / "pistats.py"
_spec = importlib.util.spec_from_file_location("pistats", _PATH)
pistats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pistats)

parse_proc_stat = pistats.parse_proc_stat
cpu_percent = pistats.cpu_percent
parse_meminfo = pistats.parse_meminfo
estimate_watts = pistats.estimate_watts

STAT = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3 4 5 6 7 8 9 10\n"
MEM = "MemTotal:        8000000 kB\nMemFree:  100 kB\nMemAvailable:    6000000 kB\n"


def test_parse_proc_stat():
    assert parse_proc_stat(STAT) == (800, 1000)


def test_cpu_percent_basic():
    assert cpu_percent((800, 1000), (850, 1100)) == 50.0


def test_cpu_percent_counter_reset():
    # Pi rebooted: counters restart lower than the previous sample.
    assert cpu_percent((800, 1000), (10, 20)) == 0.0


def test_cpu_percent_no_change():
    assert cpu_percent((800, 1000), (800, 1000)) == 0.0


def test_parse_meminfo():
    assert parse_meminfo(MEM) == (1953, 7812)


def test_estimate_watts_idle():
    assert estimate_watts(0) == 3.7


def test_estimate_watts_full():
    assert estimate_watts(100) == 7.4


def test_estimate_watts_clamps():
    assert estimate_watts(250) == 7.4


def test_is_fresh_recent_sample():
    assert pistats.is_fresh(100.0, 104.9) is True


def test_is_fresh_old_sample():
    # Sampler thread stalled: the screen must not show frozen numbers as live.
    assert pistats.is_fresh(100.0, 105.1) is False


def test_is_fresh_never_sampled():
    assert pistats.is_fresh(None, 1.0) is False


def test_parse_proc_stat_ignores_guest_time():
    # guest and guest_nice are already counted inside user and nice; adding them again inflates total.
    stat = "cpu  100 0 100 700 100 0 0 0 50 25\n"
    assert parse_proc_stat(stat) == (800, 1000)


class FakeProc:
    def __init__(self, temp="48200\n"):
        self.stat = "cpu  100 0 100 700 100 0 0 0 0 0\n"
        self.temp = temp

    def __call__(self, path):
        if path == "/proc/stat":
            return self.stat
        if path == "/proc/meminfo":
            return MEM
        if path == "/proc/uptime":
            return "123.45 456.78\n"
        if path.endswith("thermal_zone0/temp"):
            if self.temp is None:
                raise OSError("no sensor")
            return self.temp
        raise AssertionError(path)


def test_sampler_sample_builds_stats():
    proc = FakeProc()
    sampler = pistats.Sampler(read=proc, clock=lambda: 50.0)
    proc.stat = "cpu  150 0 150 750 100 0 0 0 0 0\n"   # +100 busy, +50 idle
    sampler.sample()
    stats, ts = sampler.latest()
    assert ts == 50.0
    assert stats["cpu"] == 66.7
    assert stats["ram_used_mb"] == 1953 and stats["ram_total_mb"] == 7812
    assert stats["temp_c"] == 48.2
    assert stats["uptime_s"] == 123
    assert stats["watts"] == estimate_watts(66.7)


def test_sampler_temp_unreadable_is_null_not_zero():
    sampler = pistats.Sampler(read=FakeProc(temp=None), clock=lambda: 1.0)
    sampler.sample()
    assert sampler.latest()[0]["temp_c"] is None


class StubSampler:
    def __init__(self, ts):
        self.ts = ts

    def latest(self):
        return {"cpu": 1.0}, self.ts


def _serve(sampler):
    import threading
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", 0), pistats.make_handler(sampler))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _get(server, path):
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}{path}", timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def test_stats_handler_serves_fresh_json():
    import json
    import time
    server = _serve(StubSampler(time.monotonic()))
    try:
        code, body = _get(server, "/stats")
        assert code == 200 and json.loads(body) == {"cpu": 1.0}
    finally:
        server.shutdown()


def test_stats_handler_503_when_stale():
    import time
    server = _serve(StubSampler(time.monotonic() - 60))
    try:
        assert _get(server, "/stats")[0] == 503
    finally:
        server.shutdown()


def test_stats_handler_404_elsewhere():
    import time
    server = _serve(StubSampler(time.monotonic()))
    try:
        assert _get(server, "/")[0] == 404
    finally:
        server.shutdown()


def test_handler_has_socket_timeout():
    # A client that connects and sends nothing must not hold a thread forever.
    assert pistats.make_handler(StubSampler(None)).timeout == 5
