"""launch/test/pi_frames_sync.py: the tar stream from the Pi lands as atomic, dated, safely named files."""
import pytest

# The script runs on the Windows PC only (msvcrt file lock); CI runs on Linux
pytest.importorskip("msvcrt")

import importlib.util
import io
import os
import tarfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pi_frames_sync", ROOT / "launch" / "test" / "pi_frames_sync.py")
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)


def _tar(members):
    """members: [(name, bytes, mtime)] -> tar bytes."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data, mtime in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = mtime
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeProc:
    """Stands in for the ssh Popen: stdout is the tar stream, wait() returns rc."""

    def __init__(self, stdout=b"", stderr=b"", rc=0):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.rc = rc
        self.returncode = None
        self.killed = False
        self.waited = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self):
        self.waited = True
        self.returncode = self.rc
        return self.rc


def test_safe_name_accepts_plain_camid_jpg_only():
    assert sync.safe_name("1234.jpg")
    assert sync.safe_name("cam-7_b.jpg")
    assert not sync.safe_name("../secret.jpg")
    assert not sync.safe_name("a/b.jpg")
    assert not sync.safe_name("a\\b.jpg")
    assert not sync.safe_name("..jpg")
    assert not sync.safe_name("1234.png")
    assert not sync.safe_name("1234.jpg.tmp")


def test_extract_writes_files_with_the_pi_mtime(tmp_path):
    when = int(time.time()) - 3600
    data = _tar([("100.jpg", b"AAAA", when), ("101.jpg", b"BBBBBB", when + 5)])
    stats = sync.extract(io.BytesIO(data), str(tmp_path))
    assert stats["written"] == 2
    assert (tmp_path / "100.jpg").read_bytes() == b"AAAA"
    assert int(os.path.getmtime(tmp_path / "100.jpg")) == when
    assert int(os.path.getmtime(tmp_path / "101.jpg")) == when + 5


def test_extract_skips_unsafe_names_and_leaves_no_temp_files(tmp_path):
    when = int(time.time())
    data = _tar([("../evil.jpg", b"x", when), ("ok.jpg", b"y", when), ("note.txt", b"z", when)])
    stats = sync.extract(io.BytesIO(data), str(tmp_path))
    assert stats["written"] == 1
    assert sorted(os.listdir(tmp_path)) == ["ok.jpg"]
    assert not (tmp_path.parent / "evil.jpg").exists()


def test_extract_replaces_an_existing_file(tmp_path):
    when = int(time.time())
    (tmp_path / "5.jpg").write_bytes(b"old")
    sync.extract(io.BytesIO(_tar([("5.jpg", b"new!", when)])), str(tmp_path))
    assert (tmp_path / "5.jpg").read_bytes() == b"new!"


def test_extract_reports_the_newest_pi_mtime(tmp_path):
    data = _tar([("1.jpg", b"a", 1_700_000_100), ("2.jpg", b"b", 1_700_000_900), ("3.jpg", b"c", 1_700_000_500)])
    stats = sync.extract(io.BytesIO(data), str(tmp_path))
    assert stats["newest"] == 1_700_000_900


def test_a_file_held_by_the_server_is_retried_three_times_then_skipped(tmp_path, monkeypatch):
    when = int(time.time())
    real_replace = os.replace
    tries = []

    def held(src, dst):
        if dst.endswith("locked.jpg"):
            tries.append(dst)
            raise PermissionError("held by the server")
        return real_replace(src, dst)

    monkeypatch.setattr(sync.os, "replace", held)
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    data = _tar([("locked.jpg", b"L", when), ("free.jpg", b"F", when)])
    stats = sync.extract(io.BytesIO(data), str(tmp_path))
    assert len(tries) == 3
    assert stats["written"] == 1
    assert stats["skipped"] == 1
    assert stats["skipped_names"] == ["locked.jpg"]
    assert (tmp_path / "free.jpg").read_bytes() == b"F"
    assert not (tmp_path / "locked.jpg").exists()
    assert not [p for p in os.listdir(tmp_path) if p.startswith(".sync-")]


def test_a_file_that_frees_up_on_a_retry_is_written(tmp_path, monkeypatch):
    when = int(time.time())
    real_replace = os.replace
    fails = [PermissionError("busy"), PermissionError("busy")]
    sleeps = []

    def busy_then_free(src, dst):
        if fails:
            raise fails.pop(0)
        return real_replace(src, dst)

    monkeypatch.setattr(sync.os, "replace", busy_then_free)
    monkeypatch.setattr(sync.time, "sleep", lambda s: sleeps.append(s))
    stats = sync.extract(io.BytesIO(_tar([("7.jpg", b"S", when)])), str(tmp_path))
    assert stats["written"] == 1 and stats["skipped"] == 0
    assert sleeps == [0.2, 0.2]


def test_truncated_stream_keeps_the_complete_files_and_raises(tmp_path):
    when = int(time.time())
    full = _tar([("1.jpg", b"A" * 10, when), ("2.jpg", b"B" * 600, when)])
    stats = sync.new_stats()
    with pytest.raises(tarfile.TarError):
        sync.extract(io.BytesIO(full[:1636]), str(tmp_path), stats)   # cut inside the second file's data
    assert stats["written"] == 1
    assert (tmp_path / "1.jpg").read_bytes() == b"A" * 10
    assert not (tmp_path / "2.jpg").exists()
    assert not [p for p in os.listdir(tmp_path) if p.startswith(".sync-")]


def test_stop_kills_a_running_ssh_and_closes_its_pipes():
    proc = FakeProc()
    sync._stop(proc)
    assert proc.killed and proc.waited
    assert proc.stdout.closed and proc.stderr.closed


def test_stop_leaves_a_finished_ssh_alone():
    proc = FakeProc(rc=0)
    proc.wait()
    sync._stop(proc)
    assert not proc.killed
    assert proc.stdout.closed and proc.stderr.closed


def test_since_is_the_last_newest_pi_mtime_minus_the_overlap(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "STATE_FILE", str(tmp_path / "state"))
    assert sync._since() is None
    sync._write_state(1_700_000_000.0)
    assert sync._since() == 1_700_000_000.0 - sync.OVERLAP
    assert sync.OVERLAP == 300


def _run_sync(monkeypatch, tmp_path, proc):
    monkeypatch.setattr(sync, "TARGET", str(tmp_path / "target"))
    monkeypatch.setattr(sync, "CACHE", str(tmp_path))
    monkeypatch.setattr(sync, "STATE_FILE", str(tmp_path / "state"))
    monkeypatch.setattr(sync, "LOG_FILE", str(tmp_path / "log"))
    monkeypatch.setattr(sync.subprocess, "Popen", lambda *a, **k: proc)
    return sync.sync_once()


def test_a_good_sync_advances_the_state_to_the_newest_pi_mtime(tmp_path, monkeypatch):
    data = _tar([("1.jpg", b"a", 1_700_000_100), ("2.jpg", b"b", 1_700_000_500)])
    assert _run_sync(monkeypatch, tmp_path, FakeProc(stdout=data)) is True
    assert float((tmp_path / "state").read_text()) == 1_700_000_500
    assert "copied 2 files" in (tmp_path / "log").read_text()


def test_a_truncated_sync_is_logged_as_partial_and_does_not_advance_the_state(tmp_path, monkeypatch):
    when = int(time.time())
    full = _tar([("1.jpg", b"A" * 10, when), ("2.jpg", b"B" * 600, when)])
    assert _run_sync(monkeypatch, tmp_path, FakeProc(stdout=full[:1636], rc=0)) is False
    log = (tmp_path / "log").read_text()
    assert "partial sync" in log and "copied" not in log
    assert not (tmp_path / "state").exists()


def test_an_empty_archive_from_tar_is_a_quiet_zero_copy(tmp_path, monkeypatch):
    proc = FakeProc(stdout=b"", stderr=b"tar: Cowardly refusing to create an empty archive\n", rc=2)
    assert _run_sync(monkeypatch, tmp_path, proc) is True
    assert "copied 0 files" in (tmp_path / "log").read_text()
    assert not (tmp_path / "state").exists()


def test_remote_command_names_only_jpg_newer_than_the_last_sync():
    cmd = sync.remote_command("/mnt/ssd/new_ccty_bangkok/instances/production/cache/bma_snapshots", 1700000000)
    assert "-name '*.jpg'" in cmd
    assert "-newermt '@1700000000'" in cmd
    assert "tar --null -cf - -T -" in cmd
    assert cmd.startswith("cd /mnt/ssd/new_ccty_bangkok/instances/production/cache/bma_snapshots && ")


def test_remote_command_first_run_looks_back_15_minutes():
    cmd = sync.remote_command("/d", None)
    assert "-mmin -15" in cmd
    assert "-newermt" not in cmd
