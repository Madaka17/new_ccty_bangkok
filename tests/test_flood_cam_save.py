"""FloodCamWatch._save: the state file is written outside the frame lock."""
import json

import pytest

from backend.vision import flood_cam_service


@pytest.fixture
def watch(tmp_path, monkeypatch):
    monkeypatch.setattr(flood_cam_service, "STATE_FILE", str(tmp_path / "flood_cams.json"))
    monkeypatch.setattr(flood_cam_service, "FRAME_DIR", str(tmp_path / "frames"))
    return flood_cam_service.FloodCamWatch([])


def test_lock_is_free_during_the_file_write(watch, monkeypatch):
    seen = {}

    def write(path, data, **kwargs):
        # a frame thread taking self._lock must not wait on the disk write
        seen["free"] = watch._lock.acquire(blocking=False)
        if seen["free"]:
            watch._lock.release()
        seen["data"] = data

    monkeypatch.setattr(flood_cam_service, "write_json_atomic", write)
    watch._state = {"cam1": {"verdict": "ok"}}
    watch._save()
    assert seen["free"] is True
    assert seen["data"] == {"cam1": {"verdict": "ok"}}


def test_saved_state_round_trips(watch, tmp_path):
    watch._state = {"cam1": {"verdict": "flood", "n": 2}}
    watch._save()
    with open(flood_cam_service.STATE_FILE, encoding="utf-8") as f:
        assert json.load(f) == {"cam1": {"verdict": "flood", "n": 2}}
