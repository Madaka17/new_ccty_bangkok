"""_stale_copy: a wet call on a frame whose printed time shows an old copy is turned into unclear."""
from datetime import datetime

from backend.vision.flood_cam_service import BKK, _stale_copy

FETCHED = datetime(2026, 11, 20, 22, 15, tzinfo=BKK).timestamp()
WET = {"level": "flooded", "confidence": 0.9, "note_th": "น้ำท่วม"}


def test_fresh_frame_keeps_verdict():
    assert _stale_copy(WET, "20-11-2026 22:10:00", FETCHED) == WET


def test_copy_hours_old_is_unclear():
    v = _stale_copy(WET, "20-11-2026 02:00:00", FETCHED)
    assert v["level"] == "unclear" and v["note_th"].endswith("ชม.")


def test_copy_55_days_old_is_unclear():
    # camera 1463 on 20 Nov 2026: the BMA site still served its picture of 26 Sep
    v = _stale_copy(WET, "Sep 26 2026 05:19:21", FETCHED)
    assert v["level"] == "unclear" and v["note_th"].endswith("56 วัน")   # 55.7 days


def test_clock_never_set_keeps_verdict():
    assert _stale_copy(WET, "01-01-2000 00:05:00", FETCHED) == WET


def test_no_stamp_keeps_verdict():
    assert _stale_copy(WET, "", FETCHED) == WET
