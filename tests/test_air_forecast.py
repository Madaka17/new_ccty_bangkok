from datetime import datetime, timedelta, timezone

from backend.water.air_forecast import build

BKK = timezone(timedelta(hours=7))


def hourly(first, values):
    """Open-Meteo shaped hourly block: local time strings, one value per hour."""
    return {"hourly": {
        "time": [(first + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00") for i in range(len(values))],
        "pm2_5": values,
    }}


def test_ratio_scales_to_stations():
    model = hourly(datetime(2026, 10, 17, 21), [20, 40])
    out = build(model, 30.0, datetime(2026, 10, 17, 21, 0))
    assert out["ratio"] == 1.5
    assert out["hours"][0]["pm25"] == 30.0
    assert out["hours"][1]["pm25"] == 60.0


def test_ratio_is_clamped():
    model = hourly(datetime(2026, 10, 17, 21), [10])
    out = build(model, 100.0, datetime(2026, 10, 17, 21, 0))
    assert out["ratio"] == 2.0


def test_no_station_average_keeps_model():
    model = hourly(datetime(2026, 10, 17, 21), [20, 40])
    out = build(model, None, datetime(2026, 10, 17, 21, 0))
    assert out["ratio"] == 1.0
    assert out["hours"][0]["pm25"] == 20.0


def test_days_are_labelled_and_banded():
    model = hourly(datetime(2026, 10, 17, 0), [10] * 24 + [30] * 24 + [80] * 24)
    out = build(model, None, datetime(2026, 10, 17, 0, 0))
    days = out["days"]
    assert [d["label"] for d in days] == ["วันนี้", "พรุ่งนี้", "มะรืนนี้"]
    assert [d["date"] for d in days] == ["2026-10-17", "2026-10-18", "2026-10-19"]
    assert [d["level"] for d in days] == ["very_good", "moderate", "very_unhealthy"]
    assert days[1]["label_th"] == "ปานกลาง"
    assert days[1]["mean"] == 30.0
    assert days[1]["max"] == 30.0


def test_past_hours_and_nulls_are_dropped():
    model = hourly(datetime(2026, 10, 17, 20), [5, None, 20])
    out = build(model, None, datetime(2026, 10, 17, 21, 0))
    assert len(out["hours"]) == 1
    assert out["hours"][0]["pm25"] == 20.0
    assert out["hours"][0]["t"] == int(datetime(2026, 10, 17, 22, tzinfo=BKK).timestamp())
