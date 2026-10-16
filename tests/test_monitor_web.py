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


def test_negative_content_length_is_refused_fast(srv):
    import http.client
    import time
    _, base = srv
    conn = http.client.HTTPConnection(base.split("//")[1], timeout=8)
    conn.putrequest("POST", "/api/status")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", "-1")
    conn.endheaders(b"[]")
    t = time.time()
    resp = conn.getresponse()
    assert resp.status == 400 and json.loads(resp.read())["error"] == "bad length"
    assert time.time() - t < 5
    conn.close()


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
