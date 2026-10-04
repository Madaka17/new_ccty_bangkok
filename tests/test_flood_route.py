"""Flood-avoiding routes: the line maths, and that a flooded spot on the route is sent to Valhalla to avoid."""
from backend.traffic import flood_route as fr


def _encode(pts, precision=6):
    out, plat, plng = [], 0, 0
    for lat, lng in pts:
        ilat, ilng = round(lat * 10 ** precision), round(lng * 10 ** precision)
        for d in (ilat - plat, ilng - plng):
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        plat, plng = ilat, ilng
    return "".join(out)


STRAIGHT = [(13.70, 100.50), (13.70, 100.55), (13.70, 100.60)]       # west to east, about 10.8 km
DETOUR = [(13.70, 100.50), (13.73, 100.55), (13.70, 100.60)]
A, B = {"lat": 13.70, "lng": 100.50}, {"lat": 13.70, "lng": 100.60}


def _trip(pts, name, toll=False):
    return {"summary": {"length": 11.0, "time": 900},
            "legs": [{"shape": _encode(pts), "maneuvers": [
                {"street_names": [name], "length": 11.0, "begin_shape_index": 0, "end_shape_index": len(pts) - 1,
                 **({"toll": True} if toll else {})}]}]}


def test_decode_round_trip():
    assert [tuple(round(x, 5) for x in p) for p in fr.decode(_encode(DETOUR))] == DETOUR


def test_line_near_and_along():
    line = fr.Line(STRAIGHT)
    d, along = line.near(13.7005, 100.55, 0.12)
    assert d < 0.07 and 5.0 < along < 5.9
    assert line.near(13.72, 100.55, 0.12) is None


def test_plan_avoids_flood_on_route(monkeypatch):
    calls = []
    water = [{"lat": 13.7002, "lng": 100.55, "name": "ถนนตรง", "source": "เซ็นเซอร์", "depth_cm": 30, "avoid": True}]

    def valhalla(self, a, b, avoid):
        calls.append(list(avoid))
        return [_trip(DETOUR, "ถนนอ้อม")] if avoid else [_trip(STRAIGHT, "ถนนตรง")]
    monkeypatch.setattr(fr.FloodRouter, "_valhalla", valhalla)
    r = fr.FloodRouter(hazards=lambda: water).plan(A, B)
    assert len(calls) == 2 and calls[1][0]["name"] == "ถนนตรง"
    assert r["roads"][0]["name"] == "ถนนอ้อม" and not r["flood_on_route"]
    assert r["avoided"][0]["name"] == "ถนนตรง" and "waypoints=" in r["google_maps"]


def test_water_under_an_expressway_does_not_count(monkeypatch):
    water = [{"lat": 13.7002, "lng": 100.55, "name": "ใต้ทางด่วน", "source": "Longdo", "avoid": True}]
    monkeypatch.setattr(fr.FloodRouter, "_valhalla", lambda self, a, b, avoid: [_trip(STRAIGHT, "ทางพิเศษศรีรัช", toll=True)])
    r = fr.FloodRouter(hazards=lambda: water).plan(A, B)
    assert not r["flood_on_route"] and not r["avoided"] and "waypoints" not in r["google_maps"]


def test_shallow_water_is_reported_not_avoided(monkeypatch):
    water = [{"lat": 13.7002, "lng": 100.55, "name": "น้ำขัง", "source": "กล้อง", "depth_cm": 5, "avoid": False}]
    monkeypatch.setattr(fr.FloodRouter, "_valhalla", lambda self, a, b, avoid: [_trip(STRAIGHT, "ถนนตรง")])
    r = fr.FloodRouter(hazards=lambda: water).plan(A, B)
    assert r["wet_on_route"][0]["name"] == "น้ำขัง" and not r["avoided"]


def test_jams_on_the_route_are_listed(monkeypatch):
    jams = [{"road": "ถนนตรง", "lat": 13.7001, "lng": 100.56, "km": 1.5},
            {"road": "ถนนอื่น", "lat": 13.7001, "lng": 100.57, "km": 2.0}]     # crosses the route, not on it
    monkeypatch.setattr(fr.FloodRouter, "_valhalla", lambda self, a, b, avoid: [_trip(STRAIGHT, "ถนนตรง")])
    r = fr.FloodRouter(jams=lambda: jams).plan(A, B)
    assert [j["road"] for j in r["jams"]] == ["ถนนตรง"]
    assert r["minutes"][0] == round(15 + 1.5 * fr.JAM_MIN_PER_KM)


