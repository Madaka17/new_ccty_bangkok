"""Public-exposure guard: operator-only control endpoints, chat rate limit, forwarded-IP handling."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import access_guard
from backend.core.access_guard import _is_trusted_ip, _Window, client_ip


def _req(peer, server="127.0.0.1", **headers):
    return SimpleNamespace(client=SimpleNamespace(host=peer), scope={"server": (server, 8000)},
                           headers={k.replace("_", "-"): v for k, v in headers.items()})


def test_trusted_networks():
    for ip in ("127.0.0.1", "192.168.1.20", "10.1.2.3", "100.101.102.103"):
        assert _is_trusted_ip(ip)
    for ip in ("8.8.8.8", "203.0.113.5", "not-an-ip", ""):
        assert not _is_trusted_ip(ip)


def test_direct_peer_ignores_forwarded_header():
    assert client_ip(_req("203.0.113.5", x_forwarded_for="127.0.0.1")) == "203.0.113.5"


def test_proxy_uses_forwarded_client():
    assert client_ip(_req("127.0.0.1", x_forwarded_for="203.0.113.5")) == "203.0.113.5"


def test_spoofed_forwarded_entry_is_not_trusted():
    # The local proxy appends the real client to whatever the client sent, so only the last entry is real
    assert client_ip(_req("127.0.0.1", x_forwarded_for="127.0.0.1, 203.0.113.5")) == "203.0.113.5"


def test_cloudflare_tunnel_uses_cf_connecting_ip():
    # cloudflared connects to 127.0.0.2; Cloudflare puts the visitor's address in CF-Connecting-IP
    r = _req("127.0.0.1", server="127.0.0.2", cf_connecting_ip="203.0.113.7", x_forwarded_for="127.0.0.1")
    assert client_ip(r) == "203.0.113.7"


def test_cloudflare_tunnel_without_header_is_not_trusted():
    ip = client_ip(_req("127.0.0.1", server="127.0.0.2"))
    assert not _is_trusted_ip(ip)


def test_funnel_ignores_spoofed_cf_connecting_ip():
    # Tailscale Funnel connects to 127.0.0.1 and passes on any CF-Connecting-IP the visitor sent
    r = _req("127.0.0.1", cf_connecting_ip="127.0.0.1", x_forwarded_for="203.0.113.5")
    assert client_ip(r) == "203.0.113.5"


def test_window_limits_per_key():
    w = _Window(2, 60)
    assert w.allow("a") and w.allow("a")
    assert not w.allow("a")
    assert w.allow("b")


def test_window_zero_means_unlimited():
    w = _Window(0, 60)
    assert all(w.allow("a") for _ in range(100))


def _app():
    app = FastAPI()
    app.middleware("http")(access_guard.guard)

    @app.get("/")
    def page():
        from fastapi.responses import HTMLResponse
        return HTMLResponse("<html></html>")

    @app.get("/api/data")
    def data():
        return {"ok": True}

    @app.post("/api/ai/set_fps")
    def control():
        return {"ok": True}

    @app.post("/api/chat")
    def chat():
        return {"ok": True}

    @app.post("/api/flood/parking/{sid}/full")
    def parking_full(sid: str):
        return {"ok": True}

    @app.post("/api/flood/parking/{sid}/other")
    def parking_other(sid: str):
        return {"ok": True}

    return app


def test_control_endpoint_blocked_for_strangers():
    # TestClient's peer is "testclient", which is not a trusted network
    assert TestClient(_app()).post("/api/ai/set_fps").status_code == 403


def test_control_endpoint_open_with_admin_token(monkeypatch):
    monkeypatch.setattr(access_guard, "ADMIN_TOKEN", "secret")
    r = TestClient(_app()).post("/api/ai/set_fps", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200


SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


def _visitor(monkeypatch, tmp_path):
    """A browser from outside that has opened the page (so it holds the page-session cookie)."""
    monkeypatch.setattr(access_guard, "SESSION_SECRET_FILE", str(tmp_path / "secret"))
    monkeypatch.setattr(access_guard, "_secret", None)
    c = TestClient(_app())
    assert c.get("/").status_code == 200
    return c


def test_chat_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setattr(access_guard, "chat_min", _Window(2, 60))
    monkeypatch.setattr(access_guard, "chat_day", _Window(100, 86400))
    c = _visitor(monkeypatch, tmp_path)
    codes = [c.post("/api/chat", json={}, headers=SAME_ORIGIN).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_chat_body_size_capped():
    r = TestClient(_app()).post("/api/chat", content=b"x" * (access_guard.CHAT_MAX_BODY + 1),
                                headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_api_needs_page_session(monkeypatch, tmp_path):
    c = _visitor(monkeypatch, tmp_path)
    assert c.cookies.get(access_guard.SESSION_COOKIE)
    assert c.get("/api/data", headers=SAME_ORIGIN).status_code == 200
    # a script that fakes the browser header but never loaded the page
    bare = TestClient(_app())
    assert bare.get("/api/data", headers=SAME_ORIGIN).status_code == 403
    # a forged or expired cookie
    bare.cookies.set(access_guard.SESSION_COOKIE, "1.deadbeef")
    assert bare.get("/api/data", headers=SAME_ORIGIN).status_code == 403


def test_session_age_rejects_old_and_forged(monkeypatch, tmp_path):
    monkeypatch.setattr(access_guard, "SESSION_SECRET_FILE", str(tmp_path / "secret"))
    monkeypatch.setattr(access_guard, "_secret", None)
    good = f"1000.{access_guard._sign(1000)}"
    assert access_guard.session_age(good, now=1060) == 60
    assert access_guard.session_age(good, now=1000 + access_guard.SESSION_MAX_AGE + 1) is None
    assert access_guard.session_age("1000.0000", now=1060) is None
    assert access_guard.session_age(None) is None


def test_parking_full_is_public_and_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setattr(access_guard, "parking_hour", _Window(2, 3600))
    c = _visitor(monkeypatch, tmp_path)
    codes = [c.post("/api/flood/parking/a/full", headers=SAME_ORIGIN).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    # only the exact "full" path is public
    assert c.post("/api/flood/parking/a/other", headers=SAME_ORIGIN).status_code == 403
