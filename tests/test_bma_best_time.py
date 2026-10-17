"""BMA best time: the hour with the fewest cars per road, from the last 8 weeks of counts."""
from datetime import date

from backend.bma import bma_db
from backend.bma.bma_best_time import BestTime, clean_road
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
