# BKK Monitor on the Phone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user can open BKK Monitor (status, AI agents, events, logs) on their phone through Tailscale, read-only.

**Architecture:** A small stdlib HTTP server (`launch/monitor/monitor_web.py`) on `127.0.0.1:8090` serves the same `ui/index.html` and answers `POST /api/<method>` for the reading methods of the existing `monitor_app.Api` only. `tailscale serve --bg 8090` publishes it on the tailnet as `https://vexila.<tailnet>.ts.net/` (HTTPS, tailnet devices only, never public). The page detects web mode from a `<meta name="bkk-web">` tag that the server injects, talks to the server with `fetch` instead of `window.pywebview.api`, hides every button that changes something, and gets a phone layout under 760 px.

**Tech Stack:** Python 3 stdlib (`http.server.ThreadingHTTPServer`, `json`), plain JS/CSS in `launch/monitor/ui/index.html`, PowerShell scheduled task (`launch/monitor/install.ps1`), Tailscale CLI. Tests: pytest with `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest`.

**Spec:** the user's request in this session (2026-10-16): "view the BKK Monitor app on the phone", with two decisions: access through **Tailscale**, and **view only** (no start / restart / stop / YOLO on the phone).

## Global Constraints

- Bind only to `127.0.0.1`, port `8090`. Never `0.0.0.0`, never the LAN.
- No new dependencies. Stdlib only on the server side.
- The phone side must not be able to run `action`, `start_collector`, `open_log`, `export_csv` or `csv_text`. Allowed: `status`, `events`, `processes`, `log_tail`, `check_now`.
- The desktop window (`monitor_app.py`, pywebview) must look and behave exactly as before, all buttons included.
- UI text stays English, like the rest of the app.
- Do not touch `launch/camera_status.py` (unrelated uncommitted change). Do not start, stop or restart servers or the collector from a task.
- Commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A write method called by URL (`/api/action`, `/api/start_collector`, `/api/open_log`, `/api/export_csv`) returns 403 and the method never runs. Test in Task 1.
2. A request with a foreign `Host` (DNS rebinding from a web page) or a non-JSON content type (cross-site form POST) is refused. Tests in Task 1.
3. A second copy of `monitor_web.py` (port already taken, e.g. the task restarted) exits with code 0 and does not crash-loop. Test in Task 1.
4. The desktop window still shows its kebab menus, "Start collector", "Open log" and "Export" buttons: the read-only switch only applies in web mode. Check in Task 2 (the file on disk has no `bkk-web` meta; only the served copy does).
5. Collector stopped or DB empty: the phone page shows "Collector: not running" without a button and without JS errors. Check in Task 2 manual step.

---

### Task 1: Read-only web server

**Files:**
- Create: `launch/monitor/monitor_web.py`
- Test: `tests/test_monitor_web.py`

**Interfaces:**
- Consumes: `monitor_app.Api(store)` with methods `status()`, `events(filters)`, `processes()`, `log_tail(name, offset=None)`, `check_now()`; `monitor_store.Store`, `DEFAULT_DB`.
- Produces: `monitor_web.READ_ONLY` (set of str), `monitor_web.PORT = 8090`, `monitor_web.host_ok(host: str | None) -> bool`, `monitor_web.page_bytes() -> bytes` (index.html with `<meta name="bkk-web" content="1">` right after `<head>`), `monitor_web.serve(api, host="127.0.0.1", port=PORT) -> ThreadingHTTPServer`, `monitor_web.main() -> int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_monitor_web.py`:

