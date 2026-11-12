"""Road flood classes must follow the published thresholds exactly (road_service.py docstring)."""
import threading
import types

import pytest

from backend.traffic.road_service import GAUGE_BANDS, RAIN_BANDS, ROAD_WATER_BANDS, RoadRisk, _classify, _norm


@pytest.mark.parametrize("cm, cls", [
    (0, 0), (5.0, 0),          # สนน. กทม.: <= 5 cm normal
    (5.1, 1), (10.0, 1),       # 5-10 cm slight
    (10.1, 2), (20.0, 2),      # > 10 cm flooded, ปภ. < 20 passable
    (20.1, 3), (60.0, 3),      # avoid
    (60.1, 4), (150, 4),       # do not drive through
])
def test_road_water_bands(cm, cls):
    assert _classify(cm, ROAD_WATER_BANDS)[0] == cls


@pytest.mark.parametrize("mm, cls", [
    (0, 0), (0.1, 0),
    (0.2, 1), (10.0, 1),
    (10.1, 2), (35.0, 2),
    (35.1, 3), (90.0, 3),
    (90.1, 4), (300, 4),
])
def test_rain_bands(mm, cls):
    assert _classify(mm, RAIN_BANDS)[0] == cls


@pytest.mark.parametrize("pct, cls", [(0, 0), (80.0, 0), (80.1, 2), (100.0, 2), (100.1, 4), (255, 4)])
def test_gauge_bands(pct, cls):
    assert _classify(pct, GAUGE_BANDS)[0] == cls


def test_unknown_reading_has_no_class():
    assert _classify(None, RAIN_BANDS) == (None, None, None)


def test_classify_returns_label_and_source():
    cls, label, source = _classify(70, ROAD_WATER_BANDS)
    assert (cls, label) == (4, "ห้ามขับผ่าน")
    assert source.startswith("ปภ.")


@pytest.mark.parametrize("a, b", [("ถนนสุขุมวิท", "สุขุมวิท"), ("ถ.พระราม 4", "พระราม4"), ("ซ.อ่อนนุช 46", "อ่อนนุช46")])
def test_norm_strips_prefixes_and_spaces(a, b):
    assert _norm(a) == _norm(b)


# ---------------------------------------------------------------- build(): characterization of the joined rows
class _Flood:
    def __init__(self, items):
        self.lock = threading.Lock()
        self.items = items


