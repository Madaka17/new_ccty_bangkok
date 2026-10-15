# BKK Monitor App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A desktop app ("BKK Monitor") that shows whether the production and test servers, the AI agents, the YOLO models, ENVIRO, the AI gateway and the Cloudflare tunnel are working, keeps a 30-day history of state changes, raises Windows notifications, and has confirmed action buttons.

**Architecture:** Two processes share one SQLite file. A hidden **collector** (`pythonw`, started at logon by a scheduled task) runs one round of checks every 30 s, stores the current state of each check, and writes an event row only when a state changes; it also imports `launch\watchdog\state\watchdog.log` lines and shows a Windows toast for bad changes. The **app** is a pywebview window (WebView2) that reads the same database through a Python `js_api` and runs actions (start/restart/stop `.bat` files, YOLO on/off). The checks reuse the judging logic of the existing terminal scripts `launch\ai_status.py` and `launch\yolo_status.py`, which get a data-returning function each.

**Tech Stack:** Python 3.14 (`.venv`), stdlib `sqlite3`/`urllib`/`subprocess`, `requests` (already used by `gateway_status.py`), `pywebview` 6.2.1 (already installed in `.venv` and smoke-tested: WinForms + WebView2 window opens), vanilla HTML/CSS/JS (no build step), PowerShell 5.1 for toasts and the scheduled task, pytest 9.

**Spec (agreed with the user 2026-10-15):**
- Desktop app with its own window and a Desktop icon. Dark look like the Vapi "Chat Logs" screen: left sidebar, header, filter chips, a table with Rows-per-page, pager and Export.
- UI text in **English**.
- Top: status cards. Below: an event history table (state changes only), filterable, CSV export.
- Watch: production :8000 and test :8001 (answering, uptime, GPU), the 11 AI agents + Ask AI chat + wrong-way agent (same rules as `ai_status.py`), YOLO (same rules as `yolo_status.py`) plus the YOLO switch, ENVIRO :5050, the AI gateway (`LOCAL_LLM_URL`), the `cloudflared` service, and restarts from `watchdog.log`.
- Check every 30 s; the gateway every 5 min (each gateway check sends a one-token request that takes one of the key's 3 parallel slots).
- History is collected all the time (collector starts at logon), kept 30 days.
- Windows notification when something goes down or comes back; not repeated every round.
- A server stopped on purpose (`launch\watchdog\state\stopped_<port>` exists) shows as grey "stopped" and sends no notification.
- Action buttons, each with a confirmation dialog: Start / Restart / Stop for production, test and ENVIRO; YOLO on / off for production and test.

## Global Constraints

- Run Python only with `E:\new_ccty_bangkok\.venv\Scripts\python.exe` (tests: `.venv\Scripts\python.exe -m pytest tests/<file> -v` from the repo root). Never use `pip.exe`; use `.venv\Scripts\python.exe -m pip`.
- Never touch `instances\production\` or start/stop/restart any server while implementing. Production :8000 is the public site. The only allowed live calls are read-only GETs to `127.0.0.1:8000` / `127.0.0.1:8001` during the final smoke test.
- Never call `torch.cuda.*` anywhere in this feature.
- `launch\ai_status.py` and `launch\yolo_status.py` terminal output must stay the same (same lines, same exit codes) after the refactor, except the 503 fix in Task 2.
- New monitor modules live in `launch\monitor\` and are named `monitor_*.py` (generic names like `store.py` could collide with installed packages). They import the old scripts by putting `launch\` on `sys.path`.
- Database: `launch\monitor\state\monitor.db` (folder created on demand; add `launch/monitor/state/` to `.gitignore`).
- Check states are exactly: `ok`, `warn`, `fail`, `idle`, `stopped`. Watchdog events use new-state `restart` or `warn`.
- Status keys: `server:<target>`, `agent:<target>:<name>`, `yolo:<target>:<name>`, `service:gateway`, `service:tunnel`; watchdog events use key `watchdog:<target>`. Targets: `production` (8000), `test` (8001), `enviro` (5050), `gateway`, `tunnel`.
- Commit messages: conventional (`feat(monitor): ...`), ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never stage `launch/camera_status.py` (unrelated uncommitted change).
- Code style: match the existing `launch\*.py` scripts — module docstring explaining usage, short comments only where the reason is not obvious, `# noqa: BLE001` on deliberate broad excepts.

## Review Focus

- A server that answers `/api/health` with **503** (BMA scan stale) is up, not down: it must show `warn`, and its agents/YOLO rows must still be checked. (Test in Task 2 and Task 4.)
- The test server is usually stopped on purpose (`stopped_8001` exists): no `fail`, no toast, no agent rows for it. (Test in Task 4 and Task 5.)
- `watchdog.log` is appended by another process and may be rotated or shrink: the importer must not re-import or crash. (Test in Task 4.)
- The app runs while the collector writes: reads must not fail with `database is locked` (WAL + timeout). (Test in Task 3.)
- An action call with an unknown target or verb (from JS) must be refused, never turned into a shell command. (Test in Task 6.)

---

### Task 1: `ai_status.check_agents` returns rows

**Files:**
- Modify: `launch/ai_status.py` (function `report`, lines ~92-170)
- Test: `tests/test_ai_status_check.py`

**Interfaces:**
- Produces: `ai_status.check_agents(port, fetch=None) -> dict` with keys `summary` (str, the "models … · last N min: …" line), `window` (float minutes), `rows` (list of dict). Each row: `{"name": str, "state": "ok"|"fail"|"idle"|"warn", "data": str, "analysis": str, "calls": int|"", "fails": int|"", "tokens": int|"", "note": str}`. `fetch(port, path)` defaults to the module's `get`. Raises whatever `fetch` raises when `/api/ai/usage` fails (the caller reports the server).

- [ ] **Step 1: Write the failing test**

```python
import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ai_status_mod", ROOT / "launch" / "ai_status.py")
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)


def fake_fetch(responses):
    def fetch(port, path):
        val = responses.get(path.split("?")[0])
        if isinstance(val, Exception):
            raise val
        return val if val is not None else {}
    return fetch


def test_fresh_agent_is_ok_and_stale_agent_fails():
    now = time.time()
    resp = {
        "/api/ai/usage": {"callers": [{"caller": "backend.agents.flood_agent", "model": "qwen", "calls": 2,
                                        "errors": 0, "total_tokens": 900}], "covered_minutes": 60,
                          "calls": 2, "total_tokens": 900},
        "/api/flood/agent": {"report": {"generated_at": now - 60}},
        "/api/flood/analysis": {"feed_time": now - 10 * 3600, "updated_at": now - 10 * 3600},
    }
    out = ai.check_agents(8000, fetch=fake_fetch(resp))
    rows = {r["name"]: r for r in out["rows"]}
    assert rows["Bangkok flood report"]["state"] == "ok"
    assert rows["Bangkok flood report"]["calls"] == 2
    assert rows["Bangkok road water"]["state"] == "fail"
    assert rows["Bangkok road water"]["note"] == "data stale"
    assert "qwen" in out["summary"]


def test_endpoint_error_is_a_fail_row():
    resp = {"/api/ai/usage": {"callers": [], "covered_minutes": 5},
            "/api/flood/agent": OSError("boom")}
    rows = {r["name"]: r for r in ai.check_agents(8000, fetch=fake_fetch(resp))["rows"]}
    assert rows["Bangkok flood report"]["state"] == "fail"
    assert "endpoint error" in rows["Bangkok flood report"]["note"]


def test_usage_failure_raises():
    resp = {"/api/ai/usage": OSError("refused")}
    try:
        ai.check_agents(8000, fetch=fake_fetch(resp))
    except OSError:
        return
    raise AssertionError("expected OSError")


def test_chat_row_is_idle_without_calls():
    resp = {"/api/ai/usage": {"callers": [], "covered_minutes": 60}}
    rows = {r["name"]: r for r in ai.check_agents(8000, fetch=fake_fetch(resp))["rows"]}
    assert rows["Ask AI chat"]["state"] == "idle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_status_check.py -v`
Expected: FAIL with `AttributeError: module 'ai_status_mod' has no attribute 'check_agents'`

- [ ] **Step 3: Implement**

Move the judging part of `report()` into `check_agents`; `report()` prints from its result. Replace the whole `report` function with:

```python
def check_agents(port, fetch=None):
    """Every agent judged once: {"summary", "window", "rows"}. Raises when /api/ai/usage does not answer."""
    fetch = fetch or get
    usage = fetch(port, "/api/ai/usage?minutes=60")
    calls = {c["caller"]: c for c in usage.get("callers") or []}
    models = ", ".join(dict.fromkeys(c["model"] for c in usage.get("callers") or [])) or "–"
    window = usage.get("covered_minutes", 0)
    per_hour = usage.get("tokens_per_hour")
    summary = (f"models {models} · last {window:.0f} min: {usage.get('calls', 0)} requests, "
               f"{usage.get('total_tokens', 0):,} tokens" + (f" (~{per_hour:,}/h)" if per_hour else ""))
    rows = []

    def row(state, name, data="", analysis="", calls="", fails="", tokens="", note=""):
        rows.append({"name": name, "state": state, "data": data, "analysis": analysis, "calls": calls,
                     "fails": fails, "tokens": tokens, "note": note})

    for name, caller, path, data_f, ai_f, err_fs, data_max, ai_max in AGENTS:
        try:
            d = fetch(port, path)
        except Exception as e:  # noqa: BLE001 - one agent down leaves the others
            row("fail", name, "–", "–", note=f"endpoint error: {e}")
            continue
        data_t, ai_t = dig(d, data_f), dig(d, ai_f)
        err = next((dig(d, f) for f in err_fs if dig(d, f)), None)
        u = calls.get(caller) or {}
        fresh = bool(data_t) and time.time() - data_t <= data_max
        analysed = bool(ai_t) and time.time() - ai_t <= ai_max
        failed = u.get("errors", 0) > 0 and u.get("errors", 0) >= u.get("calls", 0)
        ok = fresh and analysed and not err and not failed
        note = str(err)[:60] if err else "model calls failing" if failed else \
            "source sent no readings" if not data_t else "data stale" if not fresh else "no recent analysis" if not analysed else \
            "picture unchanged, last report reused" if not u.get("calls") else ""
        row("ok" if ok else "fail", name, ago(data_t), ago(ai_t), u.get("calls", 0), u.get("errors", 0), u.get("total_tokens", 0), note)
    chat = calls.get("backend.agents.chat_service") or {}
    row("ok" if chat.get("calls") else "idle", "Ask AI chat", calls=chat.get("calls", 0), fails=chat.get("errors", 0),
        tokens=chat.get("total_tokens", 0), note="" if chat.get("calls") else "answers only when someone asks")
    try:
        ww = fetch(port, "/api/wrongway/status")
        u = calls.get("backend.vision.wrongway_service") or {}
        row("ok" if ww.get("enabled") and not ww.get("agent_error") else "warn", f"Wrong-way check ({ww.get('agent')})",
            analysis=ago(ww.get("last_check")), calls=ww.get("calls_last_hour", 0), fails=u.get("errors", 0),
            tokens=u.get("total_tokens", 0), note=ww.get("agent_error") or "")
    except Exception:  # noqa: BLE001 - optional line
        pass
    # model callers with no row above (incident check, violation check, ...): still count their tokens
    shown = {a[1] for a in AGENTS} | {"backend.agents.chat_service", "backend.vision.wrongway_service"}
    for c in usage.get("callers") or []:
        if c["caller"] not in shown:
            row("ok", c["caller"].rsplit(".", 1)[-1], calls=c["calls"], fails=c["errors"], tokens=c["total_tokens"],
                note=c["model"])
    return {"summary": summary, "window": window, "rows": rows}


def report(port):
    if not LOG:
        print(f"AI agent status  ·  server :{port}  ·  {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        result = check_agents(port)
    except Exception as e:  # noqa: BLE001 - the server itself is the first thing to report
        emit("fail", "server", note=f"not answering on :{port} ({e})")
        return 1
    if LOG:
        log("INFO", result["summary"])
    else:
        print(f"  {result['summary']}")
        print("-" * 104)
        print(f"  {'':6}  {'agent':<26} {'data':>6}  {'analysis':>8}  {'calls':>7} {'fail':>4} {'tokens':>9}  note")
    bad = 0
    for r in result["rows"]:
        emit(r["state"], r["name"], r["data"], r["analysis"], r["calls"], r["fails"], r["tokens"], r["note"])
        bad += r["state"] == "fail"
    if LOG:
        log("INFO" if not bad else "ERROR", "all AI agents are fetching and analysing" if not bad else f"{bad} agent(s) not working")
    else:
        print("-" * 104)
        print(f"  data / analysis = how long ago · calls / tokens = real model requests in the last {result['window']:.0f} min")
        print("  all AI agents are fetching and analysing" if not bad else f"  {bad} agent(s) not working: see [FAIL] above")
    return 1 if bad else 0
```

Note: in the old code, `bad` counted only the `AGENTS` loop failures; endpoint-error rows are `fail` too, so counting `state == "fail"` over all rows gives the same number (the chat row is never `fail`; the wrong-way row is `ok`/`warn`; extra callers are `ok`).

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_status_check.py -v`
Expected: 4 passed.
Then run `.venv\Scripts\python.exe launch\ai_status.py 59999 --once` (no server on that port). Expected: one `[FAIL]  server ... not answering on :59999` line, exit code 1.

- [ ] **Step 5: Commit**

```bash
git add launch/ai_status.py tests/test_ai_status_check.py
git commit -m "refactor(ai_status): check_agents returns rows for the monitor app"
```

---

### Task 2: `yolo_status.check_yolo` returns rows; 503 health is not "down"

**Files:**
- Modify: `launch/yolo_status.py` (function `report` and helpers)
- Test: `tests/test_yolo_status_check.py`

**Interfaces:**
- Produces:
  - `yolo_status.get_health(port, fetch=None) -> dict` — the `/api/health` body; on HTTP 503 it returns the JSON body of the 503 (the server is up, the BMA scan is stale). Other errors raise.
  - `yolo_status.check_yolo(port, fetch=None, health=None) -> dict` with keys `server` (`{"uptime_s": int, "gpu": dict|None, "ok": bool}`) and `rows` (list of `{"name": str, "state": "ok"|"fail"|"idle", "detail": str}`). Row names (exact): `"YOLO switch"`, `"YOLO26x  BMA camera scan"`, `"<model>  live AI camera"`, `"helmet  <detector>"` or `"helmet detector"`, `"wrong-way  <detector>"` or `"wrong-way classifier"`. `health` may be passed in to avoid a second request.

- [ ] **Step 1: Write the failing test**

```python
import importlib.util
import io
import json
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("yolo_status_mod", ROOT / "launch" / "yolo_status.py")
ys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ys)

