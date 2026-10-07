"""Road flooding: the depth -> vehicle rule table, the plain-Thai notices, and the check that the AI adds no numbers."""
from backend.water import flood_service as fs


def _item(level, **kw):
    return {"code": "X1", "name": "ถ.สุขุมวิท (ซ. 101/1)", "short_name": "ถ.สุขุมวิท (ซ. 101/1)", "road": "ถนนสุขุมวิท",
            "district": "พระโขนง", "lat": 13.68, "lng": 100.61, "level_cm": level,
            "status": "flood" if level > fs.FLOOD_CM else "slight", "status_th": "", "ts": 1_790_000_400,
            "ts_th": "", "started": None, "max_cm": None, "trend": "steady", "trend_th": "ทรงตัว", "delta_cm": 0,
            "kind": "road", **kw}


def _roads(*items):
    r = fs.FloodRoads()   # reads the instance cache, then the test's stations replace it
    r.items, r.feed_time = list(items), 1_790_000_400
    return r


def test_vehicle_rules_edges():
    assert [fs.vehicle_advice(cm)[0] for cm in (0, 9.9, 10, 19.9, 20, 30, 30.1, None)] == \
        ["passable", "passable", "careful", "careful", "no_car", "no_car", "avoid", "passable"]


def test_notice_keeps_the_fixed_order_and_source():
    n = _roads(_item(25, trend="rising")).notices()["items"][0]
    assert n["what"] == "น้ำท่วมขังประมาณ 25 ซม. ระดับกำลังเพิ่มขึ้น"
    assert n["where"] == "ถ.สุขุมวิท (ซ. 101/1) เขตพระโขนง"
    assert n["action"] == "รถเก๋งไม่ควรผ่าน"
    assert n["source"].startswith(fs.SOURCE_NAME) and "อัปเดต" in n["source"]


def test_numbers_not_in_the_data_are_caught():
    facts = '{"level_cm": 24.6, "where": "ซ. 101/1", "time": "18:40"}'
    assert fs.unsupported_numbers(["น้ำลึก 25 ซม. ที่ ซ. 101/1 เวลา 18:40"], facts) == []
    assert fs.unsupported_numbers(["น้ำลึก ๒๔.๖ ซม."], facts) == []
    assert fs.unsupported_numbers(["คาดว่าน้ำลดใน 2-3 ชั่วโมง"], facts) == [2.0, 3.0]


def test_ai_report_with_made_up_numbers_falls_back_to_template(monkeypatch):
    r = _roads(_item(25))
    made_up = {"severity": "alert", "headline": "น้ำท่วม 45 ซม. ที่สุขุมวิท", "detail": "", "hotspots": [],
               "advice": [], "outlook": "คาดว่าน้ำจะลดใน 2 ชั่วโมง"}
    monkeypatch.setattr(r, "_ask", lambda prompt: (made_up, "test-model"))
    out = r._analyse(force=True)
    assert out["source"] == "template"
    assert "รถเก๋งไม่ควรผ่าน" in " ".join(out["advice"])


def test_ai_report_from_the_data_is_kept(monkeypatch):
    r = _roads(_item(25))
    good = {"severity": "alert", "headline": "น้ำท่วมขัง 1 จุด ลึก 25 ซม. ที่สุขุมวิท 101/1", "detail": "", "hotspots": [],
            "advice": ["รถเก๋งไม่ควรผ่าน"], "outlook": ""}
    monkeypatch.setattr(r, "_ask", lambda prompt: (good, "test-model"))
    assert r._analyse(force=True)["source"] == "test-model"


def test_notices_say_when_the_feed_is_down():
    out = _roads().notices()
    assert out["sensors"] == 0 and out["items"] == []
    assert _roads(_item(25)).notices()["sensors"] == 1


def test_feed_since_october_2026_takes_the_position_from_floodtbl(monkeypatch, tmp_path):
    # dtTbl lost latitude / longitude / site_timestamp; floodTbl has the position per station code
    feed = {
        "dtTbl": [{"flood_code": "FL.MBR.01", "flood_id": 7, "flood": 22.0, "status": 1, "chkStatustxt": "น้ำท่วม",
                   "flood_shortname": "ถ.สุวินทวงศ์ (ถ.หทัยราษฎร์)", "districtName": "มีนบุรี", "road_name": "ถนนสุวินทวงศ์",
                   "typesite": 1, "site_timestatmpTH": "07/10/2569 21:40"},
                  {"flood_code": "FL.XX.09", "flood": 3.0, "status": 1, "chkStatustxt": "ปกติ", "site_timestatmpTH": "07/10/2569 21:40"}],
        "floodTbl": [{"flood_code": "FL.MBR.01", "latitude": 13.81645, "longitude": 100.72226, "flood_max": 25.0}],
    }
    monkeypatch.setattr(fs, "CACHE_FILE", str(tmp_path / "flood_roads.json"))
    r = fs.FloodRoads()
    monkeypatch.setattr(r, "_fetch", lambda: feed)
    assert r.refresh() == 1      # the station without a position anywhere is left out
    item = r.items[0]
    assert (item["lat"], item["lng"], item["status"], item["max_cm"]) == (13.81645, 100.72226, "flood", 25.0)
    assert item["ts"] == fs._epoch("2026-10-07T21:40:00") and r.feed_time == item["ts"]


def test_no_stations_means_no_ai_call(monkeypatch):
    r = _roads()

    def ask(prompt):
        raise AssertionError("the model must not be asked about an empty feed")
    monkeypatch.setattr(r, "_ask", ask)
    assert r._analyse(force=True)["source"] == "template"
