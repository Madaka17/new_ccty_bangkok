"""
HTTP access to the BMA Traffic camera site: BmaSession keeps one ASP.NET session per camera so a frame costs one
request. Moved out of bma_service.py (Oct 2026).
"""
import threading
import time

import requests

from backend.bma import bma_site


class BmaSession:
    """HTTP access to the BMA Traffic site: one requests.Session per thread (connection pooling), and one
    ASP.NET session (cookie jar) per camera.

    show.aspx serves the camera the ASP.NET session last opened in PlayVideo.aspx and ignores its image=
    (asked for camera 420 while bound to 310, it sends 310's picture). A session per camera stays bound,
    so a frame costs one request (show.aspx, ~1.3 s) instead of PlayVideo + show; a camera's first frame,
    or one after its session expired, costs the home page + PlayVideo + show (5-6 s). Tested 2026-09-28/29:
    a jar bound once kept serving that camera's live frame on later calls, and was still bound after
    8 min idle (a scan cycle revisits it every 3-4 min).

    A camera that sends nothing keeps its bound session, so each cycle asks it once (show.aspx) and it
    comes back as soon as it sends again; a new session is started for it at most every REBIND_BACKOFF
    (15 such cameras bound again every cycle took ~30 s of a 230 s cycle)."""

    REBIND_BACKOFF = 600

    def __init__(self):
        self._local = threading.local()
        self._jars = {}          # camid -> RequestsCookieJar of the ASP.NET session bound to that camera
        self._rebind_after = {}  # camid -> time before which a camera that sent nothing is not bound again

    def _get_session(self) -> requests.Session:
        s = getattr(self._local, 'session', None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language': 'th,en-US;q=0.9,en;q=0.8',
            })
            self._local.session = s
        return s

    @staticmethod
    def _show(s, camid_str, timeout):
        """The camera's JPEG from show.aspx, or None for a placeholder (< 2500 bytes), an error or a timeout."""
        try:
            res = s.get(
                f'{bma_site.base()}show.aspx?image={camid_str}&time={int(time.time() * 1000)}',
                headers={'Referer': f'{bma_site.base()}PlayVideo.aspx?ID={camid_str}'},
                timeout=timeout
            )
            if res.status_code == 200 and len(res.content) > 2500:
                return res.content
        except Exception:
            pass
        return None

    def reset(self):
        """Forget every bound ASP.NET session (after the site moved to another address)."""
        self._jars.clear()
        self._rebind_after.clear()

    def fetch_snapshot(self, camid: str, timeout: float = 4.0) -> bytes:
        """Fetch raw snapshot JPEG for a camera ID from BMA traffic."""
        s = self._get_session()
        camid_str = str(camid)

        jar = self._jars.get(camid_str)
        if jar is not None:
            s.cookies = jar
            raw = self._show(s, camid_str, timeout)
            if raw:
                return raw

        if time.time() < self._rebind_after.get(camid_str, 0):
            return None
        # No session for this camera yet, it expired, or the camera is offline: start a new ASP.NET
        # session (the home page; PlayVideo.aspx alone gets a placeholder) and bind it to this camera.
        # The home page is the site root: index.aspx itself answers 404 since 2026-10-07.
        # It is a big page (386-416 KB, 2.5-7 s, longer while other workers ask too): more time than one frame
        s.cookies = requests.cookies.RequestsCookieJar()
        bind_timeout = max(timeout, 15.0)
        try:
            s.get(bma_site.base(), timeout=bind_timeout)
            s.get(f'{bma_site.base()}PlayVideo.aspx?ID={camid_str}', headers={'Referer': bma_site.base()}, timeout=bind_timeout)
        except Exception:
            return None   # the home page (~400 KB) timed out: BMA is busy, not this camera, so no backoff
        raw = self._show(s, camid_str, timeout)
        self._jars[camid_str] = s.cookies
        if raw:
            self._rebind_after.pop(camid_str, None)
        else:
            self._rebind_after[camid_str] = time.time() + self.REBIND_BACKOFF
        return raw
