"""Shared fixtures for the ENVIRO server tests.

Nothing here touches the real database (ENVIRO/data/enviro.db) or the network:
  * `temp_db` points server.db.DB_PATH at a file under pytest's tmp_path and
    runs the real schema/seed through init_db().
  * `app` builds the real create_app() with its background threads swapped for
    a recorder that never starts them, so no source poller, simulator or
    node simulator runs during a test.
"""
import os
import sys

ENVIRO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ENVIRO_DIR not in sys.path:
    sys.path.insert(0, ENVIRO_DIR)

import pytest  # noqa: E402

REAL_DB_PATH = os.path.join(ENVIRO_DIR, "data", "enviro.db")


class _RecordingThread:
    """Stands in for threading.Thread inside server.app: records the target and never starts it."""

    started = []

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, **_):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        _RecordingThread.started.append(self.target)

    def is_alive(self):
        return False


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """A freshly initialised ENVIRO database in tmp_path. Returns its path."""
    from server import db as dbmod

    path = str(tmp_path / "enviro-test.db")
    assert os.path.abspath(path) != os.path.abspath(REAL_DB_PATH)
    monkeypatch.setattr(dbmod, "DB_PATH", path)
    dbmod.init_db()
    return path


@pytest.fixture
def app(temp_db, monkeypatch):
    """The real Flask app from create_app(), with no background threads or pollers started."""
    from server import app as appmod
    from server import world_faults

    _RecordingThread.started = []
    monkeypatch.setattr(appmod.threading, "Thread", _RecordingThread, raising=True)
    monkeypatch.setattr(world_faults, "ensure_built_async", lambda: None)
    flask_app = appmod.create_app()
    flask_app.config["TESTING"] = True
    flask_app.config["STARTED_THREAD_TARGETS"] = _RecordingThread.started
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(temp_db):
    """Insert a login into the temp users table and return its username and password."""
    from werkzeug.security import generate_password_hash
    from server import db as dbmod

    def _make(username="tester", password="s3cret-pass", role="admin", display_name="Tester"):
        conn = dbmod.get_conn()
        conn.execute(
            "INSERT INTO users(username, password_hash, role, display_name) VALUES (?,?,?,?)",
            (username, generate_password_hash(password), role, display_name),
        )
        conn.commit()
        conn.close()
        return username, password

    return _make
