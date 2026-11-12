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
    assert client(root, Factory()).get("/").json() == {"ok": True, "loaded": [], "weights": ["yolo26x.pt"]}
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


def test_health_lists_weights_in_subfolders(root):
    (root / "models").mkdir()
    (root / "models" / "x.pt").write_bytes(b"w")
    assert client(root, Factory()).get("/").json()["weights"] == ["models/x.pt", "yolo26x.pt"]


def test_same_file_spelled_differently_loads_once(root):
    # "./x.pt" and "x.pt" are one file: one copy in VRAM and one lock, or two jobs run on the GPU at once.
    f = Factory()
    pool = ModelPool(str(root), f)
    m1, l1 = pool.get("yolo26x.pt")
    m2, l2 = pool.get("./yolo26x.pt")
    assert len(f.made) == 1 and m1 is m2 and l1 is l2
    assert pool.loaded() == ["yolo26x.pt"]


@pytest.mark.parametrize("kwargs", [{"save": True}, {"project": "C:/x"}, {"device": "cpu"}, {"source": "x"},
                                    {"stream": True}, {"imgsz": 100000}, {"imgsz": [640, 100000]}])
def test_unsafe_kwargs_rejected(root, kwargs):
    f = Factory()
    r = predict(client(root, f), kwargs=kwargs)
    assert r.status_code == 400
    assert f.made == []


def test_safe_kwargs_pass(root):
    f = Factory()
    r = predict(client(root, f), kwargs={"classes": [0, 2], "conf": 0.1, "imgsz": 960, "iou": 0.45})
    assert r.status_code == 200


def test_too_many_images_rejected(root):
    assert predict(client(root, Factory()), n=33).status_code == 400


def test_oversized_body_rejected(root):
    c = client(root, Factory())
    r = c.post("/predict", content=b"x" * 10, headers={"X-AI-Token": TOKEN, "Content-Length": str(30 * 2**20),
                                                        "Content-Type": "multipart/form-data; boundary=x"})
    assert r.status_code == 413


def test_huge_image_rejected(root):
    big = cv2.imencode(".png", np.zeros((5000, 100, 3), dtype=np.uint8))[1].tobytes()
    c = client(root, Factory())
    r = c.post("/predict", data={"meta": json.dumps({"model": "yolo26x.pt", "kwargs": {}})},
               files={"image0": ("0.png", big, "image/png")}, headers={"X-AI-Token": TOKEN})
    assert r.status_code == 400


def test_job_dropped_when_client_already_gave_up(root):
    # The Pi stops waiting after 10 s; a job still queued behind the model lock then must not run.
    now = {"t": 0.0}
    f = Factory()
    app = create_app(str(root), TOKEN, {"192.168.1.109"}, factory=f, clock=lambda: now["t"], start_janitor=False)
    pool = app.state.pool
    model, lock = pool.get("yolo26x.pt")
    lock.acquire()
    import threading
    out = {}
    t = threading.Thread(target=lambda: out.update(r=predict(TestClient(app, client=PI))))
    t.start()
    import time as _t
    _t.sleep(0.3)
    now["t"] = 11.0
    lock.release()
    t.join(5)
    assert out["r"].status_code == 503
    assert model.calls == []


def test_weights_list_cached(root):
    pool = ModelPool(str(root), Factory(), clock=lambda: 0.0)
    assert pool.weights() == ["yolo26x.pt"]
    (root / "new.pt").write_bytes(b"w")
    assert pool.weights() == ["yolo26x.pt"]      # cached for 60 s


def test_gpu_jobs_stay_on_a_fixed_set_of_threads(root):
    """Torch/CUDA keeps about 1 MB of private commit per thread that ran inference and never frees it when
    the thread exits. anyio's to_thread pool retires idle threads after 10 s, so the worker leaked about
    24 GB a day. Every model call must run on a few long-lived threads instead."""
    import threading

    from backend.vision.ai_worker import GPU_THREADS

    seen = []

    class ThreadRecordingModel(FakeModel):
        def __call__(self, source, **kwargs):
            seen.append(threading.current_thread())
            return super().__call__(source, **kwargs)

    c = client(root, lambda path: ThreadRecordingModel(path))
    for _ in range(3 * GPU_THREADS + 3):
        assert predict(c).status_code == 200
    assert len(seen) == 3 * GPU_THREADS + 3
    assert len({id(t) for t in seen}) <= GPU_THREADS
