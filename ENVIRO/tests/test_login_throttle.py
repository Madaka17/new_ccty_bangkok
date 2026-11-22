"""Login throttle on POST /api/auth/login.

A failed attempt is counted per client IP and per username inside a sliding 15-minute window.
After 5 failures from one IP, or 10 against one username, further attempts get 429 before the
password is even checked. Behind Cloudflare Tunnel the client IP comes from CF-Connecting-IP.
"""
import pytest

LOGIN = "/api/auth/login"
WRONG = "not-the-password"


@pytest.fixture(autouse=True)
def _fresh_throttle_state():
    from server import login_throttle

    login_throttle.reset()
    yield
    login_throttle.reset()


def _login(client, username, password, ip=None):
    headers = {"CF-Connecting-IP": ip} if ip else {}
    return client.post(LOGIN, json={"username": username, "password": password}, headers=headers)


def test_fifth_wrong_password_from_one_ip_is_401_and_sixth_is_blocked_even_with_right_password(client, make_user):
    username, password = make_user()

    for _ in range(5):
        assert _login(client, username, WRONG, ip="198.51.100.10").status_code == 401

    blocked = _login(client, username, WRONG, ip="198.51.100.10")
    assert blocked.status_code == 429
    assert blocked.get_json()["error"] == "too_many_attempts"
    assert blocked.get_json()["message"]

    right = _login(client, username, password, ip="198.51.100.10")
    assert right.status_code == 429


def test_loopback_with_different_cf_connecting_ip_is_counted_separately(client, make_user):
    username, password = make_user()

    for _ in range(5):
        _login(client, username, WRONG, ip="198.51.100.20")
    assert _login(client, username, WRONG, ip="198.51.100.20").status_code == 429

    # Same socket peer (the test client is 127.0.0.1, i.e. loopback), different real client IP
    other = _login(client, username, password, ip="198.51.100.21")
    assert other.status_code == 200


def test_successful_login_clears_the_failures_of_that_ip_and_username(client, make_user):
    username, password = make_user()

    for _ in range(4):
        assert _login(client, username, WRONG, ip="198.51.100.30").status_code == 401

    assert _login(client, username, password, ip="198.51.100.30").status_code == 200

    # Counter was reset: five more failures are allowed again before the block
    for _ in range(5):
        assert _login(client, username, WRONG, ip="198.51.100.30").status_code == 401
    assert _login(client, username, WRONG, ip="198.51.100.30").status_code == 429


def test_ten_failures_on_one_username_from_different_ips_lock_that_username(client, make_user):
    username, password = make_user()

    for i in range(10):
        assert _login(client, username, WRONG, ip=f"203.0.113.{i + 1}").status_code == 401

    # A fresh IP that has never failed is still refused for this username
    locked = _login(client, username, password, ip="203.0.113.200")
    assert locked.status_code == 429
    assert locked.get_json()["error"] == "too_many_attempts"


def test_loopback_peer_is_still_trusted_for_cf_connecting_ip_and_non_loopback_peer_is_not(client, make_user):
    username, _ = make_user()

    # Peer is a LAN address, not loopback: the CF-Connecting-IP header is ignored, so every
    # attempt counts against 192.168.1.5 no matter which client IP the header claims.
    for i in range(5):
        resp = client.post(
            LOGIN,
            json={"username": username, "password": WRONG},
            headers={"CF-Connecting-IP": f"198.51.100.{100 + i}"},
            environ_overrides={"REMOTE_ADDR": "192.168.1.5"},
        )
        assert resp.status_code == 401

    blocked = client.post(
        LOGIN,
        json={"username": username, "password": WRONG},
        headers={"CF-Connecting-IP": "198.51.100.200"},
        environ_overrides={"REMOTE_ADDR": "192.168.1.5"},
    )
    assert blocked.status_code == 429


def test_username_is_normalised_so_case_and_outer_spaces_share_one_counter(client, make_user):
    make_user(username="admin.x")

    for _ in range(5):
        assert _login(client, "Admin.X ", WRONG, ip="198.51.100.41").status_code == 401
    for _ in range(5):
        assert _login(client, "admin.x", WRONG, ip="198.51.100.42").status_code == 401

    # Ten failures across both spellings: the username counter is full for every spelling
    assert _login(client, "ADMIN.X", WRONG, ip="198.51.100.43").status_code == 429


def test_ip_is_allowed_again_after_the_window_passes(client, make_user, monkeypatch):
    from server import login_throttle

    now = [10_000.0]
    monkeypatch.setattr(login_throttle, "_clock", lambda: now[0])
    username, password = make_user()

    for _ in range(5):
        assert _login(client, username, WRONG, ip="198.51.100.50").status_code == 401
    assert _login(client, username, WRONG, ip="198.51.100.50").status_code == 429

    now[0] += login_throttle.WINDOW_SECONDS + 1
    again = _login(client, username, password, ip="198.51.100.50")
    assert again.status_code == 200


def test_non_string_username_or_password_is_bad_request_not_server_error(client, make_user):
    username, _ = make_user()
    bodies = [
        {"username": 123, "password": WRONG},
        {"username": username, "password": ["x"]},
        {"username": {"a": 1}, "password": WRONG},
        {"username": username, "password": 42},
    ]
    for body in bodies:
        resp = client.post(LOGIN, json=body)
        assert resp.status_code == 400, body
        assert resp.get_json() == {"error": "bad_request"}, body


def test_json_body_that_is_not_an_object_is_bad_request(client):
    resp = client.post(LOGIN, json=["admin", "password"])
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "bad_request"}


def test_stale_keys_from_many_random_usernames_and_ips_are_swept(monkeypatch):
    from server import login_throttle

    now = [1_000.0]
    monkeypatch.setattr(login_throttle, "_clock", lambda: now[0])

    for i in range(1000):
        login_throttle.record_failure(f"10.0.{i // 256}.{i % 256}", f"user-{i}")
    assert len(login_throttle._user_failures) == 1000

    now[0] += login_throttle.WINDOW_SECONDS + 60 + 1
    login_throttle.record_failure("203.0.113.9", "newcomer")

    assert set(login_throttle._user_failures) == {"newcomer"}
    assert set(login_throttle._ip_failures) == {"203.0.113.9"}


def test_sweep_runs_at_most_once_per_minute(monkeypatch):
    from server import login_throttle

    now = [1_000.0]
    sweeps = []
    real_sweep = login_throttle._sweep_stale
    monkeypatch.setattr(login_throttle, "_clock", lambda: now[0])
    monkeypatch.setattr(login_throttle, "_sweep_stale", lambda t: (sweeps.append(t), real_sweep(t)))

    for i in range(100):
        login_throttle.record_failure(f"10.1.1.{i}", f"user-{i}")
    assert sweeps == [1_000.0]  # first failure sweeps; the other 99 within the same minute do not

    now[0] += 59
    login_throttle.record_failure("10.1.2.1", "late")
    assert sweeps == [1_000.0]

    now[0] += 1  # 60 s since the last sweep
    login_throttle.record_failure("10.1.2.2", "later")
    assert sweeps == [1_000.0, 1_060.0]


def test_keys_are_capped_at_64_characters_and_normalised(monkeypatch):
    from server import login_throttle

    monkeypatch.setattr(login_throttle, "_clock", lambda: 1_000.0)
    long_name = "  " + ("A" * 200) + "  "
    login_throttle.record_failure("2001:db8::" + "f" * 80, long_name)

    (user_key,) = login_throttle._user_failures.keys()
    (ip_key,) = login_throttle._ip_failures.keys()
    assert user_key == ("a" * 64)
    assert len(ip_key) <= 64