EXPECTED_ORDER = ['ถนนสุขุมวิท', 'ถนนบางนา', 'ถนนเลียบ', 'ถนนไกล']
EXPECTED_ROWS = {'ถนนบางนา': {'basis': 'inferred',
              'class': 1,
              'district': 'บางนา',
              'flood_at': None,
              'flood_cm': None,
              'flood_started': None,
              'flood_status': None,
              'flood_trend': None,
              'flow': 30.0,
              'gauge_at': 'เจ้าพระยา',
              'gauge_class': 4,
              'gauge_kind': 'river',
              'gauge_km': 2.2,
              'gauge_label': 'ล้นตลิ่ง',
              'gauge_level': 'overflow',
              'gauge_pct': 105,
              'gauge_source': 'คลังข้อมูลน้ำฯ: 100% ของตลิ่งขึ้นไป',
              'lat': 13.6,
              'length_km': 3.0,
              'level': 'watch',
              'level_th': 'เฝ้าระวัง',
              'lng': 100.7,
              'measured': False,
              'province': 'กรุงเทพมหานคร',
              'rain_24h': 100,
              'rain_at': 'สถานีบางนา',
              'rain_class': 4,
              'rain_km': 2.2,
              'rain_label': 'ฝนหนักมาก',
              'rain_level': 'very_heavy',
              'rain_source': 'กรมอุตุฯ: 90.1 มม. ขึ้นไป',
              'red_km': None,
              'red_pct': 0,
              'road': 'ถนนบางนา',
              'sensors': 0,
              'traffic_level': 'free',
              'water_class': None,
              'water_label': None,
              'water_source': None,
              'wet_sensors': 0},
 'ถนนสุขุมวิท': {'basis': 'sensor',
                 'class': 4,
                 'district': 'คลองเตย',
                 'flood_at': 'สุขุมวิท 21',
                 'flood_cm': 70,
                 'flood_started': '10:00',
                 'flood_status': 'flood',
                 'flood_trend': 'rising',
                 'flow': 12.5,
                 'gauge_at': None,
                 'gauge_class': None,
                 'gauge_kind': None,
                 'gauge_km': None,
                 'gauge_label': None,
                 'gauge_level': None,
                 'gauge_pct': None,
                 'gauge_source': None,
                 'lat': 13.7,
                 'length_km': 5.0,
                 'level': 'closed',
                 'level_th': 'ห้ามขับผ่าน',
                 'lng': 100.6,
                 'measured': True,
                 'province': 'กรุงเทพมหานคร',
                 'rain_24h': None,
                 'rain_at': None,
                 'rain_class': None,
                 'rain_km': None,
                 'rain_label': None,
                 'rain_level': None,
                 'rain_source': None,
                 'red_km': 2.0,
                 'red_pct': 40,
                 'road': 'ถนนสุขุมวิท',
                 'sensors': 2,
                 'traffic_level': 'heavy',
                 'water_class': 4,
                 'water_label': 'ห้ามขับผ่าน',
                 'water_source': 'ปภ.: 60-80 ซม. เฉพาะรถยกสูง · เกิน 80 ซม. ห้ามผ่านเด็ดขาด',
                 'wet_sensors': 2},
 'ถนนเลียบ': {'basis': 'both',
              'class': 1,
              'district': 'บางซื่อ',
              'flood_at': None,
              'flood_cm': 0,
              'flood_started': None,
              'flood_status': 'normal',
              'flood_trend': 'steady',
              'flow': None,
              'gauge_at': None,
              'gauge_class': None,
              'gauge_kind': None,
              'gauge_km': None,
              'gauge_label': None,
              'gauge_level': None,
              'gauge_pct': None,
              'gauge_source': None,
              'lat': 13.8,
              'length_km': 4.0,
              'level': 'watch',
              'level_th': 'เฝ้าระวัง',
              'lng': 100.5,
              'measured': True,
              'province': 'กรุงเทพมหานคร',
              'rain_24h': 40,
              'rain_at': 'สถานีปากเกร็ด',
              'rain_class': 3,
              'rain_km': 1.1,
              'rain_label': 'ฝนหนัก',
              'rain_level': 'heavy',
              'rain_source': 'กรมอุตุฯ: 35.1-90.0 มม.',
              'red_km': None,
              'red_pct': 0,
              'road': 'ถนนเลียบ',
              'sensors': 1,
              'traffic_level': None,
              'water_class': 0,
              'water_label': 'ปกติ',
              'water_source': 'สนน. กทม.: ไม่เกิน 5 ซม.',
              'wet_sensors': 0},
 'ถนนไกล': {'basis': 'none',
            'class': 0,
            'district': None,
            'flood_at': None,
            'flood_cm': None,
            'flood_started': None,
            'flood_status': None,
            'flood_trend': None,
            'flow': None,
            'gauge_at': None,
            'gauge_class': None,
            'gauge_kind': None,
            'gauge_km': None,
            'gauge_label': None,
            'gauge_level': None,
            'gauge_pct': None,
            'gauge_source': None,
            'lat': 14.2,
            'length_km': 2.0,
            'level': 'none',
            'level_th': 'ปกติ',
            'lng': 100.9,
            'measured': False,
            'province': None,
            'rain_24h': None,
            'rain_at': None,
            'rain_class': None,
            'rain_km': None,
            'rain_label': None,
            'rain_level': None,
            'rain_source': None,
            'red_km': None,
            'red_pct': 0,
            'road': 'ถนนไกล',
            'sensors': 0,
            'traffic_level': None,
            'water_class': None,
            'water_label': None,
            'water_source': None,
            'wet_sensors': 0}}


