"""
SQLite storage of the BMA camera counts (vehicle_counts.db): the latest figures per camera and their history.
Moved out of bma_service.py (Oct 2026).
"""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime

from backend.core.instance import DATA_DIR


DB_PATH = os.path.join(DATA_DIR, "vehicle_counts.db")


class BmaDatabase:
    """Manages SQLite storage for BMA vehicle counts, latest metrics, and historical logs."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bma_latest (
                    camid           TEXT PRIMARY KEY,
                    camera_code     TEXT,
                    title           TEXT,
                    road            TEXT,
                    district        TEXT,
                    latitude        REAL,
                    longitude       REAL,
                    cars            INTEGER NOT NULL DEFAULT 0,
                    motorcycles     INTEGER NOT NULL DEFAULT 0,
                    trucks          INTEGER NOT NULL DEFAULT 0,
                    total           INTEGER NOT NULL DEFAULT 0,
                    level           TEXT NOT NULL DEFAULT 'free',
                    status          TEXT NOT NULL DEFAULT 'offline',
                    latency_ms      REAL DEFAULT 0.0,
                    ts              INTEGER NOT NULL DEFAULT 0,
                    detections      TEXT DEFAULT '[]'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bma_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    camid           TEXT NOT NULL,
                    hour            TEXT NOT NULL,
                    cars            INTEGER NOT NULL DEFAULT 0,
                    motorcycles     INTEGER NOT NULL DEFAULT 0,
                    trucks          INTEGER NOT NULL DEFAULT 0,
                    total           INTEGER NOT NULL DEFAULT 0,
                    level           TEXT NOT NULL DEFAULT 'free',
                    ts              INTEGER NOT NULL,
                    date            TEXT,
                    week            TEXT,
                    month           TEXT,
                    road            TEXT,
                    district        TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bma_archives (
                    archive_id      TEXT PRIMARY KEY,
                    ts              INTEGER NOT NULL,
                    date_str        TEXT NOT NULL,
                    total_cameras   INTEGER NOT NULL,
                    online_cameras  INTEGER NOT NULL,
                    total_vehicles  INTEGER NOT NULL,
                    cars            INTEGER NOT NULL,
                    motorcycles     INTEGER NOT NULL,
                    trucks          INTEGER NOT NULL,
                    free_count      INTEGER NOT NULL,
                    moderate_count  INTEGER NOT NULL,
                    heavy_count     INTEGER NOT NULL,
                    csv_dir         TEXT NOT NULL,
                    notes           TEXT DEFAULT ''
                )
            """)
            # Ensure columns exist if table was previously created
            existing_cols = [c[1] for c in conn.execute("PRAGMA table_info(bma_history)").fetchall()]
            for col in ['date', 'week', 'month', 'road', 'district']:
                if col not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE bma_history ADD COLUMN {col} TEXT")
                    except Exception:
                        pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_hist_hour ON bma_history (hour)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_hist_cam ON bma_history (camid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_hist_date ON bma_history (date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_hist_week ON bma_history (week)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bma_hist_month ON bma_history (month)")
            conn.commit()
            conn.close()

    def update_camera_count(self, cam_info, cars, motos, trucks, total, level, status, latency_ms, detections):
        now_dt = datetime.now()
        now_ts = int(time.time())
        hour_str = now_dt.strftime('%Y-%m-%dT%H:00')
        date_str = now_dt.strftime('%Y-%m-%d')
        week_str = now_dt.strftime('%Y-W%W')
        month_str = now_dt.strftime('%Y-%m')
        road_str = cam_info.get('road', '')
        district_str = cam_info.get('district', '')
        det_json = json.dumps(detections, ensure_ascii=False)

        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("""
                INSERT INTO bma_latest (
                    camid, camera_code, title, road, district, latitude, longitude,
                    cars, motorcycles, trucks, total, level, status, latency_ms, ts, detections,
                    acc_cars, acc_motorcycles, acc_trucks, acc_total, acc_scans
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          CASE WHEN ? = 'online' THEN ? ELSE 0 END, CASE WHEN ? = 'online' THEN ? ELSE 0 END,
                          CASE WHEN ? = 'online' THEN ? ELSE 0 END, CASE WHEN ? = 'online' THEN ? ELSE 0 END,
                          CASE WHEN ? = 'online' THEN 1 ELSE 0 END)
                ON CONFLICT(camid) DO UPDATE SET
                    camera_code = excluded.camera_code,
                    title = excluded.title,
                    road = excluded.road,
                    district = excluded.district,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    cars = CASE WHEN excluded.status = 'online' THEN excluded.cars ELSE bma_latest.cars END,
                    motorcycles = CASE WHEN excluded.status = 'online' THEN excluded.motorcycles ELSE bma_latest.motorcycles END,
                    trucks = CASE WHEN excluded.status = 'online' THEN excluded.trucks ELSE bma_latest.trucks END,
                    total = CASE WHEN excluded.status = 'online' THEN excluded.total ELSE bma_latest.total END,
                    level = CASE WHEN excluded.status = 'online' THEN excluded.level ELSE bma_latest.level END,
                    status = excluded.status,
                    latency_ms = excluded.latency_ms,
                    ts = excluded.ts,
                    detections = CASE WHEN excluded.status = 'online' THEN excluded.detections ELSE bma_latest.detections END,
                    acc_cars = bma_latest.acc_cars + CASE WHEN excluded.status = 'online' THEN excluded.cars ELSE 0 END,
                    acc_motorcycles = bma_latest.acc_motorcycles + CASE WHEN excluded.status = 'online' THEN excluded.motorcycles ELSE 0 END,
                    acc_trucks = bma_latest.acc_trucks + CASE WHEN excluded.status = 'online' THEN excluded.trucks ELSE 0 END,
                    acc_total = bma_latest.acc_total + CASE WHEN excluded.status = 'online' THEN excluded.total ELSE 0 END,
                    acc_scans = bma_latest.acc_scans + CASE WHEN excluded.status = 'online' THEN 1 ELSE 0 END
            """, (
                cam_info['camid'],
                cam_info.get('camera_code', ''),
                cam_info.get('title', ''),
                cam_info.get('road', ''),
                cam_info.get('district', ''),
                cam_info.get('latitude', 0.0),
                cam_info.get('longitude', 0.0),
                cars, motos, trucks, total, level, status, latency_ms, now_ts, det_json,
                status, cars, status, motos, status, trucks, status, total, status
            ))

            # Record history only when online and counted
            if status == 'online':
                conn.execute("""
                    INSERT INTO bma_history (camid, hour, cars, motorcycles, trucks, total, level, ts, date, week, month, road, district)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (cam_info['camid'], hour_str, cars, motos, trucks, total, level, now_ts, date_str, week_str, month_str, road_str, district_str))

            conn.commit()
            conn.close()

    def get_all_latest(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM bma_latest ORDER BY total DESC").fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_camera_latest(self, camid):
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM bma_latest WHERE camid = ?", (camid,)).fetchone()
            conn.close()
            return dict(row) if row else None

    def get_history_summary(self, hours=24):
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT hour,
                       SUM(cars) as cars,
                       SUM(motorcycles) as motorcycles,
                       SUM(trucks) as trucks,
                       SUM(total) as total,
                       COUNT(DISTINCT camid) as cam_count
                FROM bma_history
                WHERE ts >= ?
                GROUP BY hour
                ORDER BY hour ASC
            """, (int(time.time() - hours * 3600),)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
