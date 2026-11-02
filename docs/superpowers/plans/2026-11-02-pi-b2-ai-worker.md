# Pi B2: YOLO runs on the PC's GPU for the Pi through a LAN AI worker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The server on the Pi gets YOLO results from the PC (RTX 3080) through an AI worker on `:8100`. When the PC is off, the Pi behaves as YOLO off, and it recovers by itself when the PC is back.

**Architecture:** Every YOLO user in the server calls `model(image_or_list, **kwargs)` and reads `Results` (`boxes`, `probs`, `names`). This covers the vehicle detector, helmet detector, wrong-way classifier and detector, and violation helmet classifier. `RemoteYolo` is a stand-in with the same call:
- It JPEG-encodes the images and POSTs them to the worker.
- It rebuilds `ultralytics.engine.results.Results` on the Pi (CPU torch is installed there since B1).
- So the detector, the trackers and the patrols work unchanged.

`load_yolo(path)` picks `RemoteYolo` when `AI_WORKER_URL` is set, else `YOLO(path)`. The worker on the PC is a small FastAPI app:
- It loads each weight file on first use and frees it after 10 minutes idle.
- It answers only the Pi's IP, and only with the shared token.

**Tech Stack:** Python 3.14, FastAPI/uvicorn, requests, ultralytics, torch (CUDA on the PC, CPU on the Pi), OpenCV.

**Spec:** chat decisions of 2026-11-02 (no separate spec file):
- B1 is done: the Pi serves with `YOLO_ALLOWED=0` and `BMA_FETCH=0`.
- B2 must cover every YOLO model.
- The worker loads on use and frees VRAM after 10 minutes idle.
- Access: a token in `.env` plus only the Pi's IP.
- Started with a Desktop icon. The existing watchdog also restarts it, but that check is turned on only at cutover.
- The Pi falls back to YOLO off when the PC is down.
- Test before production. Do not touch the PC's production :8000, ENVIRO or tunnel.

## Global Constraints

- Worker: port `8100`, binds `0.0.0.0`, `POST /predict`, `GET /` health.
- Auth:
  - Header `X-AI-Token` must equal `AI_WORKER_TOKEN` from the PC `.env`. The worker refuses to start when the token is empty.
  - The client IP must be in `AI_WORKER_ALLOW` (comma list, default `192.168.1.109,127.0.0.1`).
  - `GET /` needs only the IP check.
  - Never log the token.
- Pi config in its `.env`: `AI_WORKER_URL=http://192.168.1.101:8100` (the PC today) and the same `AI_WORKER_TOKEN`.
- Client: JPEG quality 95, connect timeout 1 s, read timeout 10 s. After a failed call, every call raises `YoloOff` at once for 30 s (circuit breaker), then the next call tries again.
- Worker: idle unload after 600 s per model, then `torch.cuda.empty_cache()`. One lock per model (one GPU job per model at a time).
- Model files are named by their path relative to the repo root (e.g. `yolo26x.pt`, `helmet_det_blur.pt`). The worker accepts only a relative `.pt` path that resolves inside its own repo root and exists.
- `YOLO_ALLOWED=0` still forbids local weights. With `AI_WORKER_URL` set, the switch is allowed and every model is remote.
- Plain Thai in docs, like `docs/MIGRATE_MACHINE.md`.

## Review Focus

1. Remote results must match local results. Tiled inference adds tile offsets to `boxes.data`, and the trackers read `boxes` too. Expect: the same frame gives the same boxes within JPEG tolerance (Task 5 compares local and remote on the PC).
2. The PC goes down mid-run. Expect: callers get `YoloOff` within about 1 s, threads do not pile up behind the timeout, nothing crashes, and the screens show AI as off. Then results come back within about 60 s of the worker returning.
3. Many Pi threads call at once: the live stream at 10 fps, the count workers and the patrols. Expect: the worker serialises per model and the queue does not grow without bound. Each call is bounded by the 10 s read timeout.
4. The token never appears in logs or responses. A wrong token or IP gets 403 with no model loaded.
5. VRAM is actually freed after 10 minutes idle (`nvidia-smi` drops). The PC production server's own YOLO is unaffected.

---

### Task 1: `RemoteYolo` client and `load_yolo`

**Files:**
- Create: `backend/vision/remote_yolo.py`
- Test: `tests/test_remote_yolo.py`