```python
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_web  # noqa: E402


class FakeApi:
    def __init__(self):
        self.calls = []

    def status(self):
        self.calls.append("status")
        return {"collector_at": None, "collector_alive": False, "items": []}

    def events(self, filters):
        self.calls.append(("events", filters))
        return {"rows": [], "total": 0}

    def processes(self):
        return []

    def log_tail(self, name, offset=None):
        return {"lines": [name], "offset": offset or 0, "reset": False}

    def check_now(self):
        return {"ok": True}

    def action(self, target, verb):
        self.calls.append("action")
        return {"ok": True}

    def start_collector(self):
        self.calls.append("start_collector")
        return {"ok": True}


@pytest.fixture
def srv():
    api = FakeApi()
    server = monitor_web.serve(api, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield api, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def req(url, body=None, host=None, ctype="application/json"):
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    r = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")
    if data is not None:
        r.add_header("Content-Type", ctype)
    if host:
        r.add_header("Host", host)
    try:
        with urllib.request.urlopen(r, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_page_is_index_with_web_marker(srv):
    _, base = srv
    code, body, headers = req(base + "/")
    assert code == 200 and b"BKK Monitor" in body
    assert b'<meta name="bkk-web" content="1">' in body
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Cache-Control"] == "no-store"


def test_file_on_disk_has_no_web_marker():
    # the desktop window loads the file itself: it must stay in desktop mode
    assert b'<meta name="bkk-web"' not in (ROOT / "launch" / "monitor" / "ui" / "index.html").read_bytes()


def test_reading_calls_answer_json(srv):
    api, base = srv
    code, body, _ = req(base + "/api/status", [])
    assert code == 200 and json.loads(body)["collector_alive"] is False
    code, body, _ = req(base + "/api/events", [{"hours": 24}])
    assert code == 200 and api.calls[-1] == ("events", {"hours": 24})
    code, body, _ = req(base + "/api/log_tail", ["production", 10])
    assert json.loads(body) == {"lines": ["production"], "offset": 10, "reset": False}


@pytest.mark.parametrize("name", ["action", "start_collector", "open_log", "export_csv", "csv_text", "_store", "__init__"])
def test_write_calls_are_refused(srv, name):
    api, base = srv
    code, body, _ = req(base + f"/api/{name}", ["production", "stop"])
    assert code == 403 and json.loads(body)["error"] == "not allowed"
    assert "action" not in api.calls and "start_collector" not in api.calls


def test_foreign_host_is_refused(srv):
    api, base = srv
    assert req(base + "/", host="evil.example.com")[0] == 403
    assert req(base + "/api/status", [], host="evil.example.com:8090")[0] == 403
    assert "status" not in api.calls


def test_host_ok():
    assert monitor_web.host_ok("127.0.0.1:8090") and monitor_web.host_ok("localhost:8090")
    assert monitor_web.host_ok("vexila.tail1234.ts.net") and monitor_web.host_ok("VEXILA.tail1234.ts.net:443")
    assert not monitor_web.host_ok("evil.com") and not monitor_web.host_ok(None) and not monitor_web.host_ok("")
    assert not monitor_web.host_ok("ts.net.evil.com") and not monitor_web.host_ok("evilts.net")


def test_form_post_is_refused(srv):
    _, base = srv
    assert req(base + "/api/status", b"[]", ctype="text/plain")[0] == 415


def test_bad_bodies(srv):
    _, base = srv
    assert req(base + "/api/status", b"{not json")[0] == 400
    assert req(base + "/api/status", {"a": 1})[0] == 400            # args must be a list
    assert req(base + "/api/status", ["extra"])[0] == 400           # wrong argument count
    assert req(base + "/api/status", b"[" + b"0," * 40000 + b"0]")[0] == 413


def test_unknown_path_404(srv):
    _, base = srv
    assert req(base + "/secret.txt")[0] == 404
    assert req(base + "/api/status/x", [])[0] == 403


def test_second_copy_exits_quietly(monkeypatch, tmp_path):
    busy = monitor_web.serve(FakeApi(), port=0)
    try:
        monkeypatch.setattr(monitor_web, "PORT", busy.server_address[1])
        monkeypatch.setattr(monitor_web, "LOG_PATH", tmp_path / "web.log")
        assert monitor_web.main(db=tmp_path / "m.db") == 0
        assert "already running" in (tmp_path / "web.log").read_text(encoding="utf-8")
    finally:
        busy.server_close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests/test_monitor_web.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'monitor_web'`.

- [ ] **Step 3: Write the implementation**

Create `launch/monitor/monitor_web.py`:

