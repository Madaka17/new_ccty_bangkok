"""
The monitor's database (launch\\monitor\\state\\monitor.db), shared by the collector (writes) and the app (reads).

    status   the latest result of every check: one row per key, `since` = when it entered its current state
    events   one row per state change (and per watchdog.log line), kept 30 days
    meta     small values: the collector's heartbeat, the watchdog.log read offset, "check now" requests
Each call opens its own connection in WAL mode, so the app can read while the collector writes.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS status (key TEXT PRIMARY KEY, grp TEXT, target TEXT, name TEXT, state TEXT,
                                   detail TEXT, since REAL, checked_at REAL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, key TEXT, grp TEXT, target TEXT,
                                   name TEXT, old TEXT, new TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""
DEFAULT_DB = Path(__file__).resolve().parent / "state" / "monitor.db"
EVENT_COLS = "id, ts, key, grp, target, name, old, new, detail"


def _event(row):
    return {"id": row[0], "ts": row[1], "key": row[2], "group": row[3], "target": row[4], "name": row[5],
            "old": row[6], "new": row[7], "detail": row[8]}


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def apply(self, statuses, now, silent_new=()):
        events = []
        with closing(self._conn()) as c, c:
            for s in statuses:
                prev = c.execute("SELECT state, since FROM status WHERE key = ?", (s["key"],)).fetchone()
                changed = prev is None or prev[0] != s["state"]
                since = now if changed else prev[1]
                c.execute("INSERT OR REPLACE INTO status (key, grp, target, name, state, detail, since, checked_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                          (s["key"], s["group"], s["target"], s["name"], s["state"], s["detail"], since, now))
                if changed and not (prev is None and (s["state"] == "ok" or s["key"] in silent_new)):
                    events.append(self._insert(c, now, s["key"], s["group"], s["target"], s["name"],
                                               prev[0] if prev else None, s["state"], s["detail"]))
        return events

    def retire(self, keys):
        """Delete status rows (no events): checks that no longer exist or whose server is down."""
        keys = list(keys)
        if keys:
            with closing(self._conn()) as c, c:
                c.executemany("DELETE FROM status WHERE key = ?", [(k,) for k in keys])

    def _insert(self, c, ts, key, group, target, name, old, new, detail):
        cur = c.execute("INSERT INTO events (ts, key, grp, target, name, old, new, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (ts, key, group, target, name, old, new, detail))
        return {"id": cur.lastrowid, "ts": ts, "key": key, "group": group, "target": target, "name": name,
                "old": old, "new": new, "detail": detail}

    def add_event(self, ts, key, group, target, name, old, new, detail):
        with closing(self._conn()) as c, c:
            return self._insert(c, ts, key, group, target, name, old, new, detail)

    def current(self):
        with closing(self._conn()) as c:
            rows = c.execute("SELECT key, grp, target, name, state, detail, since, checked_at FROM status ORDER BY key").fetchall()
        return [{"key": r[0], "group": r[1], "target": r[2], "name": r[3], "state": r[4], "detail": r[5],
                 "since": r[6], "checked_at": r[7]} for r in rows]

    def events(self, target=None, state=None, q=None, since=None, limit=25, offset=0):
        where, args = [], []
        if isinstance(target, (list, tuple)):
            if target:
                where.append(f"target IN ({', '.join('?' * len(target))})"); args += list(target)
        elif target:
            where.append("target = ?"); args.append(target)
        if state:
            where.append("new = ?"); args.append(state)
        if q:
            where.append("(name LIKE ? OR detail LIKE ?)"); args += [f"%{q}%", f"%{q}%"]
        if since is not None:
            where.append("ts >= ?"); args.append(since)
        sql_where = f" WHERE {' AND '.join(where)}" if where else ""
        with closing(self._conn()) as c:
            total = c.execute(f"SELECT COUNT(*) FROM events{sql_where}", args).fetchone()[0]
            rows = c.execute(f"SELECT {EVENT_COLS} FROM events{sql_where} ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
                             args + [int(limit), int(offset)]).fetchall()
        return {"rows": [_event(r) for r in rows], "total": total}

    def prune(self, now, days=30):
        with closing(self._conn()) as c, c:
            return c.execute("DELETE FROM events WHERE ts < ?", (now - days * 86400,)).rowcount

    def get_meta(self, k, default=None):
        with closing(self._conn()) as c:
            row = c.execute("SELECT v FROM meta WHERE k = ?", (k,)).fetchone()
        return row[0] if row else default

    def set_meta(self, k, v):
        with closing(self._conn()) as c, c:
            c.execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?, ?)", (k, str(v)))
