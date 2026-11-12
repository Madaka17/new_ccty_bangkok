"""Small backend fixes: BMA scan errors reach the log, incident snapshot ids cannot leave their folder."""
import threading
import time

from backend.bma import bma_service, bma_site
from backend.vision import incident_service


def _incidents(snapshot_dir):
    m = incident_service.IncidentManager.__new__(incident_service.IncidentManager)
    m.snapshot_dir = str(snapshot_dir)
    return m


def test_incident_snapshot_path_rejects_traversal(tmp_path):
    snap = tmp_path / "snap"
    (snap / "a").mkdir(parents=True)
    (snap / "a" / "b.jpg").write_bytes(b"x")          # would be found by "a/b" if it were joined
    (tmp_path / "outside.jpg").write_bytes(b"x")      # would be found by "..\\outside"
    m = _incidents(snap)
    assert m.snapshot_path("a/b") is None
    assert m.snapshot_path("..\\outside") is None
    assert m.snapshot_path("../outside") is None


def test_incident_snapshot_path_finds_normal_id(tmp_path):
    (tmp_path / "1234-1700000000.jpg").write_bytes(b"x")
    assert _incidents(tmp_path).snapshot_path("1234-1700000000") == str(tmp_path / "1234-1700000000.jpg")


def _scanner():
    s = bma_service.BmaScanner.__new__(bma_service.BmaScanner)
    s.is_scanning = False
    s.scan_interval = 180
    s._last_tick_error = None
    return s


def test_bma_loop_logs_start_scan_error(capsys, monkeypatch):
    s = _scanner()

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(s, "start_scan", boom)
    last = s._scan_tick(0.0)
    out = capsys.readouterr().out
    assert "[BMA]" in out and "boom" in out
    assert last > 0.0   # the cycle was due, so the tick counts it as started

    s._scan_tick(0.0)   # same error again: stays quiet
    assert capsys.readouterr().out == ""


def test_bma_tick_does_nothing_before_interval(monkeypatch):
    s = _scanner()
    calls = []
    monkeypatch.setattr(s, "start_scan", lambda: calls.append(1))
    now = time.time()
    assert s._scan_tick(now) == now
    assert calls == []


def test_bma_cycle_reports_failed_cameras(capsys, monkeypatch):
    s = bma_service.BmaScanner.__new__(bma_service.BmaScanner)

    class _Session:
        def fetch_snapshot(self, camid, timeout=7.0):
            raise RuntimeError("net down")

    class _Db:
        def get_all_latest(self):
            return []

    class _Archiver:
        def write_live_snapshot(self, rows):
            pass

    monkeypatch.setattr(bma_site, "failover", lambda: False)
    s.cameras = [{"camid": "c1"}, {"camid": "c2"}]
    s.session = _Session()
    s.db = _Db()
    s.archiver = _Archiver()
    s.download_workers = 2
    s.stop_event = threading.Event()
    s.lock = threading.Lock()
    s.current_index = 0
    s.cycle_count = 0
    s.is_scanning = True
    s.last_scan_duration = 0.0
    s.last_scan_time = None
    s._frame_ids = {}
    s._last_fresh = None
    s.source = {}
    s.flood = s.helmet = s.wrongway = None
    s._run_scan_cycle()
    out = capsys.readouterr().out
    assert "[BMA] 2 cameras failed this cycle, first: net down" in out