```python
r"""
BKK Monitor on the phone: the desktop window's page, served read-only on 127.0.0.1:8090.

    .venv\Scripts\pythonw.exe launch\monitor\monitor_web.py     started at logon by the "BKK Monitor web" task
                                                                (launch\monitor\install.ps1); no window
Tailscale publishes it to the tailnet only (never public):
    tailscale serve --bg 8090        ->  https://vexila.<tailnet>.ts.net/
The page (ui\index.html) gets <meta name="bkk-web"> here, so it calls POST /api/<method> instead of pywebview
and hides the buttons that change something. Only the methods in READ_ONLY answer; start/restart/stop, YOLO,
the collector button and the file dialogs stay on the desktop.
Errors go to state\web.log. A second copy finds the port taken and exits.
"""
import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from monitor_app import Api  # noqa: E402
from monitor_store import DEFAULT_DB, Store  # noqa: E402

PORT = 8090
READ_ONLY = {"status", "events", "processes", "log_tail", "check_now"}
INDEX = HERE / "ui" / "index.html"
LOG_PATH = HERE / "state" / "web.log"
MAX_BODY = 65536
MARKER = b'<meta name="bkk-web" content="1">'
log = logging.getLogger("bkk-monitor-web")


def host_ok(host):
    """Local names, or this machine's Tailscale name: a page on another site (DNS rebinding) gets 403."""
    name = (host or "").strip().lower().rsplit(":", 1)[0] if host and not host.startswith("[") else ""
    return name in ("127.0.0.1", "localhost") or (name.endswith(".ts.net") and len(name) > len(".ts.net"))


def page_bytes():
    return INDEX.read_bytes().replace(b"<head>", b"<head>\n" + MARKER, 1)


def make_handler(api):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):    # pythonw has no stderr; requests are not worth logging
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not host_ok(self.headers.get("Host")):
                return self._send(403, {"error": "forbidden"})
            if self.path.split("?", 1)[0] in ("/", "/index.html"):
                return self._send(200, page_bytes(), "text/html; charset=utf-8")
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not host_ok(self.headers.get("Host")):
                return self._send(403, {"error": "forbidden"})
            path = self.path.split("?", 1)[0]
            name = path[len("/api/"):] if path.startswith("/api/") else ""
            if name not in READ_ONLY:
                return self._send(403, {"error": "not allowed"})
            # a form on another site can only send text/plain or form types: JSON needs a preflight it never gets
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                return self._send(415, {"error": "JSON only"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return self._send(400, {"error": "bad length"})
            if length > MAX_BODY:
                if length <= 1 << 20:
                    self.rfile.read(length)    # drain it, or Windows resets the connection before the 413 arrives
                self.close_connection = True
                return self._send(413, {"error": "too large"})
            try:
                args = json.loads(self.rfile.read(length) or b"[]")
            except ValueError:
                return self._send(400, {"error": "bad JSON"})
            if not isinstance(args, list):
                return self._send(400, {"error": "arguments must be a list"})
            try:
                out = getattr(api, name)(*args)
            except TypeError as e:
                return self._send(400, {"error": str(e)[:200]})
            except Exception as e:  # noqa: BLE001 - shown on the page as a toast
                log.exception("%s failed", name)
                return self._send(500, {"error": str(e)[:200]})
            self._send(200, out)

    return Handler


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False     # on Windows SO_REUSEADDR lets a second copy bind the same port
    daemon_threads = True


def serve(api, host="127.0.0.1", port=None):
    return _Server((host, PORT if port is None else port), make_handler(api))


def main(db=None):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        try:
            server = serve(Api(Store(db or DEFAULT_DB)))
        except OSError as e:
            log.info("port %s already in use (%s): already running, exiting", PORT, e)
            return 0
        log.info("serving on 127.0.0.1:%s", PORT)
        server.serve_forever()
        return 0
    except Exception:  # noqa: BLE001 - under pythonw nobody sees a traceback; leave it in the log
        log.exception("web server stopped")
        return 1
    finally:
        log.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    sys.exit(main())
```

Note on `serve(api, port=0)` in the tests: `port=0` must reach the socket as 0 (OS picks a free port), which is why the default is `None`, not `PORT`.

