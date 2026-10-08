"""
The live AI camera: one shared YOLO model (tiled inference, night mode) reading the stream the page has open,
tracking and counting with vehicle_tracker.VehicleTracker, and drawing the boxes on the frames it serves.
"""
import cv2
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass
import time
import os
import threading
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO
from ultralytics.engine.results import Results

from backend.core.instance import thai_font
from backend.vision.vehicle_tracker import (CLASS_CONFIG, DEFAULT_CLASS, LEVEL_TEXT, PERSON_CLASS, VehicleTracker,
                                            frame_video_time, skip_elapsed_frames)

# The COCO classes the model looks for: vehicles (see CLASS_CONFIG) and people (PERSON_CLASS, incidents only)
TARGET_CLASSES = [PERSON_CLASS, 1, 2, 3, 5, 7]
SURE_CONF = 0.5   # on the picture, a box below this shows no percentage and a thinner line


class VehicleDetectorYOLO11x:
    def __init__(self, model_path='yolo26x.pt', target_fps=10.0, conf_threshold=0.15, vehicle_log=None):
        self.target_fps = target_fps
        self.conf_threshold = conf_threshold
        self.frame_interval = 1.0 / target_fps  # 0.10s for 10 FPS
        self.vehicle_log = vehicle_log
        # IncidentManager / ViolationMonitor, attached by the server after construction
        self.incidents = None
        self.violations = None

        # Display name for the page and logs: yolo26x.pt -> YOLO26x, yolo26x_bkk.pt -> YOLO26x_bkk
        stem = os.path.splitext(os.path.basename(model_path))[0]
        self.model_name = 'YOLO' + stem[4:] if stem.lower().startswith('yolo') else stem
        print(f"[AI] Initializing {self.model_name} ({model_path}) with target {target_fps} FPS...")
        self.model = YOLO(model_path)
        if torch.cuda.is_available():
            try:
                self.model.to('cuda').half()
                print("[AI] Accelerated with CUDA FP16 (Tensor Cores active, TDR safe)")
            except Exception as e:
                print(f"[AI] Note: FP16 acceleration skipped: {e}")
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
            'model': self.model_name,
            # 'offline' while the camera's stream cannot be opened (the worker keeps retrying)
            'stream_error': '',
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
            'traffic_level': 'ไม่มีข้อมูล',
            'night_mode': False,
            # vehicles confirmed as passing since the stream started / the counter was reset
            # (ground truth for the manual-vs-AI accuracy check on the live page)
            'passed_cars': 0,
            'passed_motorcycles': 0,
            'passed_trucks': 0,
            'passed_total': 0,
            'passed_since': 0,
        }
        self.night_mode = False
        inv_gamma = 1.0 / 0.60
        self._gamma_table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        self._clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))

    def _init_fonts(self):
        chosen = thai_font()

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

    # Inference resolution (640 native resolution prevents GPU overload and TDR timeout)
    IMGSZ = int(os.getenv('AI_IMGSZ', '640'))
    # Per-class minimum confidence. Low floor for motorcycles/bicycles to catch distant riders; 0.22 for cars/trucks
    CLASS_CONF = {PERSON_CLASS: 0.15, 1: 0.08, 2: 0.22, 3: 0.08, 5: 0.22, 7: 0.22}

    # Tiled inference: the frame is split into a 2x2 grid of overlapping crops, each run at
    # TILE_IMGSZ, and the boxes are merged with class-aware NMS.
    TILE_MAX_SIDE = 800
    TILE_IMGSZ = 640
    TILE_OVERLAP = 0.15
    # Live stream: default False to prevent 4x GPU saturation; set AI_TILED=1 in env if desired
    TILED_LIVE = {'1': True, '0': False}.get(os.getenv('AI_TILED', '0'), False)

    def _tiles(self, h, w):
        oy, ox = int(h * self.TILE_OVERLAP), int(w * self.TILE_OVERLAP)
        ys = ((0, h // 2 + oy), (h // 2 - oy, h))
        xs = ((0, w // 2 + ox), (w // 2 - ox, w))
        return [(y0, y1, x0, x1) for y0, y1 in ys for x0, x1 in xs]

    def infer(self, frame, conf=None, tiled=None):
        """Run YOLO on one frame (thread-safe). Returns the ultralytics Results object.

        tiled=None picks tiling by frame size (see TILE_MAX_SIDE)."""
        h, w = frame.shape[:2]
        if tiled is None:
            tiled = max(h, w) < self.TILE_MAX_SIDE
        # Predict at the lowest per-class floor, then drop boxes under their own class threshold
        base = self.conf_threshold if conf is None else conf
        floor = min(min(self.CLASS_CONF.values()), base)
        if not tiled:
            with self.model_lock:
                result = self.model(frame, classes=self.target_classes, conf=floor, imgsz=self.IMGSZ, iou=0.45, verbose=False)[0]
        else:
            tiles = self._tiles(h, w)
            with self.model_lock:
                parts = self.model([frame[y0:y1, x0:x1] for y0, y1, x0, x1 in tiles], classes=self.target_classes,
                                   conf=floor, imgsz=self.TILE_IMGSZ, iou=0.45, verbose=False)
            rows = []
            for (y0, y1, x0, x1), r in zip(tiles, parts):
                if len(r.boxes):
                    d = r.boxes.data.cpu()
                    d[:, :4] += torch.tensor([x0, y0, x0, y0], dtype=d.dtype)
                    rows.append(d)
            merged = torch.cat(rows) if rows else torch.zeros((0, 6))
            if len(merged):
                merged = merged[self._nms(merged.numpy(), 0.5)]
            result = Results(frame, path='', names=self.model.names, boxes=merged)
        if len(result.boxes):
            cls = result.boxes.cls
            thr = torch.tensor([max(base, self.CLASS_CONF.get(int(c), base)) for c in cls], device=cls.device)
            result = result[result.boxes.conf >= thr]
        return result

    def detect_boxes(self, frame, conf=None, tiled=None):
        """Detections as a list of (cls_id, conf, x1, y1, x2, y2) in frame pixels,
        with Rider-Bike fusion and roadway rider conversion to accurately count motorcycles and cars."""
        r = self.infer(frame, conf=conf, tiled=tiled)
        if not len(r.boxes):
            return []

        raw_cars = []
        raw_motos = []
        raw_trucks = []
        raw_persons = []

        for (x1, y1, x2, y2), cf, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            cid = int(c)
            conf_val = float(cf)
            box = [int(x1), int(y1), int(x2), int(y2)]
            if cid == 2:
                raw_cars.append((cid, conf_val, box))
            elif cid in (5, 7):
                raw_trucks.append((cid, conf_val, box))
            elif cid in (1, 3):
                raw_motos.append({'cls': cid, 'conf': conf_val, 'box': box})
            elif cid == PERSON_CLASS:
                raw_persons.append({'cls': cid, 'conf': conf_val, 'box': box})

        # 1. Merge overlapping rider (person) into motorcycle
        used_p = set()
        for m in raw_motos:
            mx1, my1, mx2, my2 = m['box']
            for pi, p in enumerate(raw_persons):
                if pi in used_p:
                    continue
                px1, py1, px2, py2 = p['box']
                ix1, iy1 = max(mx1, px1), max(my1, py1)
                ix2, iy2 = min(mx2, px2), min(my2, py2)
                # Overlap or rider seated directly above/on bike
                if (ix2 > ix1 and iy2 > iy1) or not (px2 < mx1 or px1 > mx2 or py2 < my1 - 25 or py1 > my2 + 25):
                    m['box'] = [min(mx1, px1), min(my1, py1), max(mx2, px2), max(my2, py2)]
                    m['conf'] = max(m['conf'], p['conf'])
                    used_p.add(pi)
                    break

        # 2. Standalone persons: detect motorcycle riders (seated aspect ratio in traffic)
        h_frame = frame.shape[0]
        for pi, p in enumerate(raw_persons):
            if pi in used_p:
                continue
            px1, py1, px2, py2 = p['box']
            pw, ph = px2 - px1, py2 - py1
            if pw > 0 and ph > 0 and 0.65 <= (ph / pw) <= 2.3 and ph <= (h_frame * 0.45):
                # Ensure not a false detection inside an existing car
                inside_car = False
                for _, _, (cx1, cy1, cx2, cy2) in raw_cars + raw_trucks:
                    if px1 >= cx1 and px2 <= cx2 and py1 >= cy1 and py2 <= cy2:
                        inside_car = True
                        break
                if not inside_car:
                    raw_motos.append({'cls': 3, 'conf': p['conf'], 'box': [px1, py1, px2, py2]})

        # 3. Deduplicate overlapping motorcycle boxes
        fused_motos = []
        for m in sorted(raw_motos, key=lambda x: x['conf'], reverse=True):
            dup = False
            for fm in fused_motos:
                ix1, iy1 = max(m['box'][0], fm['box'][0]), max(m['box'][1], fm['box'][1])
                ix2, iy2 = min(m['box'][2], fm['box'][2]), min(m['box'][3], fm['box'][3])
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    area = (m['box'][2] - m['box'][0]) * (m['box'][3] - m['box'][1])
                    if inter / max(1, area) > 0.45:
                        dup = True
                        break
            if not dup:
                fused_motos.append(m)

        out = []
        for cid, conf_val, box in raw_cars:
            out.append((cid, conf_val, box[0], box[1], box[2], box[3]))
        for m in fused_motos:
            out.append((m['cls'], m['conf'], m['box'][0], m['box'][1], m['box'][2], m['box'][3]))
        for cid, conf_val, box in raw_trucks:
            out.append((cid, conf_val, box[0], box[1], box[2], box[3]))

        return out

    @staticmethod
    def _nms(rows, iou_thr):
        """Greedy class-aware NMS over rows of x1,y1,x2,y2,conf,cls. Returns kept indices."""
        keep = []
        order = np.argsort(-rows[:, 4])
        x1, y1, x2, y2 = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
        area = (x2 - x1) * (y2 - y1)
        suppressed = np.zeros(len(rows), dtype=bool)
        for idx in order:
            if suppressed[idx]:
                continue
            keep.append(int(idx))
            iw = np.clip(np.minimum(x2, x2[idx]) - np.maximum(x1, x1[idx]), 0, None)
            ih = np.clip(np.minimum(y2, y2[idx]) - np.maximum(y1, y1[idx]), 0, None)
            inter = iw * ih
            iou = inter / (area + area[idx] - inter + 1e-6)
            suppressed |= (rows[:, 5] == rows[idx, 5]) & (iou > iou_thr)
            suppressed[idx] = True
        return keep

    def set_target_fps(self, fps):
        self.target_fps = max(1.0, min(30.0, float(fps)))
        self.frame_interval = 1.0 / self.target_fps
        self.latest_stats['target_fps'] = self.target_fps
        print(f"[AI] Target FPS updated to {self.target_fps}")

    def set_confidence(self, conf):
        self.conf_threshold = max(0.1, min(0.9, float(conf)))
        print(f"[AI] Confidence threshold updated to {self.conf_threshold}")

    def set_night_mode(self, enabled: bool):
        self.night_mode = bool(enabled)
        self.latest_stats['night_mode'] = self.night_mode
        print(f"[AI] Night mode updated to {self.night_mode}")

    def enhance_low_light(self, frame):
        """Adaptive low-light enhancement: Gamma shadow lifting + CLAHE contrast normalization."""
        try:
            lifted = cv2.LUT(frame, self._gamma_table)
            lab = cv2.cvtColor(lifted, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l_clahe = self._clahe.apply(l)
            return cv2.cvtColor(cv2.merge((l_clahe, a, b)), cv2.COLOR_LAB2BGR)
        except Exception:
            return frame

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
            self._reset_passed_locked()
            # Report the new camera at once, so the page does not show the previous camera's counts as this one's
            info = self.current_cam_info
            self.latest_stats.update(active=False, stream_error='', camid=info.get('camid', ''),
                                     title=info.get('short_title', info.get('title', '')), province=info.get('province', ''),
                                     fps=0.0, latency_ms=0.0, cars=0, motorcycles=0, trucks=0, total=0,
                                     moving_pct=100, level='free', traffic_level='ไม่มีข้อมูล')
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
        fail_count = 0
        # Fresh tracker per stream so IDs and counts do not carry over from the previous camera
        tracker = VehicleTracker()

        while not stop_event.is_set():
            try:
                # Open stream
                if cap is None or not cap.isOpened():
                    try:
                        cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 6000])
                    except Exception:
                        cap = None
                    if not cap or not cap.isOpened():
                        if cap is not None:
                            try:
                                cap.release()
                            except Exception:
                                pass
                            cap = None
                        fail_count += 1
                        with self.lock:
                            if not stop_event.is_set():
                                self.latest_stats.update(active=False, stream_error='offline')
                        backoff = min(30.0, 5.0 * (1.5 ** min(fail_count, 4)))
                        print(f"[AI Worker] Could not open stream: {stream_url}. Retrying in {backoff:.0f}s (attempt #{fail_count})...")
                        stop_event.wait(backoff)
                        continue
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                    fail_count = 0

                t_start = time.time()
                ret, frame = cap.read()
                frame_t = frame_video_time(cap, t_start)

                if not ret or frame is None:
                    # Retry stream
                    print("[AI Worker] Frame read failed. Reconnecting...")
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                    time.sleep(2.0)
                    continue

                if self.night_mode:
                    frame = self.enhance_low_light(frame)

                # Run YOLO inference
                t_infer_start = time.time()
                result = self.infer(frame, tiled=self.TILED_LIVE)
                infer_latency_ms = (time.time() - t_infer_start) * 1000.0

                dets, stats, new_vehicles = tracker.update(result, frame, frame_t)
                stats['latency_ms'] = round(infer_latency_ms, 1)
                flagged = {}
                if self.violations:
                    try:
                        flagged = self.violations.observe(cam_info.get('camid', ''), cam_info.get('short_title', cam_info.get('title', '')), tracker, frame, dets, frame_t)
                    except Exception as e:
                        print(f"[Violation] observe failed: {e}")
                annotated_jpeg = self._annotate_frame(frame, dets, stats, flagged)
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
                    if any(new_vehicles.values()):
                        for k, v in new_vehicles.items():
                            self.latest_stats['passed_' + k] += v
                        self.latest_stats['passed_total'] += sum(new_vehicles.values())
                    self.latest_stats['active'] = True
                    self.latest_stats['stream_error'] = ''
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

    VIOLATION_LABEL = {'wrong_way': 'ย้อนศร', 'no_helmet': 'ไม่สวมหมวก'}

    def _annotate_frame(self, frame, dets, stats, flagged=None):
        h, w = frame.shape[:2]
        flagged = flagged or {}

        # Convert BGR OpenCV to RGB PIL for high quality anti-aliased Thai text
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        for cls_id, conf, x1, y1, x2, y2, track_id in dets:
            cfg = CLASS_CONFIG.get(cls_id, DEFAULT_CLASS)
            cat = cfg['category']
            kind = flagged.get(track_id)

            # Thin, rounded pastel box; red and thicker for a vehicle breaking a rule
            color = (220, 50, 50) if kind else cfg['color']
            draw.rounded_rectangle([x1, y1, x2, y2], radius=8, outline=color,
                                   width=3 if kind else 2 if conf >= SURE_CONF else 1)

            # Small label pill floating above the vehicle: e.g. "รถยนต์ 89%" / "ย้อนศร · มอไซ". The thresholds are
            # low on purpose (every vehicle counts), but "รถยนต์ 27%" on screen reads as a wrong guess, so a box the
            # model is unsure of keeps a thin line and its name without the number.
            label_text = (f"{self.VIOLATION_LABEL.get(kind, kind)} · {cat}" if kind
                          else f"{cat} {int(conf * 100)}%" if conf >= SURE_CONF else cat)
            ty = max(4, y1 - 20)
            text_bbox = draw.textbbox((x1 + 6, ty), label_text, font=self.font)
            pill = [text_bbox[0] - 6, text_bbox[1] - 3, text_bbox[2] + 6, text_bbox[3] + 3]
            draw.rounded_rectangle(pill, radius=9, fill=(255, 226, 226) if kind else cfg['bg_color'], outline=color, width=1)
            draw.text((x1 + 6, ty), label_text, fill=(120, 20, 20) if kind else (46, 42, 51), font=self.font)

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

    def _reset_passed_locked(self):
        self.latest_stats.update(passed_cars=0, passed_motorcycles=0, passed_trucks=0, passed_total=0,
                                 passed_since=int(time.time()))

    def reset_passed(self):
        """Restart the passed-vehicle counter (user starts counting by hand at the same moment)."""
        with self.lock:
            self._reset_passed_locked()
            return dict(self.latest_stats)
