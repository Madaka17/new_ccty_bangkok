"""GET /healthz: the public, minimal health check for outside uptime monitors.

The router is imported with a stub backend.services (the real one loads YOLO and starts camera threads)."""
import importlib
import sys
import tempfile
import threading
import time
import types
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import access_guard


@pytest.fixture(scope="module", autouse=True)
def services_stub():
    before = set(sys.modules)
    stub = types.ModuleType("backend.services")
    stub.__getattr__ = lambda attr: MagicMock(name=attr)
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "backend.services", stub)
        yield stub
    for name in set(sys.modules) - before:
        if name.startswith("backend.api."):
            sys.modules.pop(name, None)


class FakeScanner:
    def __init__(self, age_s):
        # bma_service stores last_scan_time as local "%Y-%m-%d %H:%M:%S" text
        self.last = datetime.fromtimestamp(time.time() - age_s).strftime("%Y-%m-%d %H:%M:%S")

    def get_status(self):
        return {"last_scan_time": self.last, "cycle_count": 3, "is_scanning": False, "source": "test"}


@pytest.fixture
def system(monkeypatch, tmp_path):
    monkeypatch.setenv("BMA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BMA_FETCH", raising=False)
    module = importlib.import_module("backend.api.system")
    monkeypatch.setattr(module, "SERVER_START", time.time() - 10_000)
    module._healthz_cache.clear()          # the 20 s result cache must not leak between tests
    yield module
    module._healthz_cache.clear()


class _Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def _client(module, scan_age_s, guard=False):
    module.bma_scanner = FakeScanner(scan_age_s)
    app = FastAPI()
    if guard:
        app.middleware("http")(access_guard.guard)
    app.include_router(module.router)
    return TestClient(app)


def test_ok_when_scan_fresh_and_disk_writable(system):
    r = _client(system, scan_age_s=60).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "scan": True, "disk": True}
    assert r.headers["cache-control"] == "no-store"


def test_503_when_disk_write_raises(system, monkeypatch):
    def read_only(*args, **kwargs):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(system.tempfile, "mkstemp", read_only)
    r = _client(system, scan_age_s=60).get("/healthz")
    assert r.status_code == 503
    assert r.json() == {"ok": False, "scan": True, "disk": False}


def test_503_when_scan_stale(system):
    r = _client(system, scan_age_s=3600).get("/healthz")
    assert r.status_code == 503
    assert r.json() == {"ok": False, "scan": False, "disk": True}


def test_scan_null_and_200_when_bma_fetch_off(system, monkeypatch):
    monkeypatch.setenv("BMA_FETCH", "0")
    # a stale scan does not count on an instance that never scans
    r = _client(system, scan_age_s=3600).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "scan": None, "disk": True}


def test_outside_request_passes_guard_and_gets_no_session(system):
    client = _client(system, scan_age_s=60, guard=True)   # TestClient peer is not a trusted network
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "scan": True, "disk": True}
    assert "set-cookie" not in r.headers
    # the same outsider is still refused on the operator API
    assert client.get("/api/health").status_code == 403


def test_response_has_only_the_three_keys(system):
    body = _client(system, scan_age_s=60).get("/healthz").json()
    assert set(body) == {"ok", "scan", "disk"}


def test_head_returns_200(system):
    # UptimeRobot's free monitor sends HEAD
    r = _client(system, scan_age_s=60).head("/healthz")
    assert r.status_code == 200


def test_no_probe_files_left_in_data_dir(system, tmp_path):
    _client(system, scan_age_s=60).get("/healthz")
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".healthz")] == []


def test_ten_concurrent_calls_all_200_when_healthy(system):
    client = _client(system, scan_age_s=60)
    barrier = threading.Barrier(10)
    codes = []

    def probe():
        barrier.wait()
        codes.append(client.get("/healthz").status_code)

    threads = [threading.Thread(target=probe) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert codes == [200] * 10


def test_result_cached_for_20_seconds_then_refreshed(system, monkeypatch):
    clock = _Clock(1000.0)
    monkeypatch.setattr(system, "_monotonic", clock)
    writes = []
    real_disk_ok = system._disk_ok
    monkeypatch.setattr(system, "_disk_ok", lambda: (writes.append(1), real_disk_ok())[1])
    client = _client(system, scan_age_s=60)
    assert client.get("/healthz").status_code == 200
    system.bma_scanner = FakeScanner(3600)     # stale now, but inside the window
    clock.now = 1019.0
    assert client.get("/healthz").status_code == 200
    assert len(writes) == 1
    clock.now = 1020.5                         # window over: fresh check, scan is stale
    assert client.get("/healthz").status_code == 503
    assert len(writes) == 2
