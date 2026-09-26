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
    assert "น้ำท่วมถนน" not in reply and "flow" in reply


def test_pick_topics():
    assert cs.pick_topics("น้ำท่วมตรงไหนบ้าง", {})[0] == "flood"
    assert cs.pick_topics("ฝุ่น PM2.5 วันนี้", {})[0] == "air"
    assert cs.pick_topics("สรุปภาพรวมเมือง", {}) == ["traffic", "flood", "accident", "air"]
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
