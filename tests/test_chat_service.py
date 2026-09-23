"""Chat context builders: never crash on missing data, and put the place the user asked about first."""
import chat_service as cs


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


def test_patrol_context_formats_counts():
    helmet = {"status": {"today": {"captures": 10, "no_helmet": 2, "helmet": 7, "unclear": 1, "pending": 0}, "total_no_helmet": 5},
              "recent": []}
    lines = cs.patrol_context(helmet, None, {"counts": {"wrong_way": 3}})
    assert "ไม่สวม 2" in lines[0]
    assert "ย้อนศร 3" in lines[-1]
