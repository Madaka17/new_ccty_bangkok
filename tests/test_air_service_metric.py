from datetime import datetime

import backend.water.air_service as air
from backend.water.air_service import BKK_TZ, _load_air4thai

NOW = int(datetime(2026, 11, 26, 14, 30, tzinfo=BKK_TZ).timestamp())
BMA_POINT = {"lat": 13.75, "lng": 100.5}


def pcd_station(sid="50t", lat=13.75, lng=100.5, pm24=23.5):
    return {
        "stationID": sid, "nameTH": "จุฬา", "areaTH": "แขวงวังใหม่,เขตปทุมวัน,กรุงเทพมหานคร",
        "lat": str(lat), "long": str(lng),
        "AQILast": {"PM25": {"value": str(pm24)}, "PM10": {"value": "40"},
                    "date": "2026-11-26", "time": "14:00"},
    }


def fake_get(monkeypatch, stations, hourly_pm25):
    main = {"stations": stations}
    hourly = {"stations": [{"stationID": s["stationID"],
                            "data": [{"PM25": hourly_pm25, "PM10": 41, "DATETIMEDATA": "2026-11-26 14:00"}]}
                           for s in stations]}

    def _get(url, body=None):
        return main if url == air.AIR4THAI_URL else hourly

    monkeypatch.setattr(air, "_get", _get)


def test_pcd_station_shows_the_24h_mean_and_keeps_the_hourly_value(monkeypatch):
    fake_get(monkeypatch, [pcd_station(pm24=23.5)], hourly_pm25=35.5)
    items = _load_air4thai(NOW, skip_bma=False)
    assert len(items) == 1
    it = items[0]
    assert it["pm25"] == 23.5
    assert it["level"] == "good"
    assert it["label"] == "ดี"
    assert it["pm25_24h"] == 23.5
    assert it["pm25_1h"] == 35.5


def test_pcd_station_falls_back_to_hourly_when_no_24h_mean(monkeypatch):
    fake_get(monkeypatch, [pcd_station(pm24=None)], hourly_pm25=35.5)
    items = _load_air4thai(NOW, skip_bma=False)
    assert items[0]["pm25"] == 35.5
    assert items[0]["pm25_1h"] == 35.5


def test_pcd_station_next_to_a_bma_station_is_dropped(monkeypatch):
    fake_get(monkeypatch, [pcd_station(lat=13.75 + 0.0009)], hourly_pm25=35.5)
    assert _load_air4thai(NOW, skip_bma=True, bma_items=[BMA_POINT]) == []


def test_pcd_station_two_km_from_a_bma_station_is_kept(monkeypatch):
    fake_get(monkeypatch, [pcd_station(lat=13.75 + 0.018)], hourly_pm25=35.5)
    items = _load_air4thai(NOW, skip_bma=True, bma_items=[BMA_POINT])
    assert [i["id"] for i in items] == ["pcd:50t"]
