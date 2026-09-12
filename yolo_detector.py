import cv2
import time
import os
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

class VehicleDetectorYOLO11x:
    def __init__(self, model_path='yolo11x.pt', target_fps=5.0, conf_threshold=0.30):
        self.target_fps = target_fps
        self.conf_threshold = conf_threshold
        self.frame_interval = 1.0 / target_fps  # 0.20s for 5 FPS

        print(f"[AI] Initializing YOLO11x ({model_path}) with target {target_fps} FPS...")
        self.model = YOLO(model_path)
        
        # Target vehicle classes:
        # COCO IDs: 2: car, 3: motorcycle, 5: bus, 7: truck
        self.target_classes = [2, 3, 5, 7]
        
        # Color mapping (RGB)
        self.CLASS_CONFIG = {
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

        while not stop_event.is_set():
            try:
                # Open stream
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(stream_url)
                    if not cap.isOpened():
                        print(f"[AI Worker] Could not open stream: {stream_url}. Retrying in 3s...")
                        stop_event.wait(3.0)
                        continue

                t_start = time.time()
                ret, frame = cap.read()

                if not ret or frame is None:
                    # Retry stream
                    print("[AI Worker] Frame read failed. Reconnecting...")
                    cap.release()
                    cap = None
                    time.sleep(1.0)
                    continue

                # Run YOLO11x inference
                t_infer_start = time.time()
                results = self.model(
                    frame,
                    classes=self.target_classes,
                    conf=self.conf_threshold,
                    verbose=False
                )
                infer_latency_ms = (time.time() - t_infer_start) * 1000.0

                # Annotate and count
                annotated_jpeg, stats = self._annotate_frame(frame, results[0], infer_latency_ms)

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

                actual_fps = 1.0 / max(0.001, time.time() - t_start)
                self.latest_stats['fps'] = round(actual_fps, 1)

            except Exception as e:
                print(f"[AI Worker] Processing error: {e}")
                time.sleep(1.0)

        if cap:
            cap.release()
        print("[AI Worker] Worker stopped.")

    def _annotate_frame(self, frame, detection_result, latency_ms):
        h, w = frame.shape[:2]
        
        # Convert BGR OpenCV to RGB PIL for high quality anti-aliased Thai text
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        cars_count = 0
        motorcycles_count = 0
        trucks_count = 0

        boxes = detection_result.boxes
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]

                cfg = self.CLASS_CONFIG.get(cls_id, {
                    'category': 'รถยนต์',
                    'name_en': 'Vehicle',
                    'color': (157, 191, 146),
                    'bg_color': (227, 238, 221)
                })

                cat = cfg['category']
                if cat == 'รถยนต์':
                    cars_count += 1
                elif cat == 'มอไซ':
                    motorcycles_count += 1
                elif cat == 'รถบรรทุก':
                    trucks_count += 1

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

        total_vehicles = cars_count + motorcycles_count + trucks_count

        # Evaluate traffic level
        if total_vehicles <= 4:
            traffic_level = "การจราจรคล่องตัว 🟢"
            level_color = (157, 191, 146)
        elif total_vehicles <= 12:
            traffic_level = "การจราจรปานกลาง 🟡"
            level_color = (237, 197, 92)
        else:
            traffic_level = "การจราจรหนาแน่น 🔴"
            level_color = (245, 168, 140)

        # Soft corner tag instead of a dark HUD bar (counts live in the UI tiles)
        tag = f"{cars_count + motorcycles_count + trucks_count} คัน"
        tb = draw.textbbox((0, 0), tag, font=self.font_bold)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        py = h - th - 26
        pill = [w - tw - 30, py, w - 12, py + th + 14]
        draw.rounded_rectangle(pill, radius=14, fill=(253, 252, 251), outline=level_color, width=2)
        draw.text((w - tw - 21, py + 5), tag, fill=(46, 42, 51), font=self.font_bold)

        # Convert back to BGR and encode to JPEG
        annotated_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        _, jpeg_bytes = cv2.imencode('.jpg', annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])

        stats = {
            'latency_ms': round(latency_ms, 1),
            'cars': cars_count,
            'motorcycles': motorcycles_count,
            'trucks': trucks_count,
            'total': total_vehicles,
            'traffic_level': traffic_level
        }

        return jpeg_bytes.tobytes(), stats

    def get_latest_frame(self):
        with self.lock:
            return self.latest_jpeg

    def get_stats(self):
        with self.lock:
            return dict(self.latest_stats)
