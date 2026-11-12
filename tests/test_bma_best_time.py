"""BMA best time: the hour with the fewest cars per road, from the last 8 weeks of counts."""
import sqlite3
import threading
from datetime import date

from backend.bma import bma_best_time, bma_db
from backend.bma.bma_best_time import RETRY_SECONDS, BestTime, clean_road, load_holidays
from backend.bma.bma_db import BmaDatabase

TODAY = date(2026, 10, 9)
WORKDAYS = ["2026-10-05", "2026-10-06", "2026-10-07"]


def _insert(db, camid, day, hour, total):
    with db.lock:
        conn = bma_db.sqlite3.connect(db.db_path)
        conn.execute("""INSERT INTO bma_history (camid, hour, cars, motorcycles, trucks, total, level, ts, date, week, month, road, district)
                        VALUES (?, ?, ?, 0, 0, ?, 'free', 0, ?, '', '', '', '')""",
                     (camid, f"{day}T{hour:02d}:00", total, total, day))
        conn.commit()
        conn.close()


def _fill_day(db, camid, day, totals=None, skip=()):
    """One camera on one day: 10 cars every hour 6..22, unless `totals` overrides some hours."""
    for hour in range(6, 23):
        if hour not in skip:
            _insert(db, camid, day, hour, (totals or {}).get(hour, 10))


def _profile(db_path, cameras, **kwargs):
    return BestTime(db_path, cameras, today=lambda: TODAY).profile(**kwargs)


def test_clean_road_restores_rama_number():
    assert clean_road({"road": "ถนนพระรามที่", "title": "แยกสะพานแดง ด้านถนนพระรามที่ 5"}) == "ถนนพระรามที่ 5"
    assert clean_road({"road": "ถนนพระราม", "title": "หน้าห้าง ถนนพระราม 4"}) == "ถนนพระรามที่ 4"
    assert clean_road({"road": "ถนนสามเสน", "title": "x"}) == "ถนนสามเสน"


