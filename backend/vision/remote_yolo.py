"""
RemoteYolo: a stand-in for an ultralytics YOLO model that runs on the PC's AI worker (backend/vision/ai_worker.py).

The Raspberry Pi has no GPU. With AI_WORKER_URL set (and AI_WORKER_TOKEN) every YOLO holder loads its weights
through load_yolo(), gets a RemoteYolo, and calls it exactly like a local model: model(image_or_list, **kwargs)
returns a list of ultralytics Results with boxes / probs / names. The images go to the worker as PNG (lossless: a JPEG round trip, even at quality 100, changes
YOLO results on the small 352x288 BMA frames); the
Results are rebuilt here on the CPU, so the detector, the trackers and the patrols work unchanged.

When the worker cannot be reached every call raises YoloOff, which callers already treat as "YOLO is off".
After a failure the worker is left alone for BREAKER_S seconds, so threads do not queue behind the timeout.
"""
import json
import os
import threading
import time

import cv2
import requests

from backend.core.instance import BASE_DIR
from backend.vision.yolo_switch import NOT_ALLOWED, YoloOff, yolo_allowed

TIMEOUT = (1, 10)        # connect, read seconds
BREAKER_S = 30.0
PNG_LEVEL = 1          # fastest lossless compression
OFFLINE = "AI worker offline"


def worker_url(env=os.environ):
    """AI_WORKER_URL without a trailing slash, or None when unset or empty."""
    url = (env.get("AI_WORKER_URL") or "").strip().rstrip("/")
    return url or None


class RemoteYolo:
    remote = True

    def __init__(self, rel_path, url, token, post=requests.post, clock=time.monotonic):
        self.rel_path = rel_path
        self.url = url.rstrip("/")
        self.token = token
        self._post = post
        self._clock = clock
        self._names = None
        self._down_until = None
        self._lock = threading.Lock()

    def __repr__(self):
        return f"RemoteYolo({self.rel_path!r} at {self.url})"

    @property
    def names(self):
        if self._names is None:
            self._request([], {})
        return self._names

    def __call__(self, source, **kwargs):
        many = isinstance(source, (list, tuple))
        images = list(source) if many else [source]
        kwargs.pop("verbose", None)
        rows = self._request(images, kwargs)
        if len(rows) != len(images):
            raise YoloOff(OFFLINE)
        return [self._result(img, row) for img, row in zip(images, rows)]

    def _request(self, images, kwargs):
        with self._lock:
            if self._down_until is not None and self._clock() < self._down_until:
                raise YoloOff(OFFLINE)
        files = {}
        for i, img in enumerate(images):
            ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, PNG_LEVEL])
            if not ok:
                raise ValueError("cannot encode image")
            files[f"image{i}"] = (f"{i}.png", buf.tobytes(), "image/png")
        meta = json.dumps({"model": self.rel_path, "kwargs": kwargs})
        try:
            reply = self._post(f"{self.url}/predict", data={"meta": meta}, files=files,
                               headers={"X-AI-Token": self.token}, timeout=TIMEOUT)
            if reply.status_code != 200:
                raise RuntimeError(f"HTTP {reply.status_code}")
            body = reply.json()
            names = {int(k): v for k, v in body["names"].items()}
            rows = body["results"]
        except Exception as e:  # noqa: BLE001 - any failure means the worker is not usable right now
            with self._lock:
                self._down_until = self._clock() + BREAKER_S
            raise YoloOff(OFFLINE) from e
        with self._lock:
            self._down_until = None
            self._names = names
        return rows

    def _result(self, img, row):
        import torch
        from ultralytics.engine.results import Results
        boxes = row.get("boxes")
        probs = row.get("probs")
        return Results(img, path="", names=self._names,
                       boxes=None if boxes is None else torch.tensor(boxes, dtype=torch.float32).reshape(-1, 6),
                       probs=None if probs is None else torch.tensor(probs, dtype=torch.float32))


def load_yolo(path, local_factory=None):
    """The model for a weights file: remote when AI_WORKER_URL is set, else a local ultralytics YOLO
    (local_factory, when given, builds the local one)."""
    url = worker_url()
    if url:
        rel = os.path.relpath(os.path.abspath(path), BASE_DIR).replace(os.sep, "/")
        return RemoteYolo(rel, url, os.getenv("AI_WORKER_TOKEN", ""))
    if not yolo_allowed():
        raise YoloOff(NOT_ALLOWED)
    if local_factory is None:
        from ultralytics import YOLO as local_factory
    return local_factory(path)


WEIGHTS_CACHE_S = 60.0
_weights_cache = {}   # url -> (monotonic time, set of weights on the worker)


def weights_available(path, get=requests.get, clock=time.monotonic):
    """Local: the file exists. With the AI worker: the worker has the file (asked once a minute), so a model
    the PC does not have stays off instead of failing every minute. An unreachable worker counts as yes:
    the switch's retry loads it once the PC is back."""
    url = worker_url()
    if url is None:
        return os.path.exists(path)
    rel = os.path.relpath(os.path.abspath(path), BASE_DIR).replace(os.sep, "/")
    cached = _weights_cache.get(url)
    if cached is None or clock() - cached[0] > WEIGHTS_CACHE_S:
        try:
            reply = get(f"{url}/", timeout=TIMEOUT)
            weights = set(reply.json()["weights"]) if reply.status_code == 200 else None
        except Exception:  # noqa: BLE001 - worker down or old: decide later
            weights = None
        if weights is None:
            return True
        cached = _weights_cache[url] = (clock(), weights)
    return rel in cached[1]


def is_remote(model):
    return getattr(model, "remote", False) is True
