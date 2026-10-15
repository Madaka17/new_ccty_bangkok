import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import collector  # noqa: E402
import monitor_checks  # noqa: E402
import monitor_watchdog  # noqa: E402
from monitor_store import Store  # noqa: E402


def test_one_round_stores_status_and_imports_watchdog(tmp_path, monkeypatch):
    log = tmp_path / "watchdog.log"
    log.write_text("2026-10-15 00:28:12 production :8000 down: running launch\\production\\restart.bat\n", encoding="utf-8")
    monkeypatch.setattr(collector, "WATCHDOG_LOG", log)
    monkeypatch.setattr(monitor_checks, "run_round", lambda gateway_due: [
        {"key": "server:production", "group": "server", "target": "production", "name": "Production",
         "state": "fail", "detail": "down"}])
    store = Store(tmp_path / "m.db")
    now = int(datetime(2026, 10, 15, 1, 0, 0).timestamp())     # one hour after the log line
    events = collector.one_round(store, now=now, gateway_due=False)
    assert {e["key"] for e in events} == {"server:production", "watchdog:production"}
    assert store.get_meta("collector_at") == str(now)
    # the same log line is not imported twice
    assert [e["key"] for e in collector.one_round(store, now=now + 30, gateway_due=False)] == []


def test_old_watchdog_lines_beyond_30_days_skipped(tmp_path, monkeypatch):
    log = tmp_path / "watchdog.log"
    log.write_text("2020-01-01 00:00:00 production :8000 down: running x\\restart.bat\n", encoding="utf-8")
    monkeypatch.setattr(collector, "WATCHDOG_LOG", log)
    monkeypatch.setattr(monitor_checks, "run_round", lambda gateway_due: [])
    store = Store(tmp_path / "m.db")
    assert collector.one_round(store, now=2_000_000_000, gateway_due=False) == []


def test_watchdog_import_failure_keeps_status_events(tmp_path, monkeypatch):
    def broken(path, offset):
        raise RuntimeError("log unreadable")
    monkeypatch.setattr(collector, "WATCHDOG_LOG", tmp_path / "watchdog.log")
    monkeypatch.setattr(monitor_watchdog, "read_new", broken)
    monkeypatch.setattr(monitor_checks, "run_round", lambda gateway_due: [
        {"key": "server:production", "group": "server", "target": "production", "name": "Production",
         "state": "fail", "detail": "down"}])
    store = Store(tmp_path / "m.db")
    events = collector.one_round(store, now=2_000_000_000, gateway_due=False)
    assert [e["key"] for e in events] == ["server:production"]
    assert store.get_meta("collector_at") == "2000000000"
