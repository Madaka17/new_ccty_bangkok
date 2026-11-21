# Model files to weights/ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The YOLO weights (`yolo26x.pt`, `yolo11x.pt`, `helmet_det.pt`, `helmet_det_blur.pt`, `wrongway_det.pt`, `wrongway_cls.pt`, `helmet_cls.pt` when present) live in `weights/` instead of the project root. During the change and after it, every machine still finds every model.

**Architecture:** One resolver, `model_path(name)` in `backend/core/instance.py`. It looks in `weights/` first, then in the root, and when neither has the file it gives `weights/<name>`. Every caller that names a model goes through it. The PC AI worker (`backend/vision/ai_worker.py`) accepts both spellings ("x.pt" and "weights/x.pt") and lists a bare alias for each file in `weights/`. The Pi (which has no .pt files and sends paths relative to its root) keeps working before and after its own code update. The files move only after the code is live on the PC worker.

**Tech Stack:** Python 3, pytest, ultralytics (not needed in tests).

**Spec:** User request 2026-11-21: "ระดับ 1 ย้าย model" (level 1: move the model files out of the root into weights/). Context: `weights/` already exists and is in `.gitignore`. The Pi production server loads models through the AI worker on the PC with `AI_WORKER_URL`.

## Global Constraints

- `weights/` stays in `.gitignore`. No .pt file is added to git.
- Env overrides keep working: `AI_MODEL`, `HELMET_DET`, `HELMET_CLS`, `WRONGWAY_DET`, `WRONGWAY_CLS`. An absolute value is used as is. A bare name (production `.env` has `HELMET_DET=helmet_det_blur.pt`) goes through `model_path`.
- The worker's containment check stays: no absolute path, no path outside the root.
- User-facing Thai text stays short and plain (memory: plain Thai on every page).
- Test on :8001 before production. Production only on the user's go.

## Review Focus

- A file exists in both the root and `weights/`. `weights/` wins everywhere: resolver, worker resolve, listing (the alias must not hide a real root file of the same name).
- The Pi runs the old code and sends "yolo26x.pt" after the move. The worker must resolve it, and `GET /` must list "yolo26x.pt" so the old `weights_available` says yes.
- The Pi runs the new code and the PC worker is old. The Pi sends "weights/yolo26x.pt" while the file is still in the root. `weights_available` must say yes (alternate spelling in the list), and the old worker then fails that one request. Avoid this case: deploy the worker first (see Rollout).
- `bma_service` local fallback: a bare `YOLO('yolo26x.pt')` downloads 118 MB into the cwd when the file is not in the cwd. It must get a full path from `model_path`.
- Training scripts write their output models into `weights/` (not the root), so a new train does not put a .pt back in the root.

---

### Task 1: Resolver in instance.py

**Files:**
- Modify: `backend/core/instance.py` (after `BASE_DIR`)
- Test: `tests/test_model_path.py` (create)

**Interfaces:**
- Produces: `MODELS_DIR: str` (= `os.path.join(BASE_DIR, "weights")`), `model_path(name: str, base_dir: str = BASE_DIR) -> str`, `alternate_model_rel(rel: str) -> str`.

- [ ] **Step 1: Write the failing tests** (use `tmp_path` as `base_dir`)
  - `test_prefers_weights`: the file is in both `weights/a.pt` and `a.pt`, so the result is `weights/a.pt`.
  - `test_falls_back_to_root`: the file is only in the root, so the result is `<base>/a.pt`.
  - `test_missing_gives_weights`: the file is in neither, so the result is `<base>/weights/a.pt`.
  - `test_absolute_unchanged`: `model_path(str(tmp_path/"x"/"m.pt"))` returns the same string.
  - `test_alternate_rel`: `alternate_model_rel("a.pt") == "weights/a.pt"`, `alternate_model_rel("weights/a.pt") == "a.pt"`, `alternate_model_rel("runs/x/best.pt") == "weights/runs/x/best.pt"` (only the leading `weights/` is stripped).
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests/test_model_path.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** both functions. `model_path` joins `base_dir/weights/name`, then `base_dir/name`, and returns the first that is a file, else the weights one.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(core): model_path resolver prefers weights/ over the project root`

### Task 2: AI worker accepts both spellings

**Files:**
- Modify: `backend/vision/ai_worker.py` (`ModelPool.resolve`, `ModelPool.weights`), `backend/vision/remote_yolo.py` (`weights_available`)
- Test: `tests/test_ai_worker.py`, `tests/test_remote_yolo.py` (add tests)

**Interfaces:**
- Consumes: `alternate_model_rel` from Task 1.

- [ ] **Step 1: Write the failing tests**
  - `test_resolve_root_name_finds_weights_file`: only `root/weights/a.pt` exists, so `pool.resolve("a.pt")` returns its realpath.
  - `test_resolve_weights_name_finds_root_file`: only `root/a.pt` exists, so `pool.resolve("weights/a.pt")` returns its realpath.
  - `test_resolve_alternate_still_contained`: `pool.resolve("../x.pt")` still raises ValueError even when `root/weights/../x.pt`-style alternates exist.
  - `test_weights_lists_alias`: `root/weights/a.pt` exists, so `pool.weights()` contains both "weights/a.pt" and "a.pt".
  - `test_weights_alias_does_not_duplicate_root_file`: both `root/a.pt` and `root/weights/a.pt` exist, so "a.pt" appears once.
  - `test_weights_available_alternate` (remote_yolo): the worker lists only "weights/a.pt", so `weights_available(os.path.join(BASE_DIR, "a.pt"), get=fake)` is True. Use the existing fake-get pattern in that test file.
- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests/test_ai_worker.py tests/test_remote_yolo.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** In `resolve`, run the existing checks on `rel_path`. If the file is missing, run the same checks on `alternate_model_rel(rel_path)` before raising "model file not found". Factor the checks into one helper so both spellings get the containment check. In `weights()`, after the walk, add the bare name for each `weights/<name>.pt` at depth 1 when it is not already in the list. In `weights_available`, return `rel in s or alternate_model_rel(rel) in s`.
- [ ] **Step 4: Run** the same command. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(ai-worker): accept models in weights/ under either spelling`

