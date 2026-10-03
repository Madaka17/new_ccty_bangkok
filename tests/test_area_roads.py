"""Road cards for a picked province / district (area_roads.py), on made-up tiles."""
from shapely.geometry import box

from backend.traffic import area_roads

RED, GREEN = "FF2020", "54C00C"


def line(lat0, lng0, lat1, lng1, n):
    """n pieces of a straight line, as [(lng, lat), (lng, lat)] lists."""
    pts = [(lng0 + (lng1 - lng0) * i / n, lat0 + (lat1 - lat0) * i / n) for i in range(n + 1)]
    return [[a, b] for a, b in zip(pts, pts[1:])]


ROAD_A = line(13.75, 100.50, 13.75, 100.53, 10)    # about 3.2 km, all red
ROAD_B = line(13.76, 100.50, 13.76, 100.53, 10)    # 1.1 km north of A, all green
ROAD_C = line(13.74, 100.515, 13.765, 100.515, 8)  # crosses A and B, green
UTURN = line(13.77, 100.50, 13.77, 100.52, 6)      # a U-turn point with a name: never a card


class FakeArea:
    def geometry(self, pcode, acode=""):
        return box(100.4, 13.6, 100.6, 13.9) if pcode == "10" else None

    def district_name(self, acode):
        return "ปทุมวัน"

    def locate(self, lat, lng):
        return "กรุงเทพมหานคร", "ปทุมวัน"


def fake_tiles(monkeypatch):
    base = [("ถนน A", ROAD_A), ("ถนน B", ROAD_B), ("ถนน C", ROAD_C), ("จุดกลับรถใต้สะพาน", UTURN)]
    traffic = [(RED, ROAD_A), (GREEN, ROAD_B), (GREEN, ROAD_C), (GREEN, UTURN)]
    tiles = {
        b"base": {"road": {"features": [{"properties": {"name_l": n, "type": "nu:primary"}, "geometry": seg}
                                        for n, segs in base for seg in segs]}},
        b"traffic": {"traffic": {"features": [{"properties": {"fillcolor": c}, "geometry": seg}
                                              for c, segs in traffic for seg in segs]}},
    }
    monkeypatch.setattr(area_roads, "area_traffic", FakeArea())
    monkeypatch.setattr(area_roads, "_tiles", lambda geom, z: [(0, 0)])
    monkeypatch.setattr(area_roads, "get_base_tile", lambda z, x, y: b"base")
    monkeypatch.setattr(area_roads, "get_traffic_tile", lambda z, x, y, max_age=0: (b"traffic", False))
    monkeypatch.setattr(area_roads, "decode_tile", lambda raw, z, x, y: tiles[raw])
    monkeypatch.setattr(area_roads, "feature_lonlat", lambda geom, z, x, y, extent=4096: [geom])
    area_roads._cache.clear()


def test_cards_for_a_district(monkeypatch):
    fake_tiles(monkeypatch)
    out = area_roads.analyse("10", "1007")
    assert out["area"] == "เขตปทุมวัน กรุงเทพมหานคร"
    names = [i["name"] for i in out["items"]]
    assert names[0] == "ถนน A" and "จุดกลับรถใต้สะพาน" not in names
    a = out["items"][0]
    assert a["status"] == "congested" and a["red_km"] > 3
    labels = [s["label"] for s in a["hotspots"]]
    assert len(labels) == len(set(labels))                 # the same place is one row
    assert "ใกล้ ถนน C" in labels
    alts = {x["name"]: x for x in a["alternatives"]}
    assert alts["ถนน B"]["recommended"] and "จุดกลับรถใต้สะพาน" not in alts
    assert a["action"].startswith("เลี่ยงไปใช้")


def test_an_event_on_the_road_marks_it(monkeypatch):
    fake_tiles(monkeypatch)
    out = area_roads.analyse("10", "1007", [{"kind": "accident", "title": "รถชน", "lat": 13.7501, "lng": 100.52}])
    a = next(i for i in out["items"] if i["name"] == "ถนน A")
    b = next(i for i in out["items"] if i["name"] == "ถนน B")
    assert a["status"] == "incident" and a["incidents"][0]["title"] == "รถชน"
    assert b["status"] == "free" and not b["incidents"]


def test_unknown_area(monkeypatch):
    fake_tiles(monkeypatch)
    assert area_roads.analyse("99") is None
