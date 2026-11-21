"""Public guidance cards: camera codes stripped, AI tips only name roads the card shows as green."""
from backend.traffic.guidance_service import GuidanceService, SHOWN_ALTS, ai_action_ok, plain_cam_title

# Sorted the way build() sorts them (highest flow first); the first SHOWN_ALTS are what the card shows.
ALTS = [
    {"name": "ถนนรัชดาภิเษก", "recommended": True},
    {"name": "ทางพิเศษฉลองรัช (รามอินทรา-อาจณรงค์)", "recommended": True},
    {"name": "ถนนรามอินทรา", "recommended": False},
    {"name": "ถนนประเสริฐมนูกิจ", "recommended": True},
    {"name": "ถนนประดิษฐ์มนูธรรม", "recommended": True},
]


def _item(alternatives, status="congested"):
    return {"status": status, "alternatives": alternatives, "hotspots": [], "incidents": []}


def test_shown_alts_matches_card_max_alts():
    assert SHOWN_ALTS == 3


def test_plain_cam_title_strips_camera_codes():
    assert plain_cam_title("TF-RW-04 ใต้ด่วนเพชร") == "ใต้ด่วนเพชร"
    assert plain_cam_title("TF1-RW-03 แนวถนนจตุรทิศ (2)") == "แนวถนนจตุรทิศ (2)"
    assert plain_cam_title("TF2-HK-S67-04 แยกห้วยขวาง") == "แยกห้วยขวาง"
    assert plain_cam_title("TF-BR-03 สวนพลู 1(ศรีไทย)") == "สวนพลู 1(ศรีไทย)"


def test_plain_cam_title_keeps_titles_without_code():
    assert plain_cam_title("แยกรัชดา-พระราม4") == "แยกรัชดา-พระราม4"
    assert plain_cam_title("ทางแยกอโศก-สุขุม") == "ทางแยกอโศก-สุขุม"


def test_plain_cam_title_code_only_returns_original():
    assert plain_cam_title("TF-RW-04 ") == "TF-RW-04"


def test_ai_action_rejects_roads_not_shown():
    assert ai_action_ok("ควรเลี่ยงไปใช้ถนนประเสริฐมนูกิจหรือถนนประดิษฐ์มนูธรรม", _item(ALTS)) is False


def test_ai_action_accepts_shown_green_road():
    assert ai_action_ok("เลี่ยงไปใช้รัชดาภิเษกที่รถคล่อง", _item(ALTS)) is True


def test_ai_action_rejects_shown_but_not_green_road():
    assert ai_action_ok("ใช้ถนนรามอินทรา", _item(ALTS)) is False


def test_ai_action_without_road_names_passes():
    assert ai_action_ok("ใช้เส้นทางนี้ตามปกติและระวังรถติด", _item(ALTS)) is True


def test_template_never_names_hidden_road():
    it = _item(ALTS)
    text = GuidanceService._template_text(it)
    assert "ถนนประเสริฐมนูกิจ" not in text["action"]
    assert "ถนนประเสริฐมนูกิจ" not in text["bypass"]
    assert "ถนนประดิษฐ์มนูธรรม" not in text["action"]
    assert "ถนนประดิษฐ์มนูธรรม" not in text["bypass"]