**Interfaces:**
- Produces:
  - `worker_url(env=os.environ) -> str | None`. The URL from `AI_WORKER_URL`, stripped, or `None` when unset or empty.
  - `class RemoteYolo(rel_path: str, url: str, token: str, post=requests.post, clock=time.monotonic)`.
    - `.names -> dict[int, str]`: fetched from the first successful response and cached. Before any success it asks the worker with `POST /predict` and no images.
    - `__call__(source, **kwargs) -> list[Results]`. `source` is one `np.ndarray` (BGR) or a list of them. `kwargs` pass through as JSON (`classes`, `conf`, `imgsz`, `iou`). `verbose` is dropped.
    - `.remote = True`.
    - On any connection error, timeout, non-200 reply or bad JSON it raises `YoloOff("AI worker offline")`. Calls inside the 30 s breaker window raise the same without calling `post`.
  - `load_yolo(path: str)`. Returns `RemoteYolo(relpath(path, BASE_DIR), ...)` when `worker_url()` is set. Otherwise `ultralytics.YOLO(path)` when `yolo_allowed()`. Otherwise it raises `YoloOff(NOT_ALLOWED)`.
  - `weights_available(path) -> bool`: `True` when the worker is set, else `os.path.exists(path)`.
- Wire format (Task 2 serves it):
  - Request: multipart with field `meta` (JSON `{"model": rel_path, "kwargs": {...}}`) and files `image0..imageN` (JPEG).
  - Response: JSON `{"names": {"0": "car", ...}, "results": [{"boxes": [[x1,y1,x2,y2,conf,cls], ...] | null, "probs": [p0, p1, ...] | null}, ...]}`.

- [ ] **Step 1: Write the failing tests** with a fake `post` that records calls and returns canned JSON.
  - `test_call_rebuilds_boxes`: one 100x80 image and canned boxes `[[1,2,30,40,0.9,2]]`. Assert `r[0].boxes.xyxy.tolist() == [[1,2,30,40]]`, `r[0].boxes.cls.tolist() == [2.0]` and `r[0].names[2] == "car"`.
  - `test_call_rebuilds_probs`: canned probs `[0.1, 0.9]` gives `r[0].probs.top1 == 1`.
  - `test_list_source_sends_one_request`: a list of 4 crops gives 1 `post` call with 4 image files and 4 results.
  - `test_kwargs_pass_through_without_verbose`: `meta.kwargs == {"conf": 0.2, "imgsz": 640}` for `model(img, conf=0.2, imgsz=640, verbose=False)`.
  - `test_token_sent_in_header`.
  - `test_connection_error_raises_yolo_off`.
  - `test_breaker_skips_post_for_30_s`: a failure at t=0, then a call at t=10 raises without calling `post`, and a call at t=31 calls `post` again.
  - `test_http_500_raises_yolo_off`.
  - `test_load_yolo_remote_when_url_set` (monkeypatch env).
  - `test_load_yolo_refuses_local_when_not_allowed`.
  - `test_weights_available_remote_true_for_missing_file`.

- [ ] **Step 2: Run them to see them fail**
  Run: `.venv\Scripts\python -m pytest tests/test_remote_yolo.py -q`
  Expected: ImportError for `backend.vision.remote_yolo`

- [ ] **Step 3: Implement `backend/vision/remote_yolo.py`.**
  - Build results with `Results(orig_img=img, path="", names=names, boxes=torch.tensor(rows, dtype=torch.float32).reshape(-1, 6) or None, probs=torch.tensor(p) or None)`.
  - Use `cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])`.
  - Put `post(..., timeout=(1, 10))` inside the try.

- [ ] **Step 4: Run the tests**
  Run: `.venv\Scripts\python -m pytest tests/test_remote_yolo.py -q`
  Expected: all pass

- [ ] **Step 5: Commit** `feat(vision): RemoteYolo, a YOLO stand-in that runs on the AI worker`

### Task 2: AI worker on the PC

**Files:**
- Create: `backend/vision/ai_worker.py` (FastAPI app and model pool)
- Create: `launch/ai_worker/start.bat`, `stop.bat`, `restart.bat` (same pattern as `launch/enviro/*.bat`, hidden through `launch/run_hidden.py ai_worker`, log `launch\logs\ai_worker.log`)
- Modify: `launch/run_hidden.py` (`TARGETS` gets `ai_worker`)
- Test: `tests/test_ai_worker.py`

**Interfaces:**
- Consumes: the wire format from Task 1.
- Produces:
  - `create_app(root: str, token: str, allow: set[str], factory=YOLO, clock=time.monotonic, idle_s=600) -> FastAPI`.
  - `ModelPool(root, factory, clock, idle_s)` with:
    - `get(rel_path)`, which raises `ValueError` for a bad path;
    - `unload_idle()`, which returns the paths it dropped;
    - `loaded() -> list[str]`.
  - Each model is loaded with `.to("cuda").half()` when CUDA is available.
  - A daemon thread calls `unload_idle()` every 60 s.
  - `python -m backend.vision.ai_worker` reads `.env` (`AI_WORKER_TOKEN`, `AI_WORKER_ALLOW`), exits with a clear message when the token is empty, and runs uvicorn on `0.0.0.0:8100`.