Note on `test_second_copy_exits_quietly`: `HTTPServer` sets `allow_reuse_address = 1`, and on Windows `SO_REUSEADDR` lets a second socket bind a port that is already listening. `_Server` turns it off, so the second bind raises `OSError` (WinError 10048) and `main` exits 0.

- [ ] **Step 4: Run tests to verify they pass**

Run: `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests/test_monitor_web.py -q`
Expected: all pass. Then `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests -q -k monitor` — all pass.

- [ ] **Step 5: Commit**

```bash
git add launch/monitor/monitor_web.py tests/test_monitor_web.py
git commit -m "feat(monitor): read-only web server for the phone (127.0.0.1:8090)"
```
(with the Co-Authored-By line from Global Constraints)

---

### Task 2: Page in web mode: fetch API, read-only, phone layout

**Files:**
- Modify: `launch/monitor/ui/index.html` (CSS block at the top, the `api` constant, `stateCard`, `procCard`, `render` footer, `renderEvents` bar, the start code at the bottom)

**Interfaces:**
- Consumes: Task 1's server: page carries `<meta name="bkk-web" content="1">`; `POST api/<method>` with JSON array body; answers the method's JSON, or `{"error": "..."}` with a non-2xx code.
- Produces: nothing for later tasks.

- [ ] **Step 1: Web-mode API shim.** Replace the line `const api = () => window.pywebview.api;` with:

```js
// Served by monitor_web.py (the phone, through Tailscale): read-only, fetch instead of pywebview
const WEB = !!document.querySelector('meta[name="bkk-web"]');
async function post(name, args) {
  const r = await fetch(`api/${name}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(args) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
const WEB_API = {
  status: () => post("status", []),
  events: f => post("events", [f]),
  processes: () => post("processes", []),
  log_tail: (n, off) => post("log_tail", [n, off]),
  check_now: () => post("check_now", []),
};
const api = () => WEB ? WEB_API : window.pywebview.api;
```

The URL is relative (`api/...`) so it works under `tailscale serve` at the root and on `http://127.0.0.1:8090/`.

- [ ] **Step 2: Hide what changes something, in web mode only.**
  - `stateCard`: change `const showMenu = !!menuTarget;` to `const showMenu = !!menuTarget && !WEB;`.
  - `procCard`: change `const canAct = ["production", "test", "enviro"].includes(p.name);` to `const canAct = !WEB && ["production", "test", "enviro"].includes(p.name);`, and render the `<div class="acts">…Open log…</div>` only when `!WEB` (replace it with `""` in web mode).
  - `procSkeleton`: the `<button class="btn sm" id="lopen" …>Open log</button>` only when `!WEB`. `syncProc` sets `$("lopen").dataset.n`: guard it with `if ($("lopen"))`.
  - `render` footer: `(alive ? "" : `<button …>Start collector</button>`)` becomes `(alive || WEB ? "" : …)`.
  - `renderEvents` bar: the `Export` button only when `!WEB`.
  - In web mode add a small muted line in the footer: `<div>View only</div>` (after the Collector line).

- [ ] **Step 3: Start in web mode.** At the bottom, replace

```js
if (window.pywebview && window.pywebview.api) start();
else render();
```
with
```js
if (WEB || (window.pywebview && window.pywebview.api)) start();
else render();
```

- [ ] **Step 4: Phone layout.** Append to the end of the `<style>` block (before `</style>`):

```css
/* phone (monitor_web.py through Tailscale): sidebar becomes a top bar, the page scrolls, tables scroll sideways */
@media (max-width: 760px) {
  body { min-width: 0; overflow: auto; }
  .app { flex-direction: column; height: auto; min-height: 100vh; }
  .side { width: auto; flex-direction: row; align-items: center; gap: 4px; padding: 8px 12px; overflow-x: auto;
    border-right: 0; border-bottom: 1px solid var(--line); position: sticky; top: 0; z-index: 30; }
  .brand { padding: 0 8px 0 0; white-space: nowrap; }
  .sec, .spacer { display: none; }
  .nav { width: auto; flex: none; white-space: nowrap; }
  .foot { flex-direction: row; align-items: center; border-top: 0; padding: 0 0 0 8px; white-space: nowrap; }
  .head { padding: 14px 16px 10px; }
  .head h1 { font-size: 18px; }
  .body { overflow: visible; padding: 0 16px 16px; }
  .grid { grid-template-columns: 1fr; }
  .pgrid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .wrap { overflow-x: auto; }
  .wrap table { min-width: 560px; }
  .detail { max-width: 220px; }
  .chip input { width: 110px; }
  #logpane { height: 55vh; }
  .modal { width: calc(100vw - 32px); }
  #toasts { left: 16px; right: 16px; }
}
```

