"""Live attack view on this PC, fed by ONE read-only ssh connection to the Pi.

    python -m launch.security_check.live [--port 8770] [--no-open] [--target production|test]

production: ssh to the Pi and run `python -m backend.core.security_stream` there (web + ssh events).
test:       run the same stream module locally against instances/test (no ssh, no SSH events).
Serves http://127.0.0.1:<port>/ (page), /state (JSON), /events (Server-Sent Events), /health.
Binds 127.0.0.1 only and rejects other Host headers. Exits by itself when nobody watches.
"""
import argparse
import json
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import alerts as alerts_mod
from . import collect, geo, rules
from .live_page import build_page

ROOT = collect.ROOT
DEFAULT_PORT = 8770
LOG_PATH = os.path.join(ROOT, "local", "logs", "security_live.log")
TEST_INSTANCE = os.path.join(ROOT, "instances", "test")
LAN_PREFIX = "192.168.1."
UNKNOWN_TH = "ไม่ทราบประเทศ"
OWNER_REFRESH = 600
BASELINE_REFRESH = 300
BACKOFF_MIN, BACKOFF_MAX = 2, 60
HEARTBEAT = 15
IDLE_AFTER_CLIENT = 90
IDLE_NO_CLIENT = 120
KEEP_EVENTS = 200
ROLLING = 3600

SSH_LABELS = {"failed": "เดารหัส SSH", "accepted": "เข้า SSH สำเร็จ", "invalid": "ลองชื่อผู้ใช้ SSH ที่ไม่มี"}

log = logging.getLogger("security_live")


