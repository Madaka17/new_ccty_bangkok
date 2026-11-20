"""The three guards on the flood-watch verdicts: corrupted frames (_corrupt), the note-before-level check
(_note_check, CONFIRM_PROMPT) and the second look before flooded or severe is published (_second_look)."""
import json
import time

import cv2
import numpy as np
import pytest

from backend.vision import flood_cam_service as fcs
from backend.vision.frame_utils import fingerprint


def _street(seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((288, 352, 3), (100, 110, 105), np.uint8)
    return np.clip(img.astype(np.int16) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)


def _smeared(size=120, x0=150, y0=80, cell=16):
    """A street with a square of flat, strongly coloured cells: what a broken H.264 stream looks like."""
    img = _street()
    colours = [(60, 40, 220), (220, 200, 40), (40, 200, 60), (230, 60, 200), (60, 200, 230)]
    for i, y in enumerate(range(y0, y0 + size, cell)):
        for j, x in enumerate(range(x0, x0 + size, cell)):
            img[y:y + cell, x:x + cell] = colours[(i + j) % len(colours)]
    return img


def _jpeg(img, q=90):
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()


# ---------------------------------------------------------------- 1. corrupted frames
def test_clean_street_is_not_corrupt():
    assert fcs._corrupt(_street()) is False


def test_flat_coloured_blocks_are_corrupt():
    assert fcs._corrupt(_smeared()) is True


def test_a_small_patch_is_under_the_share():
    assert fcs._corrupt(_smeared(size=20, x0=150, y0=150)) is False


def test_jpeg_bytes_are_read_too():
    assert fcs._corrupt(_jpeg(_smeared())) is True
    assert fcs._corrupt(_jpeg(_street())) is False


def test_the_top_text_band_is_ignored():
    img = _street()
    img[0:26, :] = (60, 40, 220)   # a coloured bar in the top 10% (the text bar on Pi snapshots)
    assert fcs._corrupt(img) is False


def test_undecodable_bytes_are_not_corrupt():
    assert fcs._corrupt(b"not a jpeg") is False


# ---------------------------------------------------------------- 2. note before level
REAL_NOTES_NONE = [
    "ถนนเปียกและสะท้อนแสง แต่ไม่มีน้ำขัง",
    "ถนนเปียกและสะท้อนแสงไฟ แต่ไม่มีน้ำขัง",
    "ถนนเปียกและสะท้อนแสง แต่ไม่มีน้ำขังที่ชัดเจน",
]
REAL_NOTES_KEPT = [
    "มีน้ำขังเป็นแอ่งเล็กๆ บนพื้นถนน",
    "น้ำท่วมขังในทางรถ",
    "ไม่มีน้ำท่วม แต่มีน้ำขังเล็กน้อยริมขอบทาง",
]


@pytest.mark.parametrize("note", REAL_NOTES_NONE)
def test_note_that_says_no_water_turns_a_puddle_into_none(note):
    v = fcs._note_check({"level": "puddle", "confidence": 0.7, "note_th": note})
    assert v["level"] == "none"
    assert v["note_th"] == note + " (ระดับปรับเป็นไม่มีน้ำ: คำบรรยายบอกว่าไม่มีน้ำ)"


@pytest.mark.parametrize("note", REAL_NOTES_NONE)
def test_note_that_says_no_water_turns_flooded_into_none(note):
    assert fcs._note_check({"level": "flooded", "confidence": 0.8, "note_th": note})["level"] == "none"


@pytest.mark.parametrize("note", REAL_NOTES_KEPT)
def test_note_that_describes_water_keeps_the_level(note):
    level = "flooded" if "น้ำท่วมขัง" in note else "puddle"
    v = {"level": level, "confidence": 0.7, "note_th": note}
    assert fcs._note_check(v) == v


def test_english_negations_count_too():
    v = fcs._note_check({"level": "puddle", "confidence": 0.5, "note_th": "wet road, no standing water"})
    assert v["level"] == "none"


def test_dry_road_note_with_a_wet_level_is_corrected():
    v = fcs._note_check({"level": "puddle", "confidence": 0.5, "note_th": "ถนนแห้ง ไม่พบน้ำ"})
    assert v["level"] == "none"


@pytest.mark.parametrize("note", [
    "เห็นน้ำสีน้ำตาลปกคลุมถนน ไม่แห้ง",   # "ไม่แห้ง" = not dry: must not match "แห้ง"
    "the road is not dry, brown water covers it",
    "ถนนไม่แห้ง",
])
def test_not_dry_is_wet_and_keeps_the_level(note):
    v = {"level": "flooded", "confidence": 0.8, "note_th": note}
    assert fcs._note_check(v) == v


def test_not_dry_on_a_puddle_keeps_the_puddle():
    v = {"level": "puddle", "confidence": 0.5, "note_th": "ถนนไม่แห้ง"}
    assert fcs._note_check(v) == v


def test_flooded_road_note_without_a_negation_is_kept():
    v = {"level": "flooded", "confidence": 0.8, "note_th": "ถนนจมน้ำ"}
    assert fcs._note_check(v) == v


@pytest.mark.parametrize("note", ["ไม่มีน้ำท่วมแต่ถนนปกคลุมด้วยน้ำขัง", "no flooding, but water covers the lane"])
def test_water_words_in_the_note_keep_the_wet_level(note):
    v = {"level": "puddle", "confidence": 0.5, "note_th": note}
    assert fcs._note_check(v) == v


def test_none_level_is_left_alone():
    v = {"level": "none", "confidence": 0.9, "note_th": "ไม่มีน้ำขัง"}
    assert fcs._note_check(v) == v


def test_empty_note_is_left_alone():
    v = {"level": "puddle", "confidence": 0.5, "note_th": ""}
    assert fcs._note_check(v) == v


def test_confirm_prompt_asks_for_the_note_before_the_level():
    answer_schema = fcs.CONFIRM_PROMPT[fcs.CONFIRM_PROMPT.index("Answer ONLY with JSON"):]
    order = [answer_schema.index(k) for k in ('"note_th"', '"level"', '"confidence"', '"stamp"')]
    assert order == sorted(order)


def test_confirm_prompt_keeps_the_level_rules():
    assert fcs._LEVEL_RULES in fcs.CONFIRM_PROMPT


def test_level_rules_say_a_glitched_picture_is_unclear_never_wet():
    assert "glitched" in fcs._LEVEL_RULES
    assert "unclear, never puddle or flooded" in fcs._LEVEL_RULES
    assert "ordinary night grain and blur are not broken" in fcs._LEVEL_RULES


# ---------------------------------------------------------------- 3. second look
@pytest.fixture
def frames():
    dark = fingerprint(np.full((288, 352, 3), 30, np.uint8))
    bright = fingerprint(np.full((288, 352, 3), 200, np.uint8))
    return dark, bright


def _wet(level, note="น้ำท่วมขังในทางรถ"):
    return {"level": level, "confidence": 0.9, "note_th": note}


def _candidate(level, ts, checked_at):
    return {"level": "unclear", "candidate": level, "note_th": fcs._CANDIDATE_TH + "น้ำท่วมขังในทางรถ",
            "frame_ts": ts, "checked_at": checked_at, "source": "confirm"}


def _published(level, ts, checked_at):
    return {"level": level, "confidence": 0.9, "note_th": "x", "source": "confirm",
            "frame_ts": ts, "checked_at": checked_at}


def test_first_flooded_is_a_candidate_not_published():
    v, extra = fcs._second_look(None, _wet("flooded"), 1000, 5000)
    assert v["level"] == "unclear"
    assert v["note_th"] == "รอยืนยัน: น้ำท่วมขังในทางรถ"
    assert extra == {"candidate": "flooded"}


def test_first_severe_is_a_candidate_too():
    v, extra = fcs._second_look(None, _wet("severe"), 1000, 5000)
    assert v["level"] == "unclear" and extra["candidate"] == "severe"


def test_puddle_is_published_on_one_confirm():
    v, extra = fcs._second_look(None, _wet("puddle", "มีน้ำขัง"), 1000, 5000)
    assert v["level"] == "puddle" and "candidate" not in extra


def test_none_is_published_on_one_confirm():
    v, extra = fcs._second_look(None, _wet("none", "ถนนแห้ง"), 1000, 5000)
    assert v["level"] == "none" and "candidate" not in extra


def test_second_flooded_on_a_newer_frame_publishes_flooded():
    v, extra = fcs._second_look(_candidate("flooded", 1000, 4900), _wet("flooded"), 1300, 5200)
    assert v["level"] == "flooded" and "candidate" not in extra


def test_second_look_on_a_static_scene_publishes_on_the_newer_frame_time():
    # the picture did not change (a quiet road), but the second confirm is on a newer frame: that counts
    v, extra = fcs._second_look(_candidate("flooded", 1000, 4900), _wet("flooded"), 1300, 5200)
    assert v["level"] == "flooded" and "candidate" not in extra


def test_second_severe_after_flooded_publishes_the_more_cautious_flooded():
    v, _ = fcs._second_look(_candidate("flooded", 1000, 4900), _wet("severe"), 1300, 5200)
    assert v["level"] == "flooded"


def test_two_severe_publish_severe():
    v, _ = fcs._second_look(_candidate("severe", 1000, 4900), _wet("severe"), 1300, 5200)
    assert v["level"] == "severe"


def test_second_look_on_an_older_frame_does_not_confirm():
    v, extra = fcs._second_look(_candidate("flooded", 1000, 4900), _wet("flooded"), 900, 5200)
    assert v["level"] == "unclear" and extra["candidate"] == "flooded"


def test_second_look_on_an_equal_frame_time_does_not_confirm():
    v, extra = fcs._second_look(_candidate("flooded", 1000, 4900), _wet("flooded"), 1000, 5200)
    assert v["level"] == "unclear" and extra["candidate"] == "flooded"


def test_second_look_that_says_dry_publishes_dry_and_drops_the_candidate():
    v, extra = fcs._second_look(_candidate("flooded", 1000, 4900), _wet("none", "ถนนแห้ง"), 1300, 5200)
    assert v["level"] == "none" and "candidate" not in extra


def test_expired_candidate_is_not_a_first_look():
    stale = _candidate("flooded", 1000, 5200 - 2 * fcs.WET_INTERVAL - 1)
    v, extra = fcs._second_look(stale, _wet("flooded"), 1300, 5200)
    assert v["level"] == "unclear" and extra["candidate"] == "flooded"


def test_published_flooded_confirmed_again_on_a_newer_frame_stays_flooded():
    v, _ = fcs._second_look(_published("flooded", 1000, 4900), _wet("flooded"), 1300, 5200)
    assert v["level"] == "flooded"


def test_screen_verdict_is_never_a_look_to_build_on():
    prev = {"level": "flooded", "source": "screen", "frame_ts": 1000, "checked_at": 4900}
    v, extra = fcs._second_look(prev, _wet("flooded"), 1300, 5200)
    assert v["level"] == "unclear" and extra["candidate"] == "flooded"


def test_switch_off_publishes_the_first_flooded(monkeypatch):
    monkeypatch.setattr(fcs, "CONFIRM_TWICE", 0)
    v, extra = fcs._second_look(None, _wet("flooded"), 1000, 5000)
    assert v["level"] == "flooded" and "candidate" not in extra


# ---------------------------------------------------------------- the worker path
@pytest.fixture
def watch(tmp_path, monkeypatch):
    monkeypatch.setattr(fcs, "STATE_FILE", str(tmp_path / "flood_cams.json"))
    monkeypatch.setattr(fcs, "FRAME_DIR", str(tmp_path / "frames"))
    return fcs.FloodCamWatch([{"camid": "cam1"}, {"camid": "cam2"}])


def _hold(watch, camid, img, ts):
    jpeg = _jpeg(img)
    watch._frames[camid] = (jpeg, ts, fingerprint(img))
    return jpeg


def _flooded_answer():
    return json.dumps({"note_th": "น้ำท่วมขังในทางรถ", "level": "flooded", "confidence": 0.9, "stamp": ""})


def test_corrupt_frame_is_unclear_and_never_sent_to_the_model(watch, monkeypatch):
    calls = []
    monkeypatch.setattr(watch, "_ask", lambda *a, **k: calls.append(a) or "{}")
    _hold(watch, "cam1", _smeared(), time.time())
    watch._screen(["cam1"])
    assert calls == []
    st = watch._state["cam1"]
    assert st["level"] == "unclear" and st["confidence"] == 1.0
    assert st["note_th"] == "ภาพเสีย (สัญญาณภาพแตก)" and st["source"] == "corrupt"
    assert watch._budget.used() == 0
    assert watch.frame_path("cam1") is not None   # saved like any verdict


def test_corrupt_frames_are_dropped_from_the_grid_and_the_rest_is_screened(watch, monkeypatch):
    seen = []

    def ask(jpeg, prompt, text, max_tokens):
        seen.append(text)
        return json.dumps({"tiles": [{"tile": 1, "level": "none", "confidence": 0.9}]})

    monkeypatch.setattr(watch, "_ask", ask)
    _hold(watch, "cam1", _smeared(), time.time())
    _hold(watch, "cam2", _street(), time.time())
    watch._screen(["cam1", "cam2"])
    assert seen == ["1 tiles."]
    assert watch._state["cam1"]["source"] == "corrupt"
    assert watch._state["cam2"]["source"] == "screen"


def test_corrupt_check_switch_off_sends_the_frame(watch, monkeypatch):
    monkeypatch.setattr(fcs, "CORRUPT_CHECK", 0)
    seen = []
    monkeypatch.setattr(watch, "_ask", lambda *a, **k: seen.append(1) or json.dumps({"tiles": []}))
    _hold(watch, "cam1", _smeared(), time.time())
    watch._screen(["cam1"])
    assert seen == [1]


def test_confirm_goes_through_the_note_check(watch, monkeypatch):
    answer = json.dumps({"note_th": "ถนนเปียกและสะท้อนแสง แต่ไม่มีน้ำขัง", "level": "puddle",
                         "confidence": 0.8, "stamp": ""})
    monkeypatch.setattr(watch, "_ask", lambda *a, **k: answer)
    jpeg = _hold(watch, "cam1", _street(), time.time())
    v, _extra = watch._confirm("cam1", jpeg, time.time())
    assert v["level"] == "none"


def test_candidate_is_taken_alone_and_confirmed_without_the_grid(watch, monkeypatch):
    now = time.time()
    watch._state["cam1"] = _candidate("flooded", int(now) - 400, int(now) - 400)
    _hold(watch, "cam1", _street(seed=1), now)
    _hold(watch, "cam2", _street(seed=2), now)
    watch._state["cam2"] = {"level": "none", "checked_at": int(now) - 4000, "frame_ts": int(now) - 4000}
    assert watch._take() == ["cam1"]


def test_candidate_is_due_after_wet_interval_and_not_before(watch):
    now = time.time()
    watch._state["cam1"] = _candidate("flooded", int(now) - 100, int(now) - 100)
    _hold(watch, "cam1", _street(seed=1), now)
    assert watch._due() == []                       # checked 100 s ago, WET_INTERVAL 300 s
    watch._state["cam1"]["checked_at"] = int(now) - fcs.WET_INTERVAL - 5
    assert watch._due() == ["cam1"]


def test_candidate_on_a_static_scene_is_due_again(watch):
    # the second look must not be skipped because the picture matches the one already judged
    now = time.time()
    still = _street(seed=1)
    jpeg = _hold(watch, "cam1", still, now)
    watch._judged["cam1"] = fingerprint(still)
    watch._state["cam1"] = _candidate("flooded", int(now) - 100, int(now) - 400)
    assert watch._due() == ["cam1"]


def test_dry_camera_on_a_static_scene_is_still_not_due_again(watch):
    now = time.time()
    still = _street(seed=1)
    _hold(watch, "cam1", still, now)
    watch._judged["cam1"] = fingerprint(still)
    watch._state["cam1"] = {"level": "none", "checked_at": int(now) - 400, "frame_ts": int(now) - 100}
    assert watch._due() == []


def test_static_flooded_scene_is_published_on_the_second_look(watch, monkeypatch):
    now = time.time()
    still = _street(seed=1)
    _hold(watch, "cam1", still, now)
    watch._judged["cam1"] = fingerprint(still)
    watch._state["cam1"] = _candidate("flooded", int(now) - 400, int(now) - 400)
    monkeypatch.setattr(watch, "_ask", lambda *a, **k: _flooded_answer())
    assert watch._take() == ["cam1"]
    watch._screen(["cam1"])
    assert watch._state["cam1"]["level"] == "flooded"
    assert "candidate" not in watch._state["cam1"]


def test_candidate_older_than_two_wet_intervals_expires_with_a_plain_note(watch):
    now = time.time()
    watch._state["cam1"] = _candidate("flooded", int(now) - 900, int(now) - 2 * fcs.WET_INTERVAL - 30)
    watch._take()
    st = watch._state["cam1"]
    assert "candidate" not in st and st["level"] == "unclear"
    assert st["note_th"] == "ยังไม่ยืนยัน: ตรวจซ้ำไม่ทัน"


def test_expiry_skips_a_camera_being_checked_now(watch):
    now = time.time()
    watch._state["cam1"] = _candidate("flooded", int(now) - 900, int(now) - 2 * fcs.WET_INTERVAL - 30)
    watch._inflight.add("cam1")
    watch._expire_candidates(now)
    assert watch._state["cam1"].get("candidate") == "flooded"


def test_previous_candidate_is_read_before_the_model_call(watch, monkeypatch):
    # the candidate expires while the model is thinking: the look still counts, it was read before the call
    now = time.time()
    watch._state["cam1"] = _candidate("flooded", 1000, int(now) - 100)

    def ask_and_expire(*a, **k):
        watch._state["cam1"].pop("candidate", None)
        return _flooded_answer()

    monkeypatch.setattr(watch, "_ask", ask_and_expire)
    jpeg = _hold(watch, "cam1", _street(seed=1), now)
    v, extra = watch._confirm("cam1", jpeg, now)
    assert v["level"] == "flooded" and "candidate" not in extra
