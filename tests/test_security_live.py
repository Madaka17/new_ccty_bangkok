import http.client
import json
import threading

import pytest

from launch.security_check import alerts, geo, live


class Clock:
    def __init__(self, t=1.78e9):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def fake_geo(monkeypatch):
    table = {"5.5.5.5": "RU", "6.6.6.6": "CN"}
    monkeypatch.setattr(geo, "lookup", lambda ip: table.get(ip))
    monkeypatch.setattr(geo, "country_name", lambda cc: {"RU": "Russia", "CN": "China"}.get(cc, cc))
    monkeypatch.setattr(geo, "centroid", lambda cc: {"RU": (60.0, 100.0), "CN": (35.0, 105.0)}.get(cc))


def web(ip, kind="probe", path="/.env"):
    return {"type": "web", "ts": "t", "kind": kind, "ip": ip, "path": path, "method": "GET"}


def ssh(ip, event="failed"):
    return {"type": "ssh", "ts": "t", "pid": "1", "event": event, "method": "password", "user": "root", "ip": ip}


def mk(alerter=None):
    st = live.LiveState(clock=Clock(), alerter=alerter)
    st.set_owners(["203.0.113.7"])
    return st


def test_enrich_fields_and_labels():
    st = mk()
    e = st.enrich(web("5.5.5.5"))
    assert (e["owner"], e["cc"], e["country"], e["lat"], e["lon"]) == (False, "RU", "Russia", 60.0, 100.0)
    assert e["label_th"] == "สแกนหาช่องโหว่"
    e = st.enrich(web("9.9.9.9"))
    assert e["cc"] is None and e["country"] is None and e["lat"] is None
    assert st.enrich(ssh("6.6.6.6", "failed"))["label_th"] == "เดารหัส SSH"
    assert st.enrich(ssh("6.6.6.6", "accepted"))["label_th"] == "เข้า SSH สำเร็จ"
    assert st.enrich(ssh("6.6.6.6", "invalid"))["label_th"] == "ลองชื่อผู้ใช้ SSH ที่ไม่มี"


def test_owner_detection_lan_loopback_and_public():
    st = mk()
    assert st.is_owner("192.168.1.50") and st.is_owner("127.0.0.1") and st.is_owner("203.0.113.7")
    assert not st.is_owner("192.168.2.50") and not st.is_owner("5.5.5.5")
    st.set_owners(["2001:db8:1:2::5"])
    assert st.is_owner("2001:db8:1:2:aaaa::1")   # same /64


def test_counters_exclude_owner_and_self_check():
    st = mk()
    for m in (web("5.5.5.5"), web("5.5.5.5"), web("203.0.113.7"), web("5.5.5.5", kind="self_check"),
              ssh("6.6.6.6"), ssh("6.6.6.6", "accepted"), ssh("192.168.1.9")):
        st.ingest(m)
    s = st.snapshot()
    assert s["since_start"] == 4 and s["last60"] == 4 and s["ssh60"] == 1
    assert {c["cc"]: c["n"] for c in s["countries"]} == {"RU": 2, "CN": 2}
    assert len(s["events"]) == 7           # feed keeps everything, the page filters
    assert s["events"][0]["ip"] == "192.168.1.9"   # newest first


def test_unknown_country_counted_separately():
    st = mk()
    st.ingest(web("9.9.9.9"))
    c = st.snapshot()["countries"][0]
    assert c["cc"] is None and c["country"] == "ไม่ทราบประเทศ"


def test_rolling_window_drops_old():
    clock = Clock()
    st = live.LiveState(clock=clock)
    st.ingest(web("5.5.5.5"))
    clock.t += 3601
    s = st.snapshot()
    assert s["last60"] == 0 and s["since_start"] == 1


def test_last_200_events_kept():
    st = mk()
    for i in range(250):
        st.ingest(web("5.5.5.5", path=f"/{i}"))
    ev = st.snapshot()["events"]
    assert len(ev) == 200 and ev[0]["path"] == "/249"


def test_status_hello_and_failure():
    st = mk()
    assert st.snapshot()["status"] == "reconnecting"
    st.ingest({"type": "hello", "ts": "t"})
    assert st.snapshot()["status"] == "connected"
    st.note_failure()
    s = st.snapshot()
    assert s["status"] == "reconnecting" and s["failures"] == 1
    st.ingest({"type": "hello", "ts": "t"})
    assert st.snapshot()["failures"] == 0


def test_baseline_excludes_owner():
    st = mk()
    st.set_baseline({"total": 100, "top_ips": [{"ip": "203.0.113.7", "n": 30}, {"ip": "5.5.5.5", "n": 70}]},
                    ["203.0.113.7"])
    assert st.snapshot()["baseline30"] == 70
    st.set_baseline({"_error": "not_deployed"}, [])
    assert st.snapshot()["baseline30"] == 70   # unchanged


