"""
The BMA camera scanner: every few minutes it fetches a frame from each BMA Traffic camera (bma_session), counts
the vehicles with the shared YOLO model, keeps the annotated and plain frames on disk, and stores the counts
(bma_db) for the camera pages and the analytics.
"""
import os
import time
import json
import threading
import hashlib
from datetime import datetime
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.bma import bma_site
from backend.bma.bma_archive import CycleArchiver
from backend.bma.bma_db import BmaDatabase
from backend.bma.bma_session import BmaSession

from backend.core.instance import BASE_DIR  # project root
from backend.core.instance import thai_font
from backend.core.instance import DATA_DIR   # cache / db root: instances/production, or instances/test for the test server
CACHE_DIR = os.path.join(DATA_DIR, "cache", "bma_snapshots")
os.makedirs(CACHE_DIR, exist_ok=True)
# The same frames without the YOLO boxes, for pages that show the plain camera (the live camera wall)
RAW_DIR = os.path.join(CACHE_DIR, "raw")
os.makedirs(RAW_DIR, exist_ok=True)


@lru_cache(maxsize=4)
def _label_font(size):
    """The Thai font for the snapshot labels, loaded once (it was read from disk for every snapshot)."""
    path = thai_font()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def save_raw_frame(camid, jpeg):
    """Keep a camera's newest plain frame: written whole, then swapped in, so a reader never gets half.
    Best effort: while a page reads the old one Windows refuses the swap, and the next frame tries again."""
    path = os.path.join(RAW_DIR, f"{camid}.jpg")
    tmp = f"{path}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(jpeg)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


CAMERAS_FILE = os.path.join(BASE_DIR, "config", "cameras_bma.json")

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


# A scan cycle with fresh frames from fewer than this share of the cameras means the BMA site is down (no
# frames) or frozen (the same picture again). On Oct 1 2026 the whole site answered 404 from 10:19 on.
SOURCE_MIN_SHARE = 0.05


