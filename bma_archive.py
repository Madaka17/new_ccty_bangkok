"""
Automatic count cycles for the BMA camera scanner.

Every scan adds the vehicles seen in each camera snapshot to a running total
("this cycle"). On a fixed schedule (default: every hour, aligned to the clock)
the cycle is archived and the running totals are reset:

    D:\\Data\\
      daily\\YYYY-MM-DD\\<road>.csv      one row per camera per cycle
      daily\\YYYY-MM-DD\\summary.csv     totals per road for that day
      weekly\\YYYY-Www.csv               totals per road per day, the whole week
      monthly\\YYYY-MM.csv               totals per road per day, the whole month
      roads\\<road>.csv                  every cycle ever, one file per road
      summary_daily.csv / summary_weekly.csv / summary_monthly.csv
                                        road x period totals for side-by-side comparison
      all_cameras_traffic_summary.csv    live snapshot, rewritten after every scan
      roads_index.csv                    live per-road snapshot

Counts are vehicles visible in snapshots (one snapshot per camera per scan), so
"total" is a traffic density index rather than vehicles passed. It is the same
metric every day, so day/week/month comparisons stay meaningful.
"""
import csv
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta

DATA_DIR = os.getenv("BMA_DATA_DIR", r"D:\Data")
CYCLE_MINUTES = max(5, int(os.getenv("BMA_CYCLE_MINUTES", "60")))

CYCLE_HEADER = ["Cycle_Start", "Cycle_End", "Date", "Camera_ID", "Camera_Code", "Location", "Road", "District",
                "Scans", "Cars", "Motorcycles", "Trucks", "Total_Vehicles", "Avg_Per_Scan", "Traffic_Level",
                "Latitude", "Longitude"]
ROAD_DAY_HEADER = ["Date", "Road", "Cameras", "Scans", "Cars", "Motorcycles", "Trucks", "Total_Vehicles", "Avg_Per_Scan"]


def safe_name(name):
    s = re.sub(r'[\\/*?:"<>|]', "_", (name or "").strip())
    return s or "ถนนทั่วไป"


def _week_key(dt):
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def _period_keys(dt):
    return dt.strftime("%Y-%m-%d"), _week_key(dt), dt.strftime("%Y-%m")


