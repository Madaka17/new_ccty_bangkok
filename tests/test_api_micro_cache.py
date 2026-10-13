"""The busy GET routes answer from the response cache: data source called once per TTL, gzip when asked.

The routers are imported with a stub backend.services: the real one loads YOLO and starts camera threads."""
import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import response_cache


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(response_cache, "_cache", response_cache.ResponseCache())


@pytest.fixture(scope="module", autouse=True)
def services_stub():
    """Routers bind to the stub; afterwards every backend.api module imported under it is dropped."""
    before = set(sys.modules)
    stub = types.ModuleType("backend.services")
    stub.__getattr__ = lambda attr: MagicMock(name=attr)
    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "backend.services", stub)
        yield stub
    for name in set(sys.modules) - before:
        if name.startswith("backend.api."):
            sys.modules.pop(name, None)


def _router_module(name):
    return importlib.import_module(f"backend.api.{name}")


def _router_client(name):
    module = _router_module(name)
    app = FastAPI()
    app.include_router(module.router)
    return module, TestClient(app)


class Source:
    """Stands in for a service object: every method returns `value` and counts the calls."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls += 1
            return self.value
        return method


ROUTES = [  # (router module, attribute the handler reads, path)
    ("traffic", "traffic", "/api/traffic/summary?top=25"),
    ("traffic", "area_traffic", "/api/traffic/areas"),
    ("traffic", "guidance", "/api/traffic/guidance"),
    ("traffic", "analytics_service", "/api/analytics/summary"),
    ("water", "water_service", "/api/water/summary"),
    ("weather", "air", "/api/air/stations"),
    ("flood", "flood_roads", "/api/flood/status"),
    ("flood", "traffy_reports", "/api/flood/reports"),
    ("insights", "news_feed", "/api/news?kind=flood"),
    ("site", "alerts", "/api/alerts/recent?limit=20"),
    ("bma", "bma_scanner", "/api/bma/analytics"),
]


@pytest.mark.parametrize("module_name,attr,path", ROUTES)
def test_route_builds_once_per_ttl(monkeypatch, module_name, attr, path):
    module, client = _router_client(module_name)
    source = Source({"text": "น้ำท่วม" * 400})
    monkeypatch.setattr(module, attr, source)
    first = client.get(path, headers={"Accept-Encoding": "gzip"})
    second = client.get(path, headers={"Accept-Encoding": "gzip"})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"text": "น้ำท่วม" * 400}
    assert first.headers["content-encoding"] == "gzip"
    assert source.calls == 1


def test_query_parameters_are_separate_keys(monkeypatch):
    module, client = _router_client("traffic")
    seen = []

    class Traffic:
        def get_summary(self, top):
            seen.append(top)
            return {"top": top}

    monkeypatch.setattr(module, "traffic", Traffic())
    assert client.get("/api/traffic/summary?top=25").json() == {"top": 25}
    assert client.get("/api/traffic/summary?top=8").json() == {"top": 8}
    assert seen == [25, 8]


def test_analytics_refresh_skips_the_cache(monkeypatch):
    module, client = _router_client("traffic")
    source = Source({"v": 1})
    monkeypatch.setattr(module, "analytics_service", source)
    client.get("/api/analytics/summary")
    client.get("/api/analytics/summary?refresh=true")
    assert source.calls == 2


def test_flood_status_with_min_cm_skips_the_cache(monkeypatch):
    module, client = _router_client("flood")
    source = Source({"v": 1})
    monkeypatch.setattr(module, "flood_roads", source)
    client.get("/api/flood/status?min_cm=5")
    client.get("/api/flood/status?min_cm=5")
    assert source.calls == 2


def test_water_error_answer_is_not_cached(monkeypatch):
    module, client = _router_client("water")

    class Broken:
        calls = 0

        def get_summary(self):
            Broken.calls += 1
            raise RuntimeError("thaiwater down")

        def key_status(self):
            return "ok"

    monkeypatch.setattr(module, "water_service", Broken())
    assert client.get("/api/water/summary").status_code == 503
    assert client.get("/api/water/summary").status_code == 503
    assert Broken.calls == 2


def test_all_cameras_built_once_per_ttl(monkeypatch):
    module, client = _router_client("cameras")
    calls = []

    def build():
        calls.append(1)
        return {"total": 1, "items": [{"camid": "c1", "title": "สี่แยก" * 300}]}

    monkeypatch.setattr(module, "_all_cameras", build)
    a = client.get("/api/cameras/all", headers={"Accept-Encoding": "gzip"})
    b = client.get("/api/cameras/all", headers={"Accept-Encoding": "gzip"})
    assert a.json() == b.json() and a.json()["items"][0]["camid"] == "c1"
    assert a.headers["content-encoding"] == "gzip"
    assert len(calls) == 1


def test_camera_list_cached(monkeypatch):
    module, client = _router_client("cameras")
    monkeypatch.setattr(module, "cameras_data", [{"camid": "x" * 2000}])
    assert client.get("/api/cameras").json() == {"total": 1, "items": [{"camid": "x" * 2000}]}
    monkeypatch.setattr(module, "cameras_data", [])
    assert client.get("/api/cameras").json()["total"] == 1   # still the cached answer inside the TTL
