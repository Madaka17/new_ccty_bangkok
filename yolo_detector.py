import cv2
import time
import os
import threading
from collections import deque
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO
from ultralytics.trackers import BYTETracker
from ultralytics.utils import YAML, IterableSimpleNamespace
from ultralytics.utils.checks import check_yaml

# Target classes. COCO IDs: 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck; 0: person is detected only
# as an incident signal (people on the road next to a stopped vehicle) and never counted as a vehicle
PERSON_CLASS = 0
TARGET_CLASSES = [PERSON_CLASS, 1, 2, 3, 5, 7]

# Color mapping (RGB)
CLASS_CONFIG = {
    1: {
        'category': 'มอไซ',          # Group bicycle / e-bike / scooter into motorcycle
        'name_en': 'Motorcycle',
        'color': (181, 163, 222),    # Lavender
        'bg_color': (235, 229, 247)
    },
    2: {
        'category': 'รถยนต์',
        'name_en': 'Car',
        'color': (157, 191, 146),    # Sage
        'bg_color': (227, 238, 221)
    },
    3: {
        'category': 'มอไซ',
        'name_en': 'Motorcycle',
        'color': (181, 163, 222),    # Lavender
        'bg_color': (235, 229, 247)
    },
    5: {
        'category': 'รถบรรทุก',       # Bus grouped as heavy transport / truck
        'name_en': 'Bus',
        'color': (245, 168, 140),    # Apricot
        'bg_color': (253, 230, 221)
    },
    7: {
        'category': 'รถบรรทุก',
        'name_en': 'Truck',
        'color': (245, 168, 140),    # Apricot
        'bg_color': (253, 230, 221)
    }
}
DEFAULT_CLASS = {
    'category': 'รถยนต์',
    'name_en': 'Vehicle',
    'color': (157, 191, 146),
    'bg_color': (227, 238, 221)
}
CAT_KEY = {'รถยนต์': 'cars', 'มอไซ': 'motorcycles', 'รถบรรทุก': 'trucks'}

LEVEL_TEXT = {
    'free': ("การจราจรคล่องตัว 🟢", (157, 191, 146)),
    'moderate': ("การจราจรปานกลาง 🟡", (237, 197, 92)),
    'heavy': ("การจราจรหนาแน่น 🔴", (245, 168, 140)),
}