class CycleArchiver:
    """Owns the cycle schedule and every CSV under DATA_DIR. Shares the scanner's SQLite file."""

    def __init__(self, db, data_dir=DATA_DIR, cycle_minutes=CYCLE_MINUTES):
        self.db = db                      # BmaDatabase (for its lock + path)
        self.data_dir = data_dir
        self.cycle_seconds = cycle_minutes * 60
        self.last_archive = None          # dict from the last archive run
        self.last_error = None
        self._init_schema()
        if not self._meta("cycle_started"):
            self._set_meta("cycle_started", str(int(time.time())))

    # ------------------------------------------------------------ db helpers
    def _conn(self):
        return sqlite3.connect(self.db.db_path, check_same_thread=False)

    def _init_schema(self):
        with self.db.lock:
            conn = self._conn()
            conn.execute("CREATE TABLE IF NOT EXISTS bma_meta (key TEXT PRIMARY KEY, value TEXT)")
            cols = [c[1] for c in conn.execute("PRAGMA table_info(bma_latest)").fetchall()]
            for col in ("acc_cars", "acc_motorcycles", "acc_trucks", "acc_total", "acc_scans"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE bma_latest ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
            # Per-cycle archive rows: what each camera accumulated between two resets
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bma_cycles (
                    cycle_start INTEGER NOT NULL,
                    cycle_end   INTEGER NOT NULL,
                    date        TEXT NOT NULL,
                    week        TEXT NOT NULL,
                    month       TEXT NOT NULL,
                    camid       TEXT NOT NULL,
                    camera_code TEXT,
                    title       TEXT,
                    road        TEXT,
                    district    TEXT,
                    scans       INTEGER NOT NULL DEFAULT 0,
                    cars        INTEGER NOT NULL DEFAULT 0,
                    motorcycles INTEGER NOT NULL DEFAULT 0,
                    trucks      INTEGER NOT NULL DEFAULT 0,
                    total       INTEGER NOT NULL DEFAULT 0,
                    level       TEXT,
                    latitude    REAL,
                    longitude   REAL,
                    PRIMARY KEY (cycle_end, camid)
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_cycles_date ON bma_cycles (date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_cycles_week ON bma_cycles (week)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_cycles_month ON bma_cycles (month)")
            conn.commit()
            conn.close()

    def _meta(self, key):
        with self.db.lock:
            conn = self._conn()
            row = conn.execute("SELECT value FROM bma_meta WHERE key = ?", (key,)).fetchone()
            conn.close()
        return row[0] if row else None

    def _set_meta(self, key, value):
        with self.db.lock:
            conn = self._conn()
            conn.execute("INSERT INTO bma_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
            conn.commit()
            conn.close()

    # ------------------------------------------------------------ schedule
    def cycle_started(self):
        return int(self._meta("cycle_started") or time.time())

    def next_reset(self, since=None):
        """First clock-aligned boundary strictly after `since` (default: now), in local time."""
        since = since or time.time()
        offset = -time.timezone if not time.localtime(since).tm_isdst else -time.altzone
        local = int(since) + offset
        return (local // self.cycle_seconds + 1) * self.cycle_seconds - offset

    def status(self):
        with self.db.lock:
            conn = self._conn()
            row = conn.execute("SELECT COALESCE(SUM(acc_total),0), COALESCE(SUM(acc_cars),0), COALESCE(SUM(acc_motorcycles),0), "
                               "COALESCE(SUM(acc_trucks),0), COALESCE(MAX(acc_scans),0), COUNT(*) FROM bma_latest").fetchone()
            cycles = conn.execute("SELECT COUNT(DISTINCT cycle_end) FROM bma_cycles").fetchone()[0]
            conn.close()
        return {
            "data_dir": self.data_dir,
            "cycle_minutes": self.cycle_seconds // 60,
            "cycle_started": self.cycle_started(),
            "next_reset": self.next_reset(),
            "cycle": {"total": row[0], "cars": row[1], "motorcycles": row[2], "trucks": row[3], "scans": row[4], "cameras": row[5]},
            "cycles_archived": cycles,
            "last_archive": self.last_archive,
            "last_error": self.last_error,
        }

    def run_forever(self):
        """Archive + reset on every clock-aligned boundary. Catches up if the server was down."""
        threading.Thread(target=self._loop, daemon=True, name="bma-cycle").start()

    def _loop(self):
        time.sleep(5)
        while True:
            try:
                # Reset at the first clock boundary after the cycle began (e.g. every :00 for 60 min cycles)
                if time.time() >= self.next_reset(self.cycle_started()):
                    self.archive_and_reset(auto=True)
            except Exception as e:
                self.last_error = str(e)
                print(f"[BMA Cycle] archive failed: {e}")
            wait = max(5.0, self.next_reset() - time.time() + 1)
            time.sleep(min(wait, 60))

    # ------------------------------------------------------------ archive
    def archive_and_reset(self, auto=False):
        now = int(time.time())
        start = self.cycle_started()
        with self.db.lock:
            conn = self._conn()
            conn.row_factory = sqlite3.Row
            cams = [dict(r) for r in conn.execute("SELECT * FROM bma_latest WHERE acc_scans > 0").fetchall()]
            conn.close()
        if not cams:
            self._set_meta("cycle_started", str(now))
            return {"status": "empty", "cycle_start": start, "cycle_end": now}

        end_dt = datetime.fromtimestamp(now)
        date_s, week_s, month_s = _period_keys(end_dt)
        rows = []
        for c in cams:
            rows.append({
                "cycle_start": start, "cycle_end": now, "date": date_s, "week": week_s, "month": month_s,
                "camid": c["camid"], "camera_code": c.get("camera_code") or "", "title": c.get("title") or "",
                "road": (c.get("road") or c.get("title") or "ถนนทั่วไป").strip(), "district": c.get("district") or "",
                "scans": c["acc_scans"], "cars": c["acc_cars"], "motorcycles": c["acc_motorcycles"],
                "trucks": c["acc_trucks"], "total": c["acc_total"], "level": c.get("level") or "",
                "latitude": c.get("latitude"), "longitude": c.get("longitude"),
            })

        with self.db.lock:
            conn = self._conn()
            conn.executemany("""INSERT OR REPLACE INTO bma_cycles
                (cycle_start, cycle_end, date, week, month, camid, camera_code, title, road, district,
                 scans, cars, motorcycles, trucks, total, level, latitude, longitude)
                VALUES (:cycle_start, :cycle_end, :date, :week, :month, :camid, :camera_code, :title, :road, :district,
                        :scans, :cars, :motorcycles, :trucks, :total, :level, :latitude, :longitude)""", rows)
            tot = {k: sum(r[k] for r in rows) for k in ("cars", "motorcycles", "trucks", "total")}
            conn.execute("""INSERT OR REPLACE INTO bma_archives (archive_id, ts, date_str, total_cameras, online_cameras,
                total_vehicles, cars, motorcycles, trucks, free_count, moderate_count, heavy_count, csv_dir, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (f"CYC-{end_dt.strftime('%Y%m%d-%H%M%S')}", now, end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                          len(rows), sum(1 for c in cams if c.get("status") == "online"),
                          tot["total"], tot["cars"], tot["motorcycles"], tot["trucks"],
                          sum(1 for r in rows if r["level"] == "free"), sum(1 for r in rows if r["level"] == "moderate"),
                          sum(1 for r in rows if r["level"] == "heavy"), self.data_dir,
                          f"{'auto' if auto else 'manual'} cycle {self.cycle_seconds // 60} min"))
            conn.execute("UPDATE bma_latest SET acc_cars = 0, acc_motorcycles = 0, acc_trucks = 0, acc_total = 0, acc_scans = 0")
            conn.execute("INSERT INTO bma_meta (key, value) VALUES ('cycle_started', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(now),))
            conn.commit()
            conn.close()

        files = self.write_cycle_files(rows, end_dt)
        self.write_period_files(end_dt)
        self.last_archive = {"ts": now, "cycle_start": start, "cameras": len(rows), **tot, "files": files}
        self.last_error = None
        print(f"[BMA Cycle] archived {len(rows)} cameras, {tot['total']} vehicles -> {self.data_dir}")
        return {"status": "ok", **self.last_archive}

    # ------------------------------------------------------------ csv writers
    def _open_append(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        f = open(path, "a", encoding="utf-8-sig", newline="")
        return f, csv.writer(f), new

    def write_cycle_files(self, rows, end_dt):
        """Append this cycle's rows to daily/<date>/<road>.csv and roads/<road>.csv."""
        by_road = {}
        for r in rows:
            by_road.setdefault(r["road"], []).append(r)
        date_s = end_dt.strftime("%Y-%m-%d")
        written = 0
        for road, items in by_road.items():
            for path in (os.path.join(self.data_dir, "daily", date_s, f"{safe_name(road)}.csv"),
                         os.path.join(self.data_dir, "roads", f"{safe_name(road)}.csv")):
                f, w, new = self._open_append(path)
                with f:
                    if new:
                        w.writerow(CYCLE_HEADER)
                    for r in items:
                        w.writerow([
                            datetime.fromtimestamp(r["cycle_start"]).strftime("%Y-%m-%d %H:%M:%S"),
                            datetime.fromtimestamp(r["cycle_end"]).strftime("%Y-%m-%d %H:%M:%S"),
                            r["date"], r["camid"], r["camera_code"], r["title"], r["road"], r["district"],
                            r["scans"], r["cars"], r["motorcycles"], r["trucks"], r["total"],
                            round(r["total"] / max(1, r["scans"]), 2), r["level"], r["latitude"], r["longitude"],
                        ])
                written += 1
        return written

    def _road_day_rows(self, where, args):
        with self.db.lock:
            conn = self._conn()
            rows = conn.execute(f"""
                SELECT date, road, COUNT(DISTINCT camid), SUM(scans), SUM(cars), SUM(motorcycles), SUM(trucks), SUM(total)
                FROM bma_cycles WHERE {where} GROUP BY date, road ORDER BY date, SUM(total) DESC""", args).fetchall()
            conn.close()
        return [[d, road, n, sc, c, m, t, tot, round(tot / max(1, sc), 2)] for d, road, n, sc, c, m, t, tot in rows]

    def _write_rows(self, path, header, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    def write_period_files(self, end_dt):
        """Rewrite the daily summary, the current week + month files and the three comparison tables."""
        date_s, week_s, month_s = _period_keys(end_dt)
        self._write_rows(os.path.join(self.data_dir, "daily", date_s, "summary.csv"), ROAD_DAY_HEADER,
                         self._road_day_rows("date = ?", (date_s,)))
        self._write_rows(os.path.join(self.data_dir, "weekly", f"{week_s}.csv"), ROAD_DAY_HEADER,
                         self._road_day_rows("week = ?", (week_s,)))
        self._write_rows(os.path.join(self.data_dir, "monthly", f"{month_s}.csv"), ROAD_DAY_HEADER,
                         self._road_day_rows("month = ?", (month_s,)))
        for period, fname in (("date", "summary_daily.csv"), ("week", "summary_weekly.csv"), ("month", "summary_monthly.csv")):
            with self.db.lock:
                conn = self._conn()
                rows = conn.execute(f"""
                    SELECT {period}, road, COUNT(DISTINCT camid), SUM(scans), SUM(cars), SUM(motorcycles), SUM(trucks), SUM(total)
                    FROM bma_cycles GROUP BY {period}, road ORDER BY {period}, SUM(total) DESC""").fetchall()
                conn.close()
            label = {"date": "Date", "week": "Week", "month": "Month"}[period]
            self._write_rows(os.path.join(self.data_dir, fname), [label] + ROAD_DAY_HEADER[1:],
                             [[p, road, n, sc, c, m, t, tot, round(tot / max(1, sc), 2)] for p, road, n, sc, c, m, t, tot in rows])

    def rebuild_files(self):
        """Regenerate daily/, weekly/, monthly/ and roads/ from the archived cycles (after moving old exports away)."""
        import shutil
        for sub in ("daily", "weekly", "monthly", "roads"):
            shutil.rmtree(os.path.join(self.data_dir, sub), ignore_errors=True)
        with self.db.lock:
            conn = self._conn()
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute("SELECT * FROM bma_cycles ORDER BY cycle_end").fetchall()]
            conn.close()
        by_end = {}
        for r in rows:
            by_end.setdefault(r["cycle_end"], []).append(r)
        for end, items in sorted(by_end.items()):
            self.write_cycle_files(items, datetime.fromtimestamp(end))
        for key in sorted({(r["date"], r["week"], r["month"]) for r in rows}):
            self.write_period_files(datetime.strptime(key[0], "%Y-%m-%d"))
        return len(rows)

    def write_live_snapshot(self, cams):
        """Refreshed after every scan: what every camera sees right now, plus a per-road roll-up."""
        now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_rows(os.path.join(self.data_dir, "all_cameras_traffic_summary.csv"),
                         ["Timestamp", "Camera_ID", "Camera_Code", "Location", "Road", "District", "Cars", "Motorcycles", "Trucks",
                          "Total_Vehicles", "Traffic_Level", "Status", "Cycle_Scans", "Cycle_Total", "Latitude", "Longitude"],
                         [[now_s, c.get("camid"), c.get("camera_code"), c.get("title"), c.get("road"), c.get("district"),
                           c.get("cars", 0), c.get("motorcycles", 0), c.get("trucks", 0), c.get("total", 0), c.get("level"),
                           c.get("status"), c.get("acc_scans", 0), c.get("acc_total", 0), c.get("latitude"), c.get("longitude")]
                          for c in cams])
        by_road = {}
        for c in cams:
            by_road.setdefault((c.get("road") or c.get("title") or "ถนนทั่วไป").strip(), []).append(c)
        rows = []
        for road, items in sorted(by_road.items(), key=lambda kv: -sum(i.get("total", 0) for i in kv[1])):
            tot = sum(i.get("total", 0) for i in items)
            lvl = "หนาแน่น" if tot > 12 else ("ปานกลาง" if tot >= 5 else "คล่องตัว")
            rows.append([road, len(items), tot, sum(i.get("cars", 0) for i in items), sum(i.get("motorcycles", 0) for i in items),
                         sum(i.get("trucks", 0) for i in items), sum(i.get("acc_total", 0) for i in items), lvl, now_s])
        self._write_rows(os.path.join(self.data_dir, "roads_index.csv"),
                         ["Road", "Cameras_Count", "Total_Vehicles", "Cars", "Motorcycles", "Trucks", "Cycle_Total", "Congestion_Level", "Last_Export"], rows)

    # ------------------------------------------------------------ comparison (dashboard)
    def comparison(self, period="day", roads=15):
        """Current period vs previous period, per road and overall, from archived cycles only (no estimates)."""
        col = {"day": "date", "week": "week", "month": "month"}.get(period, "date")
        now = datetime.now()
        cur = _period_keys(now)[("date", "week", "month").index(col)]
        prev_dt = now - {"date": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=now.day)}[col]
        prev = _period_keys(prev_dt)[("date", "week", "month").index(col)]
        limit = {"date": 14, "week": 8, "month": 6}[col]
        with self.db.lock:
            conn = self._conn()
            series = conn.execute(f"""
                SELECT {col}, SUM(cars), SUM(motorcycles), SUM(trucks), SUM(total), SUM(scans), COUNT(DISTINCT camid), COUNT(DISTINCT cycle_end)
                FROM bma_cycles GROUP BY {col} ORDER BY {col} DESC LIMIT ?""", (limit,)).fetchall()
            per_road = conn.execute(f"""
                SELECT road, {col}, SUM(cars), SUM(motorcycles), SUM(trucks), SUM(total), SUM(scans)
                FROM bma_cycles WHERE {col} IN (?, ?) GROUP BY road, {col}""", (cur, prev)).fetchall()
            archives = [dict(zip(("archive_id", "ts", "date_str", "total_vehicles", "cars", "motorcycles", "trucks", "total_cameras"), r))
                        for r in conn.execute("SELECT archive_id, ts, date_str, total_vehicles, cars, motorcycles, trucks, total_cameras "
                                              "FROM bma_archives ORDER BY ts DESC LIMIT 12").fetchall()]
            conn.close()

        chart = [{"period_key": k, "label": k[5:] if col == "date" else k, "cars": c, "motorcycles": m, "trucks": t, "total": tot,
                  "scans": sc, "cam_count": n, "cycles": cy, "avg_per_scan": round(tot / max(1, sc), 2)}
                 for k, c, m, t, tot, sc, n, cy in reversed(series)]
        cur_d = next((x for x in chart if x["period_key"] == cur), None)
        prev_d = next((x for x in chart if x["period_key"] == prev), None)

        roads_map = {}
        for road, key, c, m, t, tot, sc in per_road:
            slot = roads_map.setdefault(road, {"road": road, "cur": None, "prev": None})
            slot["cur" if key == cur else "prev"] = {"cars": c, "motorcycles": m, "trucks": t, "total": tot, "scans": sc}
        road_rows = []
        for r in roads_map.values():
            c_tot = r["cur"]["total"] if r["cur"] else 0
            p_tot = r["prev"]["total"] if r["prev"] else None
            road_rows.append({
                "road": r["road"], "current_volume": c_tot, "previous_volume": p_tot,
                "diff": None if p_tot is None else c_tot - p_tot,
                "diff_pct": None if not p_tot else round((c_tot - p_tot) * 100.0 / p_tot, 1),
                "cars": r["cur"]["cars"] if r["cur"] else 0, "motorcycles": r["cur"]["motorcycles"] if r["cur"] else 0,
                "trucks": r["cur"]["trucks"] if r["cur"] else 0,
                "avg_per_scan": round(c_tot / max(1, r["cur"]["scans"]), 2) if r["cur"] else 0,
            })
        road_rows.sort(key=lambda x: -x["current_volume"])

        labels = {"date": ("วันนี้", "เมื่อวาน", "รายวัน"), "week": ("สัปดาห์นี้", "สัปดาห์ที่แล้ว", "รายสัปดาห์"),
                  "month": ("เดือนนี้", "เดือนที่แล้ว", "รายเดือน")}[col]
        c_tot = cur_d["total"] if cur_d else 0
        p_tot = prev_d["total"] if prev_d else None
        return {
            "period": period, "title": f"เปรียบเทียบปริมาณจราจร{labels[2]}", "curr_label": labels[0], "prev_label": labels[1],
            "current_key": cur, "previous_key": prev,
            "metrics": {
                "current_total": c_tot, "previous_total": p_tot,
                "diff": None if p_tot is None else c_tot - p_tot,
                "diff_pct": None if not p_tot else round((c_tot - p_tot) * 100.0 / p_tot, 1),
                "current_cars": cur_d["cars"] if cur_d else 0, "current_motos": cur_d["motorcycles"] if cur_d else 0,
                "current_trucks": cur_d["trucks"] if cur_d else 0,
                "prev_cars": prev_d["cars"] if prev_d else None, "prev_motos": prev_d["motorcycles"] if prev_d else None,
                "prev_trucks": prev_d["trucks"] if prev_d else None,
                "current_cycles": cur_d["cycles"] if cur_d else 0, "previous_cycles": prev_d["cycles"] if prev_d else 0,
            },
            "chart_data": chart,
            "road_comparisons": road_rows[:roads],
            "archives": archives,
            "cycle": self.status(),
            "drive_d": self.files_status(),
        }

    def files_status(self):
        out = {"path": self.data_dir, "exists": os.path.isdir(self.data_dir), "folders": {}, "total_files": 0}
        if not out["exists"]:
            return out
        for sub in ("daily", "weekly", "monthly", "roads"):
            p = os.path.join(self.data_dir, sub)
            try:
                names = sorted(os.listdir(p)) if os.path.isdir(p) else []
            except OSError:
                names = []
            out["folders"][sub] = {"count": len(names), "latest": names[-5:]}
            out["total_files"] += len(names)
        out["root_files"] = sorted(f for f in os.listdir(self.data_dir) if f.lower().endswith(".csv"))
        return out
