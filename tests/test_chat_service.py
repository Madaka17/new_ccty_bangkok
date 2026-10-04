"""Chat context builders: never crash on missing data, and put the place the user asked about first."""
from backend.agents import chat_service as cs


def test_asked_matches_with_or_without_prefix():
    assert cs._asked("ฝุ่นบางนาเป็นไง", "เขตบางนา")
    assert cs._asked("ฝุ่นเขตบางนาเป็นไง", "บางนา")
    assert not cs._asked("ฝุ่นบางนาเป็นไง", "เขตดินแดง", None, "")


def test_asked_ignores_very_short_names():
    assert not cs._asked("ถนนสายไหน", "สา")


def test_site_context_empty_sources():
    assert cs.site_context("อะไรก็ได้", {}) == []


def test_road_flood_context_puts_named_road_before_district():
    items = [{"road": f"ซอย {i}", "district": "บางนา", "province": "กรุงเทพมหานคร", "level_th": "เฝ้าระวัง", "class": 1}
             for i in range(10)]
    items.append({"road": "ถนนสุขุมวิท", "district": "สวนหลวง", "province": "กรุงเทพมหานคร", "level_th": "ปกติ", "class": 0})
    rr = {"items": items, "counts": {"watch": 10, "none": 1}, "level_th": {"watch": "เฝ้าระวัง", "none": "ปกติ"}, "total": 11}
    lines = cs.road_flood_context(rr, None, "ถนนสุขุมวิทแถวบางนาน้ำท่วมไหม")
    assert "ถนนสุขุมวิท" in lines[1]


def test_air_context_lists_asked_station():
    air = {"avg_pm25": 20, "total": 7, "counts": {"good": 7}, "updated_at": 0,
           "items": [{"name": f"สถานี {i}", "area": f"เขตที่ {i}", "province": "กทม.", "pm25": 50 - i, "label": "ดี"} for i in range(6)]
           + [{"name": "ริมถนนบางนา", "area": "เขตบางนา", "province": "กทม.", "pm25": 10, "label": "ดีมาก"}]}
    text = "\n".join(cs.air_context(air, "ฝุ่นบางนา"))
    assert "ริมถนนบางนา" in text


class _Traffic:
    def get_summary(self, top=8):
        road = {"name": "ถนนพระราม 4", "flow": 30, "level": "ติดขัด", "green_pct": 10, "yellow_pct": 20, "red_pct": 70,
                "red_km": 3, "length_km": 5}
        return {"ready": True, "updated_at": 0, "online": True, "flow_index": 55, "green_pct": 50, "yellow_pct": 30,
                "red_pct": 20, "road_count": 100, "total_km": 900, "history": [], "congested": [road] * 8, "free_flow": []}

    def find_roads_in_text(self, q):
        return []


WATER = {"updated_at": 0, "flood_roads": {"flooding": 2, "slight": 1, "normal": 200, "items": []},
         "river": [], "canals": [], "river_counts": {}, "canal_counts": {}}
AIR = {"avg_pm25": 20, "total": 1, "counts": {}, "updated_at": 0,
       "items": [{"name": "ดินแดง", "area": "เขตดินแดง", "province": "กทม.", "pm25": 20, "label": "ดี"}]}


def test_place_names_do_not_pick_a_topic():
    assert cs.question_topics("ใช้เวลานานไหม จากพระราม 2 ไป สีลม") == ["traffic"]     # สี"ลม" is not wind
    assert cs.question_topics("ปั๊มน้ำมันแถวสีลม") == []
    assert cs.question_topics("สีลมน้ำท่วมไหม") == ["flood"]


def test_offline_route_question_gets_traffic_not_flood():
    reply = cs.rule_based_reply(_Traffic(), "ใช้เวลานานไหม จากพระราม 2 ไป สีลม", WATER, {})
    assert "น้ำท่วมถนน" not in reply and "ถนนพระราม 4" in reply and "flow" not in reply


def test_pick_topics():
    assert cs.pick_topics("น้ำท่วมตรงไหนบ้าง", {})[0] == "flood"
    assert cs.pick_topics("ฝุ่น PM2.5 วันนี้", {})[0] == "air"
    assert cs.pick_topics("สรุปภาพรวมเมือง", {}) == ["traffic", "flood", "weather", "accident", "air"]
    assert cs.pick_topics("พรุ่งนี้ฝนจะตกไหม", {})[0] == "weather"
    assert "predict" in cs.pick_topics("คาดการณ์น้ำท่วมพรุ่งนี้", {})
    assert cs.pick_topics("ไปสีลม", {"route": ["เส้นทาง"]})[:1] == ["route"]
    assert cs.pick_topics("แปลคำว่า hello", {}) == []


def test_build_context_only_asked_topic_within_budget():
    full = cs.build_context(_Traffic(), "ฝุ่นเป็นยังไง", water=WATER, extra={"air": AIR})
    assert "ถนนพระราม 4" in full and "ดินแดง" in full
    cut = cs.build_context(_Traffic(), "ฝุ่นเป็นยังไง", water=WATER, extra={"air": AIR}, max_chars=600)
    assert "ดินแดง" in cut and "ถนนพระราม 4" not in cut
    assert len(cut) <= 600