def setup_logging(path=LOG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    h = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.setLevel(logging.INFO)
    log.addHandler(h)
    logging.getLogger("security_live.alerts").setLevel(logging.INFO)
    logging.getLogger("security_live.alerts").addHandler(h)


def _is_lan(ip):
    import ipaddress
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if a.is_loopback:
        return True
    return a.version == 4 and str(a).startswith(LAN_PREFIX)


class LiveState:
    """All mutable view state. Thread safe. `clock` is injectable for tests."""

    def __init__(self, target="production", clock=time.time, alerter=None):
        self.target = target
        self.clock = clock
        self.alerter = alerter
        self.lock = threading.RLock()
        self.owners = []
        self.started = clock()
        self.since_start = 0
        self.rolling = deque()          # (ts, is_ssh_guess)
        self.countries = {}             # cc -> n
        self.events = deque(maxlen=KEEP_EVENTS)
        self.alert_log = deque(maxlen=20)
        self.status = "reconnecting"
        self.failures = 0
        self.last_event = None
        self.baseline = None
        self.clients = []               # queues
        self.ever_client = False
        self.last_disconnect = None

    # ---- owners / enrichment ----------------------------------------
    def set_owners(self, owners):
        with self.lock:
            self.owners = [o for o in owners if o]

    def is_owner(self, ip):
        with self.lock:
            owners = list(self.owners)
        return _is_lan(ip) or rules._same_home(ip, owners)

    def enrich(self, raw):
        ev = dict(raw)
        t = ev.get("type")
        ip = str(ev.get("ip", ""))
        ev["owner"] = self.is_owner(ip)
        cc = geo.lookup(ip) if ip else None
        ev["cc"] = cc
        ev["country"] = geo.country_name(cc) if cc else None
        ll = geo.centroid(cc) if cc else None
        ev["lat"], ev["lon"] = (ll[0], ll[1]) if ll else (None, None)
        if t == "ssh":
            ev["label_th"] = SSH_LABELS.get(ev.get("event"), "SSH")
        elif ev.get("kind") == "self_check":
            ev["label_th"] = "ตรวจตัวเอง"
        else:
            ev["label_th"] = rules.KIND_TH.get(ev.get("kind"), ev.get("kind") or "")
        return ev

    # ---- ingest ------------------------------------------------------
    def ingest(self, raw):
        """Feed one decoded stream line. Returns the broadcast messages (list of dicts)."""
        t = raw.get("type")
        now = self.clock()
        if t == "hello":
            self.set_status("connected")
            return []
        if t == "ping":
            with self.lock:
                self.last_event = now
            return []
        if t not in ("web", "ssh"):
            return []
        ev = self.enrich(raw)
        counted = not ev["owner"] and ev.get("kind") != "self_check"
        out = [ev]
        with self.lock:
            self.last_event = now
            self.events.append(ev)
            if counted:
                self.since_start += 1
                is_guess = t == "ssh" and ev.get("event") in ("failed", "invalid")
                self.rolling.append((now, is_guess))
                key = ev["cc"] or "??"
                self.countries[key] = self.countries.get(key, 0) + 1
            self._trim(now)
        if self.alerter:
            for a in self.alerter.observe(ev):
                msg = {k: v for k, v in a.items() if k != "rule"}
                msg["ts"] = datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds")
                with self.lock:
                    self.alert_log.append(msg)
                out.append(msg)
        return out

    def _trim(self, now):
        while self.rolling and now - self.rolling[0][0] > ROLLING:
            self.rolling.popleft()

    def set_status(self, status):
        with self.lock:
            changed = status != self.status
            self.status = status
            if status == "connected":
                self.failures = 0
        if changed:
            self.broadcast({"type": "status", "status": status})

    def note_failure(self):
        with self.lock:
            self.failures += 1
        self.set_status("reconnecting")

    def set_baseline(self, summary, owners):
        """30-day count of blocked requests, owner-excluded like the report. None when unknown."""
        if not isinstance(summary, dict) or summary.get("_error"):
            return
        raw = summary.get("total") or 0
        own = min(rules.owner_total(summary.get("top_ips") or [], owners), raw)
        with self.lock:
            self.baseline = raw - own

    # ---- snapshot / fan-out -----------------------------------------
    def snapshot(self):
        now = self.clock()
        with self.lock:
            self._trim(now)
            countries = []
            for cc, n in sorted(self.countries.items(), key=lambda kv: -kv[1]):
                ll = geo.centroid(cc) if cc != "??" else None
                countries.append({"cc": None if cc == "??" else cc,
                                  "country": geo.country_name(cc) if cc != "??" else UNKNOWN_TH,
                                  "n": n, "lat": ll[0] if ll else None, "lon": ll[1] if ll else None})
            return {
                "target": self.target,
                "status": self.status,
                "failures": self.failures,
                "line": self.alerter.line_status() if self.alerter else "off",
                "started": datetime.fromtimestamp(self.started).astimezone().isoformat(timespec="seconds"),
                "last_event": (datetime.fromtimestamp(self.last_event).astimezone().isoformat(timespec="seconds")
                               if self.last_event else None),
                "since_start": self.since_start,
                "last60": len(self.rolling),
                "ssh60": sum(1 for _, g in self.rolling if g),
                "baseline30": self.baseline,
                "countries": countries,
                "events": list(self.events)[::-1],
                "alerts": list(self.alert_log)[::-1],
                "owners": len(self.owners),
            }

    def add_client(self):
        q = queue.Queue(maxsize=1000)
        with self.lock:
            self.clients.append(q)
            self.ever_client = True
        return q

    def remove_client(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)
            if not self.clients:
                self.last_disconnect = self.clock()

    def broadcast(self, msg):
        with self.lock:
            qs = list(self.clients)
        for q in qs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def idle_expired(self):
        with self.lock:
            now = self.clock()
            if self.clients:
                return False
            if self.last_disconnect is not None:
                return now - self.last_disconnect > IDLE_AFTER_CLIENT
            return now - self.started > IDLE_NO_CLIENT


# ---- the stream process ----------------------------------------------
def _python():
    p = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    return p if os.path.exists(p) else sys.executable


def build_stream_cmd(target):
    """(argv, env, cwd) of the process whose stdout is the JSON line stream."""
    if target == "test":
        env = dict(os.environ, INSTANCE_DIR=TEST_INSTANCE, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        return [_python(), "-u", "-m", "backend.core.security_stream"], env, ROOT
    pi = collect.PI
    repo = pi["repo"]
    remote = (f"cd {repo} && INSTANCE_DIR={repo}/instances/production "
              ".venv/bin/python -u -m backend.core.security_stream")
    argv = ["ssh", "-i", pi["key"], "-o", "BatchMode=yes", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=10", f"{pi['user']}@{pi['host']}", remote]
    return argv, None, None


class StreamRunner:
    def __init__(self, target, on_message, on_down, stop):
        self.target, self.on_message, self.on_down, self.stop = target, on_message, on_down, stop
        self.proc = None

    def run(self):
        backoff = BACKOFF_MIN
        while not self.stop.is_set():
            argv, env, cwd = build_stream_cmd(self.target)
            got_hello = False
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self.proc = subprocess.Popen(argv, env=env, cwd=cwd, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                             text=True, encoding="utf-8", errors="replace", creationflags=flags)
                last_err = []

                def drain(f=self.proc.stderr, keep=last_err):
                    for ln in f:
                        if ln.strip():
                            keep[:] = [ln.strip()[:200]]
                threading.Thread(target=drain, daemon=True).start()
                for line in self.proc.stdout:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == "hello":
                        got_hello = True
                        backoff = BACKOFF_MIN
                    self.on_message(msg)
                    if self.stop.is_set():
                        break
                self.proc.wait(timeout=5)
                rc = self.proc.returncode
                tail = last_err[0] if last_err else ""
                log.info("stream exit code %s, last stderr line: %s", rc, tail or "-")
            except Exception as e:
                log.warning("stream error (%s)", type(e).__name__)
            finally:
                self.kill()
            if self.stop.is_set():
                return
            log.info("stream ended (hello=%s), retry in %ss", got_hello, backoff)
            self.on_down()
            self.stop.wait(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    def kill(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass


# ---- HTTP ---------------------------------------------------------------
def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _host_ok(self):
            host = (self.headers.get("Host") or "").strip().lower()
            return host in (f"127.0.0.1:{app.port}", f"localhost:{app.port}")

        def _send(self, code, ctype, body):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._host_ok():
                self._send(403, "text/plain; charset=utf-8", "forbidden")
                return
            path = self.path.split("?", 1)[0]
            try:
                if path == "/health":
                    self._send(200, "application/json", json.dumps({"ok": True, "app": "bkk-security-live"}))
                elif path == "/state":
                    self._send(200, "application/json; charset=utf-8",
                               json.dumps(app.state.snapshot(), ensure_ascii=False))
                elif path == "/events":
                    self._events()
                elif path == "/":
                    self._send(200, "text/html; charset=utf-8", app.page())
                else:
                    self._send(404, "text/plain; charset=utf-8", "not found")
            except (BrokenPipeError, ConnectionError, OSError):
                pass

        def _events(self):
            q = app.state.add_client()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while not app.stop.is_set():
                    try:
                        msg = q.get(timeout=HEARTBEAT)
                        chunk = "data: " + json.dumps(msg, ensure_ascii=False) + "\n\n"
                    except queue.Empty:
                        chunk = ": hb\n\n"
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            finally:
                app.state.remove_client(q)

    return Handler


class LiveApp:
    def __init__(self, port=DEFAULT_PORT, target="production", alerter=None, start_stream=True):
        self.target = target
        self.stop = threading.Event()
        self.state = LiveState(target=target, alerter=alerter)
        self.start_stream = start_stream
        self.server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self))
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.runner = None
        self._page = None

    def page(self):
        if self._page is None:
            self._page = build_page(self.target)
        return self._page

    def handle_message(self, msg):
        for out in self.state.ingest(msg):
            self.state.broadcast(out)

    def _owners(self):
        owners = [ip for ip in (collect.public_ip(), collect.public_ip_v4()) if ip]
        self.state.set_owners(owners)
        return owners

    def _bootstrap(self):
        try:
            self._owners()
        except Exception as e:
            log.warning("owner lookup failed (%s)", type(e).__name__)
        if self.start_stream and not self.stop.is_set():
            self.runner = StreamRunner(self.target, self.handle_message, self.state.note_failure, self.stop)
            threading.Thread(target=self.runner.run, name="stream", daemon=True).start()
        while not self.stop.is_set():
            self._refresh_baseline()
            if self.stop.wait(BASELINE_REFRESH):
                return

    def _owner_loop(self):
        while not self.stop.wait(OWNER_REFRESH):
            try:
                self._owners()
            except Exception:
                pass

    def _refresh_baseline(self):
        try:
            if self.target == "test":
                s = collect.local_attack_summary(TEST_INSTANCE, 30)
            else:
                s = collect.pi_attack_summary(30)
            self.state.set_baseline(s, list(self.state.owners))
        except Exception as e:
            log.warning("baseline failed (%s)", type(e).__name__)

    def _idle_loop(self):
        while not self.stop.wait(5):
            if self.state.idle_expired():
                log.info("no viewers, exiting")
                self.shutdown()
                return

    def serve(self):
        for fn, name in ((self._bootstrap, "bootstrap"), (self._owner_loop, "owners"), (self._idle_loop, "idle")):
            threading.Thread(target=fn, name=name, daemon=True).start()
        try:
            self.server.serve_forever(poll_interval=0.5)
        finally:
            self.stop.set()
            if self.runner:
                self.runner.kill()
            self.server.server_close()

    def shutdown(self):
        self.stop.set()
        if self.runner:
            self.runner.kill()
        threading.Thread(target=self.server.shutdown, daemon=True).start()


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as r:
            return json.loads(r.read(200)).get("app") == "bkk-security-live"
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--target", choices=("production", "test"), default="production")
    a = ap.parse_args(argv)
    url = f"http://127.0.0.1:{a.port}/"
    if already_running(a.port):
        if not a.no_open:
            webbrowser.open(url)
        return 0
    setup_logging()
    try:
        app = LiveApp(a.port, a.target, alerter=alerts_mod.make_alerter())
    except OSError as e:
        log.error("cannot bind port %s (%s)", a.port, type(e).__name__)
        return 1
    log.info("live view started: target=%s port=%s line=%s", a.target, a.port, app.state.alerter.line_status())
    if not a.no_open:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    app.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