The desktop window is at least 980 px wide (`min_size` in `monitor_app.py`), so this block never applies there.

- [ ] **Step 5: Syntax check.** Extract the `<script>` block to `C:\Users\user\AppData\Local\Temp\claude\E--new-ccty-bangkok\df820df0-c04c-49bc-afbf-b1575081a048\scratchpad\monitor_index_script.js` and run `node --check` on it. Expected: no output, exit 0. Run `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests -q -k monitor`: all pass (includes `test_file_on_disk_has_no_web_marker`).

- [ ] **Step 6: Manual check (controller does this, not the implementer).** Start `monitor_web.py` on a test port against the live DB, open `http://127.0.0.1:8090/` in Chrome at 390 px width and at desktop width: Overview, Checks, Events, Processes (AI agents table, log follows) render; no kebab menus, no Start collector / Open log / Export buttons; no console errors. Then open the desktop app once and confirm its buttons are still there.

- [ ] **Step 7: Commit**

```bash
git add launch/monitor/ui/index.html
git commit -m "feat(monitor): page works in a phone browser: fetch API, view only, narrow layout"
```

---

### Task 3: Run it at logon and publish on the tailnet

**Files:**
- Modify: `launch/monitor/install.ps1`
- Modify: `launch/monitor/monitor_app.py:1-10` (docstring: one line pointing to `monitor_web.py` for the phone)

**Interfaces:**
- Consumes: Task 1's `launch\monitor\monitor_web.py` (run with `pythonw`, exits 0 when already running).

- [ ] **Step 1: install.ps1 registers a second task.** After the collector task block, register `BKK Monitor web` with the same `$settings` and `$logon`, action `$pyw "`"$PSScriptRoot\monitor_web.py`""`, description `'BKK Monitor web: read-only page for the phone on 127.0.0.1:8090 (tailscale serve --bg 8090). launch\monitor'`, then `Start-ScheduledTask`. `-Remove` stops and unregisters both tasks. Update the header comment. At the end print:

```powershell
Write-Host "[OK] Task 'BKK Monitor web' started: http://127.0.0.1:8090/ (view only)."
Write-Host "     For the phone, once: tailscale serve --bg 8090   then open https://<this PC>.<tailnet>.ts.net/ in the Tailscale-connected phone."
```

Use a `foreach` over a small table of `@{ Name; Script; Description }` so the two registrations share one code path.

- [ ] **Step 2: Commit**

```bash
git add launch/monitor/install.ps1 launch/monitor/monitor_app.py
git commit -m "feat(monitor): install.ps1 also runs the phone web server at logon"
```

- [ ] **Step 3: Deploy (controller, with the user).**
  1. Run `powershell -NoProfile -ExecutionPolicy Bypass -File launch\monitor\install.ps1` (no admin). This also restarts nothing else; the collector task is re-registered with `-Force` and started (already running: `IgnoreNew`).
  2. Check `curl http://127.0.0.1:8090/` gives 200.
  3. Tailscale must be connected on this PC (today `tailscale status` says `NoState`: the user opens the Tailscale app and signs in). Then `tailscale serve --bg 8090`. If it answers with a link to enable HTTPS for the tailnet, the user opens it once.
  4. `tailscale serve status` shows `https://vexila.<tailnet>.ts.net (tailnet only)` → `http://127.0.0.1:8090`.
  5. The user opens that URL on the phone (Tailscale app connected).
  6. Update memory `bkk-monitor-app.md` with the web task, port, and serve command.