def test_chat_uses_local_model_and_falls_back(monkeypatch):
    sent = []
    monkeypatch.setattr(cs.llm, "model", "qwen")
    monkeypatch.setattr(cs.llm, "chat", lambda messages, **kw: sent.append(messages) or "ตอบแล้ว")
    out = cs.chat(_Traffic(), [{"role": "user", "content": "น้ำท่วมไหม"}], water=WATER)
    assert out == {"reply": "ตอบแล้ว", "mode": "local", "model": "qwen"}
    assert sent[0][0]["role"] == "system" and "ท่วม 2 จุด" in sent[0][-1]["content"]

    def too_long(messages, **kw):
        raise cs.local_llm.ContextTooLong("n_ctx")
    monkeypatch.setattr(cs.llm, "chat", too_long)
    assert cs.chat(_Traffic(), [{"role": "user", "content": "น้ำท่วมไหม"}], water=WATER)["mode"] == "offline"


def test_patrol_context_formats_counts():
    helmet = {"status": {"today": {"captures": 10, "no_helmet": 2, "helmet": 7, "unclear": 1, "pending": 0}, "total_no_helmet": 5},
              "recent": []}
    lines = cs.patrol_context(helmet, None, {"counts": {"wrong_way": 3}})
    assert "ไม่สวม 2" in lines[0]
    assert "ย้อนศร 3" in lines[-1]


def test_route_questions():
    assert cs.wants_route("จากบางนาไปสีลม เลี่ยงน้ำท่วม")
    assert cs.wants_route("ไปลาดกระบังทางไหนดี")
    assert not cs.wants_route("ถนนไหนติดที่สุดตอนนี้")
    assert not cs.wants_route("พรุ่งนี้ฝนจะตกไหม")
    assert cs._trip_by_pattern("จากบางนาไปสีลมยังไงดี") == ("บางนา", "สีลม")
    assert cs._trip_by_pattern("ไปที่เซ็นทรัลเวิลด์ทางไหนดี") == ("", "เซ็นทรัลเวิลด์")


def test_answer_style_matches_question():
    assert "เส้นทาง" in cs.answer_style("จากบางนาไปสีลม", ["traffic"], route=True)
    q = "ตอนนี้ควรเลี่ยงถนนไหน"
    assert "ถนนที่ควรเลี่ยง" in cs.answer_style(q, cs.question_topics(q))
    q = "พรุ่งนี้ฝนจะตกไหม"
    assert "อากาศ" in cs.answer_style(q, cs.question_topics(q))
    assert cs.answer_style("แปลคำว่า hello", []) == ""


ROUTE = {"origin": {"name": "บางนา", "label": "บางนา"}, "destination": {"name": "สีลม", "label": "สีลม"},
         "flood_checked": True, "km": 14.0, "minutes": [32, 42], "roads": [{"name": "ถนนพระราม 4", "km": 8.0}],
         "flood_on_route": [], "wet_on_route": [], "flood_at_ends": [], "jams": [],
         "avoided": [{"name": "ถนนสุขุมวิท 101", "source": "เซ็นเซอร์ กทม.", "depth_cm": 25, "at_km": 3.0}],
         "fastest": {"km": 12.0, "minutes": 28, "roads": ["ถนนสุขุมวิท"], "floods": []},
         "line": [[13.66, 100.6], [13.72, 100.53]], "google_maps": "https://www.google.com/maps/dir/?api=1"}


class _Router:
    def geocode(self, text):
        return {"name": text, "label": text, "lat": 13.7, "lng": 100.5}

    @staticmethod
    def is_here(text):
        return not text

    def plan(self, a, b):
        return ROUTE


def test_route_context_names_the_avoided_flood():
    text = "\n".join(cs.route_context(ROUTE))
    assert "ถนนพระราม 4" in text and "ถนนสุขุมวิท 101 25 ซม." in text and "32-42 นาที" in text


def test_chat_route_reaches_model_and_browser(monkeypatch):
    sent = []
    monkeypatch.setattr(cs.llm, "model", "qwen")

    def fake(messages, **kw):
        if kw.get("json_schema"):
            return '{"origin": "บางนา", "destination": "สีลม"}'
        sent.append(messages)
        return "ไปทางพระราม 4"
    monkeypatch.setattr(cs.llm, "chat", fake)
    out = cs.chat(_Traffic(), [{"role": "user", "content": "จากบางนาไปสีลม เลี่ยงน้ำท่วม"}], water=WATER, router=_Router())
    assert out["route"] is ROUTE and out["reply"] == "ไปทางพระราม 4"
    assert "เส้นทางที่ระบบคำนวณ" in sent[0][-1]["content"] and "วิธีตอบคำถามนี้" in sent[0][-1]["content"]