def test_best_and_worst_hours(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    for day in WORKDAYS:
        _fill_day(db, "c1", day, {10: 2, 17: 20})

    result = _profile(db.db_path, cameras)

    assert result["best"] == {"from": 10, "to": 11}
    assert result["worst"] == {"from": 17, "to": 18}
    hours = {h["h"]: h for h in result["hours"]}
    assert hours[17]["level"] == "heavy"
    assert hours[10]["level"] == "free"


def test_hours_with_too_few_cells_are_no_data(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    # hour 12 is quiet, but only on two dates, so it must not count as the best hour
    _fill_day(db, "c1", WORKDAYS[0], {10: 2, 12: 0})
    _fill_day(db, "c1", WORKDAYS[1], {10: 2, 12: 0})
    _fill_day(db, "c1", WORKDAYS[2], {10: 2}, skip=(12,))

    result = _profile(db.db_path, cameras)

    hour_12 = next(h for h in result["hours"] if h["h"] == 12)
    assert hour_12["samples"] == 2
    assert hour_12["avg"] is None
    assert hour_12["level"] is None
    assert result["best"] != {"from": 12, "to": 13}
    assert result["best"] == {"from": 10, "to": 11}


def test_weekend_is_separate(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    _fill_day(db, "c1", "2026-10-10")  # Saturday
    _fill_day(db, "c1", "2026-10-11")  # Sunday

    result = _profile(db.db_path, cameras, day="workday")

    assert result["best"] is None
    assert all(h["avg"] is None for h in result["hours"])


def test_road_filter_and_road_list(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [
        {"camid": "c1", "title": "หน้าห้าง ถนนพระราม 4", "road": "ถนนพระราม", "district": ""},
        {"camid": "c2", "title": "ใกล้ ถนนพระรามที่ 4 ขาเข้า", "road": "ถนนพระรามที่", "district": ""},
        {"camid": "c3", "title": "x", "road": "ถนนสามเสน", "district": ""},
    ]
    for day in WORKDAYS:
        _fill_day(db, "c1", day)
        _fill_day(db, "c2", day)
        _fill_day(db, "c3", day, {10: 500})

    result = _profile(db.db_path, cameras, road="ถนนพระรามที่ 4")

    assert result["roads"] == [{"road": "ถนนพระรามที่ 4", "cameras": 2}]
    hour_10 = next(h for h in result["hours"] if h["h"] == 10)
    assert hour_10["samples"] == 2 * len(WORKDAYS)
    assert hour_10["avg"] == 10.0


def _cams():
    return [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""},
            {"camid": "c2", "title": "x", "road": "ถนนสามเสน", "district": ""}]


def test_is_known_road():
    bt = BestTime("unused.db", _cams())
    assert bt.is_known_road("")
    assert bt.is_known_road("ถนนสามเสน")
    assert not bt.is_known_road("ถนนที่ไม่มี")


def test_failed_reload_keeps_old_cells(tmp_path):
    clock = [0.0]
    bt = BestTime("unused.db", _cams(), ttl=10, clock=lambda: clock[0], background_refresh=False)
    bt._load_cells = lambda: [("c1", "2026-10-05", 10, 5.0, 1)]
    bt.profile()
    def boom():
        raise RuntimeError("db busy")
    bt._load_cells = boom
    clock[0] = 11
    result = bt.profile()
    assert next(h for h in result["hours"] if h["h"] == 10)["samples"] == 1


def test_first_load_failure_gives_empty_profile():
    bt = BestTime("unused.db", _cams())
    def boom():
        raise RuntimeError("no table")
    bt._load_cells = boom
    result = bt.profile()
    assert all(h["avg"] is None for h in result["hours"])
    assert result["best"] is None and result["worst"] is None
    assert result["roads"] == []


def test_no_reload_inside_backoff():
    clock = [0.0]
    calls = []
    bt = BestTime("unused.db", _cams(), clock=lambda: clock[0], background_refresh=False)
    def boom():
        calls.append(1)
        raise RuntimeError("busy")
    bt._load_cells = boom
    bt.profile()
    clock[0] = 30
    bt.profile()
    assert len(calls) == 1
    clock[0] = 61
    bt.profile()
    assert len(calls) == 2


def test_commute_windows(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    for day in WORKDAYS:
        _fill_day(db, "c1", day, {7: 2, 9: 30, 17: 40, 19: 3})

    result = _profile(db.db_path, cameras)

    assert result["commute"]["morning"] == {"best": {"from": 7, "to": 8}, "worst": {"from": 9, "to": 10}}
    assert result["commute"]["evening"] == {"best": {"from": 19, "to": 20}, "worst": {"from": 17, "to": 18}}


def test_commute_window_without_data(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    for day in WORKDAYS:
        _fill_day(db, "c1", day, skip=tuple(range(10, 23)))

    result = _profile(db.db_path, cameras)

    assert result["commute"]["evening"] == {"best": None, "worst": None}
    # all four morning hours read 10 cars, so the first hour is both the best and the worst
    assert result["commute"]["morning"] == {"best": {"from": 6, "to": 7}, "worst": {"from": 6, "to": 7}}


def test_holiday_counts_as_weekend(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    friday = "2026-10-09"          # a Friday; with it in the holiday set it is weekend
    assert date.fromisoformat(friday).weekday() == 4
    _insert(db, "c1", friday, 8, 10)
    cams = [{"camid": "c1", "road": "ถนนสีลม", "title": ""}]
    bt = BestTime(db.db_path, cams, today=lambda: TODAY, holidays={friday})
    assert bt.profile(day="weekend")["days_of_data"] == 1
    assert bt.profile(day="workday")["days_of_data"] == 0


def test_load_holidays_missing_file_is_empty(tmp_path):
    assert load_holidays(str(tmp_path / "nope.json")) == set()


def test_load_holidays_broken_file_is_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_holidays(str(p)) == set()
    p.write_text('{"dates": "2026-10-13"}', encoding="utf-8")
    assert load_holidays(str(p)) == set()


def test_load_holidays_keeps_only_valid_dates(tmp_path):
    p = tmp_path / "h.json"
    p.write_text('{"dates": ["2026-10-13", "13/10/2026", 5, "2026-02-30"]}', encoding="utf-8")
    assert load_holidays(str(p)) == {"2026-10-13"}


def test_shipped_holiday_file_loads():
    holidays = load_holidays()
    assert "2026-10-13" in holidays and "2027-01-01" in holidays


def _old_cells(db_path, cutoff):
    """The pre-change query, run as the reference for the new cell loader."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("""
            SELECT camid, date, CAST(substr(hour, 12, 2) AS INTEGER) h, AVG(total) a, COUNT(*)
            FROM bma_history WHERE date >= ? GROUP BY camid, date, h""", (cutoff,)).fetchall()
    finally:
        conn.close()


def test_cells_sql_uses_covering_index_without_sort(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    conn = sqlite3.connect(db.db_path)
    try:
        plan = " | ".join(r[3] for r in conn.execute(
            "EXPLAIN QUERY PLAN " + bma_best_time.CELLS_SQL, ("2026-09-01",)).fetchall())
    finally:
        conn.close()
    assert "COVERING INDEX idx_bma_hist_best_time" in plan
    assert "TEMP B-TREE" not in plan


def test_cells_match_old_expression_query(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""},
               {"camid": "c2", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    for cam in ("c1", "c2"):
        for day in WORKDAYS:
            for hour, totals in ((7, (3, 9, 11)), (8, (4, 4)), (17, (30, 50, 70, 10))):
                for total in totals:
                    _insert(db, cam, day, hour, total)

    bt = BestTime(db.db_path, cameras, today=lambda: TODAY)
    new = sorted(bt._load_cells())
    old = sorted(_old_cells(db.db_path, "2026-09-01"))

    assert len(new) == len(old) == 2 * len(WORKDAYS) * 3
    for (c1, d1, h1, a1, n1), (c2, d2, h2, a2, n2) in zip(new, old):
        assert (c1, d1, h1, n1) == (str(c2), d2, h2, n2)
        assert abs(a1 - a2) < 1e-9


def _stale_setup(tmp_path):
    """Three workdays of 10 cars at 10:00 for c1, loaded once; then a fourth day with 50 cars is inserted."""
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    for day in WORKDAYS:
        _insert(db, "c1", day, 10, 10)
    clock = [0.0]
    bt = BestTime(db.db_path, cameras, ttl=10, today=lambda: TODAY, clock=lambda: clock[0])
    first = next(h for h in bt.profile()["hours"] if h["h"] == 10)
    assert (first["samples"], first["avg"]) == (3, 10.0)
    _insert(db, "c1", "2026-10-08", 10, 50)
    clock[0] = 11
    return bt, clock


def test_stale_cells_returned_at_once_and_refreshed_in_background(tmp_path):
    bt, _ = _stale_setup(tmp_path)
    gate = threading.Event()
    real_load = bt._load_cells

    def slow_load():
        gate.wait(5)
        return real_load()

    bt._load_cells = slow_load
    old = next(h for h in bt.profile()["hours"] if h["h"] == 10)
    assert (old["samples"], old["avg"]) == (3, 10.0)   # answered at once with the old data
    thread = bt._refresh_thread
    assert thread is not None and thread.is_alive()

    bt.profile()   # still stale and a refresh is running: no second thread
    assert bt._refresh_thread is thread

    gate.set()
    thread.join(5)
    new = next(h for h in bt.profile()["hours"] if h["h"] == 10)
    assert (new["samples"], new["avg"]) == (4, 20.0)


def test_background_refresh_failure_keeps_old_cells(tmp_path):
    bt, clock = _stale_setup(tmp_path)

    def boom():
        raise RuntimeError("db busy")

    bt._load_cells = boom
    old = next(h for h in bt.profile()["hours"] if h["h"] == 10)
    assert (old["samples"], old["avg"]) == (3, 10.0)
    bt._refresh_thread.join(5)

    kept = next(h for h in bt.profile()["hours"] if h["h"] == 10)
    assert (kept["samples"], kept["avg"]) == (3, 10.0)
    assert bt._retry_at == clock[0] + RETRY_SECONDS
    assert bt._refreshing is False


def test_warm_loads_cells(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cameras = [{"camid": "c1", "title": "x", "road": "ถนนสามเสน", "district": ""}]
    _insert(db, "c1", WORKDAYS[0], 10, 10)
    bt = BestTime(db.db_path, cameras, today=lambda: TODAY)
    assert bt._cells is None

    bt.warm()
    bt._warm_thread.join(5)

    assert bt._cells is not None
    assert len(bt._cells) == 1
