"""RemoteYolo: the YOLO stand-in the Pi uses to run models on the PC's AI worker."""
import json
import os

import numpy as np
import pytest

from backend.core.instance import BASE_DIR
from backend.vision.remote_yolo import RemoteYolo, load_yolo, weights_available, worker_url
from backend.vision.yolo_switch import YoloOff


class Reply:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakePost:
    def __init__(self, reply=None, error=None):
        self.calls = []
        self.reply = reply
        self.error = error

    def __call__(self, url, data=None, files=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "files": files, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.reply


NAMES = {"0": "person", "2": "car"}


def boxes_reply(n=1):
    return Reply(200, {"names": NAMES, "results": [{"boxes": [[1, 2, 30, 40, 0.9, 2]], "probs": None}] * n})


def img(h=80, w=100):
    return np.zeros((h, w, 3), dtype=np.uint8)


def make(post, clock=lambda: 0.0):
    return RemoteYolo("yolo26x.pt", "http://pc:8100", "secret", post=post, clock=clock)


def test_call_rebuilds_boxes():
    r = make(FakePost(boxes_reply()))(img())
    assert r[0].boxes.xyxy.tolist() == [[1, 2, 30, 40]]
    assert r[0].boxes.cls.tolist() == [2.0]
    assert r[0].names[2] == "car"
    assert r[0].orig_shape == (80, 100)


def test_call_rebuilds_probs():
    post = FakePost(Reply(200, {"names": {"0": "no", "1": "yes"}, "results": [{"boxes": None, "probs": [0.1, 0.9]}]}))
    r = make(post)(img(), imgsz=160)
    assert int(r[0].probs.top1) == 1


def test_empty_boxes_give_empty_result():
    post = FakePost(Reply(200, {"names": NAMES, "results": [{"boxes": [], "probs": None}]}))
    r = make(post)(img())
    assert len(r[0].boxes) == 0


def test_list_source_sends_one_request():
    post = FakePost(boxes_reply(4))
    r = make(post)([img(), img(), img(), img()])
    assert len(post.calls) == 1
    assert sorted(post.calls[0]["files"]) == ["image0", "image1", "image2", "image3"]
    assert len(r) == 4


def test_kwargs_pass_through_without_verbose():
    post = FakePost(boxes_reply())
    make(post)(img(), conf=0.2, imgsz=640, verbose=False)
    meta = json.loads(post.calls[0]["data"]["meta"])
    assert meta == {"model": "yolo26x.pt", "kwargs": {"conf": 0.2, "imgsz": 640}}
    assert post.calls[0]["url"] == "http://pc:8100/predict"


def test_token_sent_in_header():
    post = FakePost(boxes_reply())
    make(post)(img())
    assert post.calls[0]["headers"]["X-AI-Token"] == "secret"
    assert post.calls[0]["timeout"] == (1, 10)


def test_names_fetched_once_and_cached():
    post = FakePost(boxes_reply())
    m = make(post)
    assert m.names == {0: "person", 2: "car"}
    assert m.names == {0: "person", 2: "car"}
    assert len(post.calls) == 1
    assert post.calls[0]["files"] == {}


def test_connection_error_raises_yolo_off():
    with pytest.raises(YoloOff):
        make(FakePost(error=ConnectionError("refused")))(img())


def test_http_500_raises_yolo_off():
    with pytest.raises(YoloOff):
        make(FakePost(Reply(500, {"error": "x"})))(img())


def test_bad_json_raises_yolo_off():
    with pytest.raises(YoloOff):
        make(FakePost(Reply(200, ValueError("not json"))))(img())


def test_breaker_skips_post_for_30_s():
    now = {"t": 0.0}
    post = FakePost(error=ConnectionError("down"))
    m = make(post, clock=lambda: now["t"])
    with pytest.raises(YoloOff):
        m(img())
    now["t"] = 10.0
    with pytest.raises(YoloOff):
        m(img())
    assert len(post.calls) == 1
    now["t"] = 31.0
    post.error, post.reply = None, boxes_reply()
    assert len(m(img())) == 1
    assert len(post.calls) == 2


def test_worker_url_reads_env():
    assert worker_url({}) is None
    assert worker_url({"AI_WORKER_URL": "  "}) is None
    assert worker_url({"AI_WORKER_URL": " http://pc:8100/ "}) == "http://pc:8100"


def test_load_yolo_remote_when_url_set(monkeypatch):
    monkeypatch.setenv("AI_WORKER_URL", "http://pc:8100")
    monkeypatch.setenv("AI_WORKER_TOKEN", "t")
    m = load_yolo(os.path.join(BASE_DIR, "models", "helmet_det_blur.pt"))
    assert isinstance(m, RemoteYolo)
    assert m.remote is True
    assert m.rel_path == "models/helmet_det_blur.pt"


def test_load_yolo_refuses_local_when_not_allowed(monkeypatch):
    monkeypatch.delenv("AI_WORKER_URL", raising=False)
    monkeypatch.setenv("YOLO_ALLOWED", "0")
    with pytest.raises(YoloOff):
        load_yolo(os.path.join(BASE_DIR, "yolo26x.pt"))


def test_weights_available_remote_true_for_missing_file(monkeypatch):
    missing = os.path.join(BASE_DIR, "no_such_weights.pt")
    monkeypatch.delenv("AI_WORKER_URL", raising=False)
    assert weights_available(missing) is False
    monkeypatch.setenv("AI_WORKER_URL", "http://pc:8100")
    assert weights_available(missing) is True

