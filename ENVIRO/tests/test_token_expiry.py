"""Login tokens expire, and only the Authorization header carries them.

Seams under test (all through public HTTP routes or the auth module's public functions):
  * /api/auth/login, /api/auth/me and a staff-only route (GET /api/admin/audit-log)
  * auth.user_for_token, which must refuse and forget an expired token

Time is moved with the module-level clock hook auth._clock, so no test sleeps.
"""
import pytest

from server import auth


@pytest.fixture
def clock(monkeypatch):
    """Replace auth._clock with a settable fake. Returns a dict holding the current 'now'."""
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(auth, "_clock", lambda: state["now"])
    return state


def _login(client, make_user, role="admin"):
    username, password = make_user(username=f"{role}.expiry", role=role)
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["token"]


def test_token_works_just_before_ttl(client, make_user, clock):
    token = _login(client, make_user)
    clock["now"] += auth.TOKEN_TTL - 1
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "admin"


def test_token_gets_401_after_ttl(client, make_user, clock):
    token = _login(client, make_user)
    clock["now"] += auth.TOKEN_TTL + 1
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"


def test_expired_token_is_forgotten_by_user_for_token(client, make_user, clock):
    token = _login(client, make_user)
    clock["now"] += auth.TOKEN_TTL + 1
    assert auth.user_for_token(token) is None
    assert token not in auth._tokens


def test_returned_user_dict_has_no_issue_time(client, make_user, clock):
    token = _login(client, make_user)
    user = auth.user_for_token(token)
    assert set(user) == {"username", "role", "display_name"}


def test_query_string_token_is_treated_as_guest(client, make_user, clock):
    token = _login(client, make_user)
    me = client.get(f"/api/auth/me?token={token}")
    assert me.status_code == 200
    assert me.get_json()["role"] == "guest"
    # a staff-only route must refuse the guest, even though a valid token is in the URL
    resp = client.get(f"/api/admin/audit-log?token={token}")
    assert resp.status_code == 403


def test_expired_tokens_are_swept_on_next_login(client, make_user, clock):
    old_token = _login(client, make_user, role="admin")
    clock["now"] += auth.TOKEN_TTL + 1
    _login(client, make_user, role="operator")
    assert old_token not in auth._tokens
