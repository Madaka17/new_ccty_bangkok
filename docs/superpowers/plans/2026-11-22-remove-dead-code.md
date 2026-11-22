# Remove Dead Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete code nothing calls (web components, JS exports, Python functions, imports) without changing any behaviour or any API endpoint.

**Architecture:** Pure deletions. Every item was found by an AST/regex scan and confirmed with `git grep -w` (only the definition matches). After the deletions, re-scan for code that only the deleted code used (cascade), delete that too, and repeat until nothing new appears.

**Tech Stack:** Python 3 (FastAPI backend, Flask ENVIRO), React + Vite (web), pytest, vitest.

**Spec:** the user's choices on 2026-11-22: a new PR from `origin/main`; delete all 10 orphan components; keep every API endpoint; delete test-only functions together with their tests; leave JS exports that are used inside their own file.

## Global Constraints

- Worktree `E:\new_ccty_bangkok-cleanup`, branch `chore/remove-dead-code`, cut from `origin/main` (d675c25). Never touch `E:\new_ccty_bangkok` itself.
- Keep every route: nothing decorated with `@router.*`, `@bp.*` or `@app.*` is removed, even when no client calls it.
- Keep `export` on names used inside their own file. Only remove what is used nowhere.
- A name counts as used if it appears anywhere outside its definition, in any of: `*.py`, `*.js(x)`, `*.ps1`, `*.bat`, `*.json`, `*.html`, `*.service`, `*.conf` (scripts call functions by name, and routes map strings). Check with `git grep -n -w <name>` before every deletion.
- Python: `E:\new_ccty_bangkok\.venv\Scripts\python.exe`. ENVIRO tests: `C:\Users\user\AppData\Local\Temp\claude\587002a2e53edb28\f3742b74-3c59-4643-b70a-471329bb410a\scratchpad\enviro-venv\Scripts\python.exe` from `ENVIRO\`. `web\node_modules` is a junction to the main checkout's.
- No commits by implementers; the controller commits per task.

## Review Focus

- Lazy or string-based use: `React.lazy(() => import(...))`, a route table with component names as strings, `getattr(obj, "name")`, a `.bat`/`.ps1` that calls `python -c "...name..."`. Expect: anything referenced this way stays.
- A CSS class or asset used only by a deleted component: it should go too, but only if `git grep` finds no other user.
- A helper used only by a deleted function (cascade): delete it in the same task, after re-checking.
- `web` build: `npm run build` must succeed. A missing import surfaces only there, not in vitest.
- Python import side effects: deleting an import must not drop a module import that registers something (routers, blueprints). Only the two named imports below are removed.

---

### Task 1: Web: orphan components and unused exports

**Files:**
- Delete: `web/src/components/FloodPinPage.jsx`, `web/src/components/dashboard/AccidentPanel.jsx`, `web/src/components/dashboard/FloodWatchCard.jsx`, `web/src/components/dashboard/KpiTiles.jsx`, `web/src/components/dashboard/RoadLists.jsx`, `web/src/components/dashboard/TrendChart.jsx`, `web/src/components/dashboard/VehicleCounts.jsx`, `web/src/components/fx/RiverBackdrop.jsx`, `web/src/components/water/WindyRadarCard.jsx`, `web/src/components/yolo/ViolationPanel.jsx`
- Modify: `web/src/lib/api.js` (remove `fetchRscPoints` ~246, `fetchFloodAnalysis` ~272, `fetchDistricts` ~426), `web/src/lib/store.js` (remove `useUserName` ~52, `greetingByHour` ~71)
- Modify: `web/src/components/fx/WeatherFx.jsx:4`: the comment that names RiverBackdrop; reword it so it does not name a deleted file.
- Cascade: any module, CSS file/class, image or test that only the deleted code used.

- [ ] **Step 1:** Run `git grep -n -w <name> -- web` for each name above. Confirm the only hit is the definition, or the WeatherFx comment for RiverBackdrop.
- [ ] **Step 2:** Run `npm run build` and `npm test` in `web\` before any change, and note the results as the baseline.
- [ ] **Step 3:** Delete the files and functions.
- [ ] **Step 4: Cascade.** For every import that a deleted file had (relative modules, CSS, assets), check with `git grep` whether anything else still uses that module or name. Delete what is now unused, and repeat.
- [ ] **Step 5:** Run `npm run build` (expected: success, no "could not resolve") and `npm test` (expected: same pass count as the baseline, minus any tests deleted with their code).
- [ ] **Step 6:** Report the deleted files and functions, the cascade deletions, and the build/test output.

### Task 2: Python: unused functions, test-only function, unused imports

**Files:**
- Modify: `backend/bma/bma_archive.py` (remove `rebuild_files` ~296), `backend/bma/bma_service.py` (remove `stop_scan` ~208, `generate_live_mjpeg` ~682), `backend/traffic/rsc_service.py` (remove `fetch_radius_points` ~318), `backend/vision/yolo_detector.py` (remove `stop_stream` ~381), `ENVIRO/server/simulator.py` (remove `reload_detector_config` ~133)
- Modify: `backend/agents/chat_context.py` (remove `site_context` ~570), `tests/test_chat_service.py` (remove the tests and the import that exist only for `site_context`; keep every other test)
- Modify: `ENVIRO/server/routes/warning.py:1` (drop `current_app` from the flask import), `ENVIRO/server/routes/admin.py:2` (remove `import shutil`)
- Cascade: helpers, constants and imports used only by the removed functions.

- [ ] **Step 1:** Run `git grep -n -w <name>` for each name above. Confirm the only hit is the definition (`site_context`: also `tests/test_chat_service.py`).
- [ ] **Step 2:** Run both pytest suites before any change, and note the pass counts as the baseline.
- [ ] **Step 3:** Delete the functions and the two imports.
- [ ] **Step 4: Cascade.** In each edited file, check every name that the removed bodies used (module constants, private helpers, imports) with `git grep -w`. Delete it when nothing else uses it, and repeat.
- [ ] **Step 5:** Run `python -m compileall -q backend ENVIRO/server launch` (expected: no output). Run both pytest suites: the same pass counts minus the deleted `site_context` tests, with 0 failures.
- [ ] **Step 6:** Report the deletions, the cascade, and the test output.

### Task 3: Re-scan and whole-branch review (controller)

- [ ] **Step 1:** Re-run the scanner (`deadscan.py` in the scratchpad) on the worktree. Any new candidate comes from the cascade: verify it with `git grep`, then delete it or list why it stays.
- [ ] **Step 2:** Have one reviewer read the whole branch diff for anything still referenced (Review Focus list).
- [ ] **Step 3:** Commit, push the branch, and open a PR into `main`.