HEALTH = {"ok": True, "uptime_s": 600, "gpu": {"name": None, "used_mb": 2000, "total_mb": 10240},
          "scan": {"cycle": 5, "age_s": 60, "running": False}, "bma_source": {"frames_ok": 500, "frames_new": 20, "state": "ok"}}


def fake_fetch(resp):
    def fetch(port, path):
        val = resp[path]
        if isinstance(val, Exception):
            raise val
        return val
    return fetch


def base(**over):
    resp = {"/api/health": HEALTH,
            "/api/ai/yolo": {"enabled": True, "vram": {"used_mb": 2000, "total_mb": 10240}},
            "/api/ai/stats": {"active": False, "model": "YOLO26x"},
            "/api/helmet/status": {"enabled": True, "last_check": time.time() - 30, "local_detector": "helmet_det",
                                   "calls_last_hour": 10, "queue": 0, "today": {}},
            "/api/wrongway/status": {"enabled": True, "frames_seen": 100, "detector": "wrongway_det",
                                     "cameras_learned": 3, "cameras_seen": 9, "today": {}}}
    resp.update(over)
    return resp


def test_all_working():
    out = ys.check_yolo(8000, fetch=fake_fetch(base()))
    states = {r["name"]: r["state"] for r in out["rows"]}
    assert states["YOLO switch"] == "ok"
    assert states["YOLO26x  BMA camera scan"] == "ok"
    assert states["YOLO26x  live AI camera"] == "idle"
    assert states["helmet  helmet_det"] == "ok"
    assert states["wrong-way  wrongway_det"] == "ok"
    assert out["server"]["uptime_s"] == 600


def test_switch_off_is_idle():
    out = ys.check_yolo(8000, fetch=fake_fetch(base(**{"/api/ai/yolo": {"enabled": False, "vram": None}})))
    sw = next(r for r in out["rows"] if r["name"] == "YOLO switch")
    assert sw["state"] == "idle" and "off" in sw["detail"]


def test_stale_scan_fails():
    h = {**HEALTH, "ok": False, "scan": {"cycle": 5, "age_s": 3600, "running": False}}
    out = ys.check_yolo(8000, fetch=fake_fetch(base(**{"/api/health": h})))
    scan = next(r for r in out["rows"] if r["name"] == "YOLO26x  BMA camera scan")
    assert scan["state"] == "fail"


def test_health_503_returns_body():
    body = json.dumps({**HEALTH, "ok": False}).encode()

    def fetch(port, path):
        raise urllib.error.HTTPError("http://x/api/health", 503, "Service Unavailable", {}, io.BytesIO(body))
    h = ys.get_health(8000, fetch=fetch)
    assert h["ok"] is False and h["uptime_s"] == 600


