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
