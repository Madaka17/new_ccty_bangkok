"""AI worker (:8100): serves YOLO on the PC's GPU to the Raspberry Pi."""
import json

import cv2
import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from ultralytics.engine.results import Results

from backend.vision.ai_worker import ModelPool, create_app, read_settings

TOKEN = "s3cret-token"
PI = ("192.168.1.109", 5000)


class FakeModel:
    def __init__(self, path):
        self.path = path
        self.names = {0: "person", 2: "car"}
        self.calls = []

    def to(self, device):
        return self

    def half(self):
        return self

    def __call__(self, source, **kwargs):
        self.calls.append(kwargs)
        imgs = source if isinstance(source, list) else [source]
        return [Results(im, path="", names=self.names,
                        boxes=torch.tensor([[1.0, 2.0, 30.0, 40.0, 0.9, 2.0]])) for im in imgs]


class Factory:
    def __init__(self):
        self.made = []

    def __call__(self, path):
        m = FakeModel(path)
        self.made.append(m)
        return m


@pytest.fixture
def root(tmp_path):
    (tmp_path / "yolo26x.pt").write_bytes(b"w")
    (tmp_path / "notes.txt").write_text("x")
    return tmp_path


def jpg():
    ok, buf = cv2.imencode(".jpg", np.zeros((80, 100, 3), dtype=np.uint8))
    return buf.tobytes()


def client(root, factory, host=PI, clock=lambda: 0.0):
    app = create_app(str(root), TOKEN, {"192.168.1.109", "127.0.0.1"}, factory=factory, clock=clock,
                     start_janitor=False)
    return TestClient(app, client=host)


def predict(c, model="yolo26x.pt", n=1, token=TOKEN, kwargs=None):
    files = {f"image{i}": (f"{i}.jpg", jpg(), "image/jpeg") for i in range(n)}
    return c.post("/predict", data={"meta": json.dumps({"model": model, "kwargs": kwargs or {}})},
                  files=files or None, headers={"X-AI-Token": token})


def test_predict_returns_boxes_and_names(root):
    f = Factory()
    r = predict(client(root, f), n=2, kwargs={"conf": 0.2})
    assert r.status_code == 200
    body = r.json()
    assert body["names"] == {"0": "person", "2": "car"}
    assert len(body["results"]) == 2
    assert body["results"][0]["boxes"] == [[1.0, 2.0, 30.0, 40.0, pytest.approx(0.9), 2.0]]
    assert body["results"][0]["probs"] is None
    assert f.made[0].calls[0] == {"conf": 0.2, "verbose": False}


def test_names_only_request(root):
    r = predict(client(root, Factory()), n=0)
    assert r.status_code == 200
    assert r.json() == {"names": {"0": "person", "2": "car"}, "results": []}


def test_wrong_token_403_and_nothing_loaded(root):
    f = Factory()
    r = predict(client(root, f), token="nope")
    assert r.status_code == 403
    assert f.made == []


def test_ip_not_allowed_403(root):
    f = Factory()
    r = predict(client(root, f, host=("192.168.1.50", 5000)))
    assert r.status_code == 403
    assert f.made == []


def test_health_needs_ip_not_token(root):
    assert client(root, Factory()).get("/").json() == {"ok": True, "loaded": []}
    assert client(root, Factory(), host=("192.168.1.50", 1)).get("/").status_code == 403


@pytest.mark.parametrize("bad", ["../yolo26x.pt", "/etc/x.pt", "C:/x.pt", "sub/../../y.pt"])
def test_path_outside_root_rejected(root, bad):
    f = Factory()
    assert predict(client(root, f), model=bad).status_code == 400
    assert f.made == []


def test_non_pt_rejected(root):
    assert predict(client(root, Factory()), model="notes.txt").status_code == 400


def test_missing_file_rejected(root):
    assert predict(client(root, Factory()), model="missing.pt").status_code == 400


def test_model_loaded_once_and_reused(root):
    f = Factory()
    c = client(root, f)
    predict(c)
    predict(c)
    assert len(f.made) == 1
    assert c.get("/").json()["loaded"] == ["yolo26x.pt"]


def test_unload_idle_after_600_s(root):
    now = {"t": 0.0}
    pool = ModelPool(str(root), Factory(), clock=lambda: now["t"], idle_s=600)
    pool.get("yolo26x.pt")
    now["t"] = 599.0
    assert pool.unload_idle() == []
    now["t"] = 601.0
    assert pool.unload_idle() == ["yolo26x.pt"]
    assert pool.loaded() == []


def test_token_not_in_error_text(root):
    r = predict(client(root, Factory()), token="nope")
    assert TOKEN not in r.text and "nope" not in r.text


def test_empty_token_refuses_to_start():
    with pytest.raises(SystemExit):
        read_settings({"AI_WORKER_TOKEN": "  "})


def test_settings_default_allow_list():
    token, allow, port = read_settings({"AI_WORKER_TOKEN": "abc"})
    assert token == "abc"
    assert allow == {"192.168.1.109", "127.0.0.1"}
    assert port == 8100
