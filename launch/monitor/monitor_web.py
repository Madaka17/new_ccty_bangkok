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