### Task 3: Callers use model_path

**Files:**
- Modify: `backend/services.py:66-71`, `backend/vision/helmet_service.py:50`, `backend/vision/violation_service.py:75`, `backend/vision/wrongway_service.py:55,58`, `backend/bma/bma_service.py:176`, `backend/vision/yolo_detector.py:35` (default argument), and `local/pipeline/*.py` defaults and outputs that join `BASE_DIR`/`ROOT` with a model name: `collect_dataset.py:173`, `collect_helmet_dataset.py:135`, `collect_wrongway_dataset.py:451`, `relabel_dataset.py:30`, `train_from_labels.py:34-35`, `train_helmet.py:69`, `train_helmet_det.py:29,77`, `train_model.py:129`, `train_wrongway_cls.py:24`, `train_wrongway_det.py:41,49`, plus the usage docstrings that say `..\..\<name>.pt` or "project root" in those files.
- Modify (text): `web/src/components/HelmetPage.jsx:136`, `web/src/components/WrongWayPage.jsx:163` ("ที่ root" becomes "ในโฟลเดอร์ weights"), the error strings in `helmet_service.py:406` and `wrongway_service.py:472` when they name a location, and `docs/DEVELOPER.md` where it says the weights are in the project root.
- Test: `tests/test_services_import.py` (must still pass), plus `tests/test_model_path.py::test_env_bare_name` (add).

**Interfaces:**
- Consumes: `model_path`, `MODELS_DIR` from Task 1.

- [ ] **Step 1: Write the failing test** `test_env_bare_name`. With `monkeypatch.setenv("HELMET_DET", "helmet_det_blur.pt")`, reload `backend.vision.helmet_service`. Then `LOCAL_DET_PATH == model_path("helmet_det_blur.pt")`. If reloading that module is heavy or has side effects, assert the same through a small module-level helper and say so in the commit.
- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Implement.** Pattern for env vars: `model_path(os.getenv("HELMET_DET", "helmet_det.pt"))`. `services.py` keeps its fallback to `yolo26x.pt`, also through `model_path`. Training outputs use `os.path.join(MODELS_DIR, <name>)` and `os.makedirs(MODELS_DIR, exist_ok=True)` before the copy. Bare ultralytics stock names that are meant to auto-download (`yolo26s-cls.pt`, `yolo11n-cls.pt`, `yolo26m.pt` as a `--model` choice) stay bare.
- [ ] **Step 4: Run** `.venv\Scripts\python -m pytest -q tests`. Expected: everything passes. `cd web; npm run build` (or the project's web check) passes.
- [ ] **Step 5: Commit** `refactor: load and save YOLO weights through model_path (weights/ first)`

### Rollout (manual, after merge, on the user's go for production)

1. On the PC, restart the AI worker :8100 with the merged code. Check that `GET /` lists both spellings.
2. Deploy to test :8001 and check the helmet, wrong-way and vehicle-count pages.
3. On the user's go: deploy to Pi production, then restart the services.
4. Move the files in `E:\new_ccty_bangkok`: `Move-Item *.pt weights\`. Check the worker list, the AI pages and the server log for "not found".
5. Delete the root `__pycache__` and `.pytest_cache`.
