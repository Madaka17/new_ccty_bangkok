"""Live Bionic usage page: a small local web server on 127.0.0.1.

Run with:  pythonw live.py            (starts the server and opens the browser)
           python live.py --no-open   (starts the server only)
           python live.py --port 8300 (another port; default 8199 or BIONIC_USAGE_PORT)

The server does three things in the background:
  * runs collect.run() every 3 s, so the usage database stays up to date;
  * reads the newest Bionic log (live_tail.py) to show requests still running;
  * asks Bionic which models are loaded, every 10 s (2 s timeout);
  * reads the SSH tunnel that carries the Pi test server's Bionic calls (tunnel.py):
    local state every 2 s, and one ssh check of the Pi every 30 s on its own thread.

Routes:
  /            the live page (live_page.py, self-contained)
  /api/state   JSON for the page (polled every 2 s)
  /report      the full static report, rebuilt on each request
Requests whose Host header is not 127.0.0.1:<port> or localhost:<port> get 403.

The server stops itself after 15 minutes without an /api/state request, so it
does not stay in the background once the browser is closed. The scheduled task
(scheduled_run.py) keeps collecting history while this page is closed.

Errors go to live.log next to usage.db. pythonw has no console, so nothing here
writes to stdout or stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import collect
import live_tail
import report
from live_page import PAGE_HTML

# Changes whenever this server process (re)starts: an open page sees a new value and reloads itself, so it
# always runs the page code the server now serves (a restart after an update, or the auto-exit and a new start)
SERVER_ID = f"{os.getpid()}-{int(time.time())}"

HOST = "127.0.0.1"
DEFAULT_PORT = 8199
PORT_ENV = "BIONIC_USAGE_PORT"
BIONIC_MODELS_URL = "http://localhost:1235/api/v1/models"
BIONIC_TIMEOUT_SECONDS = 2
STATE_POLL_MS = 2000
IDLE_LIMIT_SECONDS = 15 * 60
IDLE_CHECK_SECONDS = 30
RECENT_LIMIT = 50
MINUTES = 60
# How often each background job runs, in seconds.
INTERVALS = {"collect": 3.0, "bionic": 10.0, "tunnel_local": 2.0, "tunnel_pi": 30.0}
UNAVAILABLE_TUNNEL = {"available": False,
                      "reason_th": "ส่วนดูทางเชื่อมใช้ไม่ได้ตอนนี้ (tunnel.py โหลดไม่ได้)"}
LOG_PATH = collect.DEFAULT_DB.parent / "live.log"
TZ_NAME = "Asia/Bangkok"
BANGKOK = collect.BANGKOK


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_error(path: Path, message: str) -> None:
    """Append a timestamped line to live.log. Never raises."""
    stamp = datetime.now(BANGKOK).strftime("%Y-%m-%d %H:%M:%S")
    collect._append_log(Path(path), f"[{stamp}] {message}")


# ---------------------------------------------------------------------------
# Bionic status (loaded models)
# ---------------------------------------------------------------------------

def parse_loaded_models(text: str) -> list[str]:
    """Return the ids of every loaded model instance in Bionic's /api/v1/models reply.

    Raises ValueError when the reply is not the expected JSON.
    """
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise ValueError("reply has no models list")
    loaded = []
    for model in data["models"]:
        if not isinstance(model, dict):
            continue
        for instance in model.get("loaded_instances") or []:
            if isinstance(instance, dict) and isinstance(instance.get("id"), str):
                loaded.append(instance["id"])
    return loaded


def fetch_models_text() -> str:
    """Ask Bionic for its model list. Raises on timeout or refusal."""
    with urllib.request.urlopen(BIONIC_MODELS_URL, timeout=BIONIC_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


class BionicStatus:
    """Keeps the last answer from Bionic. A failed check marks Bionic as down."""

    def __init__(self, fetch=None, clock=time.time) -> None:
        self._fetch = fetch or fetch_models_text
        self._clock = clock
        self._lock = threading.Lock()
        self._state = {"up": None, "loaded": [], "checked_ts": None, "error": None}

    def check(self) -> None:
        """Ask Bionic once and store the result. Never raises."""
        now = int(self._clock())
        try:
            loaded = parse_loaded_models(self._fetch())
            new = {"up": True, "loaded": loaded, "checked_ts": now, "error": None}
        except Exception as exc:  # any failure means "not answering" for the page
            new = {"up": False, "loaded": [], "checked_ts": now,
                   "error": f"{type(exc).__name__}: {exc}"}
        with self._lock:
            self._state = new

    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self._state)
            state["loaded"] = list(self._state["loaded"])
        return state


# ---------------------------------------------------------------------------
# Database reads for the page
# ---------------------------------------------------------------------------

def _empty_totals() -> dict:
    return {"calls": 0, "tokens": 0, "prompt": 0, "completion": 0, "errors": 0}


def _totals_from(row) -> dict:
    """Turn one (calls, prompt, completion, errors) aggregate row into a dict."""
    calls, prompt, completion, errors = row
    prompt, completion = int(prompt or 0), int(completion or 0)
    return {"calls": int(calls or 0), "tokens": prompt + completion,
            "prompt": prompt, "completion": completion, "errors": int(errors or 0)}


def _empty_parts() -> dict:
    return {
        "totals": {"hour": _empty_totals(), "today": _empty_totals(), "all": _empty_totals()},
        "per_minute": [0] * MINUTES,
        "recent": [],
        "db_error": None,
    }


def read_db_parts(db_path: Path, now: float) -> dict:
    """Read the numbers the page shows. Uses its own short-lived connection.

    A missing database gives empty numbers and is not created. A database
    error is reported in `db_error` and never raised.
    """
    parts = _empty_parts()
    db_path = Path(db_path)
    if not db_path.exists():
        return parts
    now_int = int(now)
    today_start = int(report._day_start(datetime.fromtimestamp(now_int, BANGKOK)).timestamp())
    minute_start = (now_int // 60) * 60
    window_start = minute_start - (MINUTES - 1) * 60
    try:
        con = sqlite3.connect(db_path, timeout=5)
        try:
            agg = ("SELECT COUNT(*), COALESCE(SUM(prompt_tokens), 0), "
                   "COALESCE(SUM(completion_tokens), 0), "
                   "COALESCE(SUM(CASE WHEN ok = 1 THEN 0 ELSE 1 END), 0) "
                   "FROM requests WHERE ts >= ?")
            parts["totals"] = {
                "hour": _totals_from(con.execute(agg, (now_int - 3600,)).fetchone()),
                "today": _totals_from(con.execute(agg, (today_start,)).fetchone()),
                "all": _totals_from(con.execute(agg, (0,)).fetchone()),
            }
            for ts, prompt, completion in con.execute(
                    "SELECT ts, prompt_tokens, completion_tokens FROM requests WHERE ts >= ?",
                    (window_start,)).fetchall():
                index = (ts - window_start) // 60
                if 0 <= index < MINUTES:
                    parts["per_minute"][index] += int(prompt or 0) + int(completion or 0)
            rows = con.execute(
                "SELECT ts, model, job, prompt_tokens, completion_tokens, reasoning_tokens, "
                "total_ms, ok FROM requests ORDER BY ts DESC, id DESC LIMIT ?",
                (RECENT_LIMIT,)).fetchall()
            parts["recent"] = [
                {"ts": ts, "model": model, "job": job,
                 "prompt": int(prompt or 0), "completion": int(completion or 0),
                 "reasoning": int(reasoning or 0), "total_ms": total_ms, "ok": bool(ok)}
                for ts, model, job, prompt, completion, reasoning, total_ms, ok in rows
            ]
        finally:
            con.close()
    except sqlite3.Error as exc:
        parts["db_error"] = f"{type(exc).__name__}: {exc}"
    return parts


def build_state(db_path: Path, tracker_snap: dict, bionic_snap: dict, now: float,
                tunnel_snap: dict | None = None) -> dict:
    """Assemble the JSON the page polls for."""
    parts = read_db_parts(db_path, now)
    now_int = int(now)
    minute_start = (now_int // 60) * 60
    return {
        "now": now_int,
        "server_id": SERVER_ID,
        "tz": TZ_NAME,
        "poll_ms": STATE_POLL_MS,
        "bionic": bionic_snap,
        "tunnel": tunnel_snap if tunnel_snap is not None else dict(UNAVAILABLE_TUNNEL),
        "in_flight": tracker_snap["in_flight"],
        "recent": parts["recent"],
        "totals": parts["totals"],
        "per_minute": parts["per_minute"],
        "minute_start": minute_start - (MINUTES - 1) * 60,
        "newest_log_ts": tracker_snap["newest_log_ts"],
        "db_error": parts["db_error"],
    }


# ---------------------------------------------------------------------------
# Scheduling and the idle exit
# ---------------------------------------------------------------------------

def idle_expired(last_seen: float, now: float, limit: float = IDLE_LIMIT_SECONDS) -> bool:
    """True when no page has asked for state for longer than `limit` seconds."""
    return now - last_seen > limit


def tick(now: float, due: dict, jobs: dict, log=None) -> dict:
    """Run every job whose time has come, and return the new due times.

    A failing job is logged and rescheduled; it never stops the other jobs.
    """
    new_due = dict(due)
    for name, job in jobs.items():
        if now < due.get(name, 0.0):
            continue
        try:
            job()
        except Exception as exc:
            message = f"{name} failed: {type(exc).__name__}: {exc}"
            if log is not None:
                log(message)
            else:
                log_error(LOG_PATH, message + "\n" + traceback.format_exc())
        new_due[name] = now + INTERVALS[name]
    return new_due


_running_lock = threading.Lock()
_running: set = set()


def start_once(fn, name: str, log) -> bool:
    """Run fn on its own thread unless a call with the same name is still running.

    Used for the slow SSH check, so that it never holds up the collector or the
    1-second log poll. Returns False when the earlier call has not finished yet.
    """
    with _running_lock:
        if name in _running:
            return False
        _running.add(name)

    def run():
        try:
            fn()
        except Exception as exc:
            log(f"{name} failed: {type(exc).__name__}: {exc}")
        finally:
            with _running_lock:
                _running.discard(name)

    threading.Thread(target=run, daemon=True).start()
    return True


def make_jobs(collect_fn, bionic: BionicStatus, tunnel, log) -> dict:
    """The named background jobs. The tunnel jobs exist only when the tunnel module loaded."""
    jobs = {"collect": collect_fn, "bionic": bionic.check}
    if tunnel is not None:
        jobs["tunnel_local"] = tunnel.check_local
        jobs["tunnel_pi"] = lambda: start_once(tunnel.check_pi, "tunnel_pi", log)
    return jobs


def load_tunnel_status(factory=None):
    """Create the tunnel status reader, or None when tunnel.py cannot be loaded (e.g. no psutil)."""
    make = factory or (lambda: __import__("tunnel").TunnelStatus())
    try:
        return make()
    except Exception:
        return None


def background_loop(stop: threading.Event, tracker, bionic: BionicStatus, log,
                    tunnel=None) -> None:
    """Poll the log every second and run the background jobs on schedule."""
    jobs = make_jobs(lambda: collect.run(collect.DEFAULT_LOG_ROOT, collect.DEFAULT_DB),
                     bionic, tunnel, log)
    due = {name: 0.0 for name in jobs}
    while not stop.is_set():
        try:
            tracker.poll()
        except Exception as exc:
            log(f"tracker failed: {type(exc).__name__}: {exc}")
        due = tick(time.monotonic(), due, jobs, log)
        stop.wait(1.0)


def watch_idle(app: "App", server, stop: threading.Event, limit: float = IDLE_LIMIT_SECONDS,
               interval: float = IDLE_CHECK_SECONDS, log=None) -> None:
    """Shut the server down when the page has not asked for state for `limit` seconds."""
    log = log or (lambda message: log_error(LOG_PATH, message))
    while not stop.wait(interval):
        if idle_expired(app.last_seen, app.clock(), limit):
            log("no page open for the idle limit; stopping")
            server.shutdown()
            return


# ---------------------------------------------------------------------------
# App and HTTP server
# ---------------------------------------------------------------------------

class App:
    """Everything the request handlers need. Holds the time of the last state request."""

    def __init__(self, db_path: Path, report_out: Path, tracker, bionic,
                 clock=time.time, tunnel=None) -> None:
        self.db_path = Path(db_path)
        self.report_out = Path(report_out)
        self.tracker = tracker
        self.bionic = bionic
        self.tunnel = tunnel
        self.clock = clock
        self.last_seen = clock()
        self._report_lock = threading.Lock()

    def state(self) -> dict:
        """Current state for /api/state. Each call counts as a visit."""
        self.last_seen = self.clock()
        return build_state(self.db_path, self.tracker.snapshot(), self.bionic.snapshot(),
                           self.clock(), tunnel_snap=self._tunnel_snapshot())

    def _tunnel_snapshot(self) -> dict:
        """The tunnel part of the state. A failure here is shown, never raised."""
        if self.tunnel is None:
            return dict(UNAVAILABLE_TUNNEL)
        try:
            return {**self.tunnel.snapshot(), "available": True}
        except Exception as exc:
            return {"available": False,
                    "reason_th": f"อ่านสถานะทางเชื่อมไม่ได้: {type(exc).__name__}: {exc}"}

    def report_html(self) -> bytes:
        """Rebuild the static report and return its bytes. One rebuild at a time."""
        with self._report_lock:
            report.write_report(self.db_path, self.report_out,
                                now=datetime.fromtimestamp(self.clock(), BANGKOK))
            return self.report_out.read_bytes()


def host_allowed(host_header, port: int) -> bool:
    """True only for the loopback names this server answers to (blocks DNS rebinding)."""
    return host_header in (f"127.0.0.1:{port}", f"localhost:{port}")


def write_body(wfile, body: bytes) -> bool:
    """Write the reply body. False when the browser went away (tab closed mid-reply)."""
    try:
        wfile.write(body)
        return True
    except ConnectionError:
        # Windows raises ConnectionAbortedError when a tab closes; that is not a server error.
        return False


class _Handler(BaseHTTPRequestHandler):
    server_version = "BionicUsageLive"

    def do_GET(self) -> None:  # noqa: N802 - name required by http.server
        app = self.server.app
        path = self.path.split("?", 1)[0]
        if not host_allowed(self.headers.get("Host"), self.server.server_address[1]):
            self._send(403, "text/plain; charset=utf-8", b"forbidden")
            return
        try:
            if path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
            elif path == "/api/state":
                body = json.dumps(app.state(), ensure_ascii=False).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", body)
            elif path == "/report":
                self._send(200, "text/html; charset=utf-8", app.report_html())
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found")
        except Exception:
            log_error(LOG_PATH, "request " + path + " failed\n" + traceback.format_exc())
            self._send(500, "text/plain; charset=utf-8", b"error, see live.log")

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        except ConnectionError:
            return  # the browser went away before the reply started
        write_body(self.wfile, body)

    def log_message(self, format, *args) -> None:  # noqa: A002 - base class name
        # pythonw has no stderr, so the default request log is turned off.
        return


class LiveServer(ThreadingHTTPServer):
    """HTTP server bound to one address. A second bind to the same port must fail."""

    allow_reuse_address = False  # on Windows, SO_REUSEADDR would let two servers share a port
    daemon_threads = True

    def __init__(self, address, handler, app: App) -> None:
        self.app = app
        super().__init__(address, handler)


def make_server(app: App, port: int) -> LiveServer:
    """Bind the server to 127.0.0.1. Raises OSError when the port is taken."""
    return LiveServer((HOST, port), _Handler, app)


def port_from_env(env) -> int:
    """The port from BIONIC_USAGE_PORT, or the default when it is missing or odd."""
    raw = env.get(PORT_ENV, "")
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception as exc:
        log_error(LOG_PATH, f"could not open browser: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None, opener=None, log=None) -> int:
    """Start the server, or open the page of a server that is already running."""
    parser = argparse.ArgumentParser(description="Live Bionic usage page.")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument("--port", type=int, default=None,
                        help=f"port (default: {PORT_ENV} or {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    port = args.port if args.port is not None else port_from_env(os.environ)
    opener = opener or _open_browser
    log = log or (lambda message: log_error(LOG_PATH, message))
    url = f"http://{HOST}:{port}/"

    tracker = live_tail.LiveTracker(collect.DEFAULT_LOG_ROOT, log=log)
    bionic = BionicStatus()
    tunnel = load_tunnel_status()
    app = App(db_path=collect.DEFAULT_DB, report_out=report.DEFAULT_OUT,
              tracker=tracker, bionic=bionic, tunnel=tunnel)
    try:
        server = make_server(app, port)
    except OSError as exc:
        log(f"port {port} is busy ({exc}); opening the page that is already running")
        if not args.no_open:
            opener(url)
        return 0

    stop = threading.Event()
    threading.Thread(target=background_loop, args=(stop, tracker, bionic, log, tunnel),
                     daemon=True).start()
    threading.Thread(target=watch_idle, args=(app, server, stop), daemon=True).start()
    log(f"live page on {url}")
    if not args.no_open:
        opener(url)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
