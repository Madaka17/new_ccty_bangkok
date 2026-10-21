# BKK Monitor Workflow 3D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Workflow" page in the BKK Monitor app that draws the whole pipeline (images, data, YOLO, AI analysis, output) as a live 3D graph, each node coloured by the collector's real state.

**Architecture:** A pure Python builder (`launch/monitor/monitor_flow.py`) turns the collector's status rows into nodes and edges. `Api.flow(target)` returns it to the desktop window (pywebview) and to the phone page (`monitor_web.py`, read-only). A browser ES module (`launch/monitor/ui/flow3d.js`) draws the graph with a vendored Three.js and updates colours on every 5 s status poll.

**Tech Stack:** Python 3 stdlib, pywebview 6.2.1 (`webview.start(http_server=True)` so ES modules load), Three.js 0.170.0 (vendored: `three.module.min.js`, `OrbitControls.js`, `CSS2DRenderer.js`), pytest.

**Spec:** User request 2026-10-21 (Thai): add a workflow from fetching images and data, through AI analysis, to the end of the flow, as 3D, in the BKK Monitor app. Decisions: live status (not a static diagram); one node per agent/model; English labels like the rest of the app; Three.js stored locally, no CDN.

## Global Constraints

- UI copy in English, same tone as the existing app (`launch/monitor/ui/index.html`).
- No new pip packages. Three.js 0.170.0 files live in `launch/monitor/ui/vendor/`; the page loads nothing from the internet.
- The phone page stays read-only: only `flow` is added to `READ_ONLY`; static serving is a fixed whitelist of files.
- The collector (`collector.py`, `monitor_checks.py`) is not changed. All node states come from rows already in `status`.
- Node states use the app's state words: `ok`, `warn`, `fail`, `idle`, `stopped`, and the app's colours (`--ok #3ecf8e`, `--warn #f5a524`, `--fail #f0556a`, `--idle #6b7280`, `--stopped #4b5563`, `--accent #5b8cff`, background `#0b0d10`).
- `prefers-reduced-motion: reduce`: no auto-rotate, no moving particles.

## Review Focus

1. Target server down or stopped (no `agent:`/`yolo:` rows): nodes show `idle` "not checked", never a crash or an empty scene. Test: `test_server_down_gives_idle_nodes` (Task 1).
2. Agent names that change (e.g. `Wrong-way check (qwen)` becomes `(gemma)`, or a new caller like `violation_service`): still drawn, linked to gateway and server. Test: `test_unknown_agent_still_linked` and `test_wrongway_prefix` (Task 1).
3. Agent row without `extra` (old collector, or the "agent checks" crash row): data nodes do not crash and ignore that row. Test: `test_data_node_ignores_rows_without_extra` (Task 1).
4. Path traversal on the phone server (`/vendor/../state/monitor.db`, `/vendor/x.py`): 404. Test: `test_static_whitelist_only` (Task 2).
5. Leaving the Workflow page or switching Production/Test many times: renderer disposed, no second canvas, no growing animation loops. Check in Task 3 Step 5.

---

### Task 1: Graph builder `monitor_flow.py`

**Files:**
- Create: `launch/monitor/monitor_flow.py`
- Test: `tests/test_monitor_flow.py`

**Interfaces:**
- Consumes: status rows as `Store.current()` returns them: dicts with `key, group, target, name, state, detail, since, checked_at, extra` (`extra` is a dict or None; agent rows have `extra.data`, `extra.note`).
- Produces: `build(items: list[dict], target: str) -> dict` with
  `{"target": str, "stages": ["Images", "Data", "YOLO", "AI analysis", "Output"], "nodes": [Node], "edges": [Edge]}`
  `Node = {"id": str, "stage": int, "label": str, "state": str, "detail": str, "since": float|None}`
  `Edge = {"from": str, "to": str, "state": "ok"|"fail"|"idle"}`

Nodes (`t` = target, `production` or `test`). A node bound to a missing key is `idle` with detail `"not checked"`.

