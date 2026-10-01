"""Cleaning, routing and warnings of the northern water outlook (backend/water/north_flow.py)."""
import math

from backend.water import north_flow as nf

NOW = 1_790_690_400  # 2026-09-29 21:00 Bangkok, on the hour
H = 3600


def _upstream(t):
    # A slow 5-day swell around 1,500 m3/s
    return 1500 + 400 * math.sin(2 * math.pi * t / (5 * 86400))


def test_clean_drops_glitch_readings():
    pts = [(NOW - h * H, 1000.0) for h in range(48)]
    pts[10] = (NOW - 10 * H, 330.0)       # the RID rating sometimes sends a third of the flow
    s = nf.clean(pts)
    assert NOW - 10 * H not in s
    assert all(abs(v - 1000) < 1e-6 for v in s.values())


def test_value_at_bridges_short_gaps_only():
    s = {NOW - 4 * H: 100.0, NOW: 140.0}
    assert nf.value_at(s, NOW - 2 * H) == 120.0
    assert nf.value_at({NOW - 16 * H: 100.0, NOW: 140.0}, NOW - 8 * H) is None


def test_route_follows_upstream_water_for_one_travel_time():
    # C.3 carries 90% of what passed C.13 nine hours earlier (the prior lag for that reach)
    hours = range(-16 * 24, 1)
    up = {NOW + h * H: _upstream(NOW + h * H) for h in hours}
    down = {NOW + h * H: 0.9 * _upstream(NOW + (h - 9) * H) for h in hours}
    out = nf.route({"C.13": up, "C.3": down}, NOW)
    r = out["C.3"]
    assert abs(r["gain"] - 0.9) < 0.01
    assert r["inputs"] == [("C.13", 9)] and r["lead_h"] == 9
    for t, q in r["points"][:9]:
        assert abs(q - 0.9 * _upstream(t - 9 * H)) < 0.01 * q
    # Past the travel time the upstream gauge is held level, so the outlook flattens
    tail = [q for _, q in r["points"][9:]]
    assert max(tail) - min(tail) < 1


def test_route_skips_stale_gauges():
    old = {NOW - 20 * H - h * H: 1000.0 for h in range(400)}
    assert "C.3" not in nf.route({"C.13": old, "C.3": old}, NOW)


def _station(code, q, qmax, status, peak=None, change=None, river="chao_phraya", province="พระนครศรีอยุธยา"):
    return {"code": code, "name": "", "province": province, "river": river, "q": q, "qmax": qmax,
            "pct": round(100 * q / qmax, 1), "status": status, "peak": peak, "change_24h": change,
            "below_bank": 1.0, "official": None}


def test_alerts_rank_overflow_first_and_name_the_wave():
    peak = {"t": NOW + 36 * H, "q": 2800, "in_h": 36, "pct": 103.0, "status": "overflow", "overflow_at": NOW + 30 * H}
    stations = [
        _station("P.7A", 1650, 3000, "normal", change=850, river="ping", province="กำแพงเพชร"),
        _station("C.13", 2000, 2720, "high", peak=peak, province="ชัยนาท"),
        _station("C.35", 1316, 1159, "overflow"),
    ]
    alerts = nf._alerts(stations, NOW)
    assert [a["code"] for a in alerts] == ["C.13", "C.35", "P.7A"]
    assert "คาดว่าจะเกินความจุลำน้ำในอีก ~30 ชม." in alerts[0]["text"]
    assert "กรมชลประทาน" in alerts[0]["text"]          # the dam release is RID's call
    assert "ล้นตลิ่งแล้ว" in alerts[1]["text"]
    assert alerts[2]["tone"] == "yellow" and "น้ำขึ้นเร็ว +850" in alerts[2]["text"]
    head = nf._headline(stations, alerts)
    assert head["tone"] == "red" and "ชัยนาท" in head["text"] and "พระนครศรีอยุธยา" in head["text"]


def test_quiet_rivers_give_a_green_headline():
    stations = [_station("C.2", 900, 3735, "normal", province="นครสวรรค์")]
    alerts = nf._alerts(stations, NOW)
    assert alerts == []
    assert nf._headline(stations, alerts)["tone"] == "green"


def test_rating_curve_turns_level_into_discharge():
    # Q = 100 * (h - 10)^2 over a rising and falling level, hourly
    levels = [12 + 2 * math.sin(i / 20) for i in range(200)]
    pairs = [(h, 100 * (h - 10) ** 2) for h in levels]
    r = nf.fit_rating(pairs)
    assert r and r["mape"] < 0.5
    est = nf.ten_minute(r, [(NOW, 13.0), (NOW + 600, 20.0)])
    assert [p["q"] for p in est] == [900]        # 20 m is far outside the fitted range: no estimate


def test_rating_refuses_a_gauge_that_does_not_track():
    pairs = [(12 + (i % 7) * 0.1, 500 + (i * 37) % 300) for i in range(200)]
    r = nf.fit_rating(pairs)
    assert r is None or r["mape"] > nf.MATCH_MAPE
