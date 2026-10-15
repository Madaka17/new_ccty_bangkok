import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_processes as mp  # noqa: E402


def write_state(d, name, **kw):
    (d / f"{name}.json").write_text(json.dumps({"name": name, "runner_pid": 11, "child_pid": 22,
                                                 "started_at": 1000.0, "command": "x", **kw}), encoding="utf-8")


def test_info_running_and_exited(tmp_path):
    write_state(tmp_path, "production")
    (tmp_path / "production.log").write_bytes(b"a\n")
    i = mp.info("production", log_dir=tmp_path, alive=lambda pid: True, now=lambda: 1060.0)
    assert i["running"] is True and i["pid"] == 22 and i["uptime_s"] == 60 and i["log_size"] == 2
    assert i["label"] == "Production"
    write_state(tmp_path, "test", exited_at=1050.0, exit_code=1)
    j = mp.info("test", log_dir=tmp_path, alive=lambda pid: True, now=lambda: 1060.0)
    assert j["running"] is False and j["exit_code"] == 1 and j["uptime_s"] is None


def test_info_dead_pid_or_missing(tmp_path):
    write_state(tmp_path, "enviro")
    assert mp.info("enviro", log_dir=tmp_path, alive=lambda pid: pid != 22)["running"] is False
    k = mp.info("camera", log_dir=tmp_path)
    assert k["running"] is False and k["pid"] is None and k["log_size"] == 0


def test_alive_real_and_bogus():
    import os
    assert mp.alive(os.getpid()) is True
    assert mp.alive(0) is False and mp.alive(None) is False
    assert mp.alive(2**31 - 7) is False


def test_tail_first_then_incremental(tmp_path):
    p = tmp_path / "production.log"
    p.write_bytes(b"one\ntwo\nthr")
    t = mp.tail("production", log_dir=tmp_path)
    assert t["lines"] == ["one", "two"] and t["offset"] == 8 and t["reset"] is False
    with open(p, "ab") as f:
        f.write(b"ee\nfour\n")
    t2 = mp.tail("production", t["offset"], log_dir=tmp_path)
    assert t2["lines"] == ["three", "four"] and t2["offset"] == p.stat().st_size


def test_tail_first_drops_partial_head(tmp_path):
    (tmp_path / "test.log").write_bytes(b"x" * 100 + b"\nkeep\n")
    assert mp.tail("test", log_dir=tmp_path, first_bytes=10)["lines"] == ["keep"]


def test_tail_coerces_page_offset(tmp_path):
    body = b"x" * 100 + b"\nkeep\n"
    (tmp_path / "test.log").write_bytes(body)
    # a value that cannot convert means the first read: last 10 bytes, partial head dropped
    assert mp.tail("test", "abc", log_dir=tmp_path, first_bytes=10)["lines"] == ["keep"]
    assert mp.tail("test", None, log_dir=tmp_path, first_bytes=10)["lines"] == ["keep"]
    # a negative value is clamped to 0: read from the start
    assert mp.tail("test", -5, log_dir=tmp_path, first_bytes=10)["lines"] == ["x" * 100, "keep"]


def test_tail_rotated_and_missing(tmp_path):
    (tmp_path / "enviro.log").write_bytes(b"new\n")
    t = mp.tail("enviro", 5000, log_dir=tmp_path)
    assert t["reset"] is True and t["lines"] == ["new"]
    assert mp.tail("camera", None, log_dir=tmp_path) == {"lines": [], "offset": 0, "reset": False}
    assert mp.tail("camera", 40, log_dir=tmp_path)["reset"] is True


def test_stopped_on_purpose_marker_per_port(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "stopped_8001").write_text("", encoding="utf-8")
    assert mp.info("test", log_dir=tmp_path, state_dir=state)["stopped_on_purpose"] is True
    assert mp.info("production", log_dir=tmp_path, state_dir=state)["stopped_on_purpose"] is False
    assert mp.info("enviro", log_dir=tmp_path, state_dir=state)["stopped_on_purpose"] is False
    (state / "stopped_8000").write_text("", encoding="utf-8")
    assert mp.info("production", log_dir=tmp_path, state_dir=state)["stopped_on_purpose"] is True
    assert mp.info("camera", log_dir=tmp_path, state_dir=state)["stopped_on_purpose"] is True
    (state / "stopped_5050").write_text("", encoding="utf-8")
    assert mp.info("enviro", log_dir=tmp_path, state_dir=state)["stopped_on_purpose"] is True
