import cv2
import json
import os
import threading
import time
from collections import deque

from yolo_detector import VehicleTracker, frame_video_time, skip_elapsed_frames


class CountManager:
    """Background vehicle counting on a small set of cameras, independent of the AI page.

    Each camera gets its own thread and tracker; YOLO inference goes through the shared
    detector (one GPU, serialized). Counts are written to the same hourly VehicleLog.
    """

    def __init__(self, detector, vehicle_log, config_path, target_fps=2.0, max_cameras=6):
        self.detector = detector
        self.vehicle_log = vehicle_log
        self.config_path = config_path
        self.target_fps = target_fps
        self.max_cameras = max_cameras
        self.lock = threading.Lock()
        # camid -> {'cam': dict, 'stop': Event, 'thread': Thread, 'status': dict}
        self.workers = {}

    # ---- persistence
    def load(self, cameras_by_id):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                camids = json.load(f).get('camids', [])
        except (OSError, ValueError):
            return
        cams = [cameras_by_id[c] for c in camids if c in cameras_by_id]
        if cams:
            self.set_cameras(cams)

    def _save(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump({'camids': list(self.workers.keys())}, f, ensure_ascii=False, indent=2)

    # ---- control
    def set_cameras(self, cams):
        cams = cams[:self.max_cameras]
        wanted = {c['camid']: c for c in cams if c.get('hls_url') or c.get('vdourl')}
        with self.lock:
            for camid in [c for c in self.workers if c not in wanted]:
                self.workers.pop(camid)['stop'].set()
            for camid, cam in wanted.items():
                if camid in self.workers:
                    continue
                stop = threading.Event()
                status = {'camid': camid, 'title': cam.get('short_title') or cam.get('title') or camid,
                          'active': False, 'fps': 0.0, 'total': 0, 'moving_pct': 100, 'level': 'free',
                          'rate_per_min': 0.0, 'error': ''}
                thread = threading.Thread(target=self._loop, args=(cam, stop, status), daemon=True)
                self.workers[camid] = {'cam': cam, 'stop': stop, 'thread': thread, 'status': status}
                thread.start()
            self._save()

    def status(self):
        with self.lock:
            return {'max_cameras': self.max_cameras, 'target_fps': self.target_fps,
                    'cameras': [dict(w['status']) for w in self.workers.values()]}

    # ---- worker
    def _loop(self, cam, stop, status):
        url = cam.get('hls_url') or cam.get('vdourl')
        camid = cam['camid']
        title = status['title']
        print(f"[Counter] Start {title}")
        cap = None
        tracker = VehicleTracker()
        interval = 1.0 / self.target_fps
        # (wall time, vehicles) of recent passes, for a rolling vehicles-per-minute rate
        RATE_WINDOW = 300.0
        events = deque()
        started = time.time()

        while not stop.is_set():
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(url)
                    if not cap.isOpened():
                        status.update(active=False, error='เปิดสตรีมไม่ได้')
                        stop.wait(5.0)
                        continue

                t_start = time.time()
                ret, frame = cap.read()
                frame_t = frame_video_time(cap, t_start)
                if not ret or frame is None:
                    status.update(active=False, error='อ่านภาพไม่ได้')
                    cap.release()
                    cap = None
                    stop.wait(2.0)
                # Skip background duplicate inference if user is actively watching this camera
                if self.detector.is_running and self.detector.current_cam_info.get('camid') == camid:
                    stop.wait(interval)
                    continue

                result = self.detector.infer(frame)
                _dets, stats, new_vehicles = tracker.update(result, frame, frame_t)
                if self.detector.incidents:
                    self.detector.incidents.observe(camid, title, tracker, frame)

                n_new = sum(new_vehicles.values())
                now = time.time()
                if n_new:
                    events.append((now, n_new))
                    # The AI page already logs this camera while it is watching it; do not count twice
                    live = self.detector.get_stats()
                    if not (live.get('active') and live.get('camid') == camid):
                        self.vehicle_log.add(camid, title, **new_vehicles)
                while events and now - events[0][0] > RATE_WINDOW:
                    events.popleft()
                window = max(30.0, min(RATE_WINDOW, now - started))
                status.update(active=True, error='', total=stats['total'], moving_pct=stats['moving_pct'],
                              level=stats['level'], rate_per_min=round(sum(n for _, n in events) * 60.0 / window, 1))

                sleep_time = interval - (time.time() - t_start)
                if sleep_time > 0:
                    stop.wait(sleep_time)
                iteration = max(0.001, time.time() - t_start)
                status['fps'] = round(1.0 / iteration, 1)
                skip_elapsed_frames(cap, iteration)
            except Exception as e:
                status.update(active=False, error=str(e)[:80])
                stop.wait(2.0)

        if cap:
            cap.release()
        status.update(active=False)
        print(f"[Counter] Stop {title}")
