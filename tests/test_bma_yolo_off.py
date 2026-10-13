"""BMA analytics while YOLO is off: no camera counts as online, and scan_status says so."""
import threading
import time

from backend.bma import bma_service


class _Db:
    def get_all_latest(self):
        return [{"camid": "c1", "ts": int(time.time()), "status": "online", "total": 5,
                 "cars": 5, "motorcycles": 0, "trucks": 0, "level": "moderate"}]

    def get_history_summary(self, hours=24):
        return []


class _Detector:
    def __init__(self, loaded):
        self._loaded = loaded

    def models_loaded(self):
        return self._loaded


def _scanner(loaded):
    s = bma_service.BmaScanner.__new__(bma_service.BmaScanner)
    s.db = _Db()
    s.detector = _Detector(loaded)
    s.cameras = [{"camid": "c1"}]
    s.source = {"state": "live"}
    s.lock = threading.Lock()
    s.is_scanning = False
    s.current_index = 0
    s.total_cameras = 1
    s.cycle_count = 0
    s.last_scan_time = None
    s.last_scan_duration = 0.0
    return s


def test_analytics_counts_no_camera_online_while_yolo_is_off():
    data = _scanner(False)._build_analytics()
    assert data["scan_status"]["yolo_enabled"] is False
    assert data["summary"]["online_cameras"] == 0


def test_analytics_reports_yolo_on():
    data = _scanner(True)._build_analytics()
    assert data["scan_status"]["yolo_enabled"] is True
    assert data["summary"]["online_cameras"] == 1