- [ ] **Step 1: Write the failing tests.** Use FastAPI `TestClient` with a fake factory whose model returns fixed `Results`, and override the client host through the `TestClient(app, client=("192.168.1.109", 5000))` argument, or an equivalent.
  - `test_predict_returns_boxes_and_names`
  - `test_wrong_token_403_and_nothing_loaded`
  - `test_ip_not_allowed_403`
  - `test_health_needs_ip_not_token`
  - `test_path_outside_root_rejected` (`../x.pt` and absolute paths give 400)
  - `test_non_pt_rejected`
  - `test_missing_file_rejected`
  - `test_model_loaded_once_and_reused`
  - `test_unload_idle_after_600_s` (fake clock: used at t=0, `unload_idle()` at t=599 keeps it and at t=601 drops it)
  - `test_token_not_in_error_text`
  - `test_empty_token_refuses_to_start` (call the function `main()` uses to read settings)

- [ ] **Step 2: Run them to see them fail**
  Run: `.venv\Scripts\python -m pytest tests/test_ai_worker.py -q`
  Expected: ImportError

- [ ] **Step 3: Implement the worker and the launch scripts.**
  - `GET /` returns `{"ok": true, "loaded": [...]}`.
  - `/predict` decodes each JPEG with `cv2.imdecode` and calls `model(images if many else images[0], **kwargs)` with `verbose=False`.
  - It serialises `r.boxes.data.tolist()` or `r.probs.data.tolist()`.

- [ ] **Step 4: Run the tests**
  Run: `.venv\Scripts\python -m pytest tests/test_ai_worker.py tests/test_remote_yolo.py -q`
  Expected: all pass

- [ ] **Step 5: Commit** `feat(vision): AI worker on :8100 serves YOLO to the Pi`

### Task 3: Every YOLO holder loads through `load_yolo`

**Files:**
- Modify: `backend/vision/yolo_detector.py:101-121` (`load_models`)
- Modify: `backend/vision/helmet_service.py:117-135`
- Modify: `backend/vision/wrongway_service.py:273-300`
- Modify: `backend/vision/violation_service.py:177-195`
- Modify: `backend/vision/yolo_switch.py`: `retry_missing()`
- Modify: `backend/services.py`: `allowed=yolo_allowed() or worker_url() is not None`, and start the retry thread when the worker is set
- Test: `tests/test_remote_holders.py`, `tests/test_yolo_switch.py`

**Interfaces:**
- Consumes: `load_yolo`, `weights_available`, `worker_url` and `RemoteYolo.remote` from Task 1.
- Produces:
  - Each holder replaces `os.path.exists(P)` with `weights_available(P)` and `YOLO(P)` with `load_yolo(P)`.
  - For a remote model, the holders skip `.to('cuda').half()` and the zero-image warm-up. They still read `.names` (for the wrong-way detector this may fetch from the worker).
  - `YoloSwitch.retry_missing() -> list[str]`: when `enabled`, it calls `load_models()` on each holder whose `models_loaded()` is false and returns their names. It does nothing when off. Errors are caught per holder, like `set`.
  - `services` starts a daemon thread that calls `yolo.retry_missing()` every 60 s, only when `worker_url()` is set.

- [ ] **Step 1: Write the failing tests.**
  - `test_detector_loads_remote_without_cuda_or_warmup`: monkeypatch `load_yolo` to return a fake remote model, then check that `detector.load_models()` never calls `.to` and makes no zero-image call.
  - `test_helmet_loads_remote_when_file_missing_on_pi`
  - `test_wrongway_loads_remote_classifier`
  - `test_violation_loads_remote_classifier`
  - `test_detector_infer_raises_yolo_off_when_worker_down` (a fake model that raises `YoloOff`, so `detect_boxes` raises `YoloOff`)
  - `test_retry_missing_loads_only_missing_holders`
  - `test_retry_missing_noop_when_off`
  - `test_retry_missing_survives_holder_error`

  For each patrol, also find how its loop handles an exception from the model call. Add a test that a `YoloOff` from the model leaves the patrol running, or fix the loop.

- [ ] **Step 2: Run them to see them fail**
  Run: `.venv\Scripts\python -m pytest tests/test_remote_holders.py tests/test_yolo_switch.py -q`
  Expected: failures on the new tests

