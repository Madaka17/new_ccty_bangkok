import os
import sys
import time
import json
import sqlite3
import threading
import io
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import requests
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from bma_archive import CycleArchiver

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "bma_snapshots")
os.makedirs(CACHE_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "vehicle_counts.db")
CAMERAS_FILE = os.path.join(BASE_DIR, "cameras_bma.json")

# Target YOLO classes for traffic: 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck
VEHICLE_CLASSES = {1: 'motorcycles', 2: 'cars', 3: 'motorcycles', 5: 'trucks', 7: 'trucks'}

# Colors (BGR for OpenCV)
BOX_COLORS = {
    'cars': (220, 160, 50),       # Blueish/Cyan
    'motorcycles': (50, 180, 240), # Gold/Orange
    'trucks': (60, 80, 230),       # Crimson/Red
}

CLASS_THAI = {
    'cars': 'รถยนต์',
    'motorcycles': 'มอไซ',
    'trucks': 'บรรทุก/บัส'
}


class BmaSession:
    """Manages HTTP sessions with BMA Traffic website using thread-local cookies and connection pooling."""

    def __init__(self):
        self._local = threading.local()

    def _get_session(self) -> requests.Session:
        s = getattr(self._local, 'session', None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'th,en-US;q=0.9,en;q=0.8',
            })
            try:
                s.get('https://cpudapp.bangkok.go.th/bmatraffic/index.aspx', timeout=6.0)
            except Exception:
                pass
            self._local.session = s
            self._local.current_camid = None
        return s

    def fetch_snapshot(self, camid: str, timeout: float = 4.0) -> bytes:
        """Fetch raw snapshot JPEG for a camera ID from BMA traffic."""
        s = self._get_session()
        camid_str = str(camid)

        # BMA requires calling PlayVideo.aspx with ID to bind ASP.NET session to this camera
        if getattr(self._local, 'current_camid', None) != camid_str:
            try:
                s.get(
                    f'https://cpudapp.bangkok.go.th/bmatraffic/PlayVideo.aspx?ID={camid_str}',
                    headers={'Referer': 'https://cpudapp.bangkok.go.th/bmatraffic/index.aspx'},
                    timeout=timeout
                )
                self._local.current_camid = camid_str
            except Exception:
                self._local.current_camid = None

        ts_ms = int(time.time() * 1000)
        url = f'https://cpudapp.bangkok.go.th/bmatraffic/show.aspx?image={camid_str}&time={ts_ms}'
        try:
            res = s.get(
                url,
                headers={'Referer': f'https://cpudapp.bangkok.go.th/bmatraffic/PlayVideo.aspx?ID={camid_str}'},
                timeout=timeout
            )
            if res.status_code == 200 and len(res.content) > 2500:
                return res.content
        except Exception:
            pass

        # If placeholder (< 2500 bytes) or failed, session may have expired/reset.
        # Re-initialize session via index.aspx and retry once.
        try:
            s.get('https://cpudapp.bangkok.go.th/bmatraffic/index.aspx', timeout=timeout)
            s.get(
                f'https://cpudapp.bangkok.go.th/bmatraffic/PlayVideo.aspx?ID={camid_str}',
                headers={'Referer': 'https://cpudapp.bangkok.go.th/bmatraffic/index.aspx'},
                timeout=timeout
            )
            self._local.current_camid = camid_str
            ts_ms = int(time.time() * 1000)
            url = f'https://cpudapp.bangkok.go.th/bmatraffic/show.aspx?image={camid_str}&time={ts_ms}'
            res = s.get(
                url,
                headers={'Referer': f'https://cpudapp.bangkok.go.th/bmatraffic/PlayVideo.aspx?ID={camid_str}'},
                timeout=timeout
            )
            if res.status_code == 200 and len(res.content) > 2500:
                return res.content
        except Exception:
            pass

        return None


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

