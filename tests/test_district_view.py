"""One Bangkok district at a glance: name handling, each section from fake sources, empty sections."""
import time
from urllib.parse import quote

from backend.traffic import district_view
from backend.traffic.district_view import DISTRICTS, build

NOW = 1_781_000_000  # any fixed epoch: the tests pass sources, never the clock


def air_item(area, pm25, province="กรุงเทพมหานคร"):
    return {"area": area, "province": province, "pm25": pm25, "level": "moderate", "label": "ปานกลาง",
            "color": "#FFD400", "name": area}


def sources(**over):
    base = {
        "air": {"items": []},
        "flood": {"wet": [], "items": []},
        "traffy": {"items": [], "updated_at": None},
        "cameras": [],
        "area_traffic": {"ready": True, "provinces": []},
        "incidents": {"incidents": [], "closures": []},
        "calendar": [],
    }
    base.update(over)
    return {k: (lambda v=v: v) for k, v in base.items()}


def test_district_list_is_fifty_bangkok_names_without_prefix():
    assert len(DISTRICTS) == 50
    assert "ดินแดง" in DISTRICTS and "วัฒนา" in DISTRICTS
    assert not any(d.startswith("เขต") for d in DISTRICTS)


def test_name_with_or_without_prefix_and_url_encoded_is_the_same():
    a = build("เขตดินแดง", sources())
    b = build("ดินแดง", sources())
    c = build(quote("เขตดินแดง"), sources())
    assert a is not None and a["district"] == "ดินแดง"
    assert b["district"] == "ดินแดง"
    assert c["district"] == "ดินแดง"


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
    out = build("ดินแดง", sources(air={"items": []}))
    assert out["air"] is None


def test_cameras_are_filtered_by_district():
    rows = [
        {"camid": "c1", "title": "A", "road": "ดินแดง", "district": "ดินแดง", "level": 2, "total": 5, "status": "ok", "x": 1},
        {"camid": "c2", "title": "B", "road": "พระราม 9", "district": "ห้วยขวาง", "level": 1, "total": 3, "status": "ok"},
    ]
    out = build("ดินแดง", sources(cameras=rows))
    assert [c["camid"] for c in out["cameras"]] == ["c1"]
    assert set(out["cameras"][0]) == {"camid", "title", "road", "level", "total", "status"}
    assert build("ดินแดง", sources(cameras=[]))["cameras"] == []


def test_incidents_and_closures_match_with_khet_prefix():
    ev = {"incidents": [
            {"kind": "accident", "title": "อุบัติเหตุ", "latitude": 13.7, "longitude": 100.5, "amphoe": "เขตดินแดง"},
            {"kind": "breakdown", "title": "รถเสีย", "latitude": 13.7, "longitude": 100.5, "amphoe": "ราชเทวี"}],
          "closures": [
            {"kind": "closed", "title": "ปิดถนน", "latitude": 13.7, "longitude": 100.5, "amphoe": "ดินแดง"},
            {"kind": "closed", "title": "ปิดอื่น", "latitude": 13.7, "longitude": 100.5, "amphoe": "เขตวัฒนา"}]}
    out = build("ดินแดง", sources(incidents=ev))
    assert [i["title"] for i in out["incidents"]] == ["อุบัติเหตุ"]
    assert [c["title"] for c in out["closures"]] == ["ปิดถนน"]


def test_flood_points_and_max_for_district():
    wet = [
        {"short_name": "ถนนดินแดง", "road": "ดินแดง", "district": "ดินแดง", "level_cm": 12, "status": "slight"},
        {"short_name": "ถนนอื่น", "road": "อื่น", "district": "ห้วยขวาง", "level_cm": 40, "status": "flood"},
        {"short_name": "ถนนดินแดง 2", "road": "ดินแดง", "district": "ดินแดง", "level_cm": 25, "status": "flood"},
    ]
    out = build("ดินแดง", sources(flood={"wet": wet, "items": wet}))
    assert len(out["flood"]["points"]) == 2
    assert out["flood"]["max_cm"] == 25


def test_no_wet_road_sensor_gives_flood_none():
    assert build("ดินแดง", sources(flood={"wet": [], "items": []}))["flood"] is None


def test_traffy_reports_last_six_hours_by_district_with_locate_fallback():
    now = time.time()
    items = [
        {"id": "t1", "ts": int(now - 600), "district": "ดินแดง", "text": "น้ำท่วม", "lat": 13.76, "lng": 100.55},
        {"id": "t2", "ts": int(now - 600), "district": None, "text": "น้ำขัง", "lat": 13.7, "lng": 100.5},
        {"id": "t3", "ts": int(now - 20 * 3600), "district": "ดินแดง", "text": "เก่า", "lat": 13.76, "lng": 100.55},
        {"id": "t4", "ts": int(now - 600), "district": "ห้วยขวาง", "text": "อื่น", "lat": 13.7, "lng": 100.5},
    ]
    src = sources(traffy={"items": items, "updated_at": int(now)})
    src["locate"] = lambda lat, lng: ("กรุงเทพมหานคร", "ดินแดง") if lat == 13.7 else ("", "")
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
    out = build("ดินแดง", sources(area_traffic=area))
    assert out["traffic"] == {"score": 80, "level": "คล่องตัว"}
    assert build("วัฒนา", sources(area_traffic=area))["traffic"] is None
    assert build("ดินแดง", sources(area_traffic={"ready": False, "provinces": []}))["traffic"] is None


def test_events_filtered_by_district_and_missing_source_is_empty():
    cal = [{"id": "e1", "district": "ดินแดง", "title": "งาน"}, {"id": "e2", "district": "วัฒนา", "title": "อื่น"}]
    assert [e["id"] for e in build("ดินแดง", sources(calendar=cal))["events"]] == ["e1"]
    assert build("ดินแดง", {})["events"] == []


def test_result_shape_and_missing_sources_do_not_fail():
    out = build("ดินแดง", {})
    assert out["district"] == "ดินแดง"
    assert isinstance(out["updated_at"], int)
    assert out["air"] is None and out["flood"] is None and out["reports"] is None and out["traffic"] is None
    assert out["cameras"] == [] and out["incidents"] == [] and out["closures"] == [] and out["events"] == []