- [ ] **Step 3: Implement the holder changes, `retry_missing` and the services wiring.**

- [ ] **Step 4: Run all YOLO tests, then the whole suite**
  Run: `.venv\Scripts\python -m pytest -q -p no:cacheprovider`
  Expected: all pass (588 plus the new tests)

- [ ] **Step 5: Commit** `feat(vision): YOLO holders use the PC AI worker when AI_WORKER_URL is set`

### Task 4: Start-up on the PC: token, icon, watchdog

**Files:**
- Create: `launch/ai_worker/install.ps1`. It creates the "BKK AI Worker" Desktop icon pointing to `start.bat`, the same way `launch/monitor/install.ps1` does. If `.env` has no `AI_WORKER_TOKEN`, it writes one (32 random bytes, hex) and prints only "token created".
- Modify: `launch/watchdog/watchdog.ps1`. Add `@{ Port = 8100; Folder = 'ai_worker' }`, checked only when `launch\watchdog\state\enabled_8100` exists (created at cutover). Its health check is `GET http://127.0.0.1:8100/`.
- Modify: `.gitignore` if needed (no secrets in git).

- [ ] **Step 1: Write the scripts.**

- [ ] **Step 2: Run `install.ps1`**, then check:
  - `.env` has a non-empty `AI_WORKER_TOKEN`;
  - the Desktop icon exists;
  - `git status` shows no `.env` change.

- [ ] **Step 3: Start the worker with the icon's `start.bat` and check it**
  Run: `curl -s http://127.0.0.1:8100/`
  Expected: `{"ok":true,"loaded":[]}`

- [ ] **Step 4: Check the watchdog** runs clean with the gate file absent and leaves :8100 alone:
  `powershell -File launch\watchdog\watchdog.ps1`, then look at `launch\watchdog\state\watchdog.log`.

- [ ] **Step 5: Check Windows Firewall lets the Pi reach :8100**
  Run from the Pi: `curl -s -m 3 http://192.168.1.101:8100/`
  Expected: `{"ok":true,...}`.
  If it times out, stop and ask the user to allow the rule. The command needs an administrator PowerShell:
  `New-NetFirewallRule -DisplayName "BKK AI worker 8100 (Pi only)" -Direction Inbound -Protocol TCP -LocalPort 8100 -RemoteAddress 192.168.1.109 -Action Allow`

- [ ] **Step 6: Commit** `feat(ai-worker): Desktop icon, token setup and gated watchdog check`

### Task 5: End to end on the Pi test :8001

**Files:**
- Modify: `docs/MIGRATE_MACHINE.md` (section 9: B2 done, settings, fallback behaviour)

- [ ] **Step 1: Compare local and remote on the PC.** Load one camera frame (from `instances/production/cache` or a BMA raw jpg). Run `detector.detect_boxes` with a local model, then again with `RemoteYolo` against the worker on 127.0.0.1.
  Expected:
  - the same number of boxes;
  - each box within 3 px;
  - the same classes.
  Ledger the numbers.

- [ ] **Step 2: Configure the Pi.**
  - Add `AI_WORKER_URL=http://192.168.1.101:8100` and `AI_WORKER_TOKEN=<same>` to the Pi `.env` (mode 600). Copy the token through `ssh` stdin so it never appears on a command line.
  - Pull the branch, then `sudo systemctl restart bkk-test`.

- [ ] **Step 3: Check AI works through the PC**
  Run on the Pi: `journalctl -u bkk-test -n 120 -o cat | grep -E "YOLO|AI|Helmet|WrongWay|Violation"`
  Expected: holders loaded (remote). Then `curl -s http://192.168.1.109:8001/api/ai/stats` shows counts rising, and the PC `GET :8100/` lists the loaded models.

- [ ] **Step 4: Fallback.** Stop the worker (`launch\ai_worker\stop.bat`) and wait 2 minutes.
  Expected:
  - `bkk-test` stays active with no `Traceback`;
  - `/api/ai/stats` stops rising;
  - Pi CPU does not climb.

  Start the worker again.
  Expected: within about 60 s the counts rise again, with no restart of `bkk-test`.

- [ ] **Step 5: Idle unload.** Stop `bkk-test` and wait 11 minutes.
  Expected:
  - `GET :8100/` lists no models;
  - `nvidia-smi` used memory dropped by about the worker's share;
  - the PC production :8000 still answers on `/`.

  Leave the worker running, and `bkk-test` stopped and disabled.

- [ ] **Step 6: Write the runbook update**, then commit `docs(migrate): AI worker for the Pi — settings, fallback, VRAM`
