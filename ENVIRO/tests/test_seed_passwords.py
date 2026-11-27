"""Seeded demo accounts must not use a password committed to git.

init_db() seeds DEMO_USERS with ENVIRO_SEED_PASSWORD when that is set (at least 12 chars), otherwise
with a random password per user, written to data/initial_passwords.txt. Nothing here writes to the
real ENVIRO/data folder: BASE_DIR and DB_PATH are redirected under tmp_path.
"""
import os

import pytest
from werkzeug.security import check_password_hash

OLD_SHARED_PASSWORD = "enviro2026"
SEEDED = ["admin.wanchana", "operator.suda", "auditor.kritt", "partner.api"]


@pytest.fixture
def seed_env(tmp_path, monkeypatch):
    """Fresh database and BASE_DIR under tmp_path, with no seed password set unless the test sets one."""
    from server import db as dbmod

    monkeypatch.delenv("ENVIRO_SEED_PASSWORD", raising=False)
    monkeypatch.setattr(dbmod, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "data" / "enviro-seed.db"))
    dbmod.init_db()
    return tmp_path


def _hash_of(username):
    from server import db as dbmod

    conn = dbmod.get_conn()
    row = conn.execute("SELECT password_hash FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return row["password_hash"] if row else None


def test_no_seeded_user_accepts_the_old_shared_password(seed_env):
    for username in SEEDED:
        stored = _hash_of(username)
        assert stored is not None, username
        assert not check_password_hash(stored, OLD_SHARED_PASSWORD), username


def test_seed_password_env_var_is_used_for_every_seeded_user(tmp_path, monkeypatch):
    from server import db as dbmod

    seed_pw = "seed-from-env-2026"
    monkeypatch.setenv("ENVIRO_SEED_PASSWORD", seed_pw)
    monkeypatch.setattr(dbmod, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "data" / "enviro-env.db"))
    dbmod.init_db()

    for username in SEEDED:
        assert check_password_hash(_hash_of(username), seed_pw), username


def test_short_seed_password_env_var_falls_back_to_random_passwords(tmp_path, monkeypatch, capsys):
    from server import db as dbmod

    short = "too-short"
    monkeypatch.setenv("ENVIRO_SEED_PASSWORD", short)
    monkeypatch.setattr(dbmod, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "data" / "enviro-short.db"))
    dbmod.init_db()

    path = tmp_path / "data" / "initial_passwords.txt"
    assert path.exists()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 4
    passwords = {}
    for line in lines:
        username, password = line.split("\t", 1)
        passwords[username] = password
    assert set(passwords) == set(SEEDED)
    assert len(set(passwords.values())) == 4
    for username, password in passwords.items():
        assert password != short, username
        assert password != OLD_SHARED_PASSWORD, username
        assert check_password_hash(_hash_of(username), password), username
        assert not check_password_hash(_hash_of(username), short), username
        assert not check_password_hash(_hash_of(username), OLD_SHARED_PASSWORD), username

    printed = capsys.readouterr()
    assert "ENVIRO_SEED_PASSWORD" in printed.out + printed.err
    assert short not in printed.out + printed.err


def test_initial_passwords_file_is_created_with_owner_only_permissions(tmp_path, monkeypatch):
    import stat
    from server import db as dbmod

    real_open = os.open
    modes = []

    def spy(path, flags, mode=0o777, *args, **kwargs):
        if str(path).endswith("initial_passwords.txt"):
            modes.append(mode)
        return real_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(dbmod.os, "open", spy)
    monkeypatch.delenv("ENVIRO_SEED_PASSWORD", raising=False)
    monkeypatch.setattr(dbmod, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "data" / "enviro-perm.db"))
    dbmod.init_db()

    assert modes == [0o600]
    path = tmp_path / "data" / "initial_passwords.txt"
    if os.name != "nt":  # Windows ignores POSIX mode bits beyond read-only
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_initial_passwords_file_lists_each_new_account(seed_env):
    path = seed_env / "data" / "initial_passwords.txt"
    assert path.exists()
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == len(SEEDED)
    by_user = {}
    for line in lines:
        username, password = line.split("\t", 1)
        by_user[username] = password
    assert set(by_user) == set(SEEDED)
    for username, password in by_user.items():
        assert check_password_hash(_hash_of(username), password), username


def test_initial_passwords_file_is_not_written_for_existing_users(seed_env):
    from server import db as dbmod

    path = seed_env / "data" / "initial_passwords.txt"
    before = path.read_text(encoding="utf-8")
    dbmod.init_db()  # second start on an initialised database: no new accounts
    assert path.read_text(encoding="utf-8") == before


def test_set_password_changes_the_hash_and_writes_audit_row(seed_env):
    from server import db as dbmod
    from server.set_password import set_password

    new_pw = "brand-new-pass-2026"
    assert set_password("admin.wanchana", new_pw) is True
    assert check_password_hash(_hash_of("admin.wanchana"), new_pw)

    conn = dbmod.get_conn()
    row = conn.execute(
        "SELECT username, action FROM audit_log WHERE action LIKE ? ORDER BY id DESC LIMIT 1",
        ("%admin.wanchana%",),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["username"] == "system"


def test_set_password_returns_false_for_unknown_user(seed_env):
    from server.set_password import set_password

    assert set_password("nobody.here", "some-long-password-1") is False


def test_set_password_cli_tells_the_operator_to_restart_the_server(seed_env, monkeypatch, capsys):
    from server import set_password as sp

    new_pw = "cli-changed-pass-2026"
    monkeypatch.setattr(sp.getpass, "getpass", lambda prompt="": new_pw)
    assert sp.main(["admin.wanchana"]) == 0

    out = capsys.readouterr().out
    assert "รีสตาร์ท" in out
    assert "ENVIRO server" in out
