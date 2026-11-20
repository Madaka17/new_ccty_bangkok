"""FloodCamWatch._seed(refresh=True): a newer saved snapshot replaces the held frame (FLOOD_CAM_RESEED)."""
import os

import cv2
import numpy as np
import pytest

from backend.vision import flood_cam_service


def _jpeg(value):
    img = np.full((288, 352, 3), value, np.uint8)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def _snapshot(snap_dir, camid, value, mtime):
    path = os.path.join(snap_dir, f"{camid}.jpg")
    with open(path, "wb") as f:
        f.write(_jpeg(value))
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    snap_dir = tmp_path / "snapshots"
    snap_dir.mkdir()
    monkeypatch.setattr(flood_cam_service, "SNAPSHOT_DIR", str(snap_dir))
    monkeypatch.setattr(flood_cam_service, "STATE_FILE", str(tmp_path / "flood_cams.json"))
    monkeypatch.setattr(flood_cam_service, "FRAME_DIR", str(tmp_path / "frames"))
    return snap_dir


def test_plain_seed_keeps_the_frame_already_held(env):
    import time
    now = time.time()
    _snapshot(env, "cam1", 10, now - 600)
    watch = flood_cam_service.FloodCamWatch([{"camid": "cam1"}])
    watch._seed()
    held_ts = watch._frames["cam1"][1]

    _snapshot(env, "cam1", 200, now - 60)   # newer file on disk
    watch._seed()                           # normal seed: setdefault, nothing replaced
    assert watch._frames["cam1"][1] == held_ts


def test_refresh_seed_replaces_the_frame_when_the_file_is_newer(env):
    import time
    now = time.time()
    _snapshot(env, "cam1", 10, now - 600)
    watch = flood_cam_service.FloodCamWatch([{"camid": "cam1"}])
    watch._seed()

    newer = _snapshot(env, "cam1", 200, now - 60)
    watch._seed(refresh=True)
    jpeg, ts, _fp = watch._frames["cam1"]
    assert ts == pytest.approx(os.path.getmtime(newer))
    shown = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert shown.mean() > 150   # the bright snapshot (200), not the dark one (10)


def test_refresh_seed_skips_a_file_not_newer_than_the_held_frame(env, monkeypatch):
    import time
    now = time.time()
    _snapshot(env, "cam1", 10, now - 600)
    watch = flood_cam_service.FloodCamWatch([{"camid": "cam1"}])
    watch._seed()
    held = watch._frames["cam1"]

    decoded = []
    real = cv2.imdecode
    monkeypatch.setattr(flood_cam_service.cv2, "imdecode", lambda *a, **k: decoded.append(1) or real(*a, **k))
    watch._seed(refresh=True)   # same mtime as the held frame: not read, not decoded again
    assert watch._frames["cam1"] is held
    assert decoded == []


def test_refresh_seed_adds_a_camera_with_no_frame_yet(env):
    import time
    now = time.time()
    _snapshot(env, "cam2", 90, now - 60)
    watch = flood_cam_service.FloodCamWatch([{"camid": "cam2"}])
    watch._seed(refresh=True)
    assert "cam2" in watch._frames


def test_reseed_loop_survives_an_exception(monkeypatch, env):
    class Stop(Exception):
        pass

    calls = []
    sleeps = []

    def fake_seed(refresh=False):
        calls.append(refresh)
        if len(calls) == 1:
            raise OSError("snapshot folder vanished")

    def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= 3:
            raise Stop()

    watch = flood_cam_service.FloodCamWatch([])
    monkeypatch.setattr(watch, "_seed", fake_seed)
    monkeypatch.setattr(flood_cam_service.time, "sleep", fake_sleep)
    with pytest.raises(Stop):
        watch._reseed_forever(300)
    assert calls == [True, True]   # sleep, seed (fails), sleep, seed (works), sleep, stop: the failure did not end the loop
    assert sleeps == [300, 300, 300]
