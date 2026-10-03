"""Province flood levels from Thai Water gauges and DOH flooded highways (province_flood.py)."""
import time

from backend.water import province_flood as pf

NOW = time.time()
STAMP = time.strftime("%Y-%m-%d %H:%M", time.localtime(NOW))
OLD = time.strftime("%Y-%m-%d %H:%M", time.localtime(NOW - 3 * 86400))


def gauge(province, level, pct, msl="10.10", prev="10.00", ts=STAMP, name="สะพาน (ABC01)", river="แม่น้ำท่าจีน"):
    return {"geocode": {"province_name": {"th": province}, "amphoe_name": {"th": "เมือง"}},
            "station": {"tele_station_name": {"th": name}, "tele_station_lat": 14.0, "tele_station_long": 100.5},
            "river_name": river, "storage_percent": str(pct), "situation_level": level,
            "waterlevel_msl": msl, "waterlevel_msl_previous": prev, "waterlevel_datetime": ts}


def rain(province, mm):
    return {"geocode": {"province_name": {"th": province}}, "station": {"tele_station_name": {"th": "ฝน"}}, "rain_24h": str(mm)}


def snapshot(gauges, rains=()):
    return {"waterlevel": {"data": {"data": list(gauges)}}, "rain": {"data": {"data": list(rains)}}}


def test_gauges_drop_stale_and_station_codes():
    out = pf.parse_gauges([gauge("สุพรรณบุรี", 5, 120), gauge("สุพรรณบุรี", 5, 130, ts=OLD)], now=NOW)
    assert len(out) == 1 and out[0]["name"] == "สะพาน" and out[0]["trend"] == 1


def test_levels():
    ps = {p["province"]: p for p in pf.build(snapshot([
        *[gauge("สุพรรณบุรี", 5, 120)] * 3,                   # three of three gauges over the bank: critical
        gauge("นครปฐม", 5, 110, msl="10.00", prev="10.00"),   # one over the bank, steady: flood
        gauge("พิจิตร", 5, 110),                               # one over the bank and rising: still flood
        gauge("ชัยนาท", 4, 80),                               # its only gauge high: watch
        gauge("กาญจนบุรี", 4, 80), *[gauge("กาญจนบุรี", 3, 50)] * 9,   # one high gauge of ten: normal
        gauge("ลำปาง", 3, 50),                                # normal
    ], [rain("เชียงราย", 95)]), highways=[{"province": "ปราจีนบุรี", "active": True, "lat": 14, "lng": 101}]
        + [{"province": "นครนายก", "active": True, "lat": 14.2, "lng": 101.2}] * 5, now=NOW)}
    assert ps["สุพรรณบุรี"]["level"] == "critical"
    assert ps["นครปฐม"]["level"] == "flood"
    assert ps["พิจิตร"]["level"] == "flood"
    assert ps["ชัยนาท"]["level"] == "watch"
    assert ps["กาญจนบุรี"]["level"] == "normal"
    assert ps["เชียงราย"]["level"] == "watch"          # rain over 90 mm
    assert ps["ปราจีนบุรี"]["level"] == "flood"        # a flooded highway
    assert ps["นครนายก"]["level"] == "critical"        # five flooded highways
    assert ps["ลำปาง"]["level"] == "normal" and ps["ลำปาง"]["summary"] == "ระดับน้ำปกติ"
    first = pf.build(snapshot([gauge("สุพรรณบุรี", 5, 120), gauge("ลำปาง", 3, 50)]), [], now=NOW)[0]
    assert first["province"] == "สุพรรณบุรี" and "น้ำล้นตลิ่ง 1 จุด" in first["summary"]


def test_facts_leave_out_normal_provinces():
    ps = pf.build(snapshot([gauge("สุพรรณบุรี", 5, 120), gauge("ลำปาง", 3, 50)]), [], now=NOW)
    facts = pf._facts(ps)
    assert [f["province"] for f in facts] == ["สุพรรณบุรี"]
    assert facts[0]["gauges"][0]["trend"] == "ขึ้น"


def test_reports_are_placed_and_raise_the_level():
    snap = snapshot([gauge("ลำปาง", 3, 50), gauge("สุพรรณบุรี", 3, 50)])
    snap["waterlevel"]["data"]["data"][1]["station"].update(tele_station_lat=14.47, tele_station_long=100.12)
    reports = [{"title": "น้ำท่วมหน้าตลาด", "text": "", "lat": 14.5, "lng": 100.1, "ts": NOW}] * 5   # nearest: Suphan Buri
    reports += [{"title": "น้ำท่วม อ.เมืองลำปาง", "text": "", "lat": 14.5, "lng": 100.1, "ts": NOW}] * 2   # named
    ps = {p["province"]: p for p in pf.build(snap, [], reports, now=NOW)}
    assert ps["สุพรรณบุรี"]["counts"]["reports"] == 5 and ps["สุพรรณบุรี"]["level"] == "flood"
    assert ps["ลำปาง"]["counts"]["reports"] == 2 and ps["ลำปาง"]["level"] == "watch"
