"""Log of requests the public-exposure guard blocked, so a report can show how often the site was probed.

record() only appends to an in-memory buffer (never touches the disk, never raises); a daemon thread
flushes it to SQLite every 30 s. Two tables: hourly counts per kind (kept 30 days) and the newest 500
raw events. Only time, kind, ip, path, method and user agent are stored, no headers, cookies or bodies.

    python -m backend.core.security_log --summary-json [--days N]   prints the summary, never creates the DB
"""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta

from backend.core.instance import DATA_DIR

KINDS = ("bad_path", "docs_probe", "control_denied", "not_browser", "no_session",
         "rate_limited", "chat_limited", "report_limited", "too_large", "probe")
RECENT_KEEP = 500
HOURLY_KEEP_DAYS = 30

_log = logging.getLogger(__name__)


def _hour(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H")


class SecurityLog:
    def __init__(self, db_path: str, clock=time.time, buffer_max: int = 10_000):
        self.db_path = db_path
        self._clock = clock
        self._buffer_max = buffer_max
        self._buf: list = []
        self._dropped = 0
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._thread = None
        self._warned = False

    def record(self, kind: str, ip: str, path: str, method: str = "GET", ua: str = "") -> None:
        try:
            ev = (self._clock(), str(kind), str(ip), str(path)[:300], str(method), str(ua)[:200])
            with self._lock:
                if len(self._buf) >= self._buffer_max:
                    self._dropped += 1
                else:
                    self._buf.append(ev)
        except Exception:
            pass

    def flush(self) -> int:
        with self._flush_lock:
            with self._lock:
                events, self._buf = self._buf, []
                dropped, self._dropped = self._dropped, 0
            if not events and not dropped:
                return 0
            now = self._clock()
            counts: dict = {}
            for ts, kind, *_ in events:
                key = (_hour(ts), kind)
                counts[key] = counts.get(key, 0) + 1
            if dropped:
                key = (_hour(now), "dropped")
                counts[key] = counts.get(key, 0) + dropped
            try:
                con = sqlite3.connect(self.db_path, timeout=5)
                try:
                    con.execute("PRAGMA journal_mode=WAL")
                    con.execute("CREATE TABLE IF NOT EXISTS hourly(hour TEXT, kind TEXT, n INTEGER, "
                                "PRIMARY KEY(hour, kind))")
                    con.execute("CREATE TABLE IF NOT EXISTS recent(ts REAL, kind TEXT, ip TEXT, "
                                "path TEXT, method TEXT, ua TEXT)")
                    con.executemany(
                        "INSERT INTO hourly(hour, kind, n) VALUES(?,?,?) "
                        "ON CONFLICT(hour, kind) DO UPDATE SET n = n + excluded.n",
                        [(h, k, n) for (h, k), n in counts.items()])
                    con.executemany("INSERT INTO recent VALUES(?,?,?,?,?,?)", events)
                    con.execute("DELETE FROM recent WHERE rowid NOT IN "
                                "(SELECT rowid FROM recent ORDER BY ts DESC, rowid DESC LIMIT ?)",
                                (RECENT_KEEP,))
                    cutoff = _hour(now - HOURLY_KEEP_DAYS * 86400)
                    con.execute("DELETE FROM hourly WHERE hour < ?", (cutoff,))
                    con.commit()
                finally:
                    con.close()
                return len(events)
            except Exception as e:
                if not self._warned:
                    self._warned = True
                    _log.warning("security log write failed (%s: %s); events dropped", type(e).__name__, e)
                return 0

    def start(self, interval: float = 30.0) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            def loop():
                while True:
                    time.sleep(interval)
                    try:
                        self.flush()
                    except Exception:
                        pass

            self._thread = threading.Thread(target=loop, name="security-log", daemon=True)
            self._thread.start()

    def summary(self, days: int = 30) -> dict:
        now = self._clock()
        today = datetime.fromtimestamp(now).date()
        day_list = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        by_day = {d: 0 for d in day_list}
        by_kind: dict = {}
        top_ips: list = []
        top_paths: list = []
        recent: list = []
        if os.path.exists(self.db_path):
            try:
                con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)
                try:
                    for hour, kind, n in con.execute("SELECT hour, kind, n FROM hourly"):
                        d = hour[:10]
                        if d in by_day:
                            by_day[d] += n
                            by_kind[kind] = by_kind.get(kind, 0) + n
                    top_ips = [{"ip": r[0], "n": r[1]} for r in con.execute(
                        "SELECT ip, COUNT(*) c FROM recent GROUP BY ip ORDER BY c DESC, ip LIMIT 10")]
                    top_paths = [{"path": r[0], "n": r[1]} for r in con.execute(
                        "SELECT path, COUNT(*) c FROM recent GROUP BY path ORDER BY c DESC, path LIMIT 10")]
                    recent = [dict(zip(("ts", "kind", "ip", "path", "method", "ua"), r)) for r in con.execute(
                        "SELECT ts, kind, ip, path, method, ua FROM recent ORDER BY ts DESC, rowid DESC LIMIT 50")]
                finally:
                    con.close()
            except Exception as e:
                _log.warning("security log read failed (%s: %s)", type(e).__name__, e)
        return {
            "days": days,
            "total": sum(by_day.values()),
            "by_kind": by_kind,
            "by_day": [{"day": d, "n": by_day[d]} for d in day_list],
            "top_ips": top_ips,
            "top_paths": top_paths,
            "recent": recent,
            "generated": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        }


log = SecurityLog(os.path.join(DATA_DIR, "security_events.db"))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--summary-json", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    if args.summary_json:
        print(json.dumps(log.summary(args.days), ensure_ascii=False))
