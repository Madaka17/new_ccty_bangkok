"""
AI worker: runs YOLO on this PC's GPU for the Raspberry Pi (B2 of the Pi move, docs/MIGRATE_MACHINE.md section 9).

The Pi's YOLO holders get a RemoteYolo (remote_yolo.py) that POSTs PNG images to /predict here. Each weights
file is loaded on first use and dropped after IDLE_S without calls, so VRAM is free when the Pi does not need it.

Access: only IPs in AI_WORKER_ALLOW (default the Pi and this PC) and, for /predict, the AI_WORKER_TOKEN header.
Run: launch\\ai_worker\\start.bat (python -m backend.vision.ai_worker), port 8100.
"""
import gc
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
        self.models = {}   # rel_path -> {"model", "lock", "used"}

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
        """(model, its lock). Loads the model when needed."""
        full = self.resolve(rel_path)
        with self.lock:
            entry = self.models.get(rel_path)
            if entry is None:
                print(f"[AI worker] loading {rel_path}")
                entry = {"model": self.factory(full), "lock": threading.Lock(), "used": self.clock()}
                self.models[rel_path] = entry
            entry["used"] = self.clock()
            return entry["model"], entry["lock"]

    def unload_idle(self):
        now = self.clock()
        with self.lock:
            dropped = [p for p, e in self.models.items() if now - e["used"] > self.idle_s]
            for p in dropped:
                del self.models[p]
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

    def loaded(self):
        with self.lock:
            return sorted(self.models)


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
        return {"ok": True, "loaded": pool.loaded()}

    @app.post("/predict")
    async def predict(request: Request):
        if request.client is None or request.client.host not in allow:
            return forbidden()
        if request.headers.get("X-AI-Token") != token:
            return forbidden()
        form = await request.form()
        try:
            meta = json.loads(form["meta"])
            rel_path = meta["model"]
            kwargs = dict(meta.get("kwargs") or {})
            pool.resolve(rel_path)
        except (KeyError, ValueError, TypeError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        images = []
        i = 0
        while f"image{i}" in form:
            data = await form[f"image{i}"].read()
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return JSONResponse({"error": f"image{i} is not a picture"}, status_code=400)
            images.append(img)
            i += 1
        kwargs["verbose"] = False

        def run():
            model, lock = pool.get(rel_path)
            names = {str(k): v for k, v in model.names.items()}
            if not images:
                return {"names": names, "results": []}
            with lock:
                results = model(images if len(images) > 1 else images[0], **kwargs)
            return {"names": names, "results": [_serialise(r) for r in results]}

        import anyio
        try:
            return await anyio.to_thread.run_sync(run)
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