class BmaScanner:
    """High-performance multi-threaded scanner that processes all BMA cameras with YOLO."""

    def __init__(self, detector=None, cameras_file=CAMERAS_FILE):
        self.detector = detector
        self.cameras_file = cameras_file
        self.session = BmaSession()
        self.db = BmaDatabase()
        # Hourly count cycles + every CSV under D:\Data (see bma_archive.py)
        self.archiver = CycleArchiver(self.db)
        self.archiver.run_forever()
        self.cameras = []
        self._load_cameras()

        self.is_scanning = False
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.Lock()

        # Stats
        self.current_index = 0
        self.total_cameras = len(self.cameras)
        self.last_scan_time = None
        self.last_scan_duration = 0.0
        self.cycle_count = 0
        self.download_workers = 3
        self.infer_lock = threading.Lock()

        # Auto background scan every 3 minutes
        self.auto_scan_thread = threading.Thread(target=self._auto_scan_loop, daemon=True)
        self.auto_scan_thread.start()

    def _detect(self, img):
        """(cls_id, conf, x1, y1, x2, y2) per vehicle. Shares the server's detector (tiled 2x2 on
        small frames, per-class thresholds); falls back to a local yolo26m when run standalone."""
        if self.detector and hasattr(self.detector, 'detect_boxes'):
            return self.detector.detect_boxes(img)
        from ultralytics import YOLO
        if not hasattr(self, '_local_model'):
            m_path = 'yolo26x.pt' if os.path.exists(os.path.join(BASE_DIR, 'yolo26x.pt')) else 'yolo26m.pt'
            self._local_model = YOLO(m_path)
        r = self._local_model(img, conf=0.08, classes=[0, 1, 2, 3, 5, 7], imgsz=960, verbose=False)[0]
        return [(int(c), float(cf), int(x1), int(y1), int(x2), int(y2))
                for (x1, y1, x2, y2), cf, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())]

    def _load_cameras(self):
        if os.path.exists(self.cameras_file):
            try:
                with open(self.cameras_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.cameras = data.get("items", [])
                    self.total_cameras = len(self.cameras)
                    print(f"[BMA Scanner] Loaded {len(self.cameras)} BMA cameras")
            except Exception as e:
                print(f"[BMA Scanner] Error loading cameras: {e}")

    def start_scan(self):
        with self.lock:
            if self.is_scanning:
                return {"status": "already_running", "message": "การสแกนกำลังทำงานอยู่"}
            self.is_scanning = True
            self.stop_event.clear()
            self.current_index = 0
            self.thread = threading.Thread(target=self._run_scan_cycle, daemon=True)
            self.thread.start()
            return {"status": "started", "total_cameras": self.total_cameras}

    def stop_scan(self):
        with self.lock:
            self.stop_event.set()
            self.is_scanning = False
            return {"status": "stopped"}

    def get_status(self):
        with self.lock:
            pct = round((self.current_index / max(1, self.total_cameras)) * 100, 1)
            return {
                "is_scanning": self.is_scanning,
                "current_index": self.current_index,
                "total_cameras": self.total_cameras,
                "percent": pct,
                "cycle_count": self.cycle_count,
                "last_scan_time": self.last_scan_time,
                "last_scan_duration": round(self.last_scan_duration, 1)
            }

    def _auto_scan_loop(self):
        """Periodically run scans in background."""
        time.sleep(3.0) # wait for server start
        while True:
            try:
                if not self.is_scanning:
                    self.start_scan()
                # Wait 4 minutes between scan cycles
                time.sleep(240)
            except Exception as e:
                time.sleep(30)

    def _run_scan_cycle(self):
        t0 = time.time()
        print(f"[BMA Scanner] Starting scan cycle #{self.cycle_count + 1} on {len(self.cameras)} cameras...")
        
        # We fetch and process cameras using worker thread pool
        cams = list(self.cameras)
        
        def process_camera(cam):
            if self.stop_event.is_set():
                return
            camid = cam['camid']
            try:
                t_cam = time.time()
                raw_bytes = self.session.fetch_snapshot(camid)
                
                if not raw_bytes:
                    # Offline
                    self.db.update_camera_count(
                        cam, cars=0, motos=0, trucks=0, total=0,
                        level='free', status='offline', latency_ms=0.0, detections=[]
                    )
                    return

                # Decode
                arr = np.frombuffer(raw_bytes, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    self.db.update_camera_count(
                        cam, cars=0, motos=0, trucks=0, total=0,
                        level='free', status='offline', latency_ms=0.0, detections=[]
                    )
                    return

                # YOLO Inference (serialize via detector.model_lock if present)
                t_infer = time.time()
                cars, motos, trucks = 0, 0, 0
                dets = []
                infer_latency = 0.0
                
                try:
                    # Tiled 2x2 inference on the small 352x288 BMA frames (see VehicleDetectorYOLO11x.infer)
                    with self.infer_lock:
                        boxes = self._detect(img)
                    infer_latency = (time.time() - t_infer) * 1000.0
                    for cls_id, conf, x1, y1, x2, y2 in boxes:
                        category = VEHICLE_CLASSES.get(cls_id)
                        if not category:
                            continue
                        if category == 'cars':
                            cars += 1
                        elif category == 'motorcycles':
                            motos += 1
                        elif category == 'trucks':
                            trucks += 1

                        dets.append({
                            'class': category,
                            'name': CLASS_THAI.get(category, category),
                            'conf': round(conf, 2),
                            'box': [x1, y1, x2, y2]
                        })

                    total = cars + motos + trucks
                    
                    # Determine traffic level
                    if total <= 4:
                        level = 'free'
                    elif total <= 12:
                        level = 'moderate'
                    else:
                        level = 'heavy'

                    # Draw annotated image
                    annotated = self._annotate_snapshot(img, dets, cam, cars, motos, trucks, total, level)
                    # Save annotated snapshot to cache
                    out_path = os.path.join(CACHE_DIR, f"{camid}.jpg")
                    cv2.imwrite(out_path, annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])

                    # Update database
                    self.db.update_camera_count(
                        cam, cars, motos, trucks, total, level, 'online', infer_latency, dets
                    )
                except Exception as e:
                    print(f"[BMA Scanner] Error inferring camera {camid}: {e}")
            finally:
                with self.lock:
                    self.current_index += 1

        # Run with ThreadPoolExecutor
        self.current_index = 0
        with ThreadPoolExecutor(max_workers=self.download_workers) as executor:
            futures = []
            for cam in cams:
                if self.stop_event.is_set():
                    break
                futures.append(executor.submit(process_camera, cam))

            for f in futures:
                try:
                    f.result()
                except Exception:
                    pass

        self.last_scan_duration = time.time() - t0
        self.last_scan_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.cycle_count += 1
        self.is_scanning = False
        print(f"[BMA Scanner] Finished scan cycle #{self.cycle_count} in {self.last_scan_duration:.1f}s")
        # Live snapshot CSVs (what every camera sees right now); cycle files are written by the archiver
        try:
            self.archiver.write_live_snapshot(self.db.get_all_latest())
        except Exception as e:
            print(f"[BMA Scanner] live snapshot export failed: {e}")

    def archive_and_reset(self, target_dir=None):
        return self.archiver.archive_and_reset(auto=False)

    def get_comparison(self, period="day"):
        return self.archiver.comparison(period=period)

    def get_cycle_status(self):
        return self.archiver.status()

    def _annotate_snapshot(self, img, dets, cam, cars, motos, trucks, total, level):
        """Draw bounding boxes, counters, and location banner on the image."""
        draw_img = img.copy()
        h, w = draw_img.shape[:2]

        # Boxes in OpenCV; labels are Thai so they are drawn with PIL below (cv2.putText has no Thai glyphs)
        for d in dets:
            x1, y1, x2, y2 = d['box']
            cv2.rectangle(draw_img, (x1, y1), (x2, y2), BOX_COLORS.get(d['class'], (0, 255, 0)), 2)

        # Top overlay bar for camera title and counts
        cv2.rectangle(draw_img, (0, 0), (w, 34), (20, 20, 25), -1)
        
        # Traffic level indicator
        level_color = (80, 200, 100) if level == 'free' else ((60, 180, 240) if level == 'moderate' else (60, 60, 230))
        cv2.circle(draw_img, (14, 17), 6, level_color, -1)

        # Camera Code & Title
        title_text = f"{cam.get('camera_code', '')} | {cam.get('short_title', '')[:28]}"
        # Use English/ASCII fallback for OpenCV putText, or PIL for Thai
        try:
            pil_im = Image.fromarray(cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_im)
            font_path = 'C:\\Windows\\Fonts\\tahoma.ttf'
            if os.path.exists(font_path):
                font = ImageFont.truetype(font_path, 13)
                font_bold = ImageFont.truetype(font_path, 13)
            else:
                font = ImageFont.load_default()
                font_bold = font

            # Box labels (PIL works in RGB; BOX_COLORS are BGR)
            for d in dets:
                x1, y1 = d['box'][:2]
                label = f"{d['name']} {int(d['conf'] * 100)}%"
                b, g, r_ = BOX_COLORS.get(d['class'], (0, 255, 0))
                tw = int(draw.textlength(label, font=font))
                ty = max(0, y1 - 16)
                draw.rectangle((x1, ty, x1 + tw + 6, ty + 16), fill=(r_, g, b))
                draw.text((x1 + 3, ty + 1), label, font=font, fill=(255, 255, 255))

            # Title, cut so it never runs into the counters on the right
            count_str = f"รวม {total} · รถยนต์ {cars} · มอไซ {motos} · บรรทุก {trucks}"
            cw = int(draw.textlength(count_str, font=font))
            avail = w - cw - 40
            while title_text and draw.textlength(title_text, font=font_bold) > avail:
                title_text = title_text[:-2] + '…' if not title_text.endswith('…') else title_text[:-2] + '…'
            draw.text((26, 8), title_text, font=font_bold, fill=(240, 240, 250))
            
            # Counters on right
            draw.text((w - cw - 8, 8), count_str, font=font, fill=(255, 255, 255))
            
            draw_img = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
        except Exception:
            pass

        return draw_img

    def get_analytics(self):
        """Generate comprehensive Data Analysis on the counted vehicle data."""
        latest_cams = self.db.get_all_latest()
        total_cameras = len(self.cameras)
        
        now_ts = int(time.time())
        online_cams = [c for c in latest_cams if c.get('status') == 'online' or (c.get('total', 0) > 0 and c.get('ts', 0) > now_ts - 1800)]
        offline_cams = [c for c in latest_cams if c not in online_cams]
        
        total_cars = sum(c.get('cars', 0) for c in online_cams)
        total_motos = sum(c.get('motorcycles', 0) for c in online_cams)
        total_trucks = sum(c.get('trucks', 0) for c in online_cams)
        total_vehicles = total_cars + total_motos + total_trucks

        # Congestion counts
        free_cams = [c for c in online_cams if c.get('level') == 'free']
        mod_cams = [c for c in online_cams if c.get('level') == 'moderate']
        heavy_cams = [c for c in online_cams if c.get('level') == 'heavy']

        online_count = len([c for c in latest_cams if c.get('status') == 'online'])
        if online_count == 0 and len(online_cams) > 0:
            online_count = len(online_cams)
        free_pct = round((len(free_cams) / max(1, online_count)) * 100, 1)
        mod_pct = round((len(mod_cams) / max(1, online_count)) * 100, 1)
        heavy_pct = round((len(heavy_cams) / max(1, online_count)) * 100, 1)

        # Vehicle type shares
        cars_pct = round((total_cars / max(1, total_vehicles)) * 100, 1)
        motos_pct = round((total_motos / max(1, total_vehicles)) * 100, 1)
        trucks_pct = round((total_trucks / max(1, total_vehicles)) * 100, 1)

        # Top 15 Most Congested Cameras
        top_congested = sorted(online_cams, key=lambda x: x.get('total', 0), reverse=True)[:15]

        # Top 10 Clear / Free Flow Cameras
        top_free = sorted(online_cams, key=lambda x: x.get('total', 0))[:10]

        # District aggregation
        district_data = {}
        for c in online_cams:
            dist = c.get('district') or 'กรุงเทพมหานคร'
            if dist not in district_data:
                district_data[dist] = {
                    'district': dist,
                    'cameras': 0,
                    'cars': 0,
                    'motorcycles': 0,
                    'trucks': 0,
                    'total': 0,
                    'heavy_count': 0
                }
            district_data[dist]['cameras'] += 1
            district_data[dist]['cars'] += c.get('cars', 0)
            district_data[dist]['motorcycles'] += c.get('motorcycles', 0)
            district_data[dist]['trucks'] += c.get('trucks', 0)
            district_data[dist]['total'] += c.get('total', 0)
            if c.get('level') == 'heavy':
                district_data[dist]['heavy_count'] += 1

        districts_list = list(district_data.values())
        for d in districts_list:
            d['avg_vehicles'] = round(d['total'] / max(1, d['cameras']), 1)
        districts_list.sort(key=lambda x: x['total'], reverse=True)

        # Road aggregation
        road_data = {}
        for c in online_cams:
            r = c.get('road') or c.get('title')
            if r not in road_data:
                road_data[r] = {'road': r, 'cameras': 0, 'total': 0, 'level': 'free'}
            road_data[r]['cameras'] += 1
            road_data[r]['total'] += c.get('total', 0)
        
        roads_list = list(road_data.values())
        for r in roads_list:
            r['avg_vehicles'] = round(r['total'] / max(1, r['cameras']), 1)
            r['level'] = 'heavy' if r['avg_vehicles'] > 12 else ('moderate' if r['avg_vehicles'] >= 5 else 'free')
        roads_list.sort(key=lambda x: x['total'], reverse=True)

        # Hourly history
        hourly_history = self.db.get_history_summary(hours=24)

        return {
            "summary": {
                "total_cameras": total_cameras,
                "online_cameras": online_count,
                "offline_cameras": len(offline_cams),
                "total_vehicles": total_vehicles,
                "cars": total_cars,
                "cars_pct": cars_pct,
                "motorcycles": total_motos,
                "motorcycles_pct": motos_pct,
                "trucks": total_trucks,
                "trucks_pct": trucks_pct,
                "avg_per_camera": round(total_vehicles / max(1, online_count), 1),
                "congestion": {
                    "free_count": len(free_cams),
                    "free_pct": free_pct,
                    "moderate_count": len(mod_cams),
                    "moderate_pct": mod_pct,
                    "heavy_count": len(heavy_cams),
                    "heavy_pct": heavy_pct
                }
            },
            "top_congested": top_congested,
            "top_free": top_free,
            "districts": districts_list,
            "major_roads": roads_list[:20],
            "hourly_trends": hourly_history,
            "scan_status": self.get_status()
        }

    def process_image_and_detect(self, cam, raw_bytes):
        """Runs YOLO on raw image bytes, returns (annotated_jpeg_bytes, stats_dict)."""
        if not raw_bytes:
            return None, None
        try:
            arr = np.frombuffer(raw_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None, None

            dets = []
            cars, motos, trucks = 0, 0, 0
            for cls_id, conf, x1, y1, x2, y2 in self._detect(img):
                cat = VEHICLE_CLASSES.get(cls_id)
                if cat:
                    if cat == 'cars': cars += 1
                    elif cat == 'motorcycles': motos += 1
                    elif cat == 'trucks': trucks += 1
                    dets.append({
                        'class': cat,
                        'name': CLASS_THAI.get(cat, cat),
                        'conf': conf,
                        'box': [x1, y1, x2, y2]
                    })

            total = cars + motos + trucks
            level = 'heavy' if total > 12 else ('moderate' if total >= 5 else 'free')
            annotated = self._annotate_snapshot(img, dets, cam, cars, motos, trucks, total, level)
            ret, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                return None, None
            
            stats = {
                'cars': cars,
                'motorcycles': motos,
                'trucks': trucks,
                'total': total,
                'level': level,
                'timestamp': time.time(),
                'detections': dets
            }
            return jpeg.tobytes(), stats
        except Exception as e:
            print(f"[BMA Detect Error] {e}")
            return None, None

    def get_live_snapshot(self, camid: str, annotate: bool = True):
        """Fetches fresh live snapshot from BMA and runs YOLO in real-time."""
        cam = next((c for c in self.cameras if str(c.get('camid')) == str(camid)), None)
        if not cam:
            return None, None
        raw = self.session.fetch_snapshot(str(camid), timeout=7.0)
        if raw and annotate:
            jpeg_bytes, stats = self.process_image_and_detect(cam, raw)
            if jpeg_bytes:
                return jpeg_bytes, stats
            return raw, None
        return raw, None

    def generate_live_mjpeg(self, camid: str, fps: float = 2.0):
        """Continuous live stream of a BMA camera with YOLO detection overlay."""
        cam = next((c for c in self.cameras if str(c.get('camid')) == str(camid)), None)
        if not cam:
            return
        
        interval = 1.0 / max(0.5, min(5.0, fps))
        while True:
            t0 = time.time()
            raw = self.session.fetch_snapshot(str(camid), timeout=4.0)
            if raw:
                jpeg_bytes, _ = self.process_image_and_detect(cam, raw)
                if jpeg_bytes:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
            
            elapsed = time.time() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)
