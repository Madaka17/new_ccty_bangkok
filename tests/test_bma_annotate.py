"""BMA snapshot labels: a title too long for the room left by the counters is cut, never looped on forever."""
import numpy as np

from backend.bma.bma_service import BmaScanner


def test_title_cut_ends_when_counters_leave_no_room():
    # A 352 px BMA frame with five-digit counters: less room than the "…" itself. This spun forever before
    # Oct 2026 and held the GIL, slowing every request of the server.
    img = np.zeros((288, 352, 3), dtype=np.uint8)
    cam = {"camera_code": "TF2-DD-S9-02", "short_title": "แยกสุทธิสาร ด้านถนนสุทธิสารวินิจฉัย"}
    out = BmaScanner._annotate_snapshot(None, img, [], cam, 12345, 45678, 7890, 99999, "heavy")
    assert out.shape == img.shape


def test_short_title_is_kept_on_a_wide_frame():
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    out = BmaScanner._annotate_snapshot(None, img, [], {"camera_code": "A1", "short_title": "แยก"}, 1, 1, 0, 2, "free")
    assert out.shape == img.shape and out[:34].any()   # the title bar was drawn
