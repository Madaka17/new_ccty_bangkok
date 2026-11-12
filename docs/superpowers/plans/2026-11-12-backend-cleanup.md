# Backend Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bugs found in the 2026-11-12 review of `backend/` (group A) and make the code easier to read and change (group B) without changing what the site does.

**Architecture:** Small shared helpers in `backend/core/` and `backend/vision/patrol_common.py` replace code that is copied across modules. Each module keeps its public names and behavior. Every task ends with the full test suite green.

**Tech Stack:** Python 3.14, FastAPI, sqlite3, pytest. Run Python as `.venv/Scripts/python.exe` from the repo root `E:\new_ccty_bangkok`.

**Spec:** the review in the 2026-11-12 session (items A1–A6, B1–B6), summarized per task below.

## Global Constraints

- Branch `refactor/backend-cleanup` (from `main`). Never touch `main`, production or test servers.
- Group B tasks must not change behavior: same API responses, same files on disk, same DB schema, same log text.
- Full suite must pass after each task: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider` (baseline: 664 passed).
- `.venv/Scripts/pyflakes.exe backend server.py` must print nothing after Task 2.
- Code comments and docstrings in English, plain style matching the repo (short, says why). User-facing strings stay Thai and unchanged.
- One commit per task, message style `fix(scope): ...` / `refactor(scope): ...`, ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Do not stage untracked files you did not create (`.claude/`, `.github/`, `.impeccable/`, `local/`, `skills-lock.json`).

## Review Focus

- A state file read while it is being swapped on Windows: `os.replace` raises `PermissionError`; the save must retry briefly and the caller's existing error handling must still apply.
- A crash in the middle of a JSON save: the old file must stay readable (no truncated file).
- The patrol cleanup thread hitting `sqlite3.OperationalError: database is locked`: the thread must log and keep running.
- Two threads checking and spending the AI hourly budget at once: no call lost from the count.
- `print` output captured by `capsys` in existing tests (`test_local_llm_usage.py`, `test_yolo_off_callers.py`) after the move to logging: tests must still see the text on stdout.

---

### Task 1: Atomic JSON writes (A1)

**Files:**
- Create: `backend/core/atomic_file.py`
- Test: `tests/test_atomic_file.py`
- Modify (direct `json.dump` to the final path today): `backend/agents/flood_agent.py:202`, `backend/agents/riskbkk_agent.py:281`, `backend/agents/traffy_agent.py:254`, `backend/bma/bma_events.py:101`, `backend/core/alert_service.py:128-131`, `backend/core/thai_regions.py:143`, `backend/traffic/area_traffic.py:104`, `backend/traffic/rsc_service.py:242,308`, `backend/traffic/traffic_service.py:276`, `backend/vision/count_workers.py:42`, `backend/vision/longdo_cameras.py:59`, `backend/vision/violation_service.py:122`, `backend/vision/wrongway_service.py:143`, `backend/water/flood_service.py:172`, `backend/water/national_forecast.py:429`, `backend/water/river_roads.py:235`, `backend/water/thaiwater_api.py:55`
- Modify (already tmp + `os.replace`, switch to the helper for one code path): `backend/traffic/events_calendar.py:202`, `backend/traffic/flood_route.py:203`, `backend/vision/doh_cameras.py:167`, `backend/vision/flood_cam_service.py:212-219`, `backend/vision/world_cameras.py:339`, `backend/vision/yolo_switch.py:99`, `backend/water/bkk_districts.py:286`, `backend/water/nasa_feeds.py:220`, `backend/water/national_forecast.py:593`, `backend/water/north_route.py:410`, `backend/water/province_flood.py:372`
- Do not touch `backend/bma/bma_service.py:save_raw_frame` (binary JPEG, best effort by design).

**Interfaces:**
- Produces: `write_json_atomic(path: str, data, **dump_kwargs) -> None` in `backend/core/atomic_file.py`. Writes `f"{path}.{threading.get_ident()}.tmp"` with `encoding="utf-8"`, flushes, `os.fsync`, then `os.replace(tmp, path)`. On `PermissionError` from `os.replace` it retries up to 5 times with `time.sleep(0.05)`. On any failure it removes the tmp file and re-raises the original exception. `dump_kwargs` go to `json.dump` unchanged (callers keep their own `ensure_ascii`, `indent`).

- [ ] **Step 1: Write failing tests** in `tests/test_atomic_file.py`:
  - `test_writes_and_reads_back(tmp_path)`: write `{"a": "ถนน"}` with `ensure_ascii=False`; `json.load` returns the same dict; file text contains `ถนน`.
  - `test_old_file_kept_when_dump_fails(tmp_path)`: existing file holds `{"old": 1}`; write `{"x": object()}` raises `TypeError`; file still loads as `{"old": 1}`; no `*.tmp` left in `tmp_path`.
  - `test_retries_replace_on_permission_error(tmp_path, monkeypatch)`: patch `os.replace` in the module to raise `PermissionError` twice then call the real one; write succeeds.
  - `test_gives_up_after_retries(tmp_path, monkeypatch)`: `os.replace` always raises `PermissionError`; call raises `PermissionError`; no `*.tmp` left.
- [ ] **Step 2:** Run `.venv/Scripts/python.exe -m pytest tests/test_atomic_file.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `write_json_atomic` as specified.
- [ ] **Step 4:** Run the test file. Expected: 4 passed.
- [ ] **Step 5:** Replace each listed write site. Keep each caller's surrounding `try/except` and its log text. Where the caller had no `try` (`alert_service._save`, `events_calendar`), keep it without one (same as today). For the "already atomic" sites remove the hand-written tmp/replace lines.
- [ ] **Step 6:** Add `test_alert_save_keeps_subscribers_when_write_fails` to `tests/test_alert_service.py`: build the service as the existing tests do with one subscriber, save, then monkeypatch `json.dump` inside `backend.core.atomic_file` to raise `OSError`; a second `_save()` raises; a fresh service on the same paths still has the subscriber.
- [ ] **Step 7:** Run the full suite and `grep -rn "json.dump(" backend` (only `atomic_file.py` and in-memory `json.dumps` remain). Expected: all pass.
- [ ] **Step 8:** Commit `fix(storage): write state JSON files atomically so a crash cannot truncate them`.

