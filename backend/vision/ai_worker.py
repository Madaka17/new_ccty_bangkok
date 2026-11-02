"""
AI worker: runs YOLO on this PC's GPU for the Raspberry Pi (B2 of the Pi move, docs/MIGRATE_MACHINE.md section 9).

The Pi's YOLO holders get a RemoteYolo (remote_yolo.py) that POSTs PNG images to /predict here. Each weights
file is loaded on first use and dropped after IDLE_S without calls, so VRAM is free when the Pi does not need it.

Access: only IPs in AI_WORKER_ALLOW (default the Pi and this PC) and, for /predict, the AI_WORKER_TOKEN header.
Run: launch\\ai_worker\\start.bat (python -m backend.vision.ai_worker), port 8100.
"""
import gc
import hmac
import json
import os
import threading
import time

import cv2
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

DEFAULT_ALLOW = "192.168.1.109,127.0.0.1"
PORT = 8100
IDLE_S = 600
# What a caller may pass on to model(...): nothing that writes files, picks the device or streams.
SAFE_KWARGS = {"classes", "conf", "imgsz", "iou", "max_det", "agnostic_nms", "half"}
MAX_IMGSZ = 1920
MAX_IMAGES = 32
MAX_BODY = 20 * 2**20       # bytes per request
MAX_SIDE = 4096             # pixels per image side
JOB_DEADLINE_S = 10.0       # the Pi stops waiting after its 10 s read timeout: later jobs are dropped
WEIGHTS_CACHE_S = 60.0


def check_kwargs(kwargs):
    """The kwargs, or ValueError for anything outside SAFE_KWARGS or an image size over MAX_IMGSZ."""
    bad = set(kwargs) - SAFE_KWARGS
    if bad:
        raise ValueError(f"not allowed: {sorted(bad)}")
    size = kwargs.get("imgsz")
    if size is not None:
        sizes = size if isinstance(size, (list, tuple)) else [size]
        if not all(isinstance(v, int) and 0 < v <= MAX_IMGSZ for v in sizes):
            raise ValueError(f"imgsz must be 1..{MAX_IMGSZ}")
    return kwargs


def read_settings(env=os.environ):
    """(token, allowed IPs, port) from the environment. No token: refuse to start."""
    token = (env.get("AI_WORKER_TOKEN") or "").strip()
    if not token:
        raise SystemExit("[AI worker] AI_WORKER_TOKEN is empty in .env: run launch\\ai_worker\\install.ps1 first")
    allow = {ip.strip() for ip in (env.get("AI_WORKER_ALLOW") or DEFAULT_ALLOW).split(",") if ip.strip()}
    return token, allow, int(env.get("AI_WORKER_PORT") or PORT)


def _default_factory(path):
    from ultralytics import YOLO
    model = YOLO(path)
    try:
        import torch
        if torch.cuda.is_available():
            model.to("cuda").half()
    except Exception as e:  # noqa: BLE001 - FP16 is a speed-up, not a requirement
        print(f"[AI worker] FP16 skipped for {path}: {e}")
    return model


class ModelPool:
    """Weights files under root, loaded on first use, one GPU job per model at a time."""

    def __init__(self, root, factory=_default_factory, clock=time.monotonic, idle_s=IDLE_S):
        self.root = os.path.realpath(root)
        self.factory = factory
        self.clock = clock
        self.idle_s = idle_s
        self.lock = threading.Lock()
        self.models = {}   # normcase(full path) -> {"name", "model", "lock", "used"}
        self._weights = None   # (time, list)

    def resolve(self, rel_path):
        """Absolute path of a .pt file inside root, else ValueError."""
        if not isinstance(rel_path, str) or not rel_path.endswith(".pt"):
            raise ValueError("model must be a .pt file")
        if os.path.isabs(rel_path) or rel_path.startswith(("/", "\\")) or ":" in rel_path:
            raise ValueError("model path must be relative")
        full = os.path.realpath(os.path.join(self.root, rel_path))
        if os.path.commonpath([full, self.root]) != self.root:
            raise ValueError("model path is outside the project")
        if not os.path.isfile(full):
            raise ValueError("model file not found")
        return full

    def get(self, rel_path):
        """(model, its lock). Loads the model when needed. Keyed by the resolved file, so two spellings
        of one file share one copy in VRAM and one lock."""
        full = self.resolve(rel_path)
        key = os.path.normcase(full)
        with self.lock:
            entry = self.models.get(key)
            if entry is None:
                name = os.path.relpath(full, self.root).replace(os.sep, "/")
                print(f"[AI worker] loading {name}")
                entry = {"name": name, "model": self.factory(full), "lock": threading.Lock(), "used": self.clock()}
                self.models[key] = entry
            entry["used"] = self.clock()
            return entry["model"], entry["lock"]

    def unload_idle(self):
        now = self.clock()
        with self.lock:
            keys = [k for k, e in self.models.items() if now - e["used"] > self.idle_s]
            dropped = [self.models.pop(k)["name"] for k in keys]
        if dropped:
            print(f"[AI worker] idle, unloaded {dropped}")
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
        return dropped

    def weights(self):
        """Every .pt file under root (two folders deep), as paths relative to root. Cached for 60 s."""
        cached = self._weights
        if cached is not None and self.clock() - cached[0] < WEIGHTS_CACHE_S:
            return list(cached[1])
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            rel_dir = os.path.relpath(dirpath, self.root)
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            dirnames[:] = [d for d in dirnames if depth < 2 and not d.startswith(".") and d not in ("node_modules", "instances")]
            for f in filenames:
                if f.endswith(".pt"):
                    out.append(f if rel_dir == "." else f"{rel_dir}/{f}".replace(os.sep, "/"))
        self._weights = (self.clock(), sorted(out))
        return list(self._weights[1])

    def loaded(self):
        with self.lock:
            return sorted(e["name"] for e in self.models.values())


