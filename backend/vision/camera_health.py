"""
Is each live-AI camera's stream reachable right now? For the camera search on the Camera AI page.

Fetches the HLS playlist (or the MJPEG URL when a camera has no HLS) of every camera in
config/cameras_bkk.json, all in parallel, at most once per CACHE_SECONDS. A camera whose source
host is down (camera1.iticfoundation.org timed out its HTTPS handshake for weeks) is "offline",
so people can skip it instead of waiting on a stream that never starts.
"""
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CACHE_SECONDS = 300
TIMEOUT = 6
WORKERS = 40  # one round, so a check takes about TIMEOUT even when many hosts are down
USER_AGENT = "Mozilla/5.0 (BKK StreetSmart camera check)"


class CameraHealth:
    def __init__(self, cameras):
        # cameras: callable returning the current camera list (the server appends cameras at runtime)
        self._cameras = cameras
        self._status = {}
        self._checked = 0.0
        self._lock = threading.Lock()

    def start(self):
        # First check in the background, so the first search does not wait for it
        threading.Thread(target=self.get, daemon=True).start()

    @staticmethod
    def _probe(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                resp.read(512)  # an MJPEG URL never ends: a first chunk is enough
                return "online" if resp.status == 200 else "offline"
        except Exception:
            return "offline"

    def get(self):
        # One check round at a time; callers that arrive during it wait and share its result
        with self._lock:
            if time.time() - self._checked > CACHE_SECONDS:
                cams = [(c["camid"], c.get("hls_url") or c.get("vdourl")) for c in self._cameras()]
                cams = [(camid, url) for camid, url in cams if url]
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    self._status = dict(zip((camid for camid, _ in cams), pool.map(self._probe, (url for _, url in cams))))
                self._checked = time.time()
            return {"checked_at": int(self._checked), "items": dict(self._status)}