def test_health_refused_raises():
    def fetch(port, path):
        raise urllib.error.URLError("refused")
    try:
        ys.get_health(8000, fetch=fetch)
    except urllib.error.URLError:
        return
    raise AssertionError("expected URLError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_yolo_status_check.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'check_yolo'`

- [ ] **Step 3: Implement**

Add `import urllib.error` at the top. Replace `line()` and `report()` with:

```python
MARK = {"ok": "[ OK ]", "fail": "[FAIL]", "idle": "[IDLE]"}


def line(state, name, detail):
    if LOG:
        level = {"ok": "INFO", "fail": "ERROR", "idle": "WARNING"}[state]
        log(level, f"{LEVEL_COLOR[level]}{MARK[state]}{RESET} {name:<28} {detail}")
    else:
        print(f"  {MARK[state]}  {name:<28} {detail}")


def get_health(port, fetch=None):
    """/api/health, also when it answers 503: that only means the BMA scan is stale, the server is up."""
    fetch = fetch or get
    try:
        return fetch(port, "/api/health")
    except urllib.error.HTTPError as e:
        if e.code != 503:
            raise
        return json.loads(e.read().decode("utf-8"))


def check_yolo(port, fetch=None, health=None):
    """Every YOLO model judged once: {"server": {...}, "rows": [{"name", "state", "detail"}]}."""
    fetch = fetch or get
    h = health if health is not None else get_health(port, fetch)
    rows = []

    def row(state, name, detail):
        rows.append({"name": name, "state": state, "detail": detail})

    sw = fetch(port, "/api/ai/yolo")
    vram = sw.get("vram")
    mem = f" · GPU {vram['used_mb'] / 1024:.1f} / {vram['total_mb'] / 1024:.1f} GB" if vram else ""
    row("ok" if sw.get("enabled") else "idle", "YOLO switch", ("on" if sw.get("enabled") else "switched off") + mem)

    scan, src = h.get("scan") or {}, h.get("bma_source") or {}
    fresh = scan.get("age_s") is not None and scan["age_s"] < SCAN_FRESH_S
    state = "scanning now" if scan.get("running") else f"last cycle {scan['age_s']}s ago" if scan.get("age_s") is not None else "no cycle yet"
    working = bool(fresh or scan.get("running"))
    row(("ok" if working else "fail") if scan.get("cycle") else "idle", "YOLO26x  BMA camera scan",
        f"{state} · cycle {scan.get('cycle')} · frames {src.get('frames_ok', '–')} ok, {src.get('frames_new', '–')} new · source {src.get('state', '–')}")

    ai = fetch(port, "/api/ai/stats")
    if ai.get("active"):
        live_ok = (ai.get("fps") or 0) > 0
        row("ok" if live_ok else "fail", f"{ai.get('model', 'YOLO')}  live AI camera",
            f"{ai.get('fps')} fps (target {ai.get('target_fps')}) · {ai.get('latency_ms')} ms · {ai.get('title') or ai.get('camid')} · {ai.get('total')} vehicles")
    else:
        why = f"camera offline ({ai.get('title') or ai.get('camid')})" if ai.get("stream_error") else "nobody is watching the AI page"
        row("idle", f"{ai.get('model', 'YOLO')}  live AI camera", f"not playing: {why}")

    hs = fetch(port, "/api/helmet/status")
    if not hs.get("enabled"):
        row("idle", "helmet detector", "switched off")
    else:
        recent = hs.get("last_check") and time.time() - hs["last_check"] < HELMET_FRESH_S
        t = hs.get("today") or {}
        row("ok" if recent else "fail", f"helmet  {hs.get('local_detector', '')}",
            f"last check {ago(hs.get('last_check'))} · {hs.get('calls_last_hour')} checks/h · queue {hs.get('queue')} · today {t.get('captures', 0)} captures, {t.get('no_helmet', 0)} no helmet"
            + (f" · agent error: {hs['agent_error']}" if hs.get("agent_error") else ""))

    ww = fetch(port, "/api/wrongway/status")
    if not ww.get("enabled"):
        row("idle", "wrong-way classifier", "switched off")
    else:
        learning = (ww.get("frames_seen") or 0) > 0
        t = ww.get("today") or {}
        row("ok" if learning else "fail", f"wrong-way  {ww.get('detector', '')}",
            f"{ww.get('frames_seen')} frames read · {ww.get('cameras_learned')}/{ww.get('cameras_seen')} cameras learned · today {t.get('captures', 0)} captures, {t.get('wrong_way', 0)} wrong way"
            + (f" · agent error: {ww['agent_error']}" if ww.get("agent_error") else ""))
    return {"server": {"uptime_s": h.get("uptime_s", 0), "gpu": h.get("gpu"), "ok": bool(h.get("ok"))}, "rows": rows}


def report(port):
    if not LOG:
        print(f"YOLO status  ·  server :{port}  ·  {datetime.now():%Y-%m-%d %H:%M:%S}")
        print("-" * 78)
    try:
        h = get_health(port)
    except Exception as e:  # noqa: BLE001 - the server itself is the first thing to report
        line("fail", "server", f"not answering on :{port} ({e})")
        return 1
    gpu = h.get("gpu")
    say(f"  server :{port} up {h['uptime_s'] // 60} min · GPU {gpu['name']} {gpu['used_mb']:,} / {gpu['total_mb']:,} MB in use"
        if gpu else f"  server :{port} up {h['uptime_s'] // 60} min · no GPU found: the models run on the CPU")
    if not LOG:
        print()
    result = check_yolo(port, health=h)
    bad = 0
    for r in result["rows"]:
        if r["name"] == "YOLO switch":
            continue        # the terminal report has no switch line; the monitor app shows it
        line(r["state"], r["name"], r["detail"])
        bad += r["state"] == "fail"
    if LOG:
        log("INFO" if not bad else "ERROR", "all YOLO models are working" if not bad else f"{bad} model(s) not working")
    else:
        print("-" * 78)
        print("  all YOLO models are working" if not bad else f"  {bad} model(s) not working: see [FAIL] above")
    return 1 if bad else 0
```

Behaviour change on purpose: the old `report()` printed "server not answering" when `/api/health` answered 503; now it reports the models (the stale scan shows as `[FAIL]`).

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_yolo_status_check.py tests/test_ai_status_check.py -v`
Expected: all pass. Also `.venv\Scripts\python.exe launch\yolo_status.py 59999 --once` prints one `[FAIL]  server ... not answering on :59999` line.

- [ ] **Step 5: Commit**

```bash
git add launch/yolo_status.py tests/test_yolo_status_check.py
git commit -m "refactor(yolo_status): check_yolo returns rows; a 503 health means scan stale, not server down"
```

---

### Task 3: `monitor_store` — SQLite state and event history

**Files:**
- Create: `launch/monitor/monitor_store.py`
- Modify: `.gitignore` (add `launch/monitor/state/`)
- Test: `tests/test_monitor_store.py`

**Interfaces:**
- Produces `class Store(path)`:
  - `apply(statuses: list[dict], now: float) -> list[dict]` — each status `{"key","group","target","name","state","detail"}`. Upserts the `status` table (`since` changes only when the state changes; `checked_at = now`). Returns new event dicts `{"ts","key","group","target","name","old","new","detail"}` for each state change; a first-seen status makes an event (`old=None`) only when its state is not `ok`. Keys not in `statuses` are left untouched.
  - `add_event(ts, key, group, target, name, old, new, detail) -> dict` — inserts and returns the event dict.
  - `current() -> list[dict]` — all status rows (`key, group, target, name, state, detail, since, checked_at`), ordered by key.
  - `events(target=None, state=None, q=None, since=None, limit=25, offset=0) -> dict` — `{"rows": [...event dicts with "id"], "total": int}`, newest first. `q` matches name or detail (case-insensitive LIKE).
  - `prune(now, days=30) -> int` — deletes events older than `days`; returns rows deleted.
  - `get_meta(k, default=None) -> str|None`, `set_meta(k, v)`.
- Every method opens its own connection (`sqlite3.connect(path, timeout=10)`), WAL mode, so two processes can share the file.

- [ ] **Step 1: Write the failing test**

```python
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
from monitor_store import Store  # noqa: E402


def st(key, state, detail="", target="production", group="server", name=None):
    return {"key": key, "group": group, "target": target, "name": name or key, "state": state, "detail": detail}


def test_first_ok_makes_no_event_but_bad_does(tmp_path):
    s = Store(tmp_path / "m.db")
    ev = s.apply([st("server:production", "ok"), st("server:test", "stopped", target="test")], now=100)
    assert [e["key"] for e in ev] == ["server:test"]
    assert ev[0]["old"] is None and ev[0]["new"] == "stopped"


def test_change_makes_event_and_moves_since(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([st("server:production", "ok", "up")], now=100)
    assert s.apply([st("server:production", "ok", "up 2")], now=130) == []
    ev = s.apply([st("server:production", "fail", "no answer")], now=160)
    assert ev[0]["old"] == "ok" and ev[0]["new"] == "fail" and ev[0]["detail"] == "no answer"
    cur = {r["key"]: r for r in s.current()}["server:production"]
    assert cur["since"] == 160 and cur["checked_at"] == 160


def test_detail_update_without_event(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([st("server:production", "ok", "up 1 min")], now=100)
    s.apply([st("server:production", "ok", "up 2 min")], now=130)
    cur = s.current()[0]
    assert cur["detail"] == "up 2 min" and cur["since"] == 100


def test_missing_keys_untouched(tmp_path):
    s = Store(tmp_path / "m.db")
    s.apply([st("service:gateway", "ok", group="service", target="gateway")], now=100)
    s.apply([st("server:production", "ok")], now=130)
    assert {r["key"] for r in s.current()} == {"service:gateway", "server:production"}


def test_events_filters_and_paging(tmp_path):
    s = Store(tmp_path / "m.db")
    for i in range(30):
        s.add_event(1000 + i, "server:production", "server", "production", "Production", "ok", "fail", f"boom {i}")
    s.add_event(2000, "server:test", "server", "test", "Test", "ok", "stopped", "stopped")
    page = s.events(limit=25)
    assert page["total"] == 31 and len(page["rows"]) == 25 and page["rows"][0]["ts"] == 2000
    assert s.events(target="test")["total"] == 1
    assert s.events(state="fail", q="BOOM 29")["total"] == 1
    assert s.events(since=1025)["total"] == 6
    assert len(s.events(limit=25, offset=25)["rows"]) == 6


def test_prune(tmp_path):
    s = Store(tmp_path / "m.db")
    s.add_event(0, "k", "server", "production", "P", "ok", "fail", "")
    s.add_event(40 * 86400, "k", "server", "production", "P", "fail", "ok", "")
    assert s.prune(now=40 * 86400, days=30) == 1
    assert s.events()["total"] == 1


def test_meta(tmp_path):
    s = Store(tmp_path / "m.db")
    assert s.get_meta("x", "d") == "d"
    s.set_meta("x", "1")
    assert s.get_meta("x") == "1"


def test_concurrent_read_while_writing(tmp_path):
    s = Store(tmp_path / "m.db")
    errors = []

    def writer():
        for i in range(200):
            s.add_event(i, "k", "server", "production", "P", "ok", "fail", "")

    def reader():
        try:
            for _ in range(200):
                s.events(limit=5)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1, t2 = threading.Thread(target=writer), threading.Thread(target=reader)
    t1.start(); t2.start(); t1.join(); t2.join()
    assert errors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_store'`

- [ ] **Step 3: Implement `launch/monitor/monitor_store.py`**

```python
"""
The monitor's database (launch\\monitor\\state\\monitor.db), shared by the collector (writes) and the app (reads).

    status   the latest result of every check: one row per key, `since` = when it entered its current state
    events   one row per state change (and per watchdog.log line), kept 30 days
    meta     small values: the collector's heartbeat, the watchdog.log read offset, "check now" requests
Each call opens its own connection in WAL mode, so the app can read while the collector writes.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS status (key TEXT PRIMARY KEY, grp TEXT, target TEXT, name TEXT, state TEXT,
                                   detail TEXT, since REAL, checked_at REAL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, key TEXT, grp TEXT, target TEXT,
                                   name TEXT, old TEXT, new TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""
EVENT_COLS = "id, ts, key, grp, target, name, old, new, detail"


def _event(row):
    return {"id": row[0], "ts": row[1], "key": row[2], "group": row[3], "target": row[4], "name": row[5],
            "old": row[6], "new": row[7], "detail": row[8]}


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def apply(self, statuses, now):
        events = []
        with closing(self._conn()) as c, c:
            for s in statuses:
                prev = c.execute("SELECT state, since FROM status WHERE key = ?", (s["key"],)).fetchone()
                changed = prev is None or prev[0] != s["state"]
                since = now if changed else prev[1]
                c.execute("INSERT OR REPLACE INTO status (key, grp, target, name, state, detail, since, checked_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (s["key"], s["group"], s["target"], s["name"], s["state"], s["detail"], since, now))
                if changed and not (prev is None and s["state"] == "ok"):
                    events.append(self._insert(c, now, s["key"], s["group"], s["target"], s["name"],
                                               prev[0] if prev else None, s["state"], s["detail"]))
        return events

    def _insert(self, c, ts, key, group, target, name, old, new, detail):
        cur = c.execute("INSERT INTO events (ts, key, grp, target, name, old, new, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (ts, key, group, target, name, old, new, detail))
        return {"id": cur.lastrowid, "ts": ts, "key": key, "group": group, "target": target, "name": name,
                "old": old, "new": new, "detail": detail}

    def add_event(self, ts, key, group, target, name, old, new, detail):
        with closing(self._conn()) as c, c:
            return self._insert(c, ts, key, group, target, name, old, new, detail)

    def current(self):
        with closing(self._conn()) as c:
            rows = c.execute("SELECT key, grp, target, name, state, detail, since, checked_at FROM status ORDER BY key").fetchall()
        return [{"key": r[0], "group": r[1], "target": r[2], "name": r[3], "state": r[4], "detail": r[5],
                 "since": r[6], "checked_at": r[7]} for r in rows]

    def events(self, target=None, state=None, q=None, since=None, limit=25, offset=0):
        where, args = [], []
        if target:
            where.append("target = ?"); args.append(target)
        if state:
            where.append("new = ?"); args.append(state)
        if q:
            where.append("(name LIKE ? OR detail LIKE ?)"); args += [f"%{q}%", f"%{q}%"]
        if since is not None:
            where.append("ts >= ?"); args.append(since)
        sql_where = f" WHERE {' AND '.join(where)}" if where else ""
        with closing(self._conn()) as c:
            total = c.execute(f"SELECT COUNT(*) FROM events{sql_where}", args).fetchone()[0]
            rows = c.execute(f"SELECT {EVENT_COLS} FROM events{sql_where} ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
                             args + [int(limit), int(offset)]).fetchall()
        return {"rows": [_event(r) for r in rows], "total": total}

    def prune(self, now, days=30):
        with closing(self._conn()) as c, c:
            return c.execute("DELETE FROM events WHERE ts < ?", (now - days * 86400,)).rowcount

    def get_meta(self, k, default=None):
        with closing(self._conn()) as c:
            row = c.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return row[0] if row else default

    def set_meta(self, k, v):
        with closing(self._conn()) as c, c:
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, str(v)))
```

(SQLite `LIKE` is case-insensitive for ASCII, which covers the `q` test.)

Append to `.gitignore`:
```
launch/monitor/state/
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_store.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add launch/monitor/monitor_store.py tests/test_monitor_store.py .gitignore
git commit -m "feat(monitor): SQLite store for check state and change history"
```

---

### Task 4: `monitor_checks` (one round) and `monitor_watchdog` (log import)

**Files:**
- Create: `launch/monitor/monitor_checks.py`
- Create: `launch/monitor/monitor_watchdog.py`
- Test: `tests/test_monitor_checks.py`, `tests/test_monitor_watchdog.py`

**Interfaces:**
- Consumes: `ai_status.check_agents(port)`, `yolo_status.get_health(port)`, `yolo_status.check_yolo(port, health=...)`, `gateway_status.load_env()`, `gateway_status.check(url, model, key, extra) -> (proxy_ok, model_ok, proxy_note, model_note, secs)`.
- Produces:
  - `monitor_checks.ROOT` (repo root `Path`), `monitor_checks.STATE_DIR` (`ROOT/"launch"/"watchdog"/"state"`), `monitor_checks.SERVERS = {"production": 8000, "test": 8001, "enviro": 5050}`, `monitor_checks.LABELS = {"production": "Production", "test": "Test", "enviro": "ENVIRO", "gateway": "AI gateway", "tunnel": "Cloudflare tunnel"}`.
  - `monitor_checks.run_round(gateway_due: bool) -> list[dict]` — status dicts (`key, group, target, name, state, detail`, see Global Constraints). Order: server rows, then agent and YOLO rows of each server that answered, then ENVIRO, then tunnel, then gateway (only when `gateway_due`).
  - Probe functions tests monkeypatch: `stopped(port) -> bool`, `health(port) -> dict` (raises when down), `http_up(port) -> bool`, `tunnel_running() -> bool`, `gateway() -> tuple`, `agents(port) -> dict`, `yolo(port, h) -> dict`.
  - `monitor_watchdog.read_new(path, offset: int) -> (list[str], int)` — complete new lines since `offset`; if the file is shorter than `offset`, read from 0; a last line with no `\n` yet is left for next time.
  - `monitor_watchdog.parse(line) -> dict|None` — `{"ts": float, "target": str, "new": "restart"|"warn", "detail": str}` or `None` for lines it does not know.

- [ ] **Step 1: Write the failing tests**

`tests/test_monitor_checks.py`:
```python
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_checks as mc  # noqa: E402

HEALTH = {"ok": True, "uptime_s": 7200, "gpu": {"name": None, "used_mb": 2048, "total_mb": 10240}}


def patch(monkeypatch, up=(), stopped=(), ok_health=True, tunnel=True):
    monkeypatch.setattr(mc, "stopped", lambda port: port in stopped)

    def health(port):
        if port not in up:
            raise urllib.error.URLError("refused")
        return {**HEALTH, "ok": ok_health}
    monkeypatch.setattr(mc, "health", health)
    monkeypatch.setattr(mc, "http_up", lambda port: port in up)
    monkeypatch.setattr(mc, "tunnel_running", lambda: tunnel)
    monkeypatch.setattr(mc, "gateway", lambda: (True, True, "200, qwen listed", "200 answered", 1.2))
    monkeypatch.setattr(mc, "agents", lambda port: {"summary": "s", "window": 60, "rows": [
        {"name": "Bangkok flood report", "state": "ok", "data": "1m", "analysis": "1m", "calls": 1, "fails": 0,
         "tokens": 10, "note": ""}]})
    monkeypatch.setattr(mc, "yolo", lambda port, h: {"server": {}, "rows": [
        {"name": "YOLO switch", "state": "ok", "detail": "on"}]})


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_production_up_test_stopped(monkeypatch):
    patch(monkeypatch, up={8000, 5050}, stopped={8001})
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["server:production"]["state"] == "ok"
    assert "up 2 h" in rows["server:production"]["detail"]
    assert rows["server:test"]["state"] == "stopped"
    assert "agent:production:Bangkok flood report" in rows
    assert "yolo:production:YOLO switch" in rows
    assert not any(k.startswith(("agent:test", "yolo:test")) for k in rows)
    assert rows["server:enviro"]["state"] == "ok"
    assert rows["service:tunnel"]["state"] == "ok"
    assert "service:gateway" not in rows


def test_down_without_marker_fails(monkeypatch):
    patch(monkeypatch, up=set(), stopped=set())
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["server:production"]["state"] == "fail"
    assert rows["server:enviro"]["state"] == "fail"


def test_health_503_is_warn_and_still_checks_agents(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, ok_health=False)
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["server:production"]["state"] == "warn"
    assert "agent:production:Bangkok flood report" in rows


def test_gateway_and_tunnel(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050}, tunnel=False)
    rows = by_key(mc.run_round(gateway_due=True))
    assert rows["service:gateway"]["state"] == "ok"
    assert rows["service:tunnel"]["state"] == "fail"


def test_agent_check_crash_becomes_fail_row(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050})

    def boom(port):
        raise RuntimeError("bad json")
    monkeypatch.setattr(mc, "agents", boom)
    rows = by_key(mc.run_round(gateway_due=False))
    assert rows["agent:production:checks"]["state"] == "fail"
    assert "bad json" in rows["agent:production:checks"]["detail"]
```

`tests/test_monitor_watchdog.py`:
```python
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_watchdog as mw  # noqa: E402


def test_parse_lines():
    a = mw.parse("2026-10-09 17:46:13 production :8000 down: running launch\\production\\restart.bat")
    assert a["target"] == "production" and a["new"] == "restart"
    assert a["ts"] == datetime(2026, 10, 9, 17, 46, 13).timestamp()
    b = mw.parse("2026-10-15 00:08:54 enviro :5050 did not answer (check 1 of 2)")
    assert b["target"] == "enviro" and b["new"] == "warn" and "did not answer" in b["detail"]
    assert mw.parse("garbage") is None
    assert mw.parse("") is None


def test_read_new_incremental(tmp_path):
    p = tmp_path / "watchdog.log"
    p.write_bytes(b"line1\nline2\npart")
    lines, off = mw.read_new(p, 0)
    assert lines == ["line1", "line2"] and off == len(b"line1\nline2\n")
    with open(p, "ab") as f:
        f.write(b"ial\n")
    lines, off2 = mw.read_new(p, off)
    assert lines == ["partial"]
    assert mw.read_new(p, off2) == ([], off2)


def test_read_new_after_shrink(tmp_path):
    p = tmp_path / "watchdog.log"
    p.write_bytes(b"new\n")
    lines, off = mw.read_new(p, 9999)
    assert lines == ["new"] and off == 4


def test_read_missing_file(tmp_path):
    assert mw.read_new(tmp_path / "nope.log", 5) == ([], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_checks.py tests/test_monitor_watchdog.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `launch/monitor/monitor_watchdog.py`**

```python
"""
Reads launch\\watchdog\\state\\watchdog.log for the monitor: the watchdog task (every 2 min) appends one line per
failed check ("... did not answer (check 1 of 2)") and per restart ("... down: running ...\\restart.bat").
"""
import re
from datetime import datetime
from pathlib import Path

LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\w+) :\d+ (.+)$")


def read_new(path, offset):
    """New complete lines since byte `offset`: (lines, new offset). A shorter file (rotated) is read from 0."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return [], 0
    if size < offset:
        offset = 0
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1     # a last line still being written waits for the next round
    text = data[:end].decode("utf-8-sig", errors="replace")
    return [ln.rstrip("\r") for ln in text.split("\n") if ln.strip()], offset + end


def parse(line):
    m = LINE.match(line or "")
    if not m:
        return None
    stamp, target, text = m.groups()
    new = "restart" if "down: running" in text else "warn" if "did not answer" in text else None
    if new is None:
        return None
    return {"ts": datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp(), "target": target, "new": new, "detail": text}
```

- [ ] **Step 4: Implement `launch/monitor/monitor_checks.py`**

```python
"""
One round of the monitor's checks (launch\\monitor\\collector.py runs it every 30 s). Returns one status per check:
    server:<target>          production :8000 / test :8001 (/api/health), enviro :5050 (its page)
    agent:<target>:<name>    the AI agents, judged like launch\\ai_status.py
    yolo:<target>:<name>     the YOLO switch and models, judged like launch\\yolo_status.py
    service:tunnel           the cloudflared Windows service
    service:gateway          the AI gateway (launch\\gateway_status.py), only when the caller says it is due
A server that does not answer while launch\\watchdog\\state\\stopped_<port> exists was stopped on purpose: "stopped".
"""
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "launch"))
import ai_status  # noqa: E402
import gateway_status  # noqa: E402
import yolo_status  # noqa: E402

STATE_DIR = ROOT / "launch" / "watchdog" / "state"
SERVERS = {"production": 8000, "test": 8001, "enviro": 5050}
LABELS = {"production": "Production", "test": "Test", "enviro": "ENVIRO", "gateway": "AI gateway",
          "tunnel": "Cloudflare tunnel"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stopped(port):
    return (STATE_DIR / f"stopped_{port}").exists()


def health(port):
    return yolo_status.get_health(port)


def http_up(port):
    """Like the watchdog: the page answers below 500."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:  # noqa: BLE001 - no answer is the answer
        return False


def tunnel_running():
    try:
        out = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
    except Exception:  # noqa: BLE001
        return False
    return "RUNNING" in out


def gateway():
    return gateway_status.check(*gateway_status.load_env())


def agents(port):
    return ai_status.check_agents(port)


def yolo(port, h):
    return yolo_status.check_yolo(port, health=h)


def _status(key, group, target, name, state, detail):
    return {"key": key, "group": group, "target": target, "name": name, "state": state, "detail": detail}


def _uptime(s):
    return f"{s // 60} min" if s < 7200 else f"{s // 3600} h"


def _server(target, port):
    """(status, health or None)."""
    key, name = f"server:{target}", LABELS[target]
    try:
        h = health(port)
    except Exception as e:  # noqa: BLE001 - down or stopped
        if stopped(port):
            return _status(key, "server", target, name, "stopped", f":{port} stopped on purpose"), None
        return _status(key, "server", target, name, "fail", f":{port} not answering ({e})"), None
    gpu = h.get("gpu")
    detail = f":{port} up {_uptime(h.get('uptime_s', 0))}" + \
        (f" · GPU {gpu['used_mb'] / 1024:.1f} / {gpu['total_mb'] / 1024:.1f} GB" if gpu else "")
    if not h.get("ok"):
        return _status(key, "server", target, name, "warn", detail + " · BMA scan stale (health 503)"), h
    return _status(key, "server", target, name, "ok", detail), h


def run_round(gateway_due):
    out = []
    for target in ("production", "test"):
        port = SERVERS[target]
        status, h = _server(target, port)
        out.append(status)
        if h is None:
            continue
        try:
            for r in agents(port)["rows"]:
                parts = [f"data {r['data']}" if r["data"] else "", f"analysis {r['analysis']}" if r["analysis"] else "",
                         f"{r['calls']} calls" if r["calls"] != "" else "",
                         f"{r['fails']} failed" if r["fails"] else "",
                         f"{r['tokens']:,} tokens" if isinstance(r["tokens"], int) and r["tokens"] else "", r["note"]]
                out.append(_status(f"agent:{target}:{r['name']}", "agent", target, r["name"], r["state"],
                                   " · ".join(p for p in parts if p)))
        except Exception as e:  # noqa: BLE001 - the server answered health but not the agent checks
            out.append(_status(f"agent:{target}:checks", "agent", target, "agent checks", "fail", str(e)[:200]))
        try:
            for r in yolo(port, h)["rows"]:
                out.append(_status(f"yolo:{target}:{r['name']}", "yolo", target, r["name"], r["state"], r["detail"]))
        except Exception as e:  # noqa: BLE001
            out.append(_status(f"yolo:{target}:checks", "yolo", target, "YOLO checks", "fail", str(e)[:200]))
    port = SERVERS["enviro"]
    if http_up(port):
        out.append(_status("server:enviro", "server", "enviro", LABELS["enviro"], "ok", f":{port} answering"))
    elif stopped(port):
        out.append(_status("server:enviro", "server", "enviro", LABELS["enviro"], "stopped", f":{port} stopped on purpose"))
    else:
        out.append(_status("server:enviro", "server", "enviro", LABELS["enviro"], "fail", f":{port} not answering"))
    up = tunnel_running()
    out.append(_status("service:tunnel", "service", "tunnel", LABELS["tunnel"], "ok" if up else "fail",
                       "cloudflared service running" if up else "cloudflared service not running: site not public"))
    if gateway_due:
        try:
            proxy_ok, model_ok, proxy_note, model_note, secs = gateway()
            out.append(_status("service:gateway", "service", "gateway", LABELS["gateway"], "ok" if model_ok else "fail",
                               f"model {model_note} ({secs:.1f}s) · proxy {proxy_note}"))
        except Exception as e:  # noqa: BLE001
            out.append(_status("service:gateway", "service", "gateway", LABELS["gateway"], "fail", str(e)[:200]))
    return out
```

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_checks.py tests/test_monitor_watchdog.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add launch/monitor/monitor_checks.py launch/monitor/monitor_watchdog.py tests/test_monitor_checks.py tests/test_monitor_watchdog.py
git commit -m "feat(monitor): one round of server, agent, YOLO, ENVIRO, tunnel and gateway checks; watchdog.log reader"
```

---

### Task 5: Notifications and the collector process

**Files:**
- Create: `launch/monitor/monitor_notify.py`
- Create: `launch/monitor/collector.py`
- Create: `launch/monitor/install.ps1`
- Test: `tests/test_monitor_notify.py`, `tests/test_monitor_collector.py`

**Interfaces:**
- Consumes: `Store` (Task 3), `monitor_checks.run_round`, `monitor_checks.STATE_DIR`, `monitor_checks.LABELS` (Task 4), `monitor_watchdog.read_new/parse` (Task 4).
- Produces:
  - `monitor_notify.worth_telling(event) -> bool` — `True` when `new` is `fail`, `warn` or `restart` and `old` is not the same; or when `old` is `fail`/`warn` and `new` is `ok`. `False` for `idle`, `stopped`, and for `warn` events from the watchdog (key starts with `watchdog:` and `new == "warn"`: the first missed check is noise, the restart line follows).
  - `monitor_notify.summarize(events) -> tuple[str, str] | None` — `(title, body)` for the events worth telling, or `None`. Title: `"BKK Monitor: <n> problem(s)"` when any is bad, else `"BKK Monitor: back to normal"`. Body: up to 4 lines `"<target label> · <name>: <new>"`, then `"+<k> more"`.
  - `monitor_notify.toast(title, body)` — fire-and-forget PowerShell toast; never raises.
  - `collector.DB_PATH` = `ROOT/"launch"/"monitor"/"state"/"monitor.db"`; `collector.one_round(store, now, gateway_due) -> list[dict]` (events made this round, including watchdog ones); `collector.main()` loop.

- [ ] **Step 1: Write the failing tests**

`tests/test_monitor_notify.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_notify as mn  # noqa: E402


def ev(old, new, key="server:production", target="production", name="Production"):
    return {"key": key, "target": target, "name": name, "old": old, "new": new, "detail": ""}


def test_rules():
    assert mn.worth_telling(ev("ok", "fail"))
    assert mn.worth_telling(ev(None, "fail"))
    assert mn.worth_telling(ev("ok", "warn"))
    assert mn.worth_telling(ev("fail", "ok"))
    assert not mn.worth_telling(ev("ok", "stopped"))
    assert not mn.worth_telling(ev("ok", "idle"))
    assert not mn.worth_telling(ev("stopped", "ok"))
    assert not mn.worth_telling(ev("fail", "fail"))
    assert mn.worth_telling(ev(None, "restart", key="watchdog:production"))
    assert not mn.worth_telling(ev(None, "warn", key="watchdog:production"))


def test_summary_bad_and_more():
    events = [ev("ok", "fail", key=f"agent:production:a{i}", name=f"a{i}") for i in range(6)]
    title, body = mn.summarize(events)
    assert title == "BKK Monitor: 6 problem(s)"
    assert body.count("\n") == 4 and body.endswith("+2 more")
    assert "Production · a0: fail" in body


def test_summary_back_and_none():
    assert mn.summarize([ev("fail", "ok")])[0] == "BKK Monitor: back to normal"
    assert mn.summarize([ev("ok", "stopped")]) is None
    assert mn.summarize([]) is None
```

`tests/test_monitor_collector.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import collector  # noqa: E402
import monitor_checks  # noqa: E402
from monitor_store import Store  # noqa: E402


def test_one_round_stores_status_and_imports_watchdog(tmp_path, monkeypatch):
    log = tmp_path / "watchdog.log"
    log.write_text("2026-10-15 00:28:12 production :8000 down: running launch\\production\\restart.bat\n", encoding="utf-8")
    monkeypatch.setattr(collector, "WATCHDOG_LOG", log)
    monkeypatch.setattr(monitor_checks, "run_round", lambda gateway_due: [
        {"key": "server:production", "group": "server", "target": "production", "name": "Production",
         "state": "fail", "detail": "down"}])
    store = Store(tmp_path / "m.db")
    events = collector.one_round(store, now=2_000_000_000, gateway_due=False)
    assert {e["key"] for e in events} == {"server:production", "watchdog:production"}
    assert store.get_meta("collector_at") == "2000000000"
    # the same log line is not imported twice
    assert [e["key"] for e in collector.one_round(store, now=2_000_000_030, gateway_due=False)] == []


def test_old_watchdog_lines_beyond_30_days_skipped(tmp_path, monkeypatch):
    log = tmp_path / "watchdog.log"
    log.write_text("2020-01-01 00:00:00 production :8000 down: running x\\restart.bat\n", encoding="utf-8")
    monkeypatch.setattr(collector, "WATCHDOG_LOG", log)
    monkeypatch.setattr(monitor_checks, "run_round", lambda gateway_due: [])
    store = Store(tmp_path / "m.db")
    assert collector.one_round(store, now=2_000_000_000, gateway_due=False) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_notify.py tests/test_monitor_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `launch/monitor/monitor_notify.py`**

```python
"""
Windows notifications for the monitor: one toast per round that had a change worth telling (something went down
or came back). Shown through PowerShell's WinRT toast API, so no extra package is needed.
"""
import os
import subprocess

from monitor_checks import LABELS

BAD = {"fail", "warn", "restart"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
SCRIPT = r"""
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$t = $xml.GetElementsByTagName('text')
$null = $t.Item(0).AppendChild($xml.CreateTextNode($env:MON_TITLE))
$null = $t.Item(1).AppendChild($xml.CreateTextNode($env:MON_BODY))
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:MON_APP).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def worth_telling(e):
    if e["key"].startswith("watchdog:") and e["new"] == "warn":
        return False        # one missed check; the watchdog's restart line follows if it was real
    if e["new"] in BAD:
        return e["old"] != e["new"]
    return e["new"] == "ok" and e["old"] in ("fail", "warn")


def summarize(events):
    told = [e for e in events if worth_telling(e)]
    if not told:
        return None
    bad = [e for e in told if e["new"] in BAD]
    title = f"BKK Monitor: {len(bad)} problem(s)" if bad else "BKK Monitor: back to normal"
    lines = [f"{LABELS.get(e['target'], e['target'])} · {e['name']}: {e['new']}" for e in (bad or told)]
    body = "\n".join(lines[:4]) + (f"\n+{len(lines) - 4} more" if len(lines) > 4 else "")
    return title, body


def toast(title, body):
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                         env={**os.environ, "MON_TITLE": title, "MON_BODY": body, "MON_APP": APP_ID},
                         creationflags=NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001 - a missed toast must not stop the collector
        pass
```

- [ ] **Step 4: Implement `launch/monitor/collector.py`**

```python
r"""
BKK Monitor collector: checks everything every 30 s and keeps the history the app shows.

    .venv\Scripts\pythonw.exe launch\monitor\collector.py     started at logon by the "BKK Monitor collector" task
                                                               (launch\monitor\install.ps1); no window
Each round: monitor_checks.run_round (the AI gateway only every 5 minutes: each check takes one of the key's
3 parallel slots), new watchdog.log lines, one Windows toast for changes worth telling. Events older than 30 days
are deleted once an hour. The app asks for an early round by setting the meta value "check_now".
Only one collector runs: a second one exits at once (lock file state\collector.lock).
Errors go to state\collector.log.
"""
import logging
import msvcrt
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor_checks  # noqa: E402
import monitor_notify  # noqa: E402
import monitor_watchdog  # noqa: E402
from monitor_store import Store  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
DB_PATH = STATE / "monitor.db"
WATCHDOG_LOG = monitor_checks.STATE_DIR / "watchdog.log"
ROUND_S = 30
GATEWAY_S = 300
KEEP_DAYS = 30
log = logging.getLogger("bkk-monitor")


def import_watchdog(store, now):
    offset = int(store.get_meta("watchdog_offset", "0"))
    lines, offset = monitor_watchdog.read_new(WATCHDOG_LOG, offset)
    events = []
    for ln in lines:
        p = monitor_watchdog.parse(ln)
        if p and p["ts"] >= now - KEEP_DAYS * 86400:
            events.append(store.add_event(p["ts"], f"watchdog:{p['target']}", "watchdog", p["target"], "Watchdog",
                                          None, p["new"], p["detail"]))
    store.set_meta("watchdog_offset", offset)
    return events


def one_round(store, now, gateway_due):
    events = store.apply(monitor_checks.run_round(gateway_due), now)
    events += import_watchdog(store, now)
    store.set_meta("collector_at", int(now))
    return events


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(STATE / "collector.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    lock = open(STATE / "collector.lock", "w")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return 0        # another collector holds the lock
    store = Store(DB_PATH)
    log.info("collector started")
    last_gateway = last_prune = 0.0
    while True:
        now = time.time()
        try:
            gateway_due = now - last_gateway >= GATEWAY_S
            events = one_round(store, now, gateway_due)
            if gateway_due:
                last_gateway = now
            if now - last_prune >= 3600:
                store.prune(now, KEEP_DAYS)
                last_prune = now
            msg = monitor_notify.summarize(events)
            if msg:
                monitor_notify.toast(*msg)
        except Exception:  # noqa: BLE001 - a bad round is logged, the next one runs
            log.exception("round failed")
        store.set_meta("check_now", "0")
        for _ in range(ROUND_S):
            time.sleep(1)
            if store.get_meta("check_now") == "1":
                break


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Implement `launch/monitor/install.ps1`**

```powershell
# Registers (or with -Remove, deletes) the "BKK Monitor collector" scheduled task for the signed-in user: it starts
# launch\monitor\collector.py with pythonw (no window) at logon and keeps it running. Also puts the "BKK Monitor"
# icon on the Desktop and starts the collector now. No administrator rights needed.
param([switch]$Remove)
$name = 'BKK Monitor collector'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$pyw = Join-Path $root '.venv\Scripts\pythonw.exe'
$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'BKK Monitor.lnk'
if ($Remove) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $link -ErrorAction SilentlyContinue
    Write-Host "[OK] Removed the task '$name' and the Desktop icon."
    return
}
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$PSScriptRoot\collector.py`"" -WorkingDirectory $root
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $logon -Settings $settings `
    -Description 'BKK Monitor: checks servers, AI agents and YOLO every 30 s. launch\monitor' -Force | Out-Null
Start-ScheduledTask -TaskName $name
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($link)
$s.TargetPath = $pyw
$s.Arguments = "`"$PSScriptRoot\monitor_app.py`""
$s.WorkingDirectory = $root
$s.IconLocation = "$PSScriptRoot\icons\monitor.ico"
$s.Save()
Write-Host "[OK] Task '$name' started (runs at every logon). Desktop icon: BKK Monitor. Log: $PSScriptRoot\state\collector.log"
```

- [ ] **Step 6: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_notify.py tests/test_monitor_collector.py tests/test_monitor_store.py tests/test_monitor_checks.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add launch/monitor/monitor_notify.py launch/monitor/collector.py launch/monitor/install.ps1 tests/test_monitor_notify.py tests/test_monitor_collector.py
git commit -m "feat(monitor): collector process with watchdog import, 30-day prune and Windows toasts"
```

---

### Task 6: The app's Python side (`monitor_app.py`)

**Files:**
- Create: `launch/monitor/monitor_app.py`
- Modify: `requirements.txt` (add `pywebview>=6.2`)
- Test: `tests/test_monitor_app.py`

**Interfaces:**
- Consumes: `Store` (Task 3), `collector.DB_PATH` (Task 5), `monitor_checks.ROOT`, `monitor_checks.SERVERS` (Task 4), `yolo_switch.call(port, method, body, timeout)` (existing, `launch/yolo_switch.py`).
- Produces `class Api(store, runner=None, yolo_call=None, now=time.time)` — every public method is callable from JS as `window.pywebview.api.<name>(...)` and returns JSON-able data:
  - `status() -> {"collector_at": int|None, "collector_alive": bool, "items": list}` — `collector_alive` is true when the heartbeat is under 90 s old.
  - `events(filters: dict) -> {"rows", "total"}` — `filters` keys: `target`, `state`, `q`, `hours` (number → `since = now - hours*3600`), `limit`, `offset`. Unknown keys ignored; `limit` clamped to 1..500.
  - `check_now() -> {"ok": True}` — sets meta `check_now=1`.
  - `start_collector() -> {"ok": bool, "message": str}` — starts `pythonw collector.py` detached.
  - `action(target: str, verb: str) -> {"ok": bool, "message": str}` — allowed: `target` in `production|test|enviro` with `verb` in `start|restart|stop`, and `target` in `production|test` with `verb` in `yolo_on|yolo_off`. Anything else returns `{"ok": False, "message": "not allowed"}` and runs nothing.
  - `export_csv(filters: dict) -> {"ok": bool, "path"|"message"}` — asks for a file with the save dialog, writes the matching events (up to 100000) as UTF-8-BOM CSV with header `time,target,check,from,to,detail`.
  - `csv_text(filters) -> str` — the CSV text (used by `export_csv`, tested directly).
- `main()` opens the window: title `BKK Monitor`, 1360×860, min 980×640, `ui/index.html`, `background_color="#0b0d10"`.

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_app  # noqa: E402
from monitor_store import Store  # noqa: E402


def make(tmp_path, now=1000.0):
    ran, posts = [], []
    store = Store(tmp_path / "m.db")
    api = monitor_app.Api(store, runner=lambda args: ran.append(args),
                          yolo_call=lambda port, method, body, timeout: posts.append((port, body)) or {"enabled": body["enabled"]},
                          now=lambda: now)
    return api, store, ran, posts


def test_action_runs_whitelisted_bat(tmp_path):
    api, _, ran, _ = make(tmp_path)
    out = api.action("production", "restart")
    assert out["ok"]
    assert ran and ran[0][-1].endswith(str(Path("launch") / "production" / "restart.bat"))
    assert api.action("enviro", "stop")["ok"]
    assert ran[-1][-1].endswith(str(Path("launch") / "enviro" / "stop.bat"))


def test_action_refuses_unknown(tmp_path):
    api, _, ran, posts = make(tmp_path)
    assert api.action("production", "del /q *")["ok"] is False
    assert api.action("..\\..\\x", "start")["ok"] is False
    assert api.action("enviro", "yolo_on")["ok"] is False
    assert ran == [] and posts == []


def test_yolo_action(tmp_path):
    api, _, _, posts = make(tmp_path)
    assert api.action("test", "yolo_off")["ok"]
    assert posts == [(8001, {"enabled": False})]


def test_status_collector_alive(tmp_path):
    api, store, _, _ = make(tmp_path, now=1000.0)
    assert api.status()["collector_alive"] is False
    store.set_meta("collector_at", 950)
    assert api.status()["collector_alive"] is True
    store.set_meta("collector_at", 900)
    assert api.status()["collector_alive"] is False


def test_events_filters_and_csv(tmp_path):
    api, store, _, _ = make(tmp_path, now=10_000.0)
    store.add_event(9_000, "server:production", "server", "production", "Production", "ok", "fail", 'said "no", bye')
    store.add_event(1_000, "server:test", "server", "test", "Test", "ok", "stopped", "")
    assert api.events({"hours": 1})["total"] == 1
    assert api.events({"limit": 99999})["total"] == 2
    csv = api.csv_text({})
    assert csv.splitlines()[0] == "time,target,check,from,to,detail"
    assert '"said ""no"", bye"' in csv


def test_check_now_sets_meta(tmp_path):
    api, store, _, _ = make(tmp_path)
    api.check_now()
    assert store.get_meta("check_now") == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'monitor_app'`

- [ ] **Step 3: Implement `launch/monitor/monitor_app.py`**

```python
r"""
BKK Monitor: the desktop window (Desktop icon "BKK Monitor", made by launch\monitor\install.ps1).

    .venv\Scripts\pythonw.exe launch\monitor\monitor_app.py

Shows what the collector (launch\monitor\collector.py) stored in state\monitor.db: status cards, every check,
and the history of changes. The buttons run the same files as the Desktop shortcuts (launch\<folder>\start.bat,
restart.bat, stop.bat) in a new window, and switch YOLO through launch\yolo_switch.py. The page asks for
confirmation first; this side only runs actions from a fixed list.
"""
import csv
import io
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import collector  # noqa: E402
import yolo_switch  # noqa: E402
from monitor_checks import ROOT, SERVERS  # noqa: E402
from monitor_store import Store  # noqa: E402

BAT_TARGETS = {"production", "test", "enviro"}
BAT_VERBS = {"start", "restart", "stop"}
YOLO_TARGETS = {"production", "test"}
ALIVE_S = 90
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def run_in_new_window(args):
    subprocess.Popen(args, cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class Api:
    def __init__(self, store, runner=None, yolo_call=None, now=time.time):
        self._store = store
        self._run = runner or run_in_new_window
        self._yolo = yolo_call or yolo_switch.call
        self._now = now
        self._window = None     # set by main(); used for the save dialog

    def status(self):
        at = self._store.get_meta("collector_at")
        at = int(at) if at else None
        return {"collector_at": at, "collector_alive": bool(at) and self._now() - at < ALIVE_S,
                "items": self._store.current()}

    def _query(self, filters):
        f = filters or {}
        hours = f.get("hours")
        return {"target": f.get("target") or None, "state": f.get("state") or None, "q": f.get("q") or None,
                "since": self._now() - float(hours) * 3600 if hours else None}

    def events(self, filters):
        f = filters or {}
        limit = max(1, min(500, int(f.get("limit") or 25)))
        return self._store.events(**self._query(f), limit=limit, offset=max(0, int(f.get("offset") or 0)))

    def check_now(self):
        self._store.set_meta("check_now", "1")
        return {"ok": True}

    def start_collector(self):
        try:
            subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "pythonw.exe"), str(HERE / "collector.py")],
                             cwd=str(ROOT), creationflags=DETACHED, close_fds=True)
        except OSError as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True, "message": "collector started"}

    def action(self, target, verb):
        if target in BAT_TARGETS and verb in BAT_VERBS:
            bat = ROOT / "launch" / target / f"{verb}.bat"
            # `start` opens the .bat in its own console window, like double-clicking the Desktop shortcut
            self._run(["cmd.exe", "/c", "start", "", str(bat)])
            return {"ok": True, "message": f"{verb} {target}: opened {bat.name} in a new window"}
        if target in YOLO_TARGETS and verb in ("yolo_on", "yolo_off"):
            want = verb == "yolo_on"
            try:
                out = self._yolo(SERVERS[target], "POST", {"enabled": want}, 120)
            except Exception as e:  # noqa: BLE001 - shown to the user as is
                return {"ok": False, "message": f"YOLO switch failed: {e}"}
            self.check_now()
            return {"ok": True, "message": f"YOLO {'on' if out.get('enabled') else 'off'} on {target}"}
        return {"ok": False, "message": "not allowed"}

    def csv_text(self, filters):
        rows = self._store.events(**self._query(filters), limit=100000)["rows"]
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["time", "target", "check", "from", "to", "detail"])
        for r in rows:
            w.writerow([datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S"), r["target"], r["name"],
                        r["old"] or "", r["new"], r["detail"] or ""])
        return buf.getvalue()

    def export_csv(self, filters):
        import webview
        name = f"bkk-monitor-{datetime.now():%Y%m%d-%H%M}.csv"
        picked = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=name,
                                                 file_types=("CSV files (*.csv)",))
        if not picked:
            return {"ok": False, "message": "cancelled"}
        path = picked if isinstance(picked, str) else picked[0]
        Path(path).write_text(self.csv_text(filters), encoding="utf-8-sig")
        return {"ok": True, "path": path}


def main():
    import webview
    api = Api(Store(collector.DB_PATH))
    api._window = webview.create_window("BKK Monitor", str(HERE / "ui" / "index.html"), js_api=api,
                                         width=1360, height=860, min_size=(980, 640), background_color="#0b0d10")
    webview.start()


if __name__ == "__main__":
    main()
```

Note: pywebview exposes every public attribute of `js_api`; the leading underscore on `_store`, `_run`, `_yolo`, `_now`, `_window` keeps them out of JS.

Add to `requirements.txt` (next to the other UI/launcher dependencies; keep the existing comment style):
```
pywebview>=6.2          # launch\monitor desktop app (WebView2 window)
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_monitor_app.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add launch/monitor/monitor_app.py tests/test_monitor_app.py requirements.txt
git commit -m "feat(monitor): app API with whitelisted actions, event filters and CSV export"
```

---

### Task 7: The window UI, icon, install and smoke test

**Files:**
- Create: `launch/monitor/ui/index.html` (single file: HTML + CSS + JS, no CDN — the app must work offline)
- Create: `launch/monitor/icons/monitor.ico` (generated, committed)
- Create: `launch/monitor/make_icon.py` (one-off generator, committed so the icon can be rebuilt)

**Interfaces:**
- Consumes: `window.pywebview.api.status()`, `.events(filters)`, `.check_now()`, `.start_collector()`, `.action(target, verb)`, `.export_csv(filters)` (Task 6). JS must wait for the `pywebviewready` event before the first call.

**Layout (Vapi "Chat Logs" look, English text):**
- Colours as CSS variables on `:root`: `--bg #0b0d10`, `--panel #111418`, `--line #1f242b`, `--text #e6e8eb`, `--muted #8b929c`, `--ok #3ecf8e`, `--warn #f5a524`, `--fail #f0556a`, `--idle #6b7280`, `--stopped #4b5563`, `--accent #5b8cff`. Font: `"Segoe UI", system-ui, sans-serif`, 13px; tables use `font-variant-numeric: tabular-nums`.
- **Sidebar** (220 px): app name "BKK Monitor" with a status dot (green when the collector is alive); nav items `Overview`, `Checks`, `Events`; a "TARGETS" section listing `Production`, `Test`, `ENVIRO`, `Services` (click = filter Checks/Events to that target); footer "Collector: running / not running" + `Start collector` button when not running.
- **Header**: page title + subtitle ("Live state of every check · updated <time>" / "State changes, kept 30 days · <total> events"), right side: `Check now` button.
- **Overview** page: a grid of cards, one per `server:*` and `service:*` status, plus a "YOLO" card per running server (from its `yolo:<target>:YOLO switch` row). Each card: label, coloured state pill (`ok`/`warn`/`fail`/`idle`/`stopped`), detail line, "since <relative time>". Counter line under the cards: "<n> checks · <ok> ok · <bad> need attention". Then "Needs attention": a table of every status whose state is `fail` or `warn`.
- Cards for `production`, `test`, `enviro` have a `⋯` menu with `Start`, `Restart`, `Stop`; production and test cards also have `YOLO on` / `YOLO off`. Disable `Start` when state is `ok`/`warn`, disable `Stop`/`Restart` when `stopped`.
- **Checks** page: table `STATE | TARGET | CHECK | DETAIL | SINCE | CHECKED`, grouped by target, rows of a server that is not `ok`/`warn` are dimmed (their result is from the last time it answered). Filter chips: target, state, search box.
- **Events** page: filter chips row (`Time range` 1 h / 24 h / 7 d / 30 d, `Target`, `State`, search), a toolbar row with refresh icon button, `Rows: 25 ▾` (25/50/100), `Export`. Table `TIME | TARGET | CHECK | CHANGE | DETAIL` where CHANGE shows `old → new` as two pills (`new` for first-seen). Footer: "Showing a–b of N" and Prev/Next.
- **Confirm dialog** (custom modal, never `alert`/`confirm`): title "Restart Production?" etc. Body text per action; for `production` + `stop`: "This takes bkksmartstreet.com down until someone starts it again." For YOLO off: "Frees GPU memory; counters, helmet and wrong-way checks pause." Buttons `Cancel` / `<Verb>` (red for stop). While the call runs the button shows a spinner; afterwards a toast-style message at the bottom right shows `message`, and the page calls `check_now()`.
- Refresh: `status()` every 5 s; on Events page also `events()` every 15 s (only when on page 1, so paging is not disturbed).
- Relative time helper: `<60 s` → "just now", minutes, hours, else `YYYY-MM-DD HH:MM`.
- Escape all text from the API before inserting into HTML (use `textContent` or an `esc()` helper).
- Phone-width rules are not needed (desktop window, min width 980).

- [ ] **Step 1: Write `launch/monitor/make_icon.py` and generate the icon**

```python
"""Makes launch\\monitor\\icons\\monitor.ico (a pulse line on a dark rounded square). Run once with the .venv Python."""
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).resolve().parent / "icons" / "monitor.ico"
out.parent.mkdir(exist_ok=True)
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=48, fill=(17, 20, 24, 255), outline=(62, 207, 142, 255), width=10)
pts = [(36, 140), (88, 140), (112, 80), (144, 190), (170, 120), (220, 120)]
d.line(pts, fill=(62, 207, 142, 255), width=18, joint="curve")
img.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
```

Run: `.venv\Scripts\python.exe launch\monitor\make_icon.py`
Expected: prints the `.ico` path; file exists.

- [ ] **Step 2: Write `launch/monitor/ui/index.html`** following the layout above. Required JS structure (implement fully, no placeholders):

```javascript
const api = () => window.pywebview.api;
const S = { page: "overview", target: "", state: "", q: "", hours: 24, limit: 25, offset: 0, status: null };
const STATES = ["ok", "warn", "fail", "idle", "stopped"];
const LABEL = { production: "Production", test: "Test", enviro: "ENVIRO", gateway: "AI gateway", tunnel: "Cloudflare tunnel" };
const ACTIONS = {
  start:   { title: t => `Start ${LABEL[t]}?`,   body: t => `Opens launch\\${t}\\start.bat in a new window.` },
  restart: { title: t => `Restart ${LABEL[t]}?`, body: t => t === "production" ? "The public site is down for about a minute while it restarts." : `Runs launch\\${t}\\restart.bat in a new window.` },
  stop:    { title: t => `Stop ${LABEL[t]}?`,    body: t => t === "production" ? "This takes bkksmartstreet.com down until someone starts it again." : `Runs launch\\${t}\\stop.bat. The watchdog leaves it stopped.`, danger: true },
  yolo_on:  { title: t => `Turn YOLO on (${LABEL[t]})?`,  body: () => "Loads the models onto the GPU (10-30 s)." },
  yolo_off: { title: t => `Turn YOLO off (${LABEL[t]})?`, body: () => "Frees GPU memory; counters, helmet and wrong-way checks pause.", danger: true },
};
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function ago(ts) { /* "just now" / "N min ago" / "N h ago" / "YYYY-MM-DD HH:MM" */ }
function pill(state) { return `<span class="pill ${esc(state)}">${esc(state)}</span>`; }
async function loadStatus() { S.status = await api().status(); render(); }
async function loadEvents() { S.events = await api().events({ target: S.target, state: S.state, q: S.q, hours: S.hours, limit: S.limit, offset: S.offset }); render(); }
function render() { /* sidebar dot + collector footer; then renderOverview() / renderChecks() / renderEvents() by S.page */ }
function confirmAction(target, verb) { /* open modal from ACTIONS; on confirm: busy spinner, await api().action(target, verb), showMessage(res.message, res.ok), loadStatus() */ }
window.addEventListener("pywebviewready", () => {
  loadStatus(); loadEvents();
  setInterval(loadStatus, 5000);
  setInterval(() => { if (S.page === "events" && S.offset === 0) loadEvents(); }, 15000);
});
```

The comment-bodied functions above (`ago`, `render`, `confirmAction`) are descriptions of what to write, not code to paste: write them in full. Event-row state is `new`; first-seen rows (`old === null`) show only the `new` pill. Watchdog rows show target + "Watchdog" + pill `restart` (colour `--fail`) or `warn`.

- [ ] **Step 3: Install and smoke test (live, read-only for the servers)**

Run, in PowerShell from the repo root:
```
powershell -NoProfile -ExecutionPolicy Bypass -File launch\monitor\install.ps1
```
Expected: `[OK] Task 'BKK Monitor collector' started ...`; `BKK Monitor.lnk` on the Desktop.

Wait ~40 s, then:
```
.venv\Scripts\python.exe -c "import sys; sys.path[:0]=['launch','launch/monitor']; from monitor_store import Store; s=Store('launch/monitor/state/monitor.db'); print(s.get_meta('collector_at')); [print(r['state'], r['key'], '|', r['detail'][:70]) for r in s.current()]"
```
Expected: a recent `collector_at`; `server:production ok` (or `warn`), `server:test stopped` (while `stopped_8001` exists), agent and YOLO rows for production, `service:tunnel ok`, `service:gateway` present. `launch\monitor\state\collector.log` has `collector started` and no tracebacks.

Open the app: `.venv\Scripts\pythonw.exe launch\monitor\monitor_app.py`. Check by eye: cards show, Checks table fills, Events table shows the watchdog history from the last 30 days, filters and paging work, Export writes a CSV. **Do not click any action button** in this smoke test (they act on the live servers); open each confirm dialog and press Cancel only.

- [ ] **Step 4: Full test run**

Run: `.venv\Scripts\python.exe -m pytest tests -q`
Expected: everything passes. If a test outside `tests/test_monitor_*`, `test_ai_status_check.py` and `test_yolo_status_check.py` fails, check whether it also fails on commit `9bd07c7` before blaming this branch.

- [ ] **Step 5: Commit**

```bash
git add launch/monitor/ui/index.html launch/monitor/icons/monitor.ico launch/monitor/make_icon.py
git commit -m "feat(monitor): BKK Monitor window (cards, checks, event history, confirmed actions)"
```
