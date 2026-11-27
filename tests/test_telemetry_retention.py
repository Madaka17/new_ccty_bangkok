"""Visitor telemetry: heartbeat view validation, retention of page views, and the visitors table."""
import sqlite3

import pytest

from backend.core import telemetry_service as svc
from backend.core.telemetry_service import Telemetry

T0 = 1_750_000_000
DAY = 86400
SID_A = "sid-aaaaaaaa"
SID_B = "sid-bbbbbbbb"
SID_C = "sid-cccccccc"


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock(T0)
    monkeypatch.setattr(svc, "time", c)
    monkeypatch.setattr(svc, "KEEP_DAYS", 30, raising=False)
    return c


def test_heartbeat_without_view_stores_dash_not_null(tmp_path, clock):
    t = Telemetry(path=str(tmp_path / "t.db"))
    assert t.heartbeat(SID_A, None) is True
    assert t.heartbeat(SID_B, "") is True
    stored = t.conn.execute("SELECT sid, view FROM sessions ORDER BY sid").fetchall()
    assert stored == [(SID_A, "-"), (SID_B, "-")]
    views = {r["view"] for r in t.stats()["online_by_view"]}
    assert views == {"-"}


def test_purge_drops_old_views_but_keeps_visitor_totals(tmp_path, clock):
    clock.t = T0 - 100 * DAY
    t = Telemetry(path=str(tmp_path / "t.db"))
    t.view(SID_A, "dashboard")
    clock.t = T0 - 50 * DAY
    t.view(SID_B, "map")
    clock.t = T0 - 1 * DAY
    t.view(SID_A, "map")
    before = t.stats()
    assert before["visitors_total"] == 2
    assert before["counting_since"] == T0 - 100 * DAY

    clock.t = T0
    t.view(SID_C, "map")  # first view after an hour: purge runs
    left_old = t.conn.execute("SELECT COUNT(*) FROM views WHERE ts < ?", (T0 - 30 * DAY,)).fetchone()[0]
    assert left_old == 0
    assert t.conn.execute("SELECT COUNT(*) FROM views").fetchone()[0] == 2

    after = t.stats()
    assert after["visitors_total"] == 3
    assert after["counting_since"] == T0 - 100 * DAY


def test_backfill_visitors_from_existing_views(tmp_path, clock):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE views (ts INTEGER NOT NULL, sid TEXT NOT NULL, view TEXT NOT NULL)")
    conn.execute("CREATE INDEX views_ts ON views (ts)")
    conn.execute("CREATE TABLE sessions (sid TEXT PRIMARY KEY, last_ts INTEGER NOT NULL, view TEXT)")
    conn.executemany("INSERT INTO views VALUES (?, ?, ?)", [
        (T0 - 10 * DAY, SID_A, "map"),
        (T0 - 2 * DAY, SID_A, "map"),
        (T0 - 5 * DAY, SID_B, "water"),
    ])
    conn.commit()
    conn.close()

    t = Telemetry(path=path)
    rows = t.conn.execute("SELECT sid, first_ts FROM visitors ORDER BY sid").fetchall()
    assert rows == [(SID_A, T0 - 10 * DAY), (SID_B, T0 - 5 * DAY)]
    stats = t.stats()
    assert stats["visitors_total"] == 2
    assert stats["counting_since"] == T0 - 10 * DAY


def test_purge_runs_at_most_once_an_hour(tmp_path, clock):
    t = Telemetry(path=str(tmp_path / "t.db"))
    t.conn.execute("INSERT INTO views VALUES (?, ?, ?)", (T0 - 40 * DAY, SID_A, "map"))
    t.conn.commit()

    clock.t = T0 + 30 * 60
    t.view(SID_B, "map")
    assert t.conn.execute("SELECT COUNT(*) FROM views WHERE ts < ?", (T0 - 30 * DAY,)).fetchone()[0] == 1

    clock.t = T0 + 61 * 60
    t.view(SID_B, "map")
    assert t.conn.execute("SELECT COUNT(*) FROM views WHERE ts < ?", (T0 - 30 * DAY,)).fetchone()[0] == 0