def _serialise(result):
    boxes = getattr(result, "boxes", None)
    probs = getattr(result, "probs", None)
    return {"boxes": None if boxes is None else boxes.data.float().cpu().tolist(),
            "probs": None if probs is None else probs.data.float().cpu().tolist()}


def create_app(root, token, allow, factory=_default_factory, clock=time.monotonic, idle_s=IDLE_S,
               start_janitor=True):
    pool = ModelPool(root, factory, clock, idle_s)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.pool = pool

    def forbidden():
        return JSONResponse({"error": "forbidden"}, status_code=403)

    @app.get("/")
    def health(request: Request):
        if request.client is None or request.client.host not in allow:
            return forbidden()
        return {"ok": True, "loaded": pool.loaded(), "weights": pool.weights()}

    @app.post("/predict")
    async def predict(request: Request):
        if request.client is None or request.client.host not in allow:
            return forbidden()
        if not hmac.compare_digest(request.headers.get("X-AI-Token", "").encode(), token.encode()):
            return forbidden()
        received = clock()
        try:
            if int(request.headers.get("Content-Length") or 0) > MAX_BODY:
                return JSONResponse({"error": "request too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"error": "bad Content-Length"}, status_code=400)
        form = await request.form(max_files=MAX_IMAGES + 1)
        try:
            meta = json.loads(form["meta"])
            rel_path = meta["model"]
            kwargs = check_kwargs(dict(meta.get("kwargs") or {}))
            pool.resolve(rel_path)
        except (KeyError, ValueError, TypeError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        if f"image{MAX_IMAGES}" in form:
            return JSONResponse({"error": f"at most {MAX_IMAGES} images"}, status_code=400)
        images = []
        i = 0
        while f"image{i}" in form:
            data = await form[f"image{i}"].read()
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return JSONResponse({"error": f"image{i} is not a picture"}, status_code=400)
            if max(img.shape[:2]) > MAX_SIDE:
                return JSONResponse({"error": f"image{i} is larger than {MAX_SIDE} px"}, status_code=400)
            images.append(img)
            i += 1
        kwargs["verbose"] = False

        def run():
            model, lock = pool.get(rel_path)
            names = {str(k): v for k, v in model.names.items()}
            if not images:
                return {"names": names, "results": []}
            with lock:
                if clock() - received > JOB_DEADLINE_S:
                    return None     # the Pi gave up on this job while it waited for the GPU
                results = model(images if len(images) > 1 else images[0], **kwargs)
            return {"names": names, "results": [_serialise(r) for r in results]}

        import anyio
        try:
            out = await anyio.to_thread.run_sync(run)
            if out is None:
                return JSONResponse({"error": "job expired before the GPU was free"}, status_code=503)
            return out
        except Exception as e:  # noqa: BLE001 - report, keep serving
            print(f"[AI worker] {rel_path} failed: {e}")
            return JSONResponse({"error": "inference failed"}, status_code=500)

    if start_janitor:
        def janitor():
            while True:
                time.sleep(60)
                try:
                    pool.unload_idle()
                except Exception as e:  # noqa: BLE001
                    print(f"[AI worker] unload failed: {e}")
        threading.Thread(target=janitor, daemon=True, name="ai-worker-janitor").start()
    return app


def main():
    from dotenv import load_dotenv
    from backend.core.instance import BASE_DIR
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    token, allow, port = read_settings()
    import uvicorn
    print(f"[AI worker] serving YOLO on :{port} to {sorted(allow)}; models load on first use, unload after {IDLE_S}s idle")
    uvicorn.run(create_app(BASE_DIR, token, allow), host="0.0.0.0", port=port, log_level="warning",
                server_header=False)


if __name__ == "__main__":
    main()
