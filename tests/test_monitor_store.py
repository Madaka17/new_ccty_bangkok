import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
from monitor_store import Store  # noqa: E402


def st(key, state, detail="", target="production", group="server", name=None):
    return {"key": key, "group": group, "target": target, "name": name or key, "state": state, "detail": detail}


def test_first_ok_makes_no_event_but_bad_does(tmp_path):
    s = Store(tmp_path / "m.db")
    ev = s.apply([st("server:production", "ok"), st("server:test", "stopped", target="test")], now=100)
    assert [e["key"] for e in ev] == ["server:test"]
    assert ev[0]["old"] is None and ev[0]["new"] == "stopped"


def test_change_makes_event_and_moves_since(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([st("server:production", "ok", "up")], now=100)
    assert s.apply([st("server:production", "ok", "up 2")], now=130) == []
    ev = s.apply([st("server:production", "fail", "no answer")], now=160)
    assert ev[0]["old"] == "ok" and ev[0]["new"] == "fail" and ev[0]["detail"] == "no answer"
    cur = {r["key"]: r for r in s.current()}["server:production"]
    assert cur["since"] == 160 and cur["checked_at"] == 160


def test_detail_update_without_event(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([st("server:production", "ok", "up 1 min")], now=100)
    s.apply([st("server:production", "ok", "up 2 min")], now=130)
    cur = s.current()[0]
    assert cur["detail"] == "up 2 min" and cur["since"] == 100


def test_missing_keys_untouched(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([st("service:gateway", "ok", group="service", target="gateway")], now=100)
    s.apply([st("server:production", "ok")], now=130)
    assert {r["key"] for r in s.current()} == {"service:gateway", "server:production"}


def test_events_filters_and_paging(tmp_path):
    s = Store(tmp_path / "m.db")
    for i in range(30):
        s.add_event(1000 + i, "server:production", "server", "production", "Production", "ok", "fail", f"boom {i}")
    s.add_event(2000, "server:test", "server", "test", "Test", "ok", "stopped", "stopped")
    page = s.events(limit=25)
    assert page["total"] == 31 and len(page["rows"]) == 25 and page["rows"][0]["ts"] == 2000
    assert s.events(target="test")["total"] == 1
    assert s.events(state="fail", q="BOOM 29")["total"] == 1
    assert s.events(since=1025)["total"] == 6
    assert len(s.events(limit=25, offset=25)["rows"]) == 6


def test_events_target_list(tmp_path):
    s = Store(tmp_path / "m.db")
    for i, t in enumerate(["production", "gateway", "tunnel", "test"]):
        s.add_event(1000 + i, f"x:{t}", "service", t, t, "ok", "fail", "")
    got = s.events(target=["gateway", "tunnel"])
    assert got["total"] == 2 and {r["target"] for r in got["rows"]} == {"gateway", "tunnel"}
    assert s.events(target=[])["total"] == 4


def test_prune(tmp_path):
    s = Store(tmp_path / "m.db")
    s.add_event(0, "k", "server", "production", "P", "ok", "fail", "")
    s.add_event(40 * 86400, "k", "server", "production", "P", "fail", "ok", "")
    assert s.prune(now=40 * 86400, days=30) == 1
    assert s.events()["total"] == 1


def test_meta(tmp_path):
    s = Store(tmp_path / "m.db")
    assert s.get_meta("x", "d") == "d"
    s.set_meta("x", "1")
    assert s.get_meta("x") == "1"


def test_concurrent_read_while_writing(tmp_path):
    s = Store(tmp_path / "m.db")
    errors = []

    def writer():
        for i in range(200):
            s.add_event(i, "k", "server", "production", "P", "ok", "fail", "")

    def reader():
        try:
            for _ in range(200):
                s.events(limit=5)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1, t2 = threading.Thread(target=writer), threading.Thread(target=reader)
    t1.start(); t2.start(); t1.join(); t2.join()
    assert errors == []


def test_extra_round_trips_and_is_none_without(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([{**st("agent:production:A", "ok", group="agent", target="production", name="A"),
              "extra": {"tokens": 500, "calls": 3, "note": ""}},
             st("server:production", "ok")], now=100)
    cur = {r["key"]: r for r in s.current()}
    assert cur["agent:production:A"]["extra"] == {"tokens": 500, "calls": 3, "note": ""}
    assert cur["server:production"]["extra"] is None


def test_bad_extra_json_reads_as_none(tmp_path):
    from contextlib import closing
    import sqlite3
    s = Store(tmp_path / "m.db")
    s.apply([st("server:production", "ok")], now=100)
    with closing(sqlite3.connect(s.path)) as c, c:
        c.execute("UPDATE status SET extra = '{not json' WHERE key = 'server:production'")
    assert s.current()[0]["extra"] is None


def test_old_db_gains_extra_column(tmp_path):
    from contextlib import closing
    import sqlite3
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as c, c:
        c.execute("CREATE TABLE status (key TEXT PRIMARY KEY, grp TEXT, target TEXT, name TEXT, state TEXT, "
                  "detail TEXT, since REAL, checked_at REAL)")
        c.execute("INSERT INTO status VALUES ('server:production', 'server', 'production', 'Production', 'ok', 'up', 100, 100)")
    s = Store(path)
    with closing(sqlite3.connect(path)) as c:
        assert "extra" in {r[1] for r in c.execute("PRAGMA table_info(status)")}
    cur = s.current()
    assert cur[0]["key"] == "server:production" and cur[0]["extra"] is None
    s.apply([{**st("agent:production:A", "ok", group="agent", target="production", name="A"), "extra": {"tokens": 1}}], now=200)
    assert {r["key"]: r["extra"] for r in s.current()}["agent:production:A"] == {"tokens": 1}


def test_retire_deletes_rows_without_events(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([{"key": "agent:production:A", "group": "agent", "target": "production", "name": "A", "state": "fail",
              "detail": "d", "uptime_s": 5}], 100)
    n = len(s.events()["rows"])
    s.retire(["agent:production:A", "nope"])
    assert s.current() == [] and len(s.events()["rows"]) == n
    s.retire([])
