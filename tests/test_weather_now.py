from backend.water import weather_now


def _entry():
    return {
        "time": "2026-10-18T05:00:00Z",
        "data": {
            "instant": {"details": {"air_temperature": 21.5, "relative_humidity": 80, "wind_speed": 9.2}},
            "next_1_hours": {"summary": {"symbol_code": "clearsky_day"}, "details": {"precipitation_amount": 0}},
        },
    }


def test_get_reports_wind_speed_and_temp(monkeypatch):
    monkeypatch.setattr(weather_now, "_series", lambda lat, lng: [_entry()])
    monkeypatch.setattr(weather_now, "_place", lambda lat, lng: (13.76, 100.5))
    out = weather_now.get()
    assert out["wind_speed"] == 9.2
    assert out["temp"] == 21.5
