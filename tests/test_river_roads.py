"""Distance to the Chao Phraya and the chance of the river over the bank (backend/water/river_roads.py)."""
from datetime import date, datetime, timedelta

from backend.water import river_roads as rr
from backend.water import water_service as ws


def test_nearest_point_on_the_centre_line():
    river = rr.River([[[13.90, 100.50], [13.95, 100.50]]])
    d, c = river.nearest((13.92, 100.502))                       # ~215 m east of a north-south line
    assert 0.2 < d < 0.23 and abs(c[0] - 13.92) < 1e-6 and abs(c[1] - 100.50) < 1e-6
    assert river.nearest((13.92, 100.60)) == (None, None)        # ~10 km away: beyond NEAR_KM


def test_closeness_weights():
    assert [rr.closeness(k) for k in (0.1, 0.3, 0.8, 1.5, 3)] == [1.0, 0.6, 0.3, 0.1, 0.0]


def test_day_chances_take_the_likeliest_day():
    today = datetime.now(ws.BKK_TZ).date()
    peaks = {today + timedelta(days=1): 2.40, today + timedelta(days=2): 2.60}
    days, p7 = rr.day_chances(peaks, 2.50, lambda lead: 0.10)
    assert [round(d["p"], 2) for d in days] == [0.16, 0.84]      # 1 sigma below and above the bank
    assert p7 == days[1]["p"]


def test_persistence_sigma_and_logged_errors():
    d0 = date(2026, 9, 20)
    obs = {d0 + timedelta(days=i): v for i, v in enumerate([2.0, 2.1, 2.3, 2.2, 2.4, 2.5])}
    s = rr.persistence_sigma(obs, 1)
    assert 0.09 < s < 0.15
    log = {"2026-09-21": {"2026-09-22": 2.25, "2026-09-23": 2.30}}
    errs = rr.logged_errors(log, obs)
    assert round(errs[1][0], 2) == 0.05 and round(errs[2][0], 2) == -0.10


def test_areas_name_the_sub_district():
    ar = rr.areas()
    assert ar.in_province((13.862, 100.513))                    # Nonthaburi city hall area
    assert not ar.in_province((13.745, 100.535))                # Bangkok, Pathum Wan
    tambon, amphoe = ar.tambon_of((13.862, 100.513))
    assert amphoe == "เมืองนนทบุรี" and tambon


def test_road_stretches_are_ranked_riskiest_first():
    stretches = [
        {"lat": 13.9, "lng": 100.5, "km": 1.5, "tambon": "ก", "amphoe": "ปากเกร็ด", "cross": None},
        {"lat": 13.9, "lng": 100.5, "km": 0.1, "tambon": "ข", "amphoe": "ปากเกร็ด", "cross": "ถนนติวานนท์"},
        {"lat": 13.9, "lng": 100.5, "km": None, "tambon": "ค", "amphoe": "ปากเกร็ด", "cross": None},
        {"lat": 13.9, "lng": 100.5, "km": 0.4, "tambon": "ข", "amphoe": "ปากเกร็ด", "cross": None},
    ]
    r = rr.rank_road("ถนนทดสอบ", stretches, 0.8)
    assert [s["km"] for s in r["stretches"]] == [0.1, 0.4, 1.5, None]
    assert r["p"] == 0.8 and r["level"] == "สูง" and r["km"] == 0.1
    assert r["stretches"][0]["place"] == "ช่วงตัดถนนติวานนท์ ต.ข อ.ปากเกร็ด"
    assert r["stretches_at_risk"] == 2 and r["stretches"][3]["p"] == 0.0
