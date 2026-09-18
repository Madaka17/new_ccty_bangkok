"""
Dashboard visitor telemetry (section 5 of the analytics page).

The browser sends one `view` per page/tab change and a `heartbeat` every 30 s while open.
Stored in cache/telemetry.db (separate from vehicle_counts.db so traffic data stays clean).
Only an anonymous random session id is kept - no IP, no user agent.
"""
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "cache", "telemetry.db")
BKK_TZ = timezone(timedelta(hours=7))

ONLINE_WINDOW = 90       # seconds since last heartbeat to count as "online now"
PEAK_DAYS = 7            # days of history used for peak-hour ranking

# Every view key the UI sends -> one of the four public topics
TOPIC_OF = {
    "dashboard": "traffic", "dashboard:overview": "traffic", "dashboard:trend": "traffic",
    "map": "traffic", "cameras": "traffic", "bma-count": "traffic", "yolo": "traffic", "ai": "traffic",
    "analytics": "traffic", "analytics:traffic": "traffic", "analytics:density": "road_status",
    "analytics:visitors": "traffic",
    "water": "flood", "dashboard:flood": "flood", "analytics:flood": "flood",
    "dashboard:roads": "road_status", "dashboard:incidents": "road_status", "dashboard:bma-reports": "road_status",
    "dashboard:safety": "accidents", "analytics:accidents": "accidents",
}
TOPICS = ("traffic", "flood", "road_status", "accidents")


class Telemetry:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS views (ts INTEGER NOT NULL, sid TEXT NOT NULL, view TEXT NOT NULL)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS views_ts ON views (ts)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, last_ts INTEGER NOT NULL, view TEXT)")
        self.conn.commit()

    @staticmethod
    def _ok(sid, view):
        return isinstance(sid, str) and 8 <= len(sid) <= 64 and isinstance(view, str) and 0 < len(view) <= 40

    def view(self, sid, view):
        if not self._ok(sid, view):
            return False
        now = int(time.time())
        with self.lock:
            self.conn.execute("INSERT INTO views VALUES (?, ?, ?)", (now, sid, view))
            self.conn.execute("INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(sid) DO UPDATE SET last_ts=excluded.last_ts, view=excluded.view",
                              (sid, now, view))
            self.conn.commit()
        return True

    def heartbeat(self, sid, view):
        if not self._ok(sid, view or "-"):
            return False
        now = int(time.time())
        with self.lock:
            self.conn.execute("INSERT INTO sessions VALUES (?, ?, ?) ON CONFLICT(sid) DO UPDATE SET last_ts=excluded.last_ts, view=excluded.view",
                              (sid, now, view))
            self.conn.commit()
        return True

    def online_count(self):
        now = int(time.time())
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM sessions WHERE last_ts >= ?", (now - ONLINE_WINDOW,)).fetchone()[0]

    def stats(self):
        now = int(time.time())
        day_start = int(datetime.now(BKK_TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        week_start = now - PEAK_DAYS * 86400
        with self.lock:
            q = self.conn.execute
            online = q("SELECT COUNT(*) FROM sessions WHERE last_ts >= ?", (now - ONLINE_WINDOW,)).fetchone()[0]
            online_views = q("SELECT view, COUNT(*) FROM sessions WHERE last_ts >= ? GROUP BY view", (now - ONLINE_WINDOW,)).fetchall()
            dau = q("SELECT COUNT(DISTINCT sid) FROM views WHERE ts >= ?", (day_start,)).fetchone()[0]
            dau_prev = q("SELECT COUNT(DISTINCT sid) FROM views WHERE ts >= ? AND ts < ?", (day_start - 86400, day_start)).fetchone()[0]
            views_today = q("SELECT COUNT(*) FROM views WHERE ts >= ?", (day_start,)).fetchone()[0]
            by_view = q("SELECT view, COUNT(*) FROM views WHERE ts >= ? GROUP BY view ORDER BY 2 DESC", (day_start,)).fetchall()
            week_rows = q("SELECT ts FROM views WHERE ts >= ?", (week_start,)).fetchall()
            daily = q("SELECT ts, sid FROM views WHERE ts >= ?", (week_start,)).fetchall()

        by_topic = {t: 0 for t in TOPICS}
        for view, n in by_view:
            by_topic[TOPIC_OF.get(view, "traffic")] += n
        topic_share = [{"topic": t, "views": n, "pct": round(100 * n / views_today) if views_today else 0} for t, n in by_topic.items()]
        topic_share.sort(key=lambda r: -r["views"])

        hours = [0] * 24
        for (ts,) in week_rows:
            hours[datetime.fromtimestamp(ts, BKK_TZ).hour] += 1
        peak = sorted(range(24), key=lambda h: -hours[h])[:3]

        per_day = {}
        for ts, sid in daily:
            per_day.setdefault(datetime.fromtimestamp(ts, BKK_TZ).strftime("%Y-%m-%d"), set()).add(sid)
        dau_series = [{"day": d, "users": len(s)} for d, s in sorted(per_day.items())]

        return {
            "updated_at": now,
            "online": online,
            "online_by_view": [{"view": v, "users": n} for v, n in online_views],
            "dau": dau,
            "dau_yesterday": dau_prev,
            "views_today": views_today,
            "by_view": [{"view": v, "views": n} for v, n in by_view],
            "by_topic": topic_share,
            "hours": hours,
            "peak_hours": [{"hour": h, "views": hours[h]} for h in peak if hours[h] > 0],
            "peak_window_days": PEAK_DAYS,
            "dau_series": dau_series,
        }


telemetry = Telemetry()
