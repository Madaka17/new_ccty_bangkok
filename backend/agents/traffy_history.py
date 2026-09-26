"""
Archive of the Traffy Fondue flood reports, for day-to-day and week-to-week comparison.

The Traffy feed (flood_feeds.TraffyFloodReports) only keeps the last 6 h, so every SYNC_SECONDS the
reports it holds are upserted into the `traffy_flood_reports` table of vehicle_counts.db (one row per
report id, its latest state kept). compare() then counts them by Bangkok day, hour and district:

    day:   today so far vs yesterday up to the same time, per hour for both, and the last 14 days
    week:  this week (Mon-now) vs last week up to the same point, per weekday, and the last 8 weeks
    districts: today vs yesterday (same time) for the busiest districts

Served by /api/traffy/history. Counts start from the first sync: `since` says when that was.
"""
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.agents.traffy_agent import _depth_level

SYNC_SECONDS = int(os.getenv("TRAFFY_HISTORY_SECONDS", "300"))
BKK_TZ = timezone(timedelta(hours=7))
DAYS = 14
WEEKS = 8
TOP_DISTRICTS = 12
WEEKDAYS_TH = ("จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา.")


def _day_start(dt):
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


class TraffyHistory:
    def __init__(self, db_path, source):
        """source: callable returning flood_feeds.TraffyFloodReports.status() ({items, updated_at})."""
        self.db_path = db_path
        self.source = source
        self.lock = threading.Lock()
        with self._db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traffy_flood_reports (
                    id          TEXT PRIMARY KEY,
                    ts          INTEGER NOT NULL,   -- report time (Traffy)
                    district    TEXT,
                    depth       TEXT,               -- one of traffy_agent.DEPTHS or ไม่ระบุ
                    state       TEXT,               -- latest state seen
                    first_seen  INTEGER NOT NULL,
                    last_seen   INTEGER NOT NULL
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS traffy_flood_reports_ts ON traffy_flood_reports(ts)")

    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------ archive
    def sync(self):
        """Upsert the reports the feed holds now. Returns how many rows were written."""
        try:
            st = self.source() or {}
        except Exception as e:  # noqa: BLE001 - feed down: try again next time
            print(f"[TraffyHistory] source failed: {e}")
            return 0
        if not st.get("updated_at"):
            return 0            # feed not loaded yet after a restart
        now = int(time.time())
        rows = [(r["id"], int(r.get("ts") or now), r.get("district") or "", _depth_level(r.get("depth")),
                 r.get("state") or "", now, now) for r in st.get("items") or [] if r.get("id")]
        with self.lock, self._db() as conn:
            conn.executemany("""
                INSERT INTO traffy_flood_reports (id, ts, district, depth, state, first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET state = excluded.state, last_seen = excluded.last_seen""", rows)
        return len(rows)

    def _loop(self):
        time.sleep(45)          # let the Traffy poller answer first
        while True:
            try:
                self.sync()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[TraffyHistory] sync failed: {e}")
            time.sleep(SYNC_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="TraffyHistory").start()

    # ------------------------------------------------------------ comparison
    def _count(self, conn, since, until):
        return conn.execute("SELECT COUNT(*) FROM traffy_flood_reports WHERE ts >= ? AND ts < ?",
                            (since, until)).fetchone()[0]

    def _deep(self, conn, since, until):
        return conn.execute("SELECT COUNT(*) FROM traffy_flood_reports WHERE ts >= ? AND ts < ? "
                            "AND depth IN ('หัวเข่า', 'ต้นขา', 'เอวขึ้นไป')", (since, until)).fetchone()[0]

    @staticmethod
    def _change(now_n, prev_n):
        return None if not prev_n else round((now_n - prev_n) / prev_n * 100)

    def compare(self):
        now_dt = datetime.now(BKK_TZ)
        now = int(now_dt.timestamp())
        today = _day_start(now_dt)
        t0 = int(today.timestamp())
        y0 = t0 - 86400
        elapsed = now - t0                               # same time of day, yesterday
        week0 = int((today - timedelta(days=today.weekday())).timestamp())
        lw0 = week0 - 7 * 86400
        week_elapsed = now - week0
        with self.lock, self._db() as conn:
            first = conn.execute("SELECT MIN(first_seen) FROM traffy_flood_reports").fetchone()[0]
            rows = conn.execute("SELECT ts, district FROM traffy_flood_reports WHERE ts >= ?",
                                (int((today - timedelta(days=max(DAYS, WEEKS * 7 + 7))).timestamp()),)).fetchall()
            day = {"today": self._count(conn, t0, now), "yesterday_same_time": self._count(conn, y0, y0 + elapsed),
                   "yesterday_total": self._count(conn, y0, t0),
                   "today_deep": self._deep(conn, t0, now), "yesterday_deep": self._deep(conn, y0, y0 + elapsed)}
            week = {"this_week": self._count(conn, week0, now), "last_week_same_time": self._count(conn, lw0, lw0 + week_elapsed),
                    "last_week_total": self._count(conn, lw0, week0)}
        day["change_pct"] = self._change(day["today"], day["yesterday_same_time"])
        week["change_pct"] = self._change(week["this_week"], week["last_week_same_time"])

        hours_today, hours_yday = [0] * 24, [0] * 24
        days = {(today - timedelta(days=i)).date().isoformat(): 0 for i in range(DAYS)}
        wd_this, wd_last = [0] * 7, [0] * 7
        weeks = {}
        d_today, d_yday = {}, {}
        for r in rows:
            ts, dist = r["ts"], r["district"] or "ไม่ระบุเขต"
            dt = datetime.fromtimestamp(ts, BKK_TZ)
            key = dt.date().isoformat()
            if key in days:
                days[key] += 1
            if t0 <= ts < now:
                hours_today[dt.hour] += 1
                d_today[dist] = d_today.get(dist, 0) + 1
            elif y0 <= ts < t0:
                hours_yday[dt.hour] += 1
                if ts < y0 + elapsed:
                    d_yday[dist] = d_yday.get(dist, 0) + 1
            if week0 <= ts < now:
                wd_this[dt.weekday()] += 1
            elif lw0 <= ts < week0:
                wd_last[dt.weekday()] += 1
            wk = (_day_start(dt) - timedelta(days=dt.weekday())).date().isoformat()
            weeks[wk] = weeks.get(wk, 0) + 1
        week_keys = [(today - timedelta(days=today.weekday() + 7 * i)).date().isoformat() for i in range(WEEKS)]
        names = sorted(set(d_today) | set(d_yday), key=lambda n: (-d_today.get(n, 0), -d_yday.get(n, 0)))[:TOP_DISTRICTS]
        return {
            "generated_at": now, "since": first, "now_hour": now_dt.hour, "weekday": now_dt.weekday(),
            "day": {**day, "hours_today": hours_today, "hours_yesterday": hours_yday,
                    "days": [{"date": k, "n": days[k]} for k in sorted(days)]},
            "week": {**week, "weekday_labels": list(WEEKDAYS_TH), "this_week_by_day": wd_this, "last_week_by_day": wd_last,
                     "weeks": [{"week_start": k, "n": weeks.get(k, 0)} for k in reversed(week_keys)]},
            "districts": [{"district": n, "today": d_today.get(n, 0), "yesterday_same_time": d_yday.get(n, 0)} for n in names],
        }