def _pixels_id(img):
    """Same id for the same picture: a frozen feed re-sends identical pixels, a live camera's clock overlay
    changes them every second even on an empty street."""
    return hashlib.md5(img.tobytes()).digest()


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
        # Is the BMA site giving us live pictures? Set after every cycle; see source_status()
        self._frame_ids = {}       # camid -> _pixels_id of its last frame
        raw = [os.path.join(RAW_DIR, f) for f in os.listdir(RAW_DIR) if f.endswith('.jpg')]
        self._last_fresh = max((os.path.getmtime(p) for p in raw), default=None)   # survives a restart
        self.source = {"state": "starting", "site": bma_site.host(), "frames_ok": None, "frames_new": None,
                       "last_frame_at": int(self._last_fresh) if self._last_fresh else None}
        # BMA answers slowly (~1.3 s a picture): 5 at a time with one session per camera (BmaSession)
        # scan the 574 cameras in ~2.5 min; the first cycle after a start binds every session (~10 min)
        self.download_workers = int(os.getenv("BMA_SCAN_WORKERS", "8"))
        # seconds from one cycle's start to the next: the helmet patrol checks each camera this often
        self.scan_interval = int(os.getenv("BMA_SCAN_INTERVAL", "180"))
        self.infer_lock = threading.Lock()
        # HelmetPatrol (helmet_service.py) / WrongWayPatrol (wrongway_service.py) set by the server:
        # both get every snapshot (+ its boxes)
        self.helmet = None
        self.wrongway = None
        # FloodCamWatch (flood_cam_service.py) set by the server: gets every raw snapshot
        self.flood = None

        # Auto background scan every scan_interval
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
                "last_scan_duration": round(self.last_scan_duration, 1),
                "source": dict(self.source),
            }

    def _auto_scan_loop(self):
        """Start a scan cycle every scan_interval, or as soon as the last one ends when it ran longer
        (a plain sleep between cycles skipped a whole turn after a long cycle: twice the time between frames)."""
        time.sleep(3.0) # wait for server start
        last_start = 0.0
        while True:
            try:
                if not self.is_scanning and time.time() - last_start >= self.scan_interval:
                    last_start = time.time()
                    self.start_scan()
            except Exception:
                pass
            time.sleep(5)

    def _run_scan_cycle(self):
        t0 = time.time()
        print(f"[BMA Scanner] Starting scan cycle #{self.cycle_count + 1} on {len(self.cameras)} cameras...")
        
        # We fetch and process cameras using worker thread pool
        cams = list(self.cameras)
        tally = {"ok": 0, "new": 0}   # cameras that sent a picture / a picture different from their last one

        def note_frame(camid, img):
            fid = _pixels_id(img)
            prev = self._frame_ids.get(camid)
            if prev is None:   # first frame since a restart: compare with the one kept on disk
                old = cv2.imread(os.path.join(RAW_DIR, f"{camid}.jpg"))
                prev = _pixels_id(old) if old is not None else None
            self._frame_ids[camid] = fid
            with self.lock:
                tally["ok"] += 1
                if fid != prev:
                    tally["new"] += 1
                    self._last_fresh = time.time()

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
                note_frame(camid, img)
                save_raw_frame(camid, raw_bytes)
                if self.flood is not None:
                    try:
                        self.flood.observe(cam, img)
                    except Exception as e:  # noqa: BLE001 - flood watch is best effort
                        print(f"[BMA Scanner] flood watch failed on {camid}: {e}")

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
                    if self.helmet is not None:
                        try:
                            self.helmet.observe(cam, img, boxes)
                        except Exception as e:  # noqa: BLE001 - patrol is best effort
                            print(f"[BMA Scanner] helmet patrol failed on {camid}: {e}")
                    if self.wrongway is not None:
                        try:
                            self.wrongway.observe(cam, img, boxes)
                        except Exception as e:  # noqa: BLE001
                            print(f"[BMA Scanner] wrong-way patrol failed on {camid}: {e}")
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
        if not self.stop_event.is_set():
            need = SOURCE_MIN_SHARE * max(1, len(cams))
            state = "down" if tally["ok"] < need else "frozen" if tally["new"] < need else "ok"
            if state != "ok":
                print(f"[BMA Scanner] BMA site {state}: {tally['ok']} pictures, {tally['new']} new, from {len(cams)} cameras")
            if state == "down" and bma_site.failover():
                self.session.reset()
                print(f"[BMA Scanner] BMA site moved: now reading {bma_site.base()}")
            self.source = {"state": state, "site": bma_site.host(), "frames_ok": tally["ok"], "frames_new": tally["new"],
                           "last_frame_at": int(self._last_fresh) if self._last_fresh else None}
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
            font = font_bold = _label_font(13)

            # Box labels (PIL works in RGB; BOX_COLORS are BGR)
            for d in dets:
                x1, y1 = d['box'][:2]
                label = f"{d['name']} {int(d['conf'] * 100)}%" if d['conf'] >= 0.5 else d['name']   # unsure: no number
                b, g, r_ = BOX_COLORS.get(d['class'], (0, 255, 0))
                tw = int(draw.textlength(label, font=font))
                ty = max(0, y1 - 16)
                draw.rectangle((x1, ty, x1 + tw + 6, ty + 16), fill=(r_, g, b))
                draw.text((x1 + 3, ty + 1), label, font=font, fill=(255, 255, 255))

            # Title, cut so it never runs into the counters on the right
            count_str = f"รวม {total} · รถยนต์ {cars} · มอไซ {motos} · บรรทุก {trucks}"
            cw = int(draw.textlength(count_str, font=font))
            avail = w - cw - 40
            # One character off at a time. It stops at "…" alone: "…"[:-2] + "…" is "…" again, so the old loop
            # spun forever (holding the GIL) whenever the counters left less room than the "…" itself.
            while len(title_text) > 1 and draw.textlength(title_text, font=font_bold) > avail:
                title_text = title_text.rstrip('…')[:-1] + '…'
            if draw.textlength(title_text, font=font_bold) > avail:
                title_text = ''
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
        if self.source["state"] in ("down", "frozen"):
            # an offline camera keeps its last counts and gets a new ts every cycle, so with the site down the
            # rule above still counted 539 cameras with the morning's traffic as live
            online_cams = []
        offline_cams = [c for c in latest_cams if c not in online_cams]
        
        total_cars = sum(c.get('cars', 0) for c in online_cams)
        total_motos = sum(c.get('motorcycles', 0) for c in online_cams)
        total_trucks = sum(c.get('trucks', 0) for c in online_cams)
        total_vehicles = total_cars + total_motos + total_trucks

        # Congestion counts
        free_cams = [c for c in online_cams if c.get('level') == 'free']
        mod_cams = [c for c in online_cams if c.get('level') == 'moderate']
        heavy_cams = [c for c in online_cams if c.get('level') == 'heavy']

        # Same set the counts come from: status 'online' OR counted in the last 30 min. Counting only
        # status == 'online' gave 1 camera against 300+ counted ones, so free_pct came out as 22400%.
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
        if raw:
            save_raw_frame(camid, raw)
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
