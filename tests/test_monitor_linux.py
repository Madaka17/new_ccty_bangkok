"""BKK Monitor on the Raspberry Pi (Linux): no Windows-only imports, systemd instead of marker files and sc.exe."""
import importlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "launch" / "monitor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "launch"))

import monitor_checks  # noqa: E402
import monitor_notify  # noqa: E402


class Run:
    """Fake subprocess.run for systemctl: {(verb, unit): stdout}."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = self.answers.get(tuple(cmd[1:3]), "")
        return subprocess.CompletedProcess(cmd, 0 if out in ("active", "enabled") else 3, stdout=out + "\n", stderr="")


def test_unit_disabled_counts_as_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor_checks, "STATE_DIR", tmp_path)
    run = Run({("is-enabled", "bkk-test"): "disabled"})
    assert monitor_checks.stopped(8001, platform="posix", run=run) is True


def test_unit_enabled_is_not_stopped(tmp_path, monkeypatch):
    # enabled but down is a real failure, not "stopped on purpose"
    monkeypatch.setattr(monitor_checks, "STATE_DIR", tmp_path)
    run = Run({("is-enabled", "bkk-production"): "enabled"})
    assert monitor_checks.stopped(8000, platform="posix", run=run) is False


def test_marker_file_still_means_stopped_on_linux(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor_checks, "STATE_DIR", tmp_path)
    (tmp_path / "stopped_8000").write_text("")
    assert monitor_checks.stopped(8000, platform="posix", run=Run({("is-enabled", "bkk-production"): "enabled"}))


def test_tunnel_running_uses_systemctl_on_linux():
    assert monitor_checks.tunnel_running(platform="posix", run=Run({("is-active", "cloudflared"): "active"}))
    assert not monitor_checks.tunnel_running(platform="posix", run=Run({("is-active", "cloudflared"): "inactive"}))


def test_toast_is_silent_on_linux(monkeypatch):
    called = []
    monkeypatch.setattr(monitor_notify.subprocess, "Popen", lambda *a, **k: called.append(a))
    monitor_notify.toast("t", "b", platform="posix")
    assert called == []


def test_processes_alive_on_posix():
    import monitor_processes
    assert monitor_processes.alive(os.getpid()) is True
    assert monitor_processes.alive(0) is False


def test_collector_lock_is_exclusive(tmp_path):
    import collector
    a = open(tmp_path / "c.lock", "w")
    b = open(tmp_path / "c.lock", "w")
    try:
        assert collector.try_lock(a) is True
        assert collector.try_lock(b) is False
    finally:
        a.close()
        b.close()
