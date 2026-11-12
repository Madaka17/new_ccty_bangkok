"""
Switch a SQLite database to WAL journal mode.

In the default rollback-journal mode, a long read holds a shared lock on the whole file, and every
writer then fails with "database is locked" after its timeout. In WAL mode, readers and the writer
do not block each other. WAL is stored in the database file, so the switch only has to succeed once,
but ensure_wal() runs on every start so a new or restored file gets it too.
"""
import sqlite3

from backend.core.log import get_logger

log = get_logger("DB")


def ensure_wal(db_path: str) -> str:
    """Make sure db_path uses WAL mode. Returns the resulting journal mode, lower-case. Never raises."""
    current = "unknown"
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            before = current = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            current = str(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        finally:
            conn.close()
    except sqlite3.Error as e:
        log.warning(f"could not switch {db_path} to WAL: {e}")
        return current
    if current == "wal" and before != "wal":
        log.info(f"{db_path} now uses WAL (readers no longer block writers)")
    return current
