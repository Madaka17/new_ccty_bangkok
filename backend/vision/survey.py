import cv2
import threading
import time

from backend.vision.yolo_detector import VehicleTracker, frame_video_time


class SurveyManager:
    """Round-robin sampling of every camera: watch each one for a few seconds, count the
    vehicles that pass, and store the sample. Gives a city-wide ranking and an estimated
    hourly count for cameras that are not counted continuously by CountManager.
    """

    def __init__(self, detector, vehicle_log, get_cameras, skip_camids, workers=3, sample_seconds=15.0, target_fps=2.0):
        self.detector = detector
        self.vehicle_log = vehicle_log
        self.get_cameras = get_cameras          # () -> list of camera dicts
        self.skip_camids = skip_camids          # () -> set of camids counted elsewhere
        self.sample_seconds = sample_seconds
        self.target_fps = target_fps
        self.n_workers = workers
        self.lock = threading.Lock()
        self._index = 0
        self.stop = threading.Event()
        # camid -> latest sample dict (also persisted in vehicle_log.samples)
        self.latest = {}
        self.cycle_started = time.time()
        self.cycle_seconds = None

    def start(self):
        for cam in self.vehicle_log.latest_samples():
            self.latest[cam['camid']] = cam
        for i in range(self.n_workers):
            threading.Thread(target=self._loop, name=f"survey-{i}", daemon=True).start()

    def _next_camera(self):
        cams = [c for c in self.get_cameras() if c.get('hls_url') or c.get('vdourl')]
        skip = self.skip_camids()
        cams = [c for c in cams if c['camid'] not in skip]
        if not cams:
            return None
        with self.lock:
            if self._index >= len(cams):
                self._index = 0
                now = time.time()
                self.cycle_seconds = round(now - self.cycle_started)
                self.cycle_started = now
            cam = cams[self._index]
            self._index += 1
        return cam

    def status(self):
        skip = self.skip_camids()
        items = [dict(s, source='survey') for cid, s in self.latest.items() if cid not in skip]
        return {'workers': self.n_workers, 'sample_seconds': self.sample_seconds,
                'cycle_seconds': self.cycle_seconds, 'cameras': items}

    def _loop(self):
        while not self.stop.is_set():
            cam = self._next_camera()
            if cam is None:
                self.stop.wait(10.0)
                continue
            try:
                self._sample(cam)
            except Exception as e:
                print(f"[Survey] {cam.get('camid')}: {e}")
                self.stop.wait(2.0)

    def _fail(self, camid, title, error):
        # Keep the last good measurement (and its ts) so the ranking still shows it, but flag the error
        prev = self.latest.get(camid) or {'camid': camid, 'title': title, 'ts': 0}
        self.latest[camid] = dict(prev, error=error, error_ts=int(time.time()))

    def _sample(self, cam):
        camid = cam['camid']
        title = cam.get('short_title') or cam.get('title') or camid
        url = cam.get('hls_url') or cam.get('vdourl')
        if not url:
            return
        try:
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
        except Exception:
            self._fail(camid, title, 'เปิดสตรีมไม่ได้')
            return
        if not cap or not cap.isOpened():
            self._fail(camid, title, 'เปิดสตรีมไม่ได้')
            return

        # Short sample: judge the traffic level over the sample itself, not a 60 s window
        tracker = VehicleTracker(level_window=self.sample_seconds)
        # Read the stream sequentially and analyse every Nth frame, so the sample covers
        # sample_seconds of *video* at target_fps whatever the HLS buffer does. Playing
        # through the buffered segments quickly is fine; it just finishes the sample sooner.
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(round(src_fps / self.target_fps)))
        passed = {'cars': 0, 'motorcycles': 0, 'trucks': 0}
        visible = []
        stats = None
        t0_video = frame_t = None
        t_wall0 = time.time()
        try:
            while not self.stop.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                frame_t = frame_video_time(cap, time.time())
                if t0_video is None:
                    t0_video = frame_t
                result = self.detector.infer(frame)
                _dets, stats, new = tracker.update(result, frame, frame_t)
                for k in passed:
                    passed[k] += new[k]
                visible.append(stats['total'])

                if frame_t - t0_video >= self.sample_seconds or time.time() - t_wall0 > self.sample_seconds * 2 + 10:
                    break
                for _ in range(step - 1):
                    if not cap.grab():
                        break
        finally:
            cap.release()

        # Too short a sample (stream dropped) says nothing useful
        if stats is None or frame_t - t0_video < self.sample_seconds * 0.4:
            self._fail(camid, title, 'อ่านภาพไม่ได้')
            print(f"[Survey] {title}: stream dropped after {round((frame_t or 0) - (t0_video or 0), 1)}s")
            return
        seconds = frame_t - t0_video
        sample = {
            'camid': camid, 'title': title, 'ts': int(time.time()), 'seconds': round(seconds, 1),
            'cars': passed['cars'], 'motorcycles': passed['motorcycles'], 'trucks': passed['trucks'],
            'passed': sum(passed.values()),
            'rate_per_min': round(sum(passed.values()) * 60.0 / seconds, 1),
            'visible': round(sum(visible) / len(visible), 1),
            'moving_pct': stats['moving_pct'], 'level': stats['level'], 'error': '',
        }
        self.latest[camid] = sample
        self.vehicle_log.add_sample(sample)
        print(f"[Survey] {title}: {sample['passed']} passed in {sample['seconds']}s ({round(time.time() - t_wall0)}s wall) level={sample['level']}")
