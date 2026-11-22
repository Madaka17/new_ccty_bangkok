"""Read routes under /api/admin that expose accounts, file paths or internal config need a staff login.

require_auth lets an anonymous visitor through as the read-only guest, so any route guarded only by
require_auth is readable by the public. The routes pinned below expose usernames, the role/account
model or a server file path, so they must answer 401/403 to a guest and 200 to a staff account.

Decisions (also documented in the route docstrings in server/routes/admin.py):
  * /api/admin/audit-log   -> staff (admin, operator, auditor): usernames and their actions
  * /api/admin/backup      -> staff: full server disk path of the backup file
  * /api/admin/roles       -> staff: account counts per role and the internal permission model
  * /api/admin/services    -> public: process health only, shown on the public status view
  * /api/admin/epicenter-options -> public: fault-line names and coordinates, no account data
  * /api/admin/telegram    -> admin only already (require_role), pinned here too
"""
import pytest

STAFF_ROLES = ["admin", "operator", "auditor"]

# Each restricted read route, with a marker that must never leak to an anonymous caller.
RESTRICTED_ROUTES = ["/api/admin/audit-log", "/api/admin/backup", "/api/admin/roles"]

LEAK_USERNAME = "leakcheck.person"
LEAK_PATH = "/srv/secret-enviro/backups/leak-backup-marker.db"


@pytest.fixture
def seeded_secrets(temp_db):
    """Put a distinctive username into audit_log and a distinctive path into backups."""
    from server import db as dbmod

    conn = dbmod.get_conn()
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)",
        ("2026-11-22T10:00:00", LEAK_USERNAME, "action-marker"),
    )
    conn.execute(
        "INSERT INTO backups(ts, size_bytes, path) VALUES (?,?,?)",
        ("2026-11-22T10:00:00", 1234, LEAK_PATH),
    )
    conn.commit()
    conn.close()


@pytest.mark.parametrize("path", RESTRICTED_ROUTES)
def test_anonymous_guest_is_refused(client, seeded_secrets, path):
    resp = client.get(path)
    assert resp.status_code in (401, 403), resp.get_data(as_text=True)
    body = resp.get_data(as_text=True)
    assert LEAK_USERNAME not in body
    assert LEAK_PATH not in body
    assert "leak-backup-marker" not in body


@pytest.mark.parametrize("path", RESTRICTED_ROUTES)
def test_unknown_bearer_token_is_refused(client, seeded_secrets, path):
    resp = client.get(path, headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    body = resp.get_data(as_text=True)
    assert LEAK_USERNAME not in body and LEAK_PATH not in body


@pytest.mark.parametrize("role", STAFF_ROLES)
@pytest.mark.parametrize("path", RESTRICTED_ROUTES)
def test_staff_login_gets_200(client, make_user, seeded_secrets, path, role):
    username, password = make_user(username=f"{role}.reader", role=role)
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_staff_login_sees_audit_rows_and_backup_path(client, make_user, seeded_secrets):
    username, password = make_user(username="auditor.reader", role="auditor")
    token = client.post("/api/auth/login", json={"username": username, "password": password}).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    audit = client.get("/api/admin/audit-log?limit=50", headers=headers).get_json()
    assert any(row["username"] == LEAK_USERNAME for row in audit)
    backup = client.get("/api/admin/backup", headers=headers).get_json()
    assert backup["path"] == LEAK_PATH


def test_partner_api_account_is_refused(client, make_user, seeded_secrets):
    # partner is an external API account: it gets public data only, not the staff read routes
    username, password = make_user(username="partner.reader", role="partner")
    token = client.post("/api/auth/login", json={"username": username, "password": password}).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    for path in RESTRICTED_ROUTES:
        assert client.get(path, headers=headers).status_code == 403, path


@pytest.mark.parametrize("path", ["/api/admin/services", "/api/admin/epicenter-options"])
def test_public_status_routes_stay_open_to_guest(client, path):
    assert client.get(path).status_code == 200


def test_telegram_read_is_admin_only(client, make_user):
    username, password = make_user(username="operator.reader", role="operator")
    token = client.post("/api/auth/login", json={"username": username, "password": password}).get_json()["token"]
    assert client.get("/api/admin/telegram").status_code == 403
    assert client.get("/api/admin/telegram", headers={"Authorization": f"Bearer {token}"}).status_code == 403