| stage | id | label | source |
|---|---|---|---|
| 0 | `cam_bma` | BMA cameras | `service:cam_bma` |
| 0 | `cam_itic` | ITIC cameras | `service:cam_itic` |
| 0 | `camera` | Camera status file | `service:camera` |
| 1 | `water` | Water & rain feeds | derived from agents: Bangkok flood report, Bangkok road water, Road flood risk, Bangkok districts (50), Provinces flood, National 7-day outlook, Northern water route |
| 1 | `traffic` | Traffic feeds | derived: Traffic guidance, Road flood risk, incident_service |
| 1 | `traffy` | Traffy Fondue | derived: Traffy flood reports |
| 1 | `riskbkk` | riskbkk accidents | derived: Accident risk (riskbkk) |
| 2 | `yolo_switch` | YOLO switch | `yolo:{t}:YOLO switch` |
| 2 | `yolo_scan` | BMA camera scan | first `yolo:{t}:*` whose name contains `BMA camera scan` |
| 2 | `yolo_live` | Live AI camera | name contains `live AI camera` |
| 2 | `helmet` | Helmet detector | name starts with `helmet` |
| 2 | `wrongway` | Wrong-way classifier | name starts with `wrong-way` |
| 3 | `gateway` | AI gateway | `service:gateway` |
| 3 | `agent:<name>` | `<name>` | every `agent:{t}:*` row, sorted by name |
| 4 | `server` | Production / Test | `server:{t}` |
| 4 | `tunnel` | Cloudflare tunnel | `service:tunnel` (production only) |
| 4 | `public` | Public site | `service:public` (production only) |

Derived data node rule: a consumer row is *judged* when it has `extra` and `extra.data` not in `("", "–", None)`. Its data is bad when `extra.note` is `"data stale"`, `"source sent no readings"`, or starts with `"endpoint error"`. No judged consumer: `idle`, detail `"no agent reads it now"`. All judged bad: `fail`. Some bad: `warn`. None bad: `ok`. Detail: `"{good} of {judged} agents get fresh data"`. `since`: None.

Edges: `cam_bma→camera`, `cam_itic→camera`, `camera→yolo_scan`, `camera→yolo_live`, `yolo_switch→{yolo_scan, yolo_live, helmet, wrongway}`, `yolo_scan→{helmet, wrongway, agent:Flood cameras (vision)}`, `helmet→agent:Helmet check (vision)`, `wrongway→` the agent whose name starts with `Wrong-way check`, each data node → its consumer agents that exist, `gateway→` every agent node, every agent node `→server`, production only: `server→tunnel→public`. Skip any edge whose end node does not exist. Edge state: `fail` when the `from` node is `fail`; `ok` when `from` is `ok`/`warn` and `to` is not `fail`/`stopped`; else `idle`.

- [ ] **Step 1: Write failing tests** in `tests/test_monitor_flow.py` (import like `tests/test_monitor_web.py`, a helper `row(key, state, name=None, extra=None)` building status dicts):
  - `test_stages_and_core_nodes`: with `server:production ok`, `service:cam_bma ok`, `service:camera ok` → `build(items, "production")["stages"] == ["Images", "Data", "YOLO", "AI analysis", "Output"]`; node `cam_bma` state `ok`, stage 0; node `server` label `"Production"`, stage 4; edge `cam_bma→camera` state `ok`.
  - `test_server_down_gives_idle_nodes`: only `server:test fail` → for `target="test"` nodes `yolo_scan` and `yolo_switch` are `idle` with detail `"not checked"`; no node id starts with `agent:`; no `tunnel` node; no exception.
  - `test_data_node_states`: agents `Traffic guidance` (extra data `"2m"`, note `""`) and `Road flood risk` (extra data `"40m"`, note `"data stale"`) → `traffic` is `warn` with detail `"1 of 2 agents get fresh data"`; if both stale → `fail`.
  - `test_data_node_ignores_rows_without_extra`: agent `Traffy flood reports` with `extra=None` → `traffy` is `idle`.
  - `test_wrongway_prefix`: agent row `Wrong-way check (gemma)` and yolo row `wrong-way  wrongway_cls.pt` → edge `wrongway→agent:Wrong-way check (gemma)` exists.
  - `test_unknown_agent_still_linked`: agent row `violation_service` → edges `gateway→agent:violation_service` and `agent:violation_service→server` exist.
  - `test_edge_fail_from_failed_node`: `service:cam_itic fail`, `service:camera ok` → edge `cam_itic→camera` state `fail`.

- [ ] **Step 2: Run tests to verify they fail**
  Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_flow.py -q`
  Expected: FAIL, `ModuleNotFoundError: No module named 'monitor_flow'`.

- [ ] **Step 3: Implement `build(items, target)`** in `launch/monitor/monitor_flow.py`, with a module docstring in the style of the sibling files (what it is, who calls it). Tables above as module constants (`STAGES`, `DATA_SOURCES = {"water": ("Water & rain feeds", [...]), ...}`, `YOLO_NODES`).

- [ ] **Step 4: Run tests to verify they pass**
  Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_flow.py -q`
  Expected: all PASS.

