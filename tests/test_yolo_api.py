"""GET/POST /api/ai/yolo: the switch status and flip. Router imported with a stub backend.services."""
import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import access_guard
from backend.vision.yolo_switch import YoloSwitch


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


class Holder:
    def __init__(self):
        self.loaded = True

    def load_models(self):
        self.loaded = True

    def unload_models(self):
        self.loaded = False

    def models_loaded(self):
        return self.loaded


@pytest.fixture
def setup(monkeypatch, tmp_path):
    module = importlib.import_module("backend.api.live_ai")
    switch = YoloSwitch(str(tmp_path / "s.json"), cuda=None)
    holder = Holder()
    switch.register("fake", holder)
    monkeypatch.setattr(module, "yolo", switch)
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), holder


def test_get_reports_enabled(setup):
    client, _ = setup
    body = client.get("/api/ai/yolo").json()
    assert body["enabled"] is True
    assert body["holders"] == {"fake": True}


def test_post_off_unloads_and_get_shows_off(setup):
    client, holder = setup
    r = client.post("/api/ai/yolo", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert holder.loaded is False
    assert client.get("/api/ai/yolo").json()["enabled"] is False


def test_post_non_bool_is_400(setup):
    client, holder = setup
    assert client.post("/api/ai/yolo", json={"enabled": "no"}).status_code == 400
    assert holder.loaded is True


def test_post_is_operator_only():
    """The guard keeps /api/ai/ POSTs local: an untrusted peer gets 403 on the new path too."""
    app = FastAPI()
    app.middleware("http")(access_guard.guard)

    @app.post("/api/ai/yolo")
    def yolo_set():
        return {"ok": True}

    assert TestClient(app).post("/api/ai/yolo", json={"enabled": False}).status_code == 403