### Task 2: Small fixes (A2, A4, A5, A6)

**Files:**
- Modify: `backend/bma/bma_service.py:226-236, 362-374, 264`, `backend/vision/incident_service.py:236-238`, `backend/vision/helmet_service.py:636-652`, `backend/vision/wrongway_service.py:813-830`, files listed by pyflakes
- Test: `tests/test_small_fixes.py`

**Interfaces:**
- Consumes: `safe_id` from `backend/vision/frame_utils.py` (already used by helmet/wrongway; raises `ValueError` on a bad id — check its behavior and return `None` from `snapshot_path` for a bad id).

- [ ] **Step 1: Write failing tests** in `tests/test_small_fixes.py`:
  - `test_incident_snapshot_path_rejects_traversal`: an `IncidentManager`-like call `snapshot_path("..\\..\\x")` and `snapshot_path("a/b")` return `None` (construct the object without starting threads; use `object.__new__` and set `snapshot_dir` if the constructor starts threads).
  - `test_bma_loop_logs_start_scan_error(capsys, monkeypatch)`: run one iteration of the scheduler loop body (extract it as `_scan_tick(self, last_start) -> float` returning the new `last_start`) with `start_scan` raising `RuntimeError("boom")`; stdout contains `[BMA]` and `boom`. A second identical error does not print again.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3 (A2):** In `bma_service.py` extract `_scan_tick`; on exception print `[BMA] start_scan failed: {e}` only when `str(e)` differs from the last printed one (store `self._last_tick_error`). In `_run_scan_cycle` count failed futures; after the loop, when the count is > 0, print one line `[BMA] {n} cameras failed this cycle, first: {first_error}`. Remove unused `t_cam`.
- [ ] **Step 4 (A4):** `snapshot_path` uses `safe_id`, returns `None` on `ValueError`.
- [ ] **Step 5 (A6):** In both `_cleanup_loop` methods: wrap each `os.remove` in its own `try/except OSError: pass`; catch `(OSError, sqlite3.Error)` around the DB part and print `[Helmet] cleanup failed: {e}` / `[WrongWay] cleanup failed: {e}` instead of letting the thread die.
- [ ] **Step 6 (A5):** Remove every item `pyflakes` reports (unused imports, `e`, `year_span`). Run `.venv/Scripts/pyflakes.exe backend server.py`. Expected: no output.
- [ ] **Step 7:** Full suite. Expected: all pass.
- [ ] **Step 8:** Commit `fix(backend): log BMA scan errors, guard incident image path, keep patrol cleanup alive`.

### Task 3: Thread-safe AI hourly budget (A3)

