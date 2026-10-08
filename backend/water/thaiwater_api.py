"""
The ThaiWater (HII) keyed API at twa-api-public.thaiwater.net: the anonymous key the public site ships, found again
when it rotates, and _get(), which every ThaiWater call goes through. Moved out of water_service.py (Oct 2026).
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from backend.core.instance import DATA_DIR

TWA_API = "https://twa-api-public.thaiwater.net"
# Anonymous key that twa.thaiwater.net ships to every browser; override with TWA_API_KEY if it rotates
TWA_API_KEY = os.getenv("TWA_API_KEY", "TPSXrHRvTHeVT2Lygq6YeTqqAm4xZ72x")
USER_AGENT = "BKK-Traffic-CCTV/2.0 (personal dashboard)"


# ---------------------------------------------------------------- api key discovery
TWA_SITE = "https://twa.thaiwater.net/th"
KEY_FILE = os.path.join(DATA_DIR, "cache", "twa_key.json")
KEY_RETRY_SECONDS = 300      # how long to wait between discovery attempts while no key works
_KEY_RE = re.compile(r'"x-api-key"\s*[:=]\s*"([A-Za-z0-9_\-]{16,128})"')
_CHUNK_RE = re.compile(r"/_next/static/chunks/[^\"']+\.js")


class _KeyStore:
    """Holds the anonymous key twa.thaiwater.net ships in its JS bundle.

    Order: env TWA_API_KEY > last key that worked (cache/twa_key.json) > built-in default.
    When the API answers 401 the key has rotated: scan the site's JS chunks for a new one.
    If none is found the scan is retried in the background every KEY_RETRY_SECONDS until it is."""

    def __init__(self):
        self.lock = threading.Lock()
        self.key = os.getenv("TWA_API_KEY") or self._load() or TWA_API_KEY
        self.last_scan = 0.0
        self.scanning = False
        self.broken = False   # True while the current key is known to be rejected

    def _load(self):
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("key") or None
        except Exception:
            return None

    def _save(self, key):
        try:
            os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
            with open(KEY_FILE, "w", encoding="utf-8") as f:
                json.dump({"key": key, "found_at": int(time.time())}, f)
        except Exception as e:
            print(f"[Water] key save failed: {e}")

    @staticmethod
    def _fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.read().decode("utf-8", "ignore")

    def scan(self):
        """Download the site's JS chunks and return every candidate key (most frequent first)."""
        html = self._fetch(TWA_SITE)
        found = {}
        for m in _KEY_RE.finditer(html):
            found[m.group(1)] = found.get(m.group(1), 0) + 1
        chunks = sorted(set(_CHUNK_RE.findall(html)))
        for path in chunks:
            try:
                js = self._fetch("https://twa.thaiwater.net" + path)
            except Exception:
                continue
            for m in _KEY_RE.finditer(js):
                found[m.group(1)] = found.get(m.group(1), 0) + 1
        return [k for k, _ in sorted(found.items(), key=lambda kv: -kv[1])]

    @staticmethod
    def _works(key):
        req = urllib.request.Request(TWA_API + "/v2/waterload-tide/list",
                                     headers={"User-Agent": USER_AGENT, "x-api-key": key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            return e.code not in (401, 403)
        except Exception:
            return False

    def rediscover(self, reason=""):
        """Scan the site once (rate limited) and switch to the first key the API accepts."""
        with self.lock:
            if self.scanning or time.time() - self.last_scan < 60:
                return False
            self.scanning = True
            self.last_scan = time.time()
        try:
            print(f"[Water] api key rejected{f' ({reason})' if reason else ''}; scanning twa.thaiwater.net for a new one")
            candidates = [k for k in self.scan() if k != self.key]
            for k in candidates:
                if self._works(k):
                    with self.lock:
                        self.key = k
                        self.broken = False
                    self._save(k)
                    print(f"[Water] new api key found ({k[:6]}...)")
                    return True
            print(f"[Water] no working key among {len(candidates)} candidate(s); retry in {KEY_RETRY_SECONDS // 60} min")
            return False
        except Exception as e:
            print(f"[Water] key scan failed: {e}")
            return False
        finally:
            with self.lock:
                self.scanning = False

    def mark_broken(self):
        with self.lock:
            first = not self.broken
            self.broken = True
        if first:
            threading.Thread(target=self._retry_loop, daemon=True, name="twa-key").start()

    def _retry_loop(self):
        """Keep looking until a key works again; the site may deploy the new bundle hours later."""
        while True:
            if self.rediscover():
                return
            with self.lock:
                if not self.broken:
                    return
            time.sleep(KEY_RETRY_SECONDS)


_keys = _KeyStore()


# ---------------------------------------------------------------- http + cache
def _get(path, **params):
    url = TWA_API + path + ("?" + urllib.parse.urlencode(params) if params else "")

    def call():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "x-api-key": _keys.key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = call()
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            raise
        # Key rotated: try to pick up the new one right away, else keep retrying in the background
        if _keys.rediscover(f"HTTP {e.code}"):
            data = call()
        else:
            _keys.mark_broken()
            raise
    _keys.broken = False
    return data


def key_status():
    return {"key_prefix": _keys.key[:6], "rejected": _keys.broken, "last_scan": int(_keys.last_scan) or None}
