"""
Frames from the iTIC cameras for the flood watch (flood_cam_service.py).

The iTIC foundation cameras (the CCTV pins on the map, listed by Longdo Traffic) watch highways and roads
the BMA cameras do not, in Bangkok and the provinces around it. Their JPEG snapshot host
camera1.iticfoundation.org has timed out its TLS handshake for weeks, so every ROUND_SECONDS this takes the
newest HLS segment of each camera (playlist -> chunklist -> last .ts, 0.2-2.5 MB) and the first frame in it.

The segments are decoded in a child process (ts_decode.py), never in the server: FFmpeg inside OpenCV has
crashed the server on corrupt Longdo streams before (see SURVEY_WORKERS in server.py).

    FLOOD_CAM_ITIC_PROVINCES  provinces to watch, comma separated, or "all". Default: Bangkok and the five
                              metro provinces, about 20 live cameras and 15 MB a round. All of them is about
                              210 live cameras and 150 MB a round.
    FLOOD_CAM_ITIC_SECONDS    seconds between rounds (default 300)

A camera whose stream fails (the camera1 host, a dead feed) is skipped for FAIL_BACKOFF seconds.
"""
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import cv2

from backend.core.instance import BASE_DIR, DATA_DIR

WORK_DIR = os.path.join(DATA_DIR, "cache", "itic_frames")
METRO = "กรุงเทพมหานคร,นนทบุรี,ปทุมธานี,สมุทรปราการ,สมุทรสาคร,นครปฐม"
PROVINCES = os.getenv("FLOOD_CAM_ITIC_PROVINCES", METRO).strip()
ROUND_SECONDS = int(os.getenv("FLOOD_CAM_ITIC_SECONDS", "300"))
TIMEOUT = 8
WORKERS = 6
FAIL_BACKOFF = 1800
DECODE_TIMEOUT = 180
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
_SAFE_ID = re.compile(r"[\w.-]{1,80}")   # the camid becomes a file name


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _last_segment(url):
    """URL of the newest .ts behind an HLS playlist; a master playlist is followed to its first variant."""
    for _ in range(2):
        uris = [ln.strip() for ln in _get(url).decode("utf-8", "ignore").splitlines()
                if ln.strip() and not ln.startswith("#")]
        if not uris:
            return None
        if not uris[-1].split("?")[0].endswith(".m3u8"):
            return urljoin(url, uris[-1])
        url = urljoin(url, uris[0])
    return None


class IticFrames:
    def __init__(self, watch, cameras):
        # cameras: callable returning the Longdo camera list (the server's /api/cameras/longdo, cached on disk)
        self._watch = watch
        self._cameras = cameras
        self._failed = {}      # camid -> when its stream last failed
        self.last_round = None
        os.makedirs(WORK_DIR, exist_ok=True)

    def _selected(self):
        provinces = None if PROVINCES.lower() == "all" else {p.strip() for p in PROVINCES.split(",") if p.strip()}
        out = []
        for c in self._cameras() or []:
            camid = str(c.get("camid") or "")
            if not _SAFE_ID.fullmatch(camid) or ".." in camid or not c.get("hls_url"):
                continue
            if provinces is not None and c.get("province") not in provinces:
                continue
            if c.get("latitude") and c.get("longitude"):
                out.append({**c, "camid": camid, "kind": "itic"})
        return out

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="itic-frames").start()

    def _loop(self):
        time.sleep(30)   # let the server finish starting
        while True:
            t0 = time.time()
            try:
                self.round()
            except Exception as e:  # noqa: BLE001 - try again next round
                print(f"[iTIC frames] round failed: {type(e).__name__}: {str(e)[:160]}")
            time.sleep(max(30, ROUND_SECONDS - (time.time() - t0)))

    def _download(self, cam):
        """The camera's newest segment on disk, or None when its stream does not answer."""
        try:
            url = _last_segment(cam["hls_url"])
            if not url:
                raise ValueError("empty playlist")
            path = os.path.join(WORK_DIR, f"{cam['camid']}.ts")
            with open(path, "wb") as f:
                f.write(_get(url))
            return path
        except Exception:  # noqa: BLE001 - host down, dead feed: skip it for a while
            self._failed[cam["camid"]] = time.time()
            return None

    def round(self):
        cams = self._selected()
        self._watch.add_cameras(cams)
        now = time.time()
        todo = [c for c in cams if now - self._failed.get(c["camid"], 0) > FAIL_BACKOFF]
        with ThreadPoolExecutor(WORKERS) as pool:
            jobs = [(c, ts, ts[:-3] + ".jpg") for c, ts in zip(todo, pool.map(self._download, todo)) if ts]
        for _, _, jpg in jobs:
            if os.path.exists(jpg):
                os.remove(jpg)   # a decoder crash must not hand over last round's frame
        if jobs:
            try:
                subprocess.run([sys.executable, "-m", "backend.vision.ts_decode"], cwd=BASE_DIR, timeout=DECODE_TIMEOUT,
                               input="".join(f"{ts}\t{jpg}\n" for _, ts, jpg in jobs), text=True, encoding="utf-8",
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                print("[iTIC frames] decoder timed out")
        frames = 0
        for cam, _, jpg in jobs:
            img = cv2.imread(jpg)
            if img is None:
                self._failed[cam["camid"]] = time.time()
                continue
            self._watch.observe(cam, img)
            frames += 1
        self.last_round = {"at": int(time.time()), "cameras": len(cams), "frames": frames}
        print(f"[iTIC frames] {frames} frames from {len(cams)} cameras")