- [ ] **Step 5: Commit**
  `git add launch/monitor/monitor_flow.py tests/test_monitor_flow.py`
  `git commit -m "feat(monitor): workflow graph from the collector's status rows"`

---

### Task 2: `Api.flow`, phone serving, ES modules in the desktop window

**Files:**
- Modify: `launch/monitor/monitor_app.py` (add `flow`; `main()` uses `webview.start(http_server=True)`)
- Modify: `launch/monitor/monitor_web.py` (`READ_ONLY` gets `"flow"`; GET serves a static whitelist)
- Create: `launch/monitor/ui/vendor/three.module.min.js`, `OrbitControls.js`, `CSS2DRenderer.js`, `LICENSE` (Three.js MIT licence)
- Test: `tests/test_monitor_app.py`, `tests/test_monitor_web.py`

**Interfaces:**
- Consumes: `monitor_flow.build(items, target)` (Task 1).
- Produces: `Api.flow(target="production") -> dict` = `build(store.current(), target)` for `target in ("production", "test")`, else `{"error": "unknown target", "nodes": [], "edges": [], "stages": []}`.
  Phone: `POST /api/flow` with body `["test"]`. `GET /flow3d.js` and `GET /vendor/<name>` for names in `STATIC = {"flow3d.js": "ui/flow3d.js", "vendor/three.module.min.js": ..., "vendor/OrbitControls.js": ..., "vendor/CSS2DRenderer.js": ...}`, content type `text/javascript; charset=utf-8`. Anything else under GET: 404.

- [ ] **Step 1: Download Three.js 0.170.0** into `launch/monitor/ui/vendor/` from `https://cdn.jsdelivr.net/npm/three@0.170.0/` paths `build/three.module.min.js`, `examples/jsm/controls/OrbitControls.js`, `examples/jsm/renderers/CSS2DRenderer.js`, `LICENSE`. Check: `three.module.min.js` contains `REVISION="170"`; `OrbitControls.js` first import is `from 'three'`.

- [ ] **Step 2: Write failing tests**
  - `tests/test_monitor_app.py::test_flow_builds_graph`: store with `server:production ok` row → `Api(store).flow("production")["nodes"]` contains id `server`; `Api(store).flow("bad")["error"] == "unknown target"`.
  - `tests/test_monitor_web.py::test_flow_is_read_only_method`: `"flow" in monitor_web.READ_ONLY`; POST `/api/flow` with `["production"]` to a server on a FakeApi that has `flow(self, target="production")` returns 200.
  - `tests/test_monitor_web.py::test_static_whitelist_only`: GET `/flow3d.js` → 200 and `Content-Type` starts with `text/javascript` (create the file first if Task 3 has not: the test can monkeypatch `STATIC` to point at a tmp file); GET `/vendor/../state/monitor.db`, `/vendor/x.py`, `/monitor_web.py` → 404.

- [ ] **Step 3: Run tests to verify they fail**
  Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_app.py tests/test_monitor_web.py -q`
  Expected: the three new tests FAIL.

- [ ] **Step 4: Implement.** `Api.flow` in `monitor_app.py`. `main()`: `webview.start(http_server=True)` (pywebview then serves `ui/` over a local HTTP port, which ES modules and the import map need; `file://` blocks them). `monitor_web.py`: `STATIC` dict keyed by request path without the leading `/`, resolved under `HERE`; exact dict lookup only, no path joining from the request.