def test_chat_route_without_origin_asks_for_it(monkeypatch):
    monkeypatch.setattr(cs.llm, "model", "")
    out = cs.chat(_Traffic(), [{"role": "user", "content": "ไปสีลมทางไหนดี"}], water=WATER, router=_Router())
    assert out["need_location"] and "ใช้ตำแหน่งของฉัน" in out["reply"]
    out = cs.chat(_Traffic(), [{"role": "user", "content": "ไปสีลมทางไหนดี"}], water=WATER, router=_Router(),
                  location={"lat": 13.7, "lng": 100.6})
    assert out["route"] is ROUTE and out["mode"] == "offline" and "ถนนพระราม 4" in out["reply"]


def test_weather_context_lists_days():
    outlook = {"days": [{"day": "พรุ่งนี้", "date": "2026-10-05", "text": "ฝนตก", "rain_mm": 5.0,
                         "rain_hours": "14:00-18:00", "tmin": 25, "tmax": 32}]}
    tmd = {"active": [{"date": "2026-10-04", "title": "ฝนตกหนัก", "summary": "", "bkk": True}]}
    lines = cs.weather_context(outlook, None, tmd)
    assert "พรุ่งนี้" in lines[1] and "14:00-18:00" in lines[1] and "25-32" in lines[1]
    assert "ฝนตกหนัก" in lines[-1]


AREAS = {"ready": True, "updated_at": 0, "national": {"flow": 90, "total_km": 1000, "red_km": 40},
         "provinces": [
             {"province": "นครราชสีมา", "region": "ภาคอีสาน", "flow": 40, "total_km": 300, "red_km": 25,
              "amphoes": [{"name": "ปากช่อง", "flow": 30, "red_km": 9}, {"name": "สีคิ้ว", "flow": 95, "red_km": 0}]},
             {"province": "เชียงใหม่", "region": "ภาคเหนือ", "flow": 92, "total_km": 200, "red_km": 2, "amphoes": []}]}
PROVINCES = {"updated_at": 0, "counts": {"critical": 1, "flood": 0, "watch": 0, "normal": 1},
             "provinces": [
                 {"province": "พระนครศรีอยุธยา", "region": "ภาคกลาง", "level": "critical", "label": "วิกฤต",
                  "counts": {"overflow": 12, "high": 9, "highways": 3}, "rain": {"max_mm": 42, "place": "นครหลวง"},
                  "gauges": [{"name": "สะพานหัวเวียง", "amphoe": "เสนา", "pct": 129.2, "lat": 14.3, "lng": 100.4}]},
                 {"province": "เชียงใหม่", "region": "ภาคเหนือ", "level": "normal", "label": "ปกติ", "counts": {}, "gauges": []}],
             "ai": {"overview": "ภาคกลางหนักสุด", "provinces": {"พระนครศรีอยุธยา": {"summary": "วิกฤต ล้นตลิ่ง 12 จุด"}}}}


def test_named_places_by_name_alias_and_district():
    assert [p for p, _ in cs.named_places("อยุธยาน้ำท่วมไหม")] == ["พระนครศรีอยุธยา"]
    assert [p for p, _ in cs.named_places("จังหวัดเชียงใหม่ฝนตกไหม")] == ["เชียงใหม่"]
    assert cs.named_places("ปากช่องรถติดไหม", AREAS) == [("นครราชสีมา", ["ปากช่อง"])]
    assert cs.named_places("รถติดไหม", AREAS) == []


def test_province_traffic_context_puts_asked_district_first():
    lines = cs.province_traffic_context(AREAS, [("นครราชสีมา", ["ปากช่อง"])])
    text = "\n".join(lines)
    assert "จังหวัดนครราชสีมา" in text and "อ.ปากช่อง: ติดขัด" in text
    assert lines[-1].startswith("จังหวัดที่รถติดที่สุดตอนนี้: นครราชสีมา")


def test_province_flood_context_reads_asked_province_and_worst():
    asked = "\n".join(cs.province_flood_context(PROVINCES, [("พระนครศรีอยุธยา", [])]))
    assert "วิกฤต ล้นตลิ่ง 12 จุด" in asked and "สะพานหัวเวียง" in asked and "129% ของความสูงตลิ่ง" in asked
    other = "\n".join(cs.province_flood_context(PROVINCES, []))
    assert "จังหวัดที่น้ำท่วมหนัก" in other and "พระนครศรีอยุธยา" in other


def test_province_question_puts_country_data_first():
    sec = cs.context_sections(_Traffic(), "อยุธยาน้ำท่วมไหม", extra={"areas": AREAS, "provinces": PROVINCES})
    assert sec["named"] == ["พระนครศรีอยุธยา"]
    assert sec["flood"][0].startswith("น้ำท่วมรายจังหวัดทั่วประเทศ")
    assert cs.pick_topics("เชียงใหม่เป็นยังไงบ้าง", {"named": ["เชียงใหม่"]}) == ["traffic", "flood", "weather"]