class VehicleTracker:
    """Per-stream ByteTrack + counting of vehicles that pass + traffic level from motion.

    One instance per video stream. The YOLO model itself is shared (see VehicleDetectorYOLO11x.infer).
    """

    # A tracked vehicle moving slower than this (box-heights per second) counts as stopped
    MOVING_SPEED = 0.3
    # Seconds of video over which a vehicle's speed is measured
    SPEED_WINDOW = 1.0
    # Forget a track after this long without being seen
    TRACK_TTL = 10.0
    # Seconds of video over which vehicle count and moving share are averaged for the traffic level
    LEVEL_WINDOW = 60.0
    # Seconds of video over which passes are counted for the turnover signal
    TURNOVER_WINDOW = 60.0
    # A vehicle stopped this long while the rest of the traffic flows is an incident candidate
    STOPPED_ALERT = 60.0
    STOPPED_SPEED = 0.1
    # Collision: a vehicle goes from moving to stopped within this many seconds...
    SUDDEN_STOP_S = 2.0
    # ...touching another vehicle that is also stopped, and both stay stopped this long
    COLLISION_CONFIRM_S = 5.0

    _cfg = None

    def __init__(self, level_window=None):
        if VehicleTracker._cfg is None:
            VehicleTracker._cfg = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
        self.tracker = BYTETracker(args=VehicleTracker._cfg)
        self.level_window = level_window or self.LEVEL_WINDOW
        # track_id -> {'t': last seen, 'seen': frames, 'speed', 'path': deque of (t, cx, cy)}
        self._tracks = {}
        # Smoothed {'t', 'moving' (%), 'total'} used for the traffic level
        self._flow = None
        # Video times of confirmed passes in the last TURNOVER_WINDOW seconds, and first frame time
        self._passes = deque()
        self._t_first = None
        # People seen in the last frame, as (cx, cy, h) boxes
        self.persons = []
        self.last_stats = None

    def update(self, result, frame, frame_t):
        """Track detections of one frame.

        Returns (dets, stats, new_vehicles):
          dets: list of (cls_id, conf, x1, y1, x2, y2, track_id)
          stats: cars/motorcycles/trucks/total/moving_pct/level/traffic_level
          new_vehicles: {'cars', 'motorcycles', 'trucks'} confirmed as passing in this frame
        """
        det = result.boxes.cpu().numpy()
        tracks = self.tracker.update(det, frame) if len(det) else np.empty((0, 8))
        # tracks rows: x1, y1, x2, y2, track_id, conf, cls, det_idx

        counts = {'cars': 0, 'motorcycles': 0, 'trucks': 0}
        new_vehicles = {'cars': 0, 'motorcycles': 0, 'trucks': 0}
        dets = []
        moving = 0
        measured = 0
        now = frame_t

        persons = []
        tracked_boxes = []

        # Separate person rows and vehicle rows from ByteTrack
        person_rows = []
        veh_rows = []
        for row in tracks:
            cls_id = int(row[6])
            if cls_id == PERSON_CLASS:
                person_rows.append(row)
            else:
                veh_rows.append(row)

        used_person_indices = set()

        for row in veh_rows:
            x1, y1, x2, y2 = [int(v) for v in row[:4]]
            track_id = int(row[4])
            conf = float(row[5])
            cls_id = int(row[6])

            # Merge rider (person) into motorcycle/bicycle if overlapping
            if cls_id in (1, 3):
                for p_i, p_row in enumerate(person_rows):
                    if p_i in used_person_indices:
                        continue
                    px1, py1, px2, py2 = [int(v) for v in p_row[:4]]
                    if not (px2 < x1 or px1 > x2 or py2 < y1 - 40 or py1 > y2 + 40):
                        x1, y1 = min(x1, px1), min(y1, py1)
                        x2, y2 = max(x2, px2), max(y2, py2)
                        conf = max(conf, float(p_row[5]))
                        used_person_indices.add(p_i)

            cat = CLASS_CONFIG.get(cls_id, DEFAULT_CLASS)['category']
            counts[CAT_KEY[cat]] += 1
            dets.append((cls_id, conf, x1, y1, x2, y2, track_id))
            tracked_boxes.append((x1, y1, x2, y2))

            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            tr = self._tracks.get(track_id)
            if tr is None:
                tr = self._tracks[track_id] = {'t': now, 'speed': None, 'path': deque(), 'seen': 0}
            tr['t'] = now
            tr['seen'] += 1
            if tr['seen'] == 2:
                new_vehicles[CAT_KEY[cat]] += 1
                self._passes.append(now)
            path = tr['path']
            path.append((now, cx, cy))
            while path and now - path[0][0] > self.SPEED_WINDOW * 1.5:
                path.popleft()
            t0, x0, y0 = path[0]
            if now - t0 >= self.SPEED_WINDOW * 0.6:
                tr['speed'] = ((cx - x0) ** 2 + (cy - y0) ** 2) ** 0.5 / max(1.0, y2 - y1) / (now - t0)
                if tr['speed'] < self.STOPPED_SPEED:
                    tr.setdefault('stop_t', now)
                elif tr['speed'] >= self.MOVING_SPEED:
                    tr.pop('stop_t', None)
                tr['box'] = (cx, cy, max(1, y2 - y1), x1, y1, x2, y2)
            if tr['speed'] is not None:
                measured += 1
                if tr['speed'] >= self.MOVING_SPEED:
                    moving += 1

        # Handle remaining tracked persons: lone rider detected as person in traffic
        for p_i, p_row in enumerate(person_rows):
            px1, py1, px2, py2 = [int(v) for v in p_row[:4]]
            p_track_id = int(p_row[4])
            p_conf = float(p_row[5])
            persons.append(((px1 + px2) / 2.0, (py1 + py2) / 2.0, max(1, py2 - py1)))
            if p_i in used_person_indices:
                continue
            h = py2 - py1
            # Standalone person in traffic view -> motorcycle rider
            if h <= 200:
                cat = 'มอไซ'
                counts[CAT_KEY[cat]] += 1
                dets.append((3, p_conf, px1, py1, px2, py2, p_track_id))
                tracked_boxes.append((px1, py1, px2, py2))

                cx, cy = (px1 + px2) / 2.0, (py1 + py2) / 2.0
                tr = self._tracks.get(p_track_id)
                if tr is None:
                    tr = self._tracks[p_track_id] = {'t': now, 'speed': None, 'path': deque(), 'seen': 0}
                tr['t'] = now
                tr['seen'] += 1
                if tr['seen'] == 2:
                    new_vehicles['motorcycles'] += 1
                    self._passes.append(now)
                path = tr['path']
                path.append((now, cx, cy))
                while path and now - path[0][0] > self.SPEED_WINDOW * 1.5:
                    path.popleft()
                t0, x0, y0 = path[0]
                if now - t0 >= self.SPEED_WINDOW * 0.6:
                    tr['speed'] = ((cx - x0) ** 2 + (cy - y0) ** 2) ** 0.5 / max(1.0, py2 - py1) / (now - t0)
                    if tr['speed'] < self.STOPPED_SPEED:
                        tr.setdefault('stop_t', now)
                    elif tr['speed'] >= self.MOVING_SPEED:
                        tr.pop('stop_t', None)
                    tr['box'] = (cx, cy, max(1, py2 - py1), px1, py1, px2, py2)
                if tr['speed'] is not None:
                    measured += 1
                    if tr['speed'] >= self.MOVING_SPEED:
                        moving += 1

        # Also capture and show raw detections that ByteTrack hasn't locked onto yet
        # so NO vehicle is missed on screen
        if len(result.boxes):
            raw_motos = []
            raw_others = []
            raw_persons = []
            for b in result.boxes:
                bx1, by1, bx2, by2 = [int(v) for v in b.xyxy[0]]
                bconf = float(b.conf[0])
                bcls = int(b.cls[0])
                if bcls == PERSON_CLASS:
                    raw_persons.append((bx1, by1, bx2, by2, bconf))
                elif bcls in (1, 3):
                    raw_motos.append([bx1, by1, bx2, by2, bconf, bcls])
                else:
                    raw_others.append((bx1, by1, bx2, by2, bconf, bcls))

            used_raw_p = set()
            for m in raw_motos:
                for p_i, (px1, py1, px2, py2, pconf) in enumerate(raw_persons):
                    if p_i in used_raw_p:
                        continue
                    if not (px2 < m[0] or px1 > m[2] or py2 < m[1] - 40 or py1 > m[3] + 40):
                        m[0], m[1] = min(m[0], px1), min(m[1], py1)
                        m[2], m[3] = max(m[2], px2), max(m[3], py2)
                        m[4] = max(m[4], pconf)
                        used_raw_p.add(p_i)

            # Standalone raw persons on road -> motorcycle
            for p_i, (px1, py1, px2, py2, pconf) in enumerate(raw_persons):
                if p_i not in used_raw_p and (py2 - py1) <= 200:
                    raw_motos.append([px1, py1, px2, py2, pconf, 3])

            all_raw = [(m[0], m[1], m[2], m[3], m[4], m[5]) for m in raw_motos] + raw_others
            for bx1, by1, bx2, by2, bconf, bcls in all_raw:
                is_dup = False
                for tx1, ty1, tx2, ty2 in tracked_boxes:
                    ix1, iy1 = max(bx1, tx1), max(by1, ty1)
                    ix2, iy2 = min(bx2, tx2), min(by2, ty2)
                    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
                    if iw * ih > 0:
                        inter = iw * ih
                        area_b = (bx2 - bx1) * (by2 - by1)
                        area_t = (tx2 - tx1) * (ty2 - ty1)
                        union = area_b + area_t - inter
                        if union > 0 and (inter / union > 0.35 or inter / max(1.0, min(area_b, area_t)) > 0.6):
                            is_dup = True
                            break
                if not is_dup:
                    cat = CLASS_CONFIG.get(bcls, DEFAULT_CLASS)['category']
                    counts[CAT_KEY[cat]] += 1
                    dets.append((bcls, bconf, bx1, by1, bx2, by2, -1))

        total = sum(counts.values())

        self._detect_collisions(now)

        # Drop tracks that left the frame
        for tid in [t for t, v in self._tracks.items() if now - v['t'] > self.TRACK_TTL]:
            del self._tracks[tid]

        # Traffic level: how many vehicles are visible AND whether they are moving.
        # Many moving vehicles = busy but flowing, not a jam. Both signals are smoothed over
        # ~LEVEL_WINDOW seconds of video so one red-light queue does not read as a jam.
        if total <= 4:
            # If current frame has 4 or fewer vehicles, the road is clear!
            # Reset smoothed total directly to current count and moving_pct to 100%
            self._flow = {'t': now, 'moving': 100.0, 'total': float(total)}
        elif measured:
            inst_moving = 100.0 * moving / measured
            if self._flow is None:
                self._flow = {'t': now, 'moving': inst_moving, 'total': float(total)}
            else:
                a = min(1.0, max(0.0, now - self._flow['t']) / self.level_window)
                self._flow['moving'] += a * (inst_moving - self._flow['moving'])
                self._flow['total'] += a * (total - self._flow['total'])
                self._flow['t'] = now
        elif self._flow:
            # If no speeds measured this frame, total still decays towards current visible count
            a = min(1.0, max(0.0, now - self._flow['t']) / self.level_window)
            self._flow['total'] += a * (total - self._flow['total'])
            self._flow['t'] = now

        moving_pct = round(self._flow['moving']) if self._flow else 100
        n = self._flow['total'] if self._flow else total

        # Turnover: fast vehicles leave before their speed can be measured, which biases the
        # moving share low on highways. If the visible vehicles are replaced about twice a
        # minute or more, traffic is flowing regardless of what the speed estimate says.
        if self._t_first is None:
            self._t_first = now
        while self._passes and now - self._passes[0] > self.TURNOVER_WINDOW:
            self._passes.popleft()
        window = max(5.0, min(self.TURNOVER_WINDOW, now - self._t_first))
        turnover = len(self._passes) * (60.0 / window) / max(1.0, n)
        moving_pct = max(moving_pct, min(100, round(turnover * 50)))
        if total <= 5 or n <= 5:
            level = 'free'
        elif moving_pct >= 50:
            level = 'free' if n <= 15 else 'moderate'
        elif moving_pct < 25 and n > 20:
            level = 'heavy'
        else:
            level = 'moderate'

        stats = dict(counts, total=total, moving_pct=moving_pct, level=level, traffic_level=LEVEL_TEXT[level][0])
        self.persons = persons
        self.last_stats = stats
        self._now = now
        return dets, stats, new_vehicles

    def _detect_collisions(self, now):
        """Mark tracks that stopped abruptly while touching another stopped vehicle as a collision pair."""
        live = {tid: tr for tid, tr in self._tracks.items()
                if tr['t'] == now and 'box' in tr and tr['speed'] is not None}
        sudden = []
        for tid, tr in live.items():
            if tr['speed'] >= self.MOVING_SPEED:
                tr['last_moving_t'] = now
                tr.pop('sudden_t', None)
                tr.pop('collision_t', None)
            stop_t = tr.get('stop_t')
            if stop_t is not None and 'sudden_t' not in tr and 'last_moving_t' in tr \
                    and stop_t - tr['last_moving_t'] <= self.SUDDEN_STOP_S:
                tr['sudden_t'] = stop_t
            if 'sudden_t' in tr and 'collision_t' not in tr:
                sudden.append(tid)
        for tid in sudden:
            tr = live[tid]
            cx, cy, h, x1, y1, x2, y2 = tr['box']
            gap = 0.3 * h
            for oid, other in live.items():
                if oid == tid or other.get('stop_t') is None:
                    continue
                ox1, oy1, ox2, oy2 = other['box'][3:]
                if not (ox2 < x1 - gap or ox1 > x2 + gap or oy2 < y1 - gap or oy1 > y2 + gap):
                    tr['collision_t'] = other['collision_t'] = now
                    tr['partner'], other['partner'] = oid, tid
                    break

    def anomaly(self):
        """Incident candidate: two vehicles that stopped abruptly in contact (collision), or a vehicle
        stopped >= STOPPED_ALERT s while traffic around it flows (so not a jam or a red light).
        Returns None or a dict describing the strongest candidate."""
        st = self.last_stats
        if not st or st['moving_pct'] < 40 or st['total'] > 25:
            return None
        now = self._now
        stopped_boxes = [tr['box'] for tr in self._tracks.values()
                         if tr.get('stop_t') is not None and 'box' in tr and now - tr['t'] <= 2.0]
        best = None
        for tid, tr in self._tracks.items():
            stop_t = tr.get('stop_t')
            if stop_t is None or 'box' not in tr or now - tr['t'] > 2.0:
                continue
            stopped = now - stop_t
            collision_t = tr.get('collision_t')
            collision = collision_t is not None and now - collision_t >= self.COLLISION_CONFIRM_S
            if stopped < self.STOPPED_ALERT and not collision:
                continue
            cx, cy, h, x1, y1, x2, y2 = tr['box']
            # A stopped vehicle with other stopped vehicles right next to it is a queue (red light), not an incident
            # (a collision pair already has one stopped neighbour: the partner)
            neighbours = sum(1 for bx, by, bh, *_ in stopped_boxes
                             if (bx, by) != (cx, cy) and abs(bx - cx) < 2.5 * h and abs(by - cy) < 2.5 * h)
            if neighbours >= (3 if collision else 2):
                continue
            # People within ~2 vehicle-heights of the stopped vehicle
            people_near = sum(1 for px, py, ph in self.persons
                              if abs(px - cx) < 2.0 * h and abs(py - cy) < 2.0 * h)
            # Hazard markers or triangular warning cones placed behind the vehicle
            # (YOLO doesn't detect cones, but stopped vehicle + people out of cars is a strong signal)
            if collision:
                conf = min(0.95, 0.65 + (0.25 if people_near else 0.0))
            else:
                conf = min(0.95, 0.45 + (0.35 if people_near else 0.0) + min(0.20, (stopped - self.STOPPED_ALERT) / 120.0))
            partner = self._tracks.get(tr.get('partner')) if collision else None
            cand = {
                'track_id': tid,
                'kind': 'collision' if collision else 'stopped',
                'stopped_s': round(stopped),
                'box': (x1, y1, x2, y2),
                'box2': partner['box'][3:] if partner and 'box' in partner else None,
                'confidence': round(conf, 2),
                'persons_near': people_near,
                'people_near': people_near,
                'moving_pct': st['moving_pct'],
                'total': st['total'],
            }
            if best is None or cand['confidence'] > best['confidence']:
                best = cand
        return best