- [ ] **Step 5: Run all monitor tests**
  Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_*.py -q`
  Expected: all PASS.

- [ ] **Step 6: Commit**
  `git add launch/monitor/monitor_app.py launch/monitor/monitor_web.py launch/monitor/ui/vendor tests/test_monitor_app.py tests/test_monitor_web.py`
  `git commit -m "feat(monitor): flow API, vendored Three.js and static files for the phone page"`

---

### Task 3: Workflow page and 3D scene

**Files:**
- Create: `launch/monitor/ui/flow3d.js`
- Modify: `launch/monitor/ui/index.html` (import map, nav button, page, polling, side panel, CSS)

**Interfaces:**
- Consumes: `api().flow(target)` (Task 2), Three.js via import map `{"imports": {"three": "./vendor/three.module.min.js", "three/addons/": "./vendor/"}}`; `flow3d.js` imports `three/addons/OrbitControls.js` and `three/addons/CSS2DRenderer.js`.
- Produces: `flow3d.js` exports `mount(el: HTMLElement, opts: {onPick(node|null)}) -> {update(flow), dispose()}`.

Scene rules (decisions the implementer cannot make alone):
- Layout: stage columns along X, `x = (stage - 2) * 16`. Nodes of one stage spread on Y (spacing 3.2) and, when a stage has more than 8 nodes (agents), split into 2 rows on Z (`z = ±3`). Stage title as a CSS2D label above each column.
- Node: rounded box (`BoxGeometry(2.6, 1.1, 1.1)` with `MeshStandardMaterial`), colour from state; `fail` nodes pulse emissive (sin, 1.2 s); CSS2D label under the node: name, plus detail on hover.
- Edge: `QuadraticBezierCurve3` from node to node, control point lifted `+2` on Y; drawn as `Line`. `ok`: accent `#5b8cff` at 0.55 opacity with 3 small spheres moving along it (one loop per 2.5 s, offset). `fail`: `#f0556a`, `LineDashedMaterial`, no particles. `idle`: `#3a4049`, no particles.
- Camera: perspective, start at `(0, 14, 46)` looking at origin; `OrbitControls` with damping; auto-rotate speed 0.4 that stops on the first user drag.
- Lights: ambient 0.6 + one directional; background `#0b0d10`; faint grid floor (`GridHelper`, `#1f242b`).
- `update(flow)`: when the set of node ids and edges is the same as last time, only recolour and retext; otherwise rebuild the scene. Raycast click on a node calls `onPick(node)`; empty-space click calls `onPick(null)`.
- `dispose()`: stop the `requestAnimationFrame` loop, remove the resize listener and both renderer DOM elements, dispose geometries, materials and controls.

index.html:
- Nav: `<button class="nav" data-page="workflow">Workflow</button>` after Processes; title `"Workflow"`, subtitle `"Images → data → YOLO → AI analysis → output · live from the collector"`.
- Page body: a toolbar with Production/Test chip buttons (reuse `.chipbtn`, `S.flowT`, default `"production"`) and a legend of the five states (reuse `.pill`); below, a stage `div#flow3d` (height `calc(100vh - 170px)`, min 420 px, border and radius like `.wrap`) with an absolutely placed side panel `#flowinfo` showing the picked node: label, `pill(state)`, detail, `since ${ago(since)}`, and stage name.
- Like the log pane on Processes, the canvas survives status polls: `render()` must not replace `#flow3d` while it exists; polls call `loadFlow()` which calls `api().flow(S.flowT)` and `scene.update(r)`. Load `flow3d.js` with `await import("./flow3d.js")` on first entry; on leaving the page call `dispose()` and drop the handle.
- `WEB_API.flow = t => post("flow", [t])`.
- If the import or WebGL fails, show `<div class="empty">3D view not available: {message}</div>` in the stage and keep the rest of the app working.
- Phone (`max-width: 760px`): stage height `60vh`, side panel moves under the stage.

- [ ] **Step 1: Write `flow3d.js`** to the rules above.
- [ ] **Step 2: Wire `index.html`** as above.
- [ ] **Step 3: Run the Python tests again** (`.venv\Scripts\python.exe -m pytest tests/test_monitor_*.py -q`): all PASS.
- [ ] **Step 4: Browser check.** Start a second phone server on a spare port against the live DB: `.venv\Scripts\python.exe -c "import sys; sys.path[:0]=['launch','launch/monitor']; import monitor_web as w; from monitor_app import Api; from monitor_store import Store, DEFAULT_DB; w.serve(Api(Store(DEFAULT_DB)), port=8093).serve_forever()"`, open `http://127.0.0.1:8093/`, click Workflow. Expected: five titled columns, every live node visible, colours match the Checks page, particles move on `ok` edges, clicking a node fills the side panel, no console errors.
- [ ] **Step 5: Leak check.** Switch Workflow → Overview → Workflow 5 times and Production ↔ Test 5 times. Expected: exactly one `canvas` in `#flow3d`, no console errors.
- [ ] **Step 6: Commit**
  `git add launch/monitor/ui/flow3d.js launch/monitor/ui/index.html`
  `git commit -m "feat(monitor): Workflow page with a live 3D pipeline"`
