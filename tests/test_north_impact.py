"""Rule scoring and report clean-up of the Bangkok district impact analyst (north_impact_agent.py)."""
import tempfile

from backend.agents import north_impact_agent as nia

PEAK_T = 1_791_187_200  # 2026-10-05 Bangkok


def _north(peak_msl=2.74, c35_pct=114.0):
    return {
        "headline": {"text": "น้ำเหนือไหลผ่านนครสวรรค์"},
        "alerts": [{"text": "อยุธยา ล้นตลิ่งแล้ว"}],
        "stations": [{"code": "C.35", "province": "พระนครศรีอยุธยา", "q": 1316, "pct": c35_pct, "status": "overflow",
                      "peak": {"q": 1635, "pct": c35_pct + 27, "in_h": 60}}],
        "bangkok": {"now_msl": 2.44, "bank": 2.5, "peak_msl": peak_msl, "peak_t": PEAK_T,
                    "over_bank_t": PEAK_T if peak_msl >= 2.5 else None},
    }


def _map(rows=()):
    return {"water": [dict(r) for r in rows]}


def test_riverside_districts_follow_the_nonthaburi_forecast():
    facts = nia.build_facts(_north(), _map(), None, [], [])
    by = {r["district"]: r for r in facts["districts"]}
    assert by["พระนคร"]["rule_level"] == "ปานกลาง"        # over the bank upstream: outside the flood wall
    assert any("สูงกว่าตลิ่ง 0.24" in w for w in by["พระนคร"]["rule_reasons"])
    assert "ปทุมวัน" not in by                            # inland, no gauge alarm: not listed
    calm = {r["district"]: r for r in nia.build_facts(_north(peak_msl=2.0, c35_pct=60), _map(), None, [], [])["districts"]}
    assert calm["พระนคร"]["rule_level"] is None


def test_own_gauges_and_road_water_raise_a_district():
    rows = [{"name": "ค.ลาดพร้าว", "kind": "canal", "province": "กรุงเทพมหานคร", "district": "บางเขน",
             "status": "overflow", "diff_bank": -0.05}]
    roads = {"wet": [{"district": "บางเขน", "level_cm": 20}]}
    facts = nia.build_facts(_north(peak_msl=2.0, c35_pct=60), _map(rows), roads, [], [])
    bk = next(r for r in facts["districts"] if r["district"] == "บางเขน")
    assert bk["rule_level"] == "ปานกลาง" and bk["gauges"][0]["bank"] == "สูงกว่าตลิ่ง 0.05 ม."


def test_model_report_keeps_only_bangkok_districts():
    agent = nia.NorthImpactAgent(tempfile.mkdtemp(), {})
    facts = nia.build_facts(_north(), _map(), None, [], [])
    report = {"level": "warning", "summary": "", "timeline": [], "watch_points": [], "districts": [
        {"district": "เมืองนนทบุรี", "level": "สูง"},
        {"district": "ดุสิต", "level": "เฝ้าระวัง", "when": "", "cause": "", "evidence": "", "advice": ""},
        {"district": "บางพลัด", "level": "สูง", "when": "", "cause": "", "evidence": "", "advice": ""},
        {"district": "บางพลัด", "level": "ปานกลาง"},
    ]}
    agent._finish(report, facts, "ai", model="test")
    out = agent.status()["report"]
    assert [d["district"] for d in out["districts"]] == ["บางพลัด", "ดุสิต"]
    assert out["status_label"] == "เตือนภัย"


def test_rules_report_without_the_model():
    r = nia.rules_report(nia.build_facts(_north(), _map(), None, [], []))
    assert r["level"] == "warning" and r["districts"][0]["district"] == "บางพลัด"   # river bank + northern edge
    assert all(d["district"] in nia.DISTRICTS for d in r["districts"])
    assert any("5 ต.ค." in t["when"] for t in r["timeline"])


def test_point_sentence_uses_the_ten_minute_figure():
    p = {"code": "C.2", "place": "นครสวรรค์", "status": "ปกติ", "q": 2314, "pct": 62.0,
         "now_10min": {"q": 2341, "change_1h": 54}, "peak": {"q": 2725, "pct": 73.0, "in_h": 11}}
    text = nia.point_text(p)
    assert text.startswith("นครสวรรค์: น้ำไหลผ่าน 2,341")
    assert "กำลังเพิ่มขึ้น +54 ใน 1 ชม." in text and "2,725 ในอีก ~11 ชม." in text
    assert nia.trend_text({"q": 1000, "now_10min": {"q": 1000, "change_1h": 2}}) == "ทรงตัว"


def test_rules_title_names_the_overflowing_province():
    facts = nia.build_facts(_north(), _map(), None, [], [])
    assert nia.rules_title(facts) == "น้ำเหนือล้นตลิ่งแล้วที่พระนครศรีอยุธยา"
    calm = nia.build_facts(_north(peak_msl=2.0, c35_pct=40), _map(), None, [], [])
    calm["north"]["chao_phraya"][0]["peak"]["pct"] = 50
    assert nia.rules_title(calm) == "น้ำเหนือยังอยู่ในลำน้ำ ปกติ"


def _road(name, province, district, **kw):
    return {"road": name, "province": province, "district": district, "lat": 13.8, "lng": 100.5, **kw}


def test_road_candidates_follow_the_river_and_skip_elevated_roads():
    rows = [
        _road("ถนนจรัญสนิทวงศ์", "กรุงเทพมหานคร", "บางพลัด", sensors=2),
        _road("ทางพิเศษศรีรัช", "กรุงเทพมหานคร", "บางซื่อ", sensors=1),
        _road("สะพานพระราม 7", "กรุงเทพมหานคร", "บางซื่อ"),
        _road("ถนนติวานนท์", "นนทบุรี", "ปากเกร็ด"),
        _road("ถนนรามอินทรา", "กรุงเทพมหานคร", "บางเขน", sensors=1, flood_cm=20, flood_at="ถ.รามอินทรา (ซ. 5) *",
              gauge_kind="canal", gauge_pct=97, gauge_at="ค.รางอ้อ"),
        _road("ถนนพหลโยธิน", "กรุงเทพมหานคร", "พญาไท"),      # inland, nothing measured: not listed
    ]
    facts = nia.build_facts(_north(), _map(), None, [], [], rows)
    by = {r["road"]: r for r in facts["roads"]}
    assert set(by) == {"ถนนจรัญสนิทวงศ์", "ถนนติวานนท์", "ถนนรามอินทรา"}
    assert any("ริมแม่น้ำเจ้าพระยา" in w for w in by["ถนนติวานนท์"]["reasons"]) and by["ถนนติวานนท์"]["river_side"]
    assert "ตอนนี้มีน้ำบนถนน 20 ซม. ที่ถ.รามอินทรา (ซ. 5)" in by["ถนนรามอินทรา"]["reasons"]
    assert by["ถนนรามอินทรา"]["rule_level"] == "ปานกลาง"      # sensor 10 + 20 cm now 30 + canal 97% 10
    rr = nia.rules_roads(facts)
    assert rr["roads"] and all(r["road"] in by for r in rr["roads"])
