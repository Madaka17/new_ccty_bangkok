"""
Best time to travel: for each road, the hour of the day with the fewest cars.
Built from the last 8 weeks of BMA counts (bma_history), read-only.
"""
import re
import sqlite3
import threading
import time
from datetime import date, timedelta
from pathlib import Path

WINDOW_DAYS = 56
RETRY_SECONDS = 60      # wait this long after a failed load
MIN_CELLS = 3          # an hour needs this many camera-days before it gets an average
HOURS = range(6, 23)   # 6:00 .. 22:00, 17 bars
BEST_WORST_HOURS = range(6, 22)

CELLS_SQL = """
    SELECT camid, date, CAST(substr(hour, 12, 2) AS INTEGER) h, AVG(total) a, COUNT(*)
    FROM bma_history
    WHERE date >= ?
    GROUP BY camid, date, h
"""

RAMA_RE = re.compile(r"ถนนพระราม(?:ที่)?\s*(\d+)")


def clean_road(cam):
    """The road name for a camera; 'ถนนพระราม' cameras get their number from the title."""
    road = cam.get("road") or ""
    if road.endswith("ที่") or road == "ถนนพระราม":
        m = RAMA_RE.search(cam.get("title") or "")
        if m:
            return f"ถนนพระรามที่ {m.group(1)}"
        return road
    return road.strip()


def _level(ratio):
    if ratio < 0.6:
        return "free"
    if ratio < 0.85:
        return "moderate"
    return "heavy"


class BestTime:
    """Hourly car averages per road, rebuilt from the database when older than `ttl` seconds."""

    def __init__(self, db_path, cameras, ttl=3600, today=date.today, clock=time.monotonic):
        self.db_path = db_path
        self.cameras = cameras
        self.ttl = ttl
        self.today = today
        self.clock = clock
        self.lock = threading.Lock()
        self.road_of = {str(c.get("camid")): clean_road(c) for c in cameras}
        self._cells = None
        self._built_at = 0.0
        self._built_ts = 0
        self._retry_at = 0.0   # after a failed load, no new attempt before this time
        self._known_roads = set(self.road_of.values()) | {""}

    def is_known_road(self, road):
        """True for '' (all roads) and for any road of the configured cameras."""
        return road in self._known_roads

    def _load_cells(self):
        cutoff = (self.today() - timedelta(days=WINDOW_DAYS)).isoformat()
        # the scanner owns this file; this connection only reads it
        uri = f"file:{Path(self.db_path).absolute().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            rows = conn.execute(CELLS_SQL, (cutoff,)).fetchall()
        finally:
            conn.close()
        return [(str(camid), d, h, a, n) for camid, d, h, a, n in rows if str(camid) in self.road_of]

    def _get_cells(self):
        with self.lock:
            now = self.clock()
            stale = self._cells is None or now - self._built_at >= self.ttl
            if stale and now >= self._retry_at:
                try:
                    self._cells = self._load_cells()
                    self._built_at = now
                    self._built_ts = int(time.time())
                except Exception as e:
                    # keep any old cells; try again in a minute, not on every request
                    self._retry_at = now + RETRY_SECONDS
                    print(f"[BestTime] load failed, keeping {'old' if self._cells is not None else 'no'} data: {e}")
            return self._cells

    def profile(self, road="", day="workday"):
        cells = self._get_cells()
        failed = cells is None
        cells = cells or []
        if road:
            camids = {camid for camid, r in self.road_of.items() if r == road}
        else:
            camids = set(self.road_of)

        mine = [
            c for c in cells
            if c[0] in camids
            and ("workday" if date.fromisoformat(c[1]).weekday() < 5 else "weekend") == day
        ]

        by_hour = {h: [] for h in HOURS}
        for _, _, h, a, _ in mine:
            if h in by_hour:
                by_hour[h].append(a)

        hours = []
        for h in HOURS:
            values = by_hour[h]
            samples = len(values)
            avg = round(sum(values) / samples, 1) if samples >= MIN_CELLS else None
            hours.append({"h": h, "avg": avg, "samples": samples, "level": None})

        with_data = [x for x in hours if x["avg"] is not None]
        top = max((x["avg"] for x in with_data), default=0)
        for x in with_data:
            x["level"] = _level(x["avg"] / top if top else 0.0)

        ranked = [x for x in with_data if x["h"] in BEST_WORST_HOURS]
        best = min(ranked, key=lambda x: x["avg"]) if ranked else None
        worst = max(ranked, key=lambda x: x["avg"]) if ranked else None

        dates = {c[1] for c in mine}

        counts = {}
        for r in self.road_of.values():
            counts[r] = counts.get(r, 0) + 1
        roads = [{"road": r, "cameras": n} for r, n in counts.items()
                 if r.startswith("ถนน") and n >= 2 and not failed]
        roads.sort(key=lambda x: (-x["cameras"], x["road"]))

        return {
            "updated_at": self._built_ts,
            "since": min(dates) if dates else None,
            "days_of_data": len(dates),
            "road": road,
            "day": day,
            "roads": roads,
            "hours": hours,
            "best": {"from": best["h"], "to": best["h"] + 1} if best else None,
            "worst": {"from": worst["h"], "to": worst["h"] + 1} if worst else None,
        }


_shared = None
_shared_lock = threading.Lock()


def shared(scanner):
    """The one BestTime for the running server, built on first use from the scanner's db and cameras."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = BestTime(scanner.db.db_path, scanner.cameras)
        return _shared
