"""Public-exposure guard: operator-only control endpoints, chat rate limit, forwarded-IP handling."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import access_guard
from backend.core.access_guard import _is_trusted_ip, _Window, client_ip


def _req(peer, **headers):
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers={k.replace("_", "-"): v for k, v in headers.items()})


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

    @app.post("/api/ai/set_fps")
    def control():
        return {"ok": True}

    @app.post("/api/chat")
    def chat():
        return {"ok": True}

    return app


def test_control_endpoint_blocked_for_strangers():
    # TestClient's peer is "testclient", which is not a trusted network
    assert TestClient(_app()).post("/api/ai/set_fps").status_code == 403


def test_control_endpoint_open_with_admin_token(monkeypatch):
    monkeypatch.setattr(access_guard, "ADMIN_TOKEN", "secret")
    r = TestClient(_app()).post("/api/ai/set_fps", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200


def test_chat_rate_limited(monkeypatch):
    monkeypatch.setattr(access_guard, "chat_min", _Window(2, 60))
    monkeypatch.setattr(access_guard, "chat_day", _Window(100, 86400))
    c = TestClient(_app())
    codes = [c.post("/api/chat", json={}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_chat_body_size_capped():
    r = TestClient(_app()).post("/api/chat", content=b"x" * (access_guard.CHAT_MAX_BODY + 1),
                                headers={"content-type": "application/json"})
    assert r.status_code == 413
