"""One Bangkok district at a glance: name handling, each section from fake sources, empty and down feeds."""
import time
from urllib.parse import quote

from backend.traffic.district_view import DISTRICTS, build

NOW = 1_781_000_000  # any fixed epoch: the tests pass sources, never the clock


def air_item(area, pm25, province="กรุงเทพมหานคร"):
    return {"area": area, "province": province, "pm25": pm25, "level": "moderate", "label": "ปานกลาง",
            "color": "#FFD400", "name": area}


def station(name, district, status, level, road="ถนนทดสอบ"):
    return {"short_name": name, "road": road, "district": district, "status": status, "level_cm": level}


def sources(**over):
    base = {
        "air": {"items": []},
        "flood": {"updated_at": NOW, "error": None, "items": []},
        "traffy": {"items": [], "updated_at": None},
        "cameras": [],
        "area_traffic": {"ready": True, "provinces": []},
        "incidents": {"updated_at": NOW, "incidents": [], "closures": []},
        "calendar": [],
    }
    base.update(over)
    return {k: (lambda v=v: v) for k, v in base.items()}


def test_district_list_is_fifty_bangkok_names_without_prefix():
    assert len(DISTRICTS) == 50
    assert "ดินแดง" in DISTRICTS and "วัฒนา" in DISTRICTS
    assert not any(d.startswith("เขต") for d in DISTRICTS)


def test_name_with_or_without_prefix_and_url_encoded_is_the_same():
    assert build("เขตดินแดง", sources())["district"] == "ดินแดง"
    assert build("ดินแดง", sources())["district"] == "ดินแดง"
    assert build(quote("เขตดินแดง"), sources())["district"] == "ดินแดง"


def test_unknown_district_gives_none():
    assert build("ไม่มีเขตนี้", sources()) is None
    assert build("", sources()) is None


def test_air_average_matches_stations_in_district():
    src = sources(air={"items": [
        air_item("ริมถนนดินแดง เขตดินแดง", 20.0),
        air_item("เขตดินแดง", 30.0),
        air_item("เขตราชเทวี", 99.0),          # another district
        air_item("เขตดินแดง", None),           # no reading: not counted
    ]})
    out = build("ดินแดง", src)
    assert out["air"]["points"] == 2
    assert out["air"]["pm25"] == 25.0
    assert out["air"]["level"] == "good"      # 25.0 is still the "good" band (<= 25)
    assert out["air"]["label"] == "ดี"


def test_air_uses_the_last_khet_in_the_area():
    src = sources(air={"items": [air_item("เขตดินแดง ซอยเขตราชเทวี", 10.0)]})
    assert build("ราชเทวี", src)["air"]["points"] == 1
    assert build("ดินแดง", src)["air"] is None


def test_empty_air_source_gives_air_none():
    assert build("ดินแดง", sources(air={"items": []}))["air"] is None


def test_air_station_outside_bangkok_with_same_khet_name_is_excluded():
    src = sources(air={"items": [air_item("เขตดินแดง", 80.0, province="นนทบุรี")]})
    assert build("ดินแดง", src)["air"] is None


def test_cameras_are_filtered_by_district():
    rows = [
        {"camid": "c1", "title": "A", "road": "ดินแดง", "district": "ดินแดง", "level": 2, "total": 5, "status": "ok", "x": 1},
        {"camid": "c2", "title": "B", "road": "พระราม 9", "district": "ห้วยขวาง", "level": 1, "total": 3, "status": "ok"},
    ]
    out = build("ดินแดง", sources(cameras=rows))
    assert [c["camid"] for c in out["cameras"]] == ["c1"]
    assert set(out["cameras"][0]) == {"camid", "title", "road", "level", "total", "status"}
    assert build("ดินแดง", sources(cameras=[]))["cameras"] == []


def test_failed_camera_feed_gives_none():
    assert build("ดินแดง", sources(cameras=None))["cameras"] is None


def test_incidents_and_closures_match_with_khet_prefix():
    ev = {"updated_at": NOW, "incidents": [
            {"kind": "accident", "title": "อุบัติเหตุ", "latitude": 13.7, "longitude": 100.5, "amphoe": "เขตดินแดง"},
            {"kind": "breakdown", "title": "รถเสีย", "latitude": 13.7, "longitude": 100.5, "amphoe": "ราชเทวี"}],
          "closures": [
            {"kind": "closed", "title": "ปิดถนน", "latitude": 13.7, "longitude": 100.5, "amphoe": "ดินแดง"},
            {"kind": "closed", "title": "ปิดอื่น", "latitude": 13.7, "longitude": 100.5, "amphoe": "เขตวัฒนา"}]}
    out = build("ดินแดง", sources(incidents=ev))
    assert [i["title"] for i in out["incidents"]] == ["อุบัติเหตุ"]
    assert [c["title"] for c in out["closures"]] == ["ปิดถนน"]


def test_dead_incident_feed_gives_null_and_live_empty_gives_empty_list():
    dead = build("ดินแดง", sources(incidents={"updated_at": None, "incidents": [], "closures": []}))
    assert dead["incidents"] is None and dead["closures"] is None
    assert build("ดินแดง", sources(incidents=None))["incidents"] is None
    live = build("ดินแดง", sources(incidents={"updated_at": NOW, "incidents": [], "closures": []}))
    assert live["incidents"] == [] and live["closures"] == []


