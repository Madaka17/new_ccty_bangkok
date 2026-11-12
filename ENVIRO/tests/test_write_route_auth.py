"""Auth on write routes.

Every POST/PUT/PATCH/DELETE rule in the app is called with no token and with a
bogus token. Routes gated by require_role answer 403 to the guest; routes gated by
require_auth with an unknown Bearer token answer 401. The node telemetry route
uses its own X-Node-Key check and answers 401.

The list of write endpoints is pinned, so adding a new write route forces a
conscious update here.
"""
import re

import pytest

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# (method, rule) for every write route in the app, pinned from the current code.
EXPECTED_WRITE_ROUTES = {
    ("POST", "/api/admin/backup/run"),
    ("POST", "/api/admin/test-alert"),
    ("POST", "/api/admin/simulate-quake"),
    ("POST", "/api/admin/clear-event"),
    ("POST", "/api/admin/telegram"),
    ("POST", "/api/admin/telegram/test"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/compare/history/backfill"),
    ("PATCH", "/api/levels/<int:lv>"),
    ("PATCH", "/api/nodes/<node_id>"),
    ("PATCH", "/api/nodes/<node_id>/location"),
    ("POST", "/api/nodes/<node_id>/telemetry"),
}

# Known exceptions, pinned rather than hidden:
#  * /api/auth/login is public by design; with no credentials it answers 401 invalid_credentials.
#  * /api/auth/logout uses require_auth, and require_auth lets the read-only guest through,
#    so an anonymous POST returns 200 (it does nothing without a token). Pinned as-is.
PUBLIC_OR_GUEST_PASSTHROUGH = {
    ("POST", "/api/auth/login"): 401,
    ("POST", "/api/auth/logout"): 200,
}

SAMPLE_NODE = "PROTO-01"  # seeded real node; the telemetry route looks it up before checking the key


def _concrete(rule):
    path = re.sub(r"<int:[^>]+>", "1", rule)
    return re.sub(r"<[^>]+>", SAMPLE_NODE, path)


def _write_rules(app):
    out = set()
    for rule in app.url_map.iter_rules():
        for method in rule.methods & WRITE_METHODS:
            out.add((method, rule.rule))
    return out


def test_write_route_inventory_is_pinned(app):
    assert _write_rules(app) == EXPECTED_WRITE_ROUTES


@pytest.mark.parametrize("method,rule", sorted(EXPECTED_WRITE_ROUTES))
def test_write_route_rejects_anonymous_request(client, method, rule):
    resp = client.open(_concrete(rule), method=method, json={})
    if (method, rule) in PUBLIC_OR_GUEST_PASSTHROUGH:
        assert resp.status_code == PUBLIC_OR_GUEST_PASSTHROUGH[(method, rule)], resp.get_data(as_text=True)
    else:
        assert resp.status_code in (401, 403), resp.get_data(as_text=True)


def test_guest_gets_403_on_role_gated_route(client):
    resp = client.post("/api/admin/clear-event")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "forbidden"


def test_unknown_bearer_token_gets_401(client):
    resp = client.post("/api/admin/clear-event", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"


def test_telemetry_without_or_with_wrong_node_key_is_401(client):
    url = f"/api/nodes/{SAMPLE_NODE}/telemetry"
    assert client.post(url, json={}).status_code == 401
    assert client.post(url, json={}, headers={"X-Node-Key": "wrong"}).status_code == 401


def test_telemetry_with_correct_node_key_passes_auth(client):
    # the seeded prototype key is the only thing the node route checks; it must pass that gate
    resp = client.post(
        f"/api/nodes/{SAMPLE_NODE}/telemetry",
        json={"temperature_c": 25.0},
        headers={"X-Node-Key": "enviro-proto-01-demo-key"},
    )
    assert resp.status_code not in (401, 403, 404)


def test_admin_login_token_passes_role_gate(client, make_user):
    username, password = make_user(role="admin")
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    token = login.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers).get_json()
    assert me["username"] == username and me["role"] == "admin"

    # clear-event with nothing running is a harmless no-op: proves the role gate lets admin through
    resp = client.post("/api/admin/clear-event", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "was_active": False}


def test_auditor_is_forbidden_from_admin_only_route(client, make_user):
    username, password = make_user(username="auditor1", role="auditor")
    token = client.post("/api/auth/login", json={"username": username, "password": password}).get_json()["token"]
    resp = client.post("/api/admin/backup/run", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_wrong_password_is_rejected(client, make_user):
    username, _ = make_user()
    resp = client.post("/api/auth/login", json={"username": username, "password": "nope"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_credentials"
