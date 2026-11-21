"""Pure-function tests for device/pcstats/pcstats.py (the Windows PC stats service for the desk display)."""
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parents[1] / "device" / "pcstats" / "pcstats.py"
_spec = importlib.util.spec_from_file_location("pcstats", _PATH)
pcstats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pcstats)

cpu_percent = pcstats.cpu_percent
parse_nvidia_smi = pcstats.parse_nvidia_smi
build_stats = pcstats.build_stats
read_gpu = pcstats.read_gpu
Sampler = pcstats.Sampler


def test_cpu_percent_basic():
    assert cpu_percent((800, 1000), (850, 1100)) == 50.0


def test_cpu_percent_counter_reset():
    # PC rebooted: counters restart lower than the previous sample.
    assert cpu_percent((800, 1000), (10, 20)) == 0.0


def test_parse_nvidia_smi():
    assert parse_nvidia_smi("8789, 10240, 55\n") == (8789, 10240, 55.0)


def test_parse_nvidia_smi_first_gpu_only():
    assert parse_nvidia_smi("100, 200, 40\n300, 400, 50\n") == (100, 200, 40.0)


def test_parse_nvidia_smi_bad():
    assert parse_nvidia_smi("") is None
    assert parse_nvidia_smi("[N/A], 10240, 55") is None
    assert parse_nvidia_smi("garbage") is None


def test_build_stats_full():
    stats = build_stats(12.5, (13420, 32684), (8789, 10240, 55.0), 99)
    assert stats == {
        "cpu": 12.5,
        "ram": round(100 * 13420 / 32684, 1),
        "ram_used_mb": 13420,
        "ram_total_mb": 32684,
        "vram": 85.8,
        "vram_used_mb": 8789,
        "vram_total_mb": 10240,
        "temp_c": 55.0,
        "uptime_s": 99,
    }


def test_build_stats_no_gpu():
    stats = build_stats(12.5, (13420, 32684), None, 99)
    assert stats["vram"] is None
    assert stats["vram_used_mb"] == 0
    assert stats["vram_total_mb"] == 0
    assert stats["temp_c"] is None
    assert stats["cpu"] == 12.5
    assert stats["ram"] == round(100 * 13420 / 32684, 1)


def test_sample_survives_gpu_failure():
    cpu_reads = iter([(800, 1000), (850, 1100)])
    sampler = Sampler(
        read_cpu=lambda: next(cpu_reads),
        read_mem=lambda: (1000, 4000),
        read_gpu=lambda: None,
        clock=lambda: 1.0,
        uptime=lambda: 5,
    )
    sampler.sample()
    stats, _ts = sampler.latest()
    assert stats["cpu"] == 50.0
    assert stats["ram"] == 25.0
    assert stats["vram"] is None


def test_gpu_query_hides_console():
    seen = {}

    def fake(cmd, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="1, 2, 3\n")

    assert read_gpu(run=fake) == "1, 2, 3\n"
    assert seen["creationflags"] == pcstats.CREATE_NO_WINDOW
    if sys.platform == "win32":
        assert pcstats.CREATE_NO_WINDOW == subprocess.CREATE_NO_WINDOW
    assert seen["timeout"] == 3


def test_gpu_query_timeout():
    def fake(cmd, **kwargs):
        raise subprocess.TimeoutExpired("nvidia-smi", 3)

    assert read_gpu(run=fake) is None


def test_gpu_query_nonzero_exit():
    def fake(cmd, **kwargs):
        return SimpleNamespace(returncode=9, stdout="")

    assert read_gpu(run=fake) is None


@pytest.mark.skipif(sys.platform != "win32", reason="reads Windows system calls")
def test_win32_readers_smoke():
    assert pcstats.read_memory()[1] > 0
    assert pcstats.read_cpu_times()[1] > 0
    assert pcstats._uptime_s() >= 0


def test_is_fresh_recent_sample():
    assert pcstats.is_fresh(100.0, 104.9) is True


def test_is_fresh_old_sample():
    assert pcstats.is_fresh(100.0, 105.1) is False
