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


def row(key, state, detail="", **extra):
    grp, target = key.split(":")[0], key.split(":")[1]
    return {"key": key, "group": grp, "target": target, "name": key.split(":")[-1], "state": state,
            "detail": detail, **extra}


def run(store, monkeypatch, tmp_path, rows, now, memory=None, quiet=None):
    monkeypatch.setattr(collector, "WATCHDOG_LOG", tmp_path / "none.log")
    monkeypatch.setattr(monitor_checks, "run_round", lambda gateway_due: rows)
    return collector.one_round(store, now=now, gateway_due=False, memory=memory, quiet=quiet)


def keys(store):
    return {i["key"] for i in store.current()}


def test_down_target_retires_agent_and_yolo_rows(tmp_path, monkeypatch):
    store = Store(tmp_path / "m.db")
    up = [row("server:production", "ok"), row("agent:production:A", "fail"), row("yolo:production:Y", "fail"),
          row("agent:test:T", "ok")]
    run(store, monkeypatch, tmp_path, up, 1000)
    assert {"agent:production:A", "yolo:production:Y"} <= keys(store)
    run(store, monkeypatch, tmp_path, [row("server:production", "fail")], 1030, memory={"streak": {}, "grace": {}})
    assert keys(store) == {"server:production"}      # production's rows gone, test's agent too (test not up this round)


def test_orphan_agent_row_retired_when_server_up(tmp_path, monkeypatch):
    store = Store(tmp_path / "m.db")
    run(store, monkeypatch, tmp_path, [row("server:production", "ok"), row("agent:production:Old", "ok")], 1000)
    run(store, monkeypatch, tmp_path, [row("server:production", "ok"), row("agent:production:New", "ok")], 1030)
    assert keys(store) == {"server:production", "agent:production:New"}


def test_debounce_holds_first_bad_round(tmp_path, monkeypatch):
    store, mem = Store(tmp_path / "m.db"), {"streak": {}, "grace": {}}
    run(store, monkeypatch, tmp_path, [row("service:tunnel", "ok")], 1000, mem)
    assert run(store, monkeypatch, tmp_path, [row("service:tunnel", "fail", "blip")], 1030, mem) == []
    assert store.current()[0]["state"] == "ok"
    ev = run(store, monkeypatch, tmp_path, [row("service:tunnel", "fail", "blip")], 1060, mem)
    assert [(e["old"], e["new"]) for e in ev] == [("ok", "fail")]
    # a single bad round that recovers never produces an event
    run(store, monkeypatch, tmp_path, [row("service:tunnel", "ok")], 1090, mem)
    assert run(store, monkeypatch, tmp_path, [row("service:tunnel", "warn")], 1120, mem) == []
    assert run(store, monkeypatch, tmp_path, [row("service:tunnel", "ok")], 1150, mem) == []


def test_first_seen_bad_key_not_held_back(tmp_path, monkeypatch):
    store = Store(tmp_path / "m.db")
    ev = run(store, monkeypatch, tmp_path, [row("service:tunnel", "fail")], 1000, {"streak": {}, "grace": {}})
    assert [e["new"] for e in ev] == ["fail"]


def test_starting_server_is_idle_for_180_s_then_fails(tmp_path, monkeypatch):
    store, mem = Store(tmp_path / "m.db"), {"streak": {}, "grace": {}}
    run(store, monkeypatch, tmp_path, [row("server:production", "stopped")], 1000, mem)
    ev = run(store, monkeypatch, tmp_path, [row("server:production", "fail", "down")], 1030, mem)
    assert [e["new"] for e in ev] == ["idle"] and ev[0]["detail"] == "starting (0 s)"
    run(store, monkeypatch, tmp_path, [row("server:production", "fail", "down")], 1090, mem)
    cur = store.current()[0]
    assert cur["state"] == "idle" and cur["detail"] == "starting (60 s)"
    run(store, monkeypatch, tmp_path, [row("server:production", "fail", "down")], 1250, mem)   # 220 s: debounce holds 1st
    ev = run(store, monkeypatch, tmp_path, [row("server:production", "fail", "down")], 1280, mem)
    assert store.current()[0]["state"] == "fail"


def test_starting_server_coming_up_ends_grace(tmp_path, monkeypatch):
    store, mem = Store(tmp_path / "m.db"), {"streak": {}, "grace": {}}
    run(store, monkeypatch, tmp_path, [row("server:production", "stopped")], 1000, mem)
    run(store, monkeypatch, tmp_path, [row("server:production", "fail")], 1030, mem)
    run(store, monkeypatch, tmp_path, [row("server:production", "ok")], 1060, mem)
    assert mem["grace"] == {}


def test_quiet_targets_collected_from_uptime(tmp_path, monkeypatch):
    store, quiet = Store(tmp_path / "m.db"), set()
    run(store, monkeypatch, tmp_path, [row("server:production", "ok", uptime_s=120), row("server:test", "ok", uptime_s=9000)],
        1000, quiet=quiet)
    assert quiet == {"production"}


def test_health_blip_does_not_renotify_unchanged_agent_rows(tmp_path, monkeypatch):
    import monitor_notify
    store, mem = Store(tmp_path / "m.db"), {"streak": {}, "grace": {}}
    ok = [row("server:production", "ok"), row("agent:production:Helmet", "fail", "x")]
    assert len(run(store, monkeypatch, tmp_path, ok, 1000, mem)) == 1      # first-seen fail: told once
    assert run(store, monkeypatch, tmp_path, [row("server:production", "fail")], 1030, mem) == []
    ev = run(store, monkeypatch, tmp_path, ok, 1060, mem)
    assert ev == [] and monitor_notify.summarize(ev, now=1060) is None
    assert {i["key"] for i in store.current()} == {"server:production", "agent:production:Helmet"}


def test_long_outage_tells_server_only(tmp_path, monkeypatch):
    import monitor_notify
    store, mem = Store(tmp_path / "m.db"), {"streak": {}, "grace": {}}
    ok = [row("server:production", "ok"), row("agent:production:Helmet", "fail", "x")]
    run(store, monkeypatch, tmp_path, ok, 1000, mem)
    down = [row("server:production", "fail")]
    assert run(store, monkeypatch, tmp_path, down, 1030, mem) == []
    assert [e["new"] for e in run(store, monkeypatch, tmp_path, down, 1060, mem)] == ["fail"]
    run(store, monkeypatch, tmp_path, down, 1090, mem)
    ev = run(store, monkeypatch, tmp_path, ok, 1120, mem)
    assert [(e["key"], e["new"]) for e in ev] == [("server:production", "ok")]
    assert monitor_notify.summarize(ev, now=1120)[0] == "BKK Monitor: back to normal"
    # a row that returns in a different state is still news
    run(store, monkeypatch, tmp_path, down, 1150, mem); run(store, monkeypatch, tmp_path, down, 1180, mem)
    ev = run(store, monkeypatch, tmp_path, [row("server:production", "ok"), row("agent:production:Helmet", "ok")], 1210, mem)
    assert "agent:production:Helmet" not in {e["key"] for e in ev}      # fail -> ok first-seen ok: no event either