def _risk():
    sensor = dict(status="normal", level_cm=0, trend="steady", started=None)
    floods = [
        {**sensor, "code": "a", "road": "สุขุมวิท", "lat": 13.90, "lng": 100.40, "level_cm": 70, "status": "flood",
         "district": "คลองเตย", "short_name": "สุขุมวิท 21", "trend": "rising", "started": "10:00"},
        {**sensor, "code": "b", "road": "ถนนอื่น", "lat": 13.7005, "lng": 100.6005, "level_cm": 10, "status": "slight",
         "district": "วัฒนา", "short_name": "ข"},
        {**sensor, "code": "c", "road": "สุขุมวิท", "lat": 13.70, "lng": 100.60, "level_cm": 99, "status": "offline"},
        {**sensor, "code": "e", "road": "ถนนอื่น", "lat": 13.612, "lng": 100.70, "district": "บางนา", "short_name": "จ"},
        {**sensor, "code": "f", "road": "ถนนเลียบ", "lat": 13.95, "lng": 100.30, "level_cm": None, "district": "บางซื่อ"},
        {**sensor, "code": "g", "road": "ถนนไม่มีพิกัด", "lat": None, "lng": None},
    ]
    roads = [
        {"name": "ถนนสุขุมวิท", "lat": 13.70, "lng": 100.60, "length_km": 5.0, "red_pct": 40, "flow": 12.5, "red_km": 2.0,
         "level": "heavy", "hotspots": [{"lat": 13.705, "lon": 100.605}]},
        {"name": "ถนนบางนา", "lat": 13.60, "lng": 100.70, "length_km": 3.0, "flow": 30.0, "level": "free"},
        {"name": "ถนนไกล", "lat": 14.20, "lng": 100.90, "length_km": 2.0},
        {"name": "ถนนเลียบ", "lat": 13.80, "lng": 100.50, "length_km": 4.0, "red_pct": 0},
        {"name": "ซอยสั้น", "lat": 13.70, "lng": 100.61, "length_km": 0.5},
        {"name": "ถนนไม่มีพิกัด", "length_km": 4.0},
    ]
    rain = [
        {"name": "สถานีบางนา", "lat": 13.62, "lng": 100.70, "rain_24h": 100, "level": "very_heavy", "province": "กรุงเทพมหานคร",
         "district": "บางนา"},
        {"name": "สถานีปากเกร็ด", "lat": 13.81, "lng": 100.50, "rain_24h": 40, "level": "heavy", "province": "นนทบุรี", "district": "ปากเกร็ด"},
        {"name": "สถานีไกลมาก", "lat": 15.0, "lng": 101.5, "rain_24h": 5},
        {"name": "ไม่มีพิกัด", "rain_24h": 5},
    ]
    water = types.SimpleNamespace(
        rain_stations=lambda: rain,
        get_summary=lambda: {"river": [{"name": "เจ้าพระยา", "lat": 13.60, "lng": 100.72, "storage_pct": 105, "level": "overflow",
                                         "province": "สมุทรปราการ", "district": "พระประแดง"}],
                             "canals": [{"name": "คลองไม่มีพิกัด", "storage_pct": 50}]})
    traffic = types.SimpleNamespace(get_roads=lambda limit: roads)
    return RoadRisk(traffic=traffic, flood=_Flood(floods), water=water)


def test_build_joins_sensors_rain_and_gauges_per_road():
    rows = _risk().build()
    # order: class, then flood cm, rain, gauge, name
    assert [r["road"] for r in rows] == EXPECTED_ORDER
    assert {r["road"]: r for r in rows} == EXPECTED_ROWS


def test_build_without_sources_is_empty():
    assert RoadRisk().build() == []