def test_clean_place_names():
    assert fr.FloodRouter.clean("แถวอนุสาวรีย์ชัย") == "อนุสาวรีย์ชัยสมรภูมิ"
    assert fr.FloodRouter.clean("ย่านสีลม ครับ") == "สีลม"
    assert fr.FloodRouter.is_here("ที่นี่") and fr.FloodRouter.is_here("")


# ---------------------------------------------------------------- the real flood sources (regression: flood_roads.status()
# keeps its flooded stations under "wet", not "items"; reading "items" failed every route's flood check)
def _flood_roads_with(items):
    """A FloodRoads whose status() runs on these stations, without its disk cache or network."""
    import threading
    from backend.water.flood_service import FloodRoads
    f = FloodRoads.__new__(FloodRoads)
    f.lock, f.items, f.updated_at, f.feed_time, f.error = threading.Lock(), items, 0, 0, None
    return f


def _station(status, cm, lat=13.7002, lng=100.55):
    return {"status": status, "level_cm": cm, "lat": lat, "lng": lng, "district": "คลองเตย", "short_name": "ถนนตรง",
            "road": "ถนนพระราม 4", "name": "ถนนพระราม 4 หน้าตลาด"}


def test_sensor_spots_read_the_real_status():
    st = _flood_roads_with([_station("flood", 32), _station("slight", 8), _station("normal", 0)]).status()
    spots = fr.sensor_spots(st)
    assert [(s["depth_cm"], s["avoid"]) for s in spots] == [(32, True), (8, False)]
    assert spots[0]["name"] == "ถนนตรง" and spots[0]["source"] == "เซ็นเซอร์น้ำ กทม."


def test_gather_keeps_the_sources_that_answer():
    def down():
        raise KeyError("items")
    spots, missing = fr.gather([("a", lambda: [{"lat": 1, "lng": 2}]), ("b", down)])
    assert spots == [{"lat": 1, "lng": 2}] and missing == ["b"]
    assert fr.gather([("b", down)]) == (None, ["b"])


def test_route_through_real_sensor_avoids_it_and_says_what_was_missing(monkeypatch):
    sensors = _flood_roads_with([_station("flood", 32)])

    def down():
        raise TimeoutError("hdms")
    hazards = lambda: fr.gather([("เซ็นเซอร์น้ำ กทม.", lambda: fr.sensor_spots(sensors.status())), ("กรมทางหลวง", down)])
    monkeypatch.setattr(fr.FloodRouter, "_valhalla",
                        lambda self, a, b, avoid: [_trip(DETOUR, "ถนนอ้อม")] if avoid else [_trip(STRAIGHT, "ถนนตรง")])
    r = fr.FloodRouter(hazards=hazards).plan(A, B)
    assert r["avoided"] and r["avoided"][0]["source"] == "เซ็นเซอร์น้ำ กทม."
    assert r["flood_checked"] is False and r["flood_missing"] == ["กรมทางหลวง"]

    from backend.agents import chat_service as cs
    text = "\n".join(cs.route_context(r))
    assert "ตรวจน้ำท่วมได้ไม่ครบ" in text and "กรมทางหลวง" in text and "ไม่พบจุดน้ำท่วม" not in text


def test_no_flood_source_means_not_checked(monkeypatch):
    def down():
        raise OSError("down")
    monkeypatch.setattr(fr.FloodRouter, "_valhalla", lambda self, a, b, avoid: [_trip(STRAIGHT, "ถนนตรง")])
    r = fr.FloodRouter(hazards=lambda: fr.gather([("เซ็นเซอร์น้ำ กทม.", down)])).plan(A, B)
    assert r["flood_checked"] is False and r["flood_missing"] == []
    from backend.agents import chat_service as cs
    text = "\n".join(cs.route_context(r))
    assert "ห้ามบอกว่าอ้อมน้ำท่วม" in text and "ไม่พบจุดน้ำท่วม" not in text
    assert "เส้นนี้ไม่ได้อ้อมจุดน้ำท่วมใด" in text
