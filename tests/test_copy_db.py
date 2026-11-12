"""launch/copy_db.py: seeding the test DB from a WAL-mode production DB with the SQLite backup API."""
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "launch" / "copy_db.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("copy_db_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wal_source(path):
    """A WAL database whose row is committed but still only in the -wal file. Returns the open connection."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t (x)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()
    assert Path(str(path) + "-wal").stat().st_size > 0
    return conn


def _rows(path):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT x FROM t").fetchall()


def test_copy_db_keeps_rows_still_in_wal(tmp_path):
    src = tmp_path / "production.db"
    dst = tmp_path / "test.db"
    live = _wal_source(src)
    try:
        _load().copy_db(str(src), str(dst))
        assert _rows(dst) == [(42,)]
    finally:
        live.close()


def test_plain_file_copy_misses_wal_rows(tmp_path):
    # documents why the launchers do not use copy: only the .db file is copied, the -wal file is left behind
    src = tmp_path / "production.db"
    dst = tmp_path / "plain.db"
    live = _wal_source(src)
    try:
        shutil.copyfile(src, dst)
        with sqlite3.connect(dst) as c:
            with pytest.raises(sqlite3.OperationalError):
                c.execute("SELECT x FROM t").fetchall()  # table was never checkpointed into the main file
    finally:
        live.close()


def test_missing_source_is_silent_success(tmp_path):
    dst = tmp_path / "test.db"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(tmp_path / "nope.db"), str(dst)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert not dst.exists()


def test_script_run_copies_wal_rows(tmp_path):
    src = tmp_path / "production.db"
    dst = tmp_path / "test.db"
    live = _wal_source(src)
    try:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), str(src), str(dst)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert _rows(dst) == [(42,)]
    finally:
        live.close()


def test_failure_exits_1_and_removes_partial_dst(tmp_path):
    src = tmp_path / "not_a_db.db"
    src.write_bytes(b"this is not sqlite" * 100)
    dst = tmp_path / "test.db"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(src), str(dst)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert result.stderr.startswith("copy_db:")
    assert not dst.exists()
