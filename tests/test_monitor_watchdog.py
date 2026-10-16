import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_watchdog as mw  # noqa: E402


def test_parse_lines():
    a = mw.parse("2026-10-09 17:46:13 production :8000 down: running launch\\production\\restart.bat")
    assert a["target"] == "production" and a["new"] == "restart"
    assert a["ts"] == datetime(2026, 10, 9, 17, 46, 13).timestamp()
    b = mw.parse("2026-10-15 00:08:54 enviro :5050 did not answer (check 1 of 2)")
    assert b["target"] == "enviro" and b["new"] == "warn" and "did not answer" in b["detail"]
    assert mw.parse("garbage") is None
    assert mw.parse("") is None


def test_read_new_incremental(tmp_path):
    p = tmp_path / "watchdog.log"
    p.write_bytes(b"line1\nline2\npart")
    lines, off = mw.read_new(p, 0)
    assert lines == ["line1", "line2"] and off == len(b"line1\nline2\n")
    with open(p, "ab") as f:
        f.write(b"ial\n")
    lines, off2 = mw.read_new(p, off)
    assert lines == ["partial"]
    assert mw.read_new(p, off2) == ([], off2)


def test_read_new_after_shrink(tmp_path):
    p = tmp_path / "watchdog.log"
    p.write_bytes(b"new\n")
    lines, off = mw.read_new(p, 9999)
    assert lines == ["new"] and off == 4


def test_read_missing_file(tmp_path):
    assert mw.read_new(tmp_path / "nope.log", 5) == ([], 0)