**Files:**
- Create: `backend/core/hourly_budget.py`
- Test: `tests/test_hourly_budget.py`
- Modify: `backend/vision/helmet_service.py` (`_calls` use at 99, 290-294, 357, 572-580), `backend/vision/wrongway_service.py` (198, 504-508, 561, 743-752), `backend/vision/flood_cam_service.py` (`_calls`, `_calls_lock`, `_budget_ok` 310-315 and the append in `_ask`), `backend/vision/incident_service.py` (`_checks`, `_budget_ok` 152-154, append in `_confirm`)

**Interfaces:**
- Produces: `class HourlyBudget(limit: int, window_s: float = 3600)` with methods `used(now: float | None = None) -> int` (prunes, returns count), `allows(now: float | None = None) -> bool` (`used(now) < limit`), `spend(now: float | None = None) -> None`. Internally a `deque` plus a `threading.Lock`; `now` defaults to `time.time()`. `limit` is read on each call from attribute `self.limit` so callers that change it at runtime still work.

- [ ] **Step 1: Write failing tests:** `test_allows_until_limit` (limit 2: allows, spend, allows, spend, not allows); `test_old_calls_expire` (spend at t=0, `used(3601) == 0`); `test_parallel_spend_counts_every_call` (8 threads × 500 `spend()` → `used() == 4000`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `HourlyBudget`.
- [ ] **Step 4:** Run. Expected: 3 passed.
- [ ] **Step 5:** Replace the four hand-written budgets. Keep each `_budget_ok` method name and its extra conditions (agent backoff in helmet/wrongway, `self.client is not None` in incident). `status()` uses `budget.used(now)` for `calls_last_hour`. Check `tests/test_wrongway_throttle.py` for direct `_calls` use and update it to the new attribute only if it reads `_calls`.
- [ ] **Step 6:** Full suite. Expected: all pass.
- [ ] **Step 7:** Commit `fix(vision): one thread-safe hourly budget for AI checks`.

### Task 4: One geo module for distances (B1)

**Files:**
- Create: `backend/core/geo.py`, `tests/test_geo.py`
- Modify: every `_km` / `_haversine_m` definition and import: `traffic/area_roads.py:45`, `traffic/events_calendar.py:92`, `traffic/guidance_service.py:85`, `traffic/road_service.py:112`, `traffic/rsc_service.py:344`, `water/nasa_feeds.py:54`, `water/north_route.py:191`, `water/river_roads.py:58`, `water/water_service.py:664`, and importers in `api/traffic.py`, `traffic/area_traffic.py`, `traffic/near_traffic.py`, `traffic/traffic_service.py`, `water/north_flow.py`

**Interfaces:**
- Produces in `backend/core/geo.py`:
  - `haversine_km(lat1, lng1, lat2, lng2, radius_km=6371.0) -> float` (the `events_calendar` / `nasa_feeds` formula).
  - `flat_km(lat1, lng1, lat2, lng2, km_per_deg_lat=110.57, km_per_deg_lng=111.32) -> float`: `math.hypot((lng2 - lng1) * km_per_deg_lng * math.cos(math.radians((lat1 + lat2) / 2)), (lat2 - lat1) * km_per_deg_lat)`.
- Mapping (must keep each module's constants): `area_roads`, `guidance_service`, `river_roads` → `flat_km` defaults; `road_service` → `flat_km(..., km_per_deg_lat=111.0, km_per_deg_lng=111.0)`; `north_route` → `flat_km(..., km_per_deg_lat=110.54)`; `events_calendar`, `nasa_feeds` → `haversine_km`; `rsc_service._haversine_m` → `haversine_km(..., radius_km=6371.0) * 1000`; `water_service._km` keeps its `None → 999.0` guard and uses `haversine_km(..., radius_km=6371.0)` (its `12742 * asin(...)` form is the same formula).
- Modules whose `_km` takes `(a, b)` tuples keep a one-line local `_km(a, b)` that unpacks and calls `flat_km`, so call sites stay unchanged. Other modules may keep `_km = flat_km`-style aliases only where a partial with constants is needed; prefer calling the geo function directly.

- [ ] **Step 1: Write failing tests** in `tests/test_geo.py`: for 5 fixed point pairs around Bangkok and Chiang Mai, assert each new call equals the old module's formula (copy the old bodies into the test as reference functions) within `1e-9` km.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `geo.py`; replace definitions and imports.
- [ ] **Step 4:** Full suite. `grep -rn "def _km\|def _haversine" backend` shows only the tuple wrappers and the `water_service` guard wrapper.
- [ ] **Step 5:** Commit `refactor(geo): one module for distance math`.

### Task 5: Shared patrol helpers for helmet and wrong-way (B2)

**Files:**
- Create: `backend/vision/patrol_common.py`, `tests/test_patrol_common.py`
- Modify: `backend/vision/helmet_service.py`, `backend/vision/wrongway_service.py`

**Interfaces:**
- Produces in `patrol_common.py`:
  - `class PatrolStore(db_path: str, table: str, schema_sql: str, index_sql: str, lock: threading.Lock)`: `init()` (runs schema + index, as `_init_db` does today), `connect() -> sqlite3.Connection` (`timeout=10`, `row_factory=sqlite3.Row`, `check_same_thread=False`), `insert(row: tuple)` (`INSERT OR REPLACE` with `len(row)` placeholders, under the lock), `update(item_id: str, **fields)`, `delete_older(cutoff_ts: int, keep_verdict: str)`.
  - `ask_cloud_vision(vision, system_prompt: str, jpeg: bytes, context: str, models: list[str], timeout_ms: int, log_tag: str | None = None) -> str`: the Gemini (with 503/UNAVAILABLE/504/DEADLINE fallback over `dict.fromkeys(models)`) and Claude branches copied from today's `_ask`; prints `[{log_tag}] {model} overloaded (503), trying {next}` only when `log_tag` is set (helmet sets it, wrong-way does not — today's behavior). The qwen branch stays in each patrol's `_ask`, because the two decide it differently.
  - `archive_evidence(archive_dir, csv_name, item_id, camid, cam, crop, marked, label, banner_h, text_y, font_scale, header: list[str], values: list, log_tag: str) -> str | None`: the shared body of both `_archive` methods; `values` are the CSV columns after `id, datetime, camid, camera, district` and before `frame, crop`; returns `frame_out`, or on `OSError` prints `[{log_tag}] archive to {archive_dir} failed: {e}` and returns `None`.
  - `clean_cache_dir(cache_dir: str, cutoff_ts: float) -> None`: per-file `os.remove` with `OSError` ignored.
- Both patrol classes keep every public method and attribute name used by `backend/api/patrols.py`, `backend/services.py` and tests.

- [ ] **Step 1: Write characterization tests first, against today's classes** in `tests/test_patrol_common.py` (they must pass before the refactor): for each patrol, build it with `object.__new__` (no threads, no models), set `db_path` to `tmp_path`, `lock`; call `_init_db`, `_insert` a full row, `_update` two fields, read back with `_db()`; call `_archive` with a 40×60 black frame into a patched `ARCHIVE_DIR` and assert file names, CSV header and row; call `_ask` with a fake `vision` whose `client.models.generate_content` raises `"503 UNAVAILABLE"` once then returns `text=' {"ok":1} '` and assert the stripped text and the models tried.
- [ ] **Step 2:** Run. Expected: PASS on the current code.
- [ ] **Step 3:** Add unit tests for `PatrolStore`, `ask_cloud_vision`, `archive_evidence`, `clean_cache_dir`. Run. Expected: FAIL (module missing).
- [ ] **Step 4:** Implement `patrol_common.py`; make both patrols delegate. Keep `_init_db`, `_db`, `_insert`, `_update`, `_archive`, `_ask`, `_cleanup_loop` as thin methods so callers and tests do not change.
- [ ] **Step 5:** Full suite including the characterization tests. Expected: all pass.
- [ ] **Step 6:** Commit `refactor(vision): share storage, archive and cloud-vision code between patrols`.

### Task 6: One Gemini client getter (B3)

**Files:**
- Create: `backend/core/gemini.py`, `tests/test_gemini_client.py`
- Modify: `backend/traffic/road_service.py:309-319`, `backend/water/flood_service.py:325-335`, `backend/traffic/guidance_service.py:130-137`, `backend/vision/incident_service.py:107-111`

**Interfaces:**
- Produces: `gemini_client()` in `backend/core/gemini.py`: returns `None` when the `google.genai` import failed or neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` is set, or when `genai.Client(...)` raises; otherwise one client per API key, cached under a lock (a key change makes a new client).
- Callers keep their method names (`_client`, `_gemini`) as one-line wrappers so tests that patch them still work. Keep `road_service` / `flood_service` `self._ai_client` behavior: check `tests/test_road_service.py` and `tests/test_flood_service.py` for how they stub the client and keep that path working.

- [ ] **Step 1: Write failing tests:** no key → `None`; key set with a fake `genai` module (monkeypatch `backend.core.gemini.genai`) → same object on two calls; a different key → new object; `Client` raising → `None`.
- [ ] **Step 2:** Run. FAIL. **Step 3:** Implement and wire callers. **Step 4:** Full suite passes.
- [ ] **Step 5:** Commit `refactor(ai): one cached Gemini client`.

### Task 7: Split the longest functions (B4)

**Files:**
- Modify: `backend/vision/vehicle_tracker.py:159-360` (`update`), `backend/core/alert_service.py:155-282` (`candidates`), `backend/traffic/road_service.py:184-306` (`build`)
- Test: `tests/test_vehicle_tracker.py` (new), existing `tests/test_alert_service.py`, `tests/test_road_service.py`

Out of scope (I/O loops without tests, splitting them gains little): `yolo_detector._process_loop`, `bma_service._run_scan_cycle`.

- [ ] **Step 1:** Write `tests/test_vehicle_tracker.py` characterization test on today's code: feed a scripted sequence of 30 synthetic detection results (two cars crossing the counting line, one motorcycle standing still, one box that disappears and returns) built the way `update` reads them; record the returned value and the tracker's public counters after every frame; assert against values captured from the current code (run once, paste the captured list into the test).
- [ ] **Step 2:** Run. PASS on current code.
- [ ] **Step 3:** Split each function into private helpers of at most ~40 lines, named for what each part does (for example `_match_tracks`, `_count_crossings`, `_expire_tracks` — choose names from the code's own comments). Pure moves only: no logic change, no reordering of side effects.
- [ ] **Step 4:** Full suite. Expected: all pass, characterization unchanged.
- [ ] **Step 5:** Commit `refactor: split tracker update, alert candidates and road risk build into named steps`.

### Task 8: Start background jobs only in `services.start()` (B5)

**Files:**
- Modify: `backend/services.py:116` (`survey.start()`), `:120` (`camera_health.start()`) → move both calls into `start()` at its top.
- Test: `tests/test_services_import.py`

- [ ] **Step 1:** Write a test that patches `SurveyManager.start` and `CameraHealth.start` to record calls, imports `backend.services` fresh (`importlib.reload` after patching), and asserts neither was called by the import. Mark it to skip if importing `backend.services` needs YOLO weights or network in the test environment (check `tests/test_yolo_holders.py` for how other tests import it).
- [ ] **Step 2:** Run. FAIL. **Step 3:** Move the calls. **Step 4:** Full suite passes.
- [ ] **Step 5:** Commit `refactor(services): start survey and camera health with the other jobs`.

### Task 9: Logging instead of print (B6)

**Files:**
- Create: `backend/core/log.py`, `tests/test_log.py`
- Modify: every `print(` in `backend/` (234 sites; work one sub-package per commit: `core`, `api`, `agents`, `bma`, `traffic`, `vision`, `water`)

**Interfaces:**
- Produces: `get_logger(tag: str) -> logging.Logger` in `backend/core/log.py`. Logger name `bkk.<tag>`. On first call it configures logger `bkk`: level `INFO`, `propagate=False`, one handler whose `emit` writes to the *current* `sys.stdout` (resolve `sys.stdout` at emit time so pytest `capsys` still captures) and flushes. Formatter: `"[%(tagname)s] %(message)s"` where `tagname` is the part after `bkk.`; for `get_logger("")` the format is `"%(message)s"`.
- Conversion rule: `print(f"[Tag] text")` → `log.info("text")` with `log = get_logger("Tag")` at module top, keeping the exact tag spelling. Lines that report failures (`failed`, `error`, `Warning`) use `log.warning`. Prints without a `[Tag]` prefix use `get_logger("")`. The stdout text must be identical to today's.

- [ ] **Step 1: Write failing tests:** `test_same_text_as_print(capsys)`: `get_logger("BMA").info("x 1")` → `capsys.readouterr().out == "[BMA] x 1\n"`; `test_untagged(capsys)`; `test_warning_same_format(capsys)`; `test_no_duplicate_handlers` (call `get_logger` 3 times, one handler on `bkk`).
- [ ] **Step 2:** Run. FAIL. **Step 3:** Implement. **Step 4:** Run. PASS.
- [ ] **Step 5:** Convert one sub-package; full suite; commit `refactor(log): use logging in backend/<pkg>`. Repeat for each sub-package.
- [ ] **Step 6:** `grep -rn "print(" backend --include=*.py` shows nothing outside CLI `__main__` blocks.

### Task 10: Whole-branch review and test-server check

- [ ] **Step 1:** Whole-branch review (`git diff main...HEAD`) by a fresh reviewer.
- [ ] **Step 2:** Full suite and pyflakes.
- [ ] **Step 3:** Report to the user. Deploy to test :8001 or production only when the user says so.
