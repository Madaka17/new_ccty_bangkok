"""The busy GET routes answer from the response cache: data source called once per TTL, gzip when asked.

The routers are imported with a stub backend.services: the real one loads YOLO and starts camera threads."""
import gzip
import importlib
import json
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


def _router_module(name):
    if "backend.services" not in sys.modules:
        stub = types.ModuleType("backend.services")
        stub.__getattr__ = lambda attr: MagicMock(name=attr)
        sys.modules["backend.services"] = stub
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
