"""Automatic paid AI calls reserve their slot with HourlyBudget.try_spend at the moment of the call.
A budget already at its limit must mean no call and the existing budget-used-up outcome."""
import json
import time

import numpy as np

from backend.vision import flood_cam_service as fcs
from backend.vision import helmet_service as hsvc
from backend.vision import wrongway_service as wsvc
from backend.vision.frame_utils import fingerprint


def _street(seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((288, 352, 3), (100, 110, 105), np.uint8)
    return np.clip(img.astype(np.int16) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)


def _flood_jpeg(img):
    import cv2
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def _fill(budget, limit):
    for _ in range(limit):
        assert budget.try_spend()
    assert budget.try_spend() is False


# ---------------------------------------------------------------- flood_cam
def _flood_watch(tmp_path, monkeypatch):
    monkeypatch.setattr(fcs, "STATE_FILE", str(tmp_path / "flood_cams.json"))
    monkeypatch.setattr(fcs, "FRAME_DIR", str(tmp_path / "frames"))
    return fcs.FloodCamWatch([{"camid": "cam1"}, {"camid": "cam2"}])


def test_flood_grid_is_not_sent_when_the_hourly_cap_is_used_up(tmp_path, monkeypatch):
    watch = _flood_watch(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(watch, "_ask", lambda *a, **k: calls.append(a) or json.dumps({"tiles": []}))
    _fill(watch._budget, watch._budget.limit)
    now = time.time()
    for camid, seed in (("cam1", 1), ("cam2", 2)):
        img = _street(seed)
        watch._frames[camid] = (_flood_jpeg(img), now, fingerprint(img))
    watch._screen(["cam1", "cam2"])
    assert calls == []
    assert "cam1" not in watch._state and "cam2" not in watch._state


def test_flood_confirm_is_not_sent_when_the_hourly_cap_is_used_up(tmp_path, monkeypatch):
    watch = _flood_watch(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(watch, "_ask", lambda *a, **k: calls.append(a) or "{}")
    _fill(watch._budget, watch._budget.limit)
    assert watch._confirm("cam1", _flood_jpeg(_street()), time.time()) is None
    assert calls == []


# ---------------------------------------------------------------- helmet_service (auto path)
def _helmet_analyser():
    m = object.__new__(hsvc.HelmetPatrol)
    m._budget = hsvc.HourlyBudget(hsvc.MAX_PER_HOUR)
    m.agent_error = None
    m._switched_off = False
    m.provider = lambda: object()
    m._local_verdict = lambda crop: None
    m.settled = []
    m._settle_without_agent = lambda *a, **k: m.settled.append(a)
    m.asked = []
    m._ask = lambda *a, **k: m.asked.append(a) or "{}"
    return m


def test_helmet_auto_check_is_not_sent_when_the_hourly_cap_is_used_up():
    m = _helmet_analyser()
    m._budget_ok = lambda now: True   # the pre-check passed, then parallel workers filled the cap
    _fill(m._budget, hsvc.MAX_PER_HOUR)
    m._analyse(1, "cam", {"title": "c"}, np.zeros((40, 40, 3), np.uint8), None)
    assert m.asked == []
    assert len(m.settled) == 1
    assert m.settled[0][6] == "ใช้ AI ตรวจซ้ำครบโควตาชั่วโมงนี้แล้ว"   # reason, the existing budget-used-up text


# ---------------------------------------------------------------- wrongway_service (auto path)
def _wrongway_analyser():
    m = object.__new__(wsvc.WrongWayPatrol)
    m._budget = wsvc.HourlyBudget(wsvc.MAX_PER_HOUR)
    m.agent_error = None
    m.provider = lambda: object()
    m._row = lambda wid: {}
    m.updates = []
    m._update = lambda wid, **kw: m.updates.append((wid, kw))
    m.asked = []
    m._ask = lambda *a, **k: m.asked.append(a) or "{}"
    return m


def test_wrongway_auto_check_is_not_sent_when_the_hourly_cap_is_used_up():
    m = _wrongway_analyser()
    m._budget_ok = lambda now: True   # the pre-check passed, then parallel workers filled the cap
    _fill(m._budget, wsvc.MAX_PER_HOUR)
    m._analyse(7, "cam", {"title": "c"}, np.zeros((40, 40, 3), np.uint8), np.zeros((40, 40, 3), np.uint8))
    assert m.asked == []
    assert m.updates and m.updates[0][0] == 7
    assert m.updates[0][1]["verdict"] == "pending"
    assert "ครบโควตาชั่วโมงนี้แล้ว" in m.updates[0][1]["note"]