def test_alert_goes_to_page_even_when_line_off(tmp_path):
    al = alerts.Alerter(sender=None, clock=Clock(), state_path=str(tmp_path / "s.json"), sync=True)
    st = mk(al)
    out = st.ingest(ssh("6.6.6.6", "accepted"))
    assert [m["type"] for m in out] == ["ssh", "alert"]
    s = st.snapshot()
    assert s["line"] == "off" and s["alerts"][0]["level"] == "critical"


def test_idle_rules():
    clock = Clock()
    st = live.LiveState(clock=clock)
    assert not st.idle_expired()
    clock.t += 121
    assert st.idle_expired()            # nobody ever came
    q = st.add_client()
    assert not st.idle_expired()
    st.remove_client(q)
    clock.t += 89
    assert not st.idle_expired()
    clock.t += 2
    assert st.idle_expired()


def test_ssh_command_is_read_only_stream():
    argv, env, cwd = live.build_stream_cmd("production")
    assert argv[0] == "ssh" and "BatchMode=yes" in argv and "ServerAliveInterval=15" in argv
    assert "ServerAliveCountMax=3" in argv
    assert argv[-1].endswith("-u -m backend.core.security_stream")
    assert "test@192.168.1.109" in argv
    argv, env, cwd = live.build_stream_cmd("test")
    assert argv[0] != "ssh" and env["INSTANCE_DIR"].endswith("test")


# ---- HTTP ----------------------------------------------------------------
@pytest.fixture()
def server():
    app = live.LiveApp(port=0, target="test", alerter=None, start_stream=False)
    t = threading.Thread(target=app.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    t.start()
    yield app
    app.stop.set()
    app.server.shutdown()
    app.server.server_close()


def get(app, path, host=None):
    c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=5)
    c.request("GET", path, headers={"Host": host or f"127.0.0.1:{app.port}"})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, body


def test_http_health_state_page(server):
    code, body = get(server, "/health")
    assert code == 200 and json.loads(body)["app"] == "bkk-security-live"
    code, body = get(server, "/state")
    assert code == 200 and json.loads(body)["status"] == "reconnecting"
    assert get(server, "/")[0] == 200
    assert get(server, "/nope")[0] == 404


def test_http_rejects_foreign_host(server):
    assert get(server, "/state", host="evil.example")[0] == 403
    assert get(server, "/health", host=f"evil.example:{server.port}")[0] == 403
    assert get(server, "/health", host=f"localhost:{server.port}")[0] == 200


def test_sse_delivers_events(server):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    c.request("GET", "/events", headers={"Host": f"127.0.0.1:{server.port}"})
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type") == "text/event-stream"
    assert r.fp.readline().startswith(b": connected")
    r.fp.readline()
    # wait for the client queue to exist, then push an event through the real path
    for _ in range(50):
        if server.state.clients:
            break
        threading.Event().wait(0.05)
    server.handle_message(web("5.5.5.5"))
    line = r.fp.readline().decode()
    assert line.startswith("data: ")
    ev = json.loads(line[6:])
    assert ev["ip"] == "5.5.5.5" and ev["cc"] == "RU"
    c.close()


# ---- Part 3: the page ----------------------------------------------------
import re

from launch.security_check import live_page


def test_page_contract():
    html = live_page.build_page("production")
    assert "prefers-reduced-motion" in html
    assert 'http-equiv="Content-Security-Policy"' in html and "connect-src 'self'" in html
    assert "BKK Security Live" in html and "ซ่อนของเจ้าของ" in html
    assert not re.search(r"(?:src|href)=[\"']?https?:", html)
    assert not re.search(r"url\(\s*[\"']?https?:", html)
    js = html.split("<script>")[1]
    assert "https://" not in js and "http://" not in js.replace("http://www.w3.org/2000/svg", "")
    assert "innerHTML" not in html and "insertAdjacentHTML" not in html and "document.write" not in html
    for field in ("ev.label_th", "ev.ip", "ev.path", "ev.user", "a.text"):
        assert field in js
    assert "textContent" in js
    assert "MAXROW=100" in js and "MAXARC=30" in js
    assert "__W__" not in html and "__BLAT__" not in html


def test_page_served_and_host_guard():
    app = live.LiveApp(port=0, start_stream=False)
    threading.Thread(target=app.server.serve_forever, daemon=True).start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", app.port, timeout=3)
        c.request("GET", "/", headers={"Host": f"127.0.0.1:{app.port}"})
        r = c.getresponse()
        body = r.read().decode("utf-8")
        assert r.status == 200 and "text/html" in r.getheader("Content-Type")
        assert "EventSource('/events')" in body
    finally:
        app.server.shutdown()
        app.server.server_close()