def test_incident_outside_bangkok_with_same_amphoe_name_is_excluded():
    ev = {"updated_at": NOW, "incidents": [
        {"kind": "accident", "title": "นนทบุรี", "latitude": 13.8, "longitude": 100.5, "amphoe": "ดินแดง",
         "province": "นนทบุรี"}], "closures": []}
    assert build("ดินแดง", sources(incidents=ev))["incidents"] == []


def test_flood_dry_district_with_sensors_is_measured_not_null():
    feed = {"updated_at": NOW, "error": None, "items": [
        station("ถนนดินแดง", "ดินแดง", "normal", 3),
        station("ถนนดินแดง 2", "ดินแดง", "normal", 0),
        station("ถนนอื่น", "ห้วยขวาง", "flood", 40),
    ]}
    flood = build("ดินแดง", sources(flood=feed))["flood"]
    assert flood["sensors"] > 0
    assert flood["wet"] == 0
    assert flood["points"] == []


def test_flood_wet_points_and_max_for_district():
    feed = {"updated_at": NOW, "error": None, "items": [
        station("ถนนดินแดง", "ดินแดง", "slight", 12),
        station("ถนนอื่น", "ห้วยขวาง", "flood", 40),
        station("ถนนดินแดง 2", "ดินแดง", "flood", 25),
        station("ถนนดินแดง 3", "ดินแดง", "normal", 4),
    ]}
    flood = build("ดินแดง", sources(flood=feed))["flood"]
    assert flood["sensors"] == 3 and flood["wet"] == 2
    assert len(flood["points"]) == 2
    assert flood["max_cm"] == 25


def test_flood_no_sensor_or_only_offline_gives_none():
    assert build("ดินแดง", sources(flood={"updated_at": NOW, "error": None, "items": []}))["flood"] is None
    off = {"updated_at": NOW, "error": None, "items": [station("x", "ดินแดง", "offline", None)]}
    assert build("ดินแดง", sources(flood=off))["flood"] is None


def test_flood_feed_down_or_never_loaded_gives_none():
    live = [station("x", "ดินแดง", "normal", 2)]
    assert build("ดินแดง", sources(flood={"updated_at": None, "error": None, "items": live}))["flood"] is None
    assert build("ดินแดง", sources(flood={"updated_at": NOW, "error": "boom", "items": live}))["flood"] is None
    assert build("ดินแดง", sources(flood=None))["flood"] is None


def test_traffy_reports_last_six_hours_by_district_with_locate_fallback():
    now = time.time()
    items = [
        {"id": "t1", "ts": int(now - 600), "district": "ดินแดง", "text": "น้ำท่วม", "lat": 13.76, "lng": 100.55},
        {"id": "t2", "ts": int(now - 600), "district": None, "text": "น้ำขัง", "lat": 13.7, "lng": 100.5},
        {"id": "t3", "ts": int(now - 20 * 3600), "district": "ดินแดง", "text": "เก่า", "lat": 13.76, "lng": 100.55},
        {"id": "t4", "ts": int(now - 600), "district": "ห้วยขวาง", "text": "อื่น", "lat": 13.7, "lng": 100.5},
        {"id": "t5", "ts": int(now - 600), "district": None, "text": "นนทบุรี", "lat": 13.9, "lng": 100.5},
    ]
    src = sources(traffy={"items": items, "updated_at": int(now)})
    src["locate"] = lambda lat, lng: {13.7: ("กรุงเทพมหานคร", "ดินแดง"), 13.9: ("นนทบุรี", "ดินแดง")}[lat]
    out = build("ดินแดง", src)
    assert out["reports"]["count"] == 2
    assert [r["id"] for r in out["reports"]["latest"]] == ["t1", "t2"]


def test_traffy_without_data_gives_reports_none():
    assert build("ดินแดง", sources(traffy={"items": [], "updated_at": None}))["reports"] is None


def test_traffic_score_from_area_traffic_district():
    area = {"ready": True, "provinces": [
        {"code": "10", "amphoes": [{"code": "1036", "name": "ดินแดง", "flow": 80}, {"code": "1037", "name": "วัฒนา", "flow": None}]},
        {"code": "11", "amphoes": [{"code": "1101", "name": "ดินแดง", "flow": 10}]},
    ]}
    assert build("ดินแดง", sources(area_traffic=area))["traffic"] == {"score": 80, "level": "คล่องตัว"}
    assert build("วัฒนา", sources(area_traffic=area))["traffic"] is None
    assert build("ดินแดง", sources(area_traffic={"ready": False, "provinces": []}))["traffic"] is None


def test_events_filtered_by_district_and_failed_calendar_is_none():
    cal = [{"id": "e1", "district": "ดินแดง", "title": "งาน"}, {"id": "e2", "district": "วัฒนา", "title": "อื่น"},
           {"id": "e3", "district": "ดินแดง", "province": "นนทบุรี", "title": "นนทบุรี"}]
    assert [e["id"] for e in build("ดินแดง", sources(calendar=cal))["events"]] == ["e1"]
    assert build("ดินแดง", sources(calendar=None))["events"] is None


def test_missing_sources_give_null_sections_and_never_fail():
    out = build("ดินแดง", {})
    assert out["district"] == "ดินแดง"
    assert isinstance(out["updated_at"], int)
    assert out["air"] is None and out["flood"] is None and out["reports"] is None and out["traffic"] is None
    assert out["cameras"] is None and out["incidents"] is None and out["closures"] is None and out["events"] is None
