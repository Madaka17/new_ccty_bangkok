import sqlite3
from pathlib import Path

from backend.bma.bma_best_time import CELLS_SQL
from backend.core.sqlite_wal import ensure_wal


def _make_table(path, rows=50):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [(i,) for i in range(rows)])
    conn.commit()
    conn.close()


def _journal_mode(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()


def _open_long_read(path):
    reader = sqlite3.connect(path)
    cur = reader.execute("SELECT * FROM t")
    cur.fetchone()  # cursor stays open, so the read transaction stays open
    return reader, cur  # keep cur alive: dropping it resets the statement and releases the lock


def test_ensure_wal_switches_and_is_idempotent(tmp_path):
    db = str(tmp_path / "new.db")
    _make_table(db)

    assert ensure_wal(db) == "wal"
    assert ensure_wal(db) == "wal"
    assert _journal_mode(db) == "wal"


def test_writer_not_blocked_by_open_read_after_ensure_wal(tmp_path):
    db = str(tmp_path / "wal.db")
    _make_table(db)
    ensure_wal(db)

    reader, cur = _open_long_read(db)
    try:
        writer = sqlite3.connect(db, timeout=0.2)
        try:
            writer.execute("INSERT INTO t (v) VALUES (999)")
            writer.commit()
        finally:
            writer.close()
    finally:
        reader.close()


def test_writer_blocked_without_wal(tmp_path):
    db = str(tmp_path / "rollback.db")
    _make_table(db)
    assert _journal_mode(db) == "delete"

    reader, cur = _open_long_read(db)
    try:
        writer = sqlite3.connect(db, timeout=0.2)
        try:
            raised = None
            try:
                writer.execute("INSERT INTO t (v) VALUES (999)")
                writer.commit()
            except sqlite3.OperationalError as e:
                raised = e
            assert raised is not None
            assert "locked" in str(raised)
        finally:
            writer.close()
    finally:
        reader.close()


def test_ensure_wal_never_raises(tmp_path):
    db = str(tmp_path / "missing_dir" / "x.db")

    result = ensure_wal(db)

    assert isinstance(result, str)


def test_best_time_ro_read_works_on_wal_db(tmp_path):
    db = str(tmp_path / "bma.db")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE bma_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camid TEXT NOT NULL,
            hour TEXT NOT NULL,
            cars INTEGER NOT NULL DEFAULT 0,
            motorcycles INTEGER NOT NULL DEFAULT 0,
            trucks INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL DEFAULT 0,
            level TEXT NOT NULL DEFAULT 'free',
            ts INTEGER NOT NULL,
            date TEXT,
            week TEXT,
            month TEXT,
            road TEXT,
            district TEXT
        )
    """)
    conn.execute(
        "INSERT INTO bma_history (camid, hour, total, ts, date) "
        "VALUES ('c1', '2026-11-10 08:00', 12, 0, '2026-11-10')"
    )
    conn.commit()
    conn.close()
    assert ensure_wal(db) == "wal"

    writer = sqlite3.connect(db, timeout=0.2)
    try:
        writer.execute("INSERT INTO bma_history (camid, hour, total, ts, date) "
                       "VALUES ('c2', '2026-11-10 09:00', 5, 0, '2026-11-10')")
        writer.commit()

        # same read-only URI form as bma_best_time._load_cells
        uri = f"file:{Path(db).absolute().as_posix()}?mode=ro"
        ro = sqlite3.connect(uri, uri=True)
        try:
            rows = ro.execute(CELLS_SQL, ("2026-11-01",)).fetchall()
        finally:
            ro.close()
    finally:
        writer.close()

    assert sorted(str(r[0]) for r in rows) == ["c1", "c2"]