def frame_video_time(cap, t_wall=None):
    """Video-time (seconds) of the frame just read, from the frame counter.
    Falls back to wall time if OpenCV stream properties are unavailable or negative."""
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps and fps > 0:
        pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
        if pos and pos >= 0:
            return pos / fps
    msec = cap.get(cv2.CAP_PROP_POS_MSEC)
    if msec and msec > 0:
        return msec / 1000.0
    return t_wall if t_wall is not None else time.time()


def skip_elapsed_frames(cap, seconds):
    """Skip a few buffered frames so the feed stays live without blocking network I/O."""
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames_to_skip = min(4, max(0, int(src_fps * min(0.5, seconds)) - 1))
    for _ in range(frames_to_skip):
        if not cap.grab():
            break


class VehicleDetectorYOLO11x:
    def __init__(self, model_path='yolo11x.pt', target_fps=10.0, conf_threshold=0.15, vehicle_log=None):
        self.target_fps = target_fps
        self.conf_threshold = conf_threshold
        self.frame_interval = 1.0 / target_fps  # 0.10s for 10 FPS
        self.vehicle_log = vehicle_log
        # IncidentManager, attached by the server after construction
        self.incidents = None

        print(f"[AI] Initializing YOLO11x ({model_path}) with target {target_fps} FPS...")
        self.model = YOLO(model_path)
        # Warmup model once on dummy image so initial stream frames don't stall
        try:
            dummy = np.zeros((320, 320, 3), dtype=np.uint8)
            self.model(dummy, verbose=False)
        except Exception:
            pass
        # One GPU: inference from all streams (this one and the background counters) is serialized
        self.model_lock = threading.Lock()

        self.target_classes = TARGET_CLASSES
        self.CLASS_CONFIG = CLASS_CONFIG

        # Fonts
        self.font = None
        self.font_bold = None
        self.font_title = None
        self._init_fonts()

        # State
        self.current_stream_url = None
        self.current_cam_info = {}
        self.is_running = False
        self.thread = None
        self.stop_event = None
        self.lock = threading.Lock()

        # Latest output
        self.latest_jpeg = None
        self.latest_stats = {
            'active': False,
            'camid': '',
            'title': '',
            'province': '',
            'fps': 0.0,
            'target_fps': self.target_fps,
            'latency_ms': 0.0,
            'cars': 0,
            'motorcycles': 0,
            'trucks': 0,
            'total': 0,
            'moving_pct': 100,
            'level': 'free',
            'traffic_level': 'ไม่มีข้อมูล'
        }

    def _init_fonts(self):
        font_candidates = [
            'C:\\Windows\\Fonts\\tahoma.ttf',
            'C:\\Windows\\Fonts\\leelawad.ttf',
            'C:\\Windows\\Fonts\\arial.ttf'
        ]
        chosen = None
        for fc in font_candidates:
            if os.path.exists(fc):
                chosen = fc
                break

        if chosen:
            try:
                self.font = ImageFont.truetype(chosen, 15)
                self.font_bold = ImageFont.truetype(chosen, 17)
                self.font_title = ImageFont.truetype(chosen, 20)
            except Exception as e:
                print(f"[AI] Font load warning: {e}")
                self.font = ImageFont.load_default()
                self.font_bold = self.font
                self.font_title = self.font
        else:
            self.font = ImageFont.load_default()
            self.font_bold = self.font
            self.font_title = self.font

    # Inference resolution. Streams are 1280x720; 960 keeps distant motorcycles at a usable pixel size
    IMGSZ = 960
    # Per-class minimum confidence. Small classes need a low floor; large ones false-positive easily at 0.15
    CLASS_CONF = {PERSON_CLASS: 0.25, 1: 0.15, 2: 0.30, 3: 0.15, 5: 0.30, 7: 0.30}

    def infer(self, frame, conf=None):
        """Run YOLO on one frame (thread-safe). Returns the ultralytics Results object."""
        with self.model_lock:
            # Predict at the lowest per-class floor, then drop boxes under their own class threshold
            base = self.conf_threshold if conf is None else conf
            floor = min(self.CLASS_CONF.values())
            result = self.model(
                frame,
                classes=self.target_classes,
                conf=min(floor, base),
                imgsz=self.IMGSZ,
                iou=0.45,
                verbose=False
            )[0]
        if len(result.boxes):
            cls = result.boxes.cls
            thr = torch.tensor([max(base, self.CLASS_CONF.get(int(c), base)) for c in cls], device=cls.device)
            result = result[result.boxes.conf >= thr]
        return result

    def set_target_fps(self, fps):
        self.target_fps = max(1.0, min(30.0, float(fps)))
        self.frame_interval = 1.0 / self.target_fps
        self.latest_stats['target_fps'] = self.target_fps
        print(f"[AI] Target FPS updated to {self.target_fps}")

    def set_confidence(self, conf):
        self.conf_threshold = max(0.1, min(0.9, float(conf)))
        print(f"[AI] Confidence threshold updated to {self.conf_threshold}")

    def start_stream(self, stream_url, cam_info=None):
        with self.lock:
            if self.is_running and self.current_stream_url == stream_url:
                print(f"[AI] Already streaming {stream_url}")
                return

            # Signal old worker to stop (do not join while holding the lock)
            if self.stop_event:
                self.stop_event.set()
            self.stop_event = threading.Event()
            self.current_stream_url = stream_url
            self.current_cam_info = cam_info or {}
            self.latest_jpeg = None
            self.is_running = True
            self.thread = threading.Thread(
                target=self._process_loop,
                args=(stream_url, self.current_cam_info, self.stop_event),
                daemon=True
            )
            self.thread.start()
            print(f"[AI] Started detection thread for {self.current_cam_info.get('title', stream_url)}")

    def stop_stream(self):
        with self.lock:
            self.is_running = False
            if self.stop_event:
                self.stop_event.set()
            thread = self.thread
            self.thread = None
            self.latest_stats['active'] = False
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def _process_loop(self, stream_url, cam_info, stop_event):
        print(f"[AI Worker] Processing stream at target {self.target_fps} FPS...")
        cap = None
        # Fresh tracker per stream so IDs and counts do not carry over from the previous camera
        tracker = VehicleTracker()

        while not stop_event.is_set():
            try:
                # Open stream
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(stream_url)
                    if not cap.isOpened():
                        print(f"[AI Worker] Could not open stream: {stream_url}. Retrying in 3s...")
                        stop_event.wait(3.0)
                        continue
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass

                t_start = time.time()
                ret, frame = cap.read()
                frame_t = frame_video_time(cap, t_start)

                if not ret or frame is None:
                    # Retry stream
                    print("[AI Worker] Frame read failed. Reconnecting...")
                    cap.release()
                    cap = None
                    time.sleep(1.0)
                    continue

                # Run YOLO11x inference
                t_infer_start = time.time()
                result = self.infer(frame)
                infer_latency_ms = (time.time() - t_infer_start) * 1000.0

                dets, stats, new_vehicles = tracker.update(result, frame, frame_t)
                stats['latency_ms'] = round(infer_latency_ms, 1)
                annotated_jpeg = self._annotate_frame(frame, dets, stats)
                if self.incidents:
                    self.incidents.observe(cam_info.get('camid', ''), cam_info.get('short_title', cam_info.get('title', '')), tracker, frame)

                if self.vehicle_log and any(new_vehicles.values()):
                    self.vehicle_log.add(
                        cam_info.get('camid', ''),
                        cam_info.get('short_title', cam_info.get('title', '')),
                        **new_vehicles
                    )

                with self.lock:
                    if stop_event.is_set():
                        break
                    self.latest_jpeg = annotated_jpeg
                    self.latest_stats.update(stats)
                    self.latest_stats['active'] = True
                    self.latest_stats['camid'] = cam_info.get('camid', '')
                    self.latest_stats['title'] = cam_info.get('short_title', cam_info.get('title', ''))
                    self.latest_stats['province'] = cam_info.get('province', '')

                # Regulate to target FPS (e.g. 5 FPS -> 0.20s per frame)
                t_elapsed = time.time() - t_start
                sleep_time = self.frame_interval - t_elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

                iteration = max(0.001, time.time() - t_start)
                self.latest_stats['fps'] = round(1.0 / iteration, 1)
                skip_elapsed_frames(cap, iteration)

            except Exception as e:
                print(f"[AI Worker] Processing error: {e}")
                time.sleep(1.0)

        if cap:
            cap.release()
        print("[AI Worker] Worker stopped.")

    def _annotate_frame(self, frame, dets, stats):
        h, w = frame.shape[:2]

        # Convert BGR OpenCV to RGB PIL for high quality anti-aliased Thai text
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        for cls_id, conf, x1, y1, x2, y2, _track_id in dets:
            cfg = CLASS_CONFIG.get(cls_id, DEFAULT_CLASS)
            cat = cfg['category']

            # Thin, rounded pastel box
            color = cfg['color']
            draw.rounded_rectangle([x1, y1, x2, y2], radius=8, outline=color, width=2)

            # Small label pill floating above the vehicle: e.g. "รถยนต์ 89%"
            label_text = f"{cat} {int(conf * 100)}%"
            ty = max(4, y1 - 20)
            text_bbox = draw.textbbox((x1 + 6, ty), label_text, font=self.font)
            pill = [text_bbox[0] - 6, text_bbox[1] - 3, text_bbox[2] + 6, text_bbox[3] + 3]
            draw.rounded_rectangle(pill, radius=9, fill=cfg['bg_color'], outline=color, width=1)
            draw.text((x1 + 6, ty), label_text, fill=(46, 42, 51), font=self.font)

        level_color = LEVEL_TEXT[stats['level']][1]

        # Soft corner tag instead of a dark HUD bar (counts live in the UI tiles)
        tag = f"{stats['total']} คัน"
        tb = draw.textbbox((0, 0), tag, font=self.font_bold)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        py = h - th - 26
        pill = [w - tw - 30, py, w - 12, py + th + 14]
        draw.rounded_rectangle(pill, radius=14, fill=(253, 252, 251), outline=level_color, width=2)
        draw.text((w - tw - 21, py + 5), tag, fill=(46, 42, 51), font=self.font_bold)

        # Convert back to BGR and encode to JPEG
        annotated_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        _, jpeg_bytes = cv2.imencode('.jpg', annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg_bytes.tobytes()

    def get_latest_frame(self):
        with self.lock:
            return self.latest_jpeg

    def get_stats(self):
        with self.lock:
            return dict(self.latest_stats)
