"""
The camera list Longdo Traffic publishes (iTIC and other owners), kept in memory and on disk.
Moved out of services.py (Oct 2026) so it can be used and tested without starting the detectors.

One live fetch at a time: requests that arrive meanwhile get the old list at once (or wait when there is
none). After a failed fetch the next live try waits RETRY_SECONDS; with Longdo down, every request would
otherwise wait out the 5 s timeout and call Longdo again.
"""
import json
import os
import re
import threading
import time
import urllib.request

from backend.core.instance import DATA_DIR

URL = "https://traffic.longdo.com/camera.json"
FRESH_SECONDS = 300    # a live copy is reused this long
RETRY_SECONDS = 60     # after a failed live try, wait this long before trying Longdo again
CACHE_FILE = os.path.join(DATA_DIR, "cache", "longdo_cameras.json")

_cache = {"data": None, "next_try": 0.0}
_lock = threading.Lock()


def _fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        items = json.loads(resp.read().decode("utf-8")).get("item", [])
    if not items:
        raise ValueError("empty camera list")
    formatted = []
    for it in items:
        title = (it.get("title") or "").strip()
        m = re.match(r"^\(([^)]+)\)", title)
        prov = m.group(1).replace("จ.", "").strip() if m else ""
        formatted.append({
            "camid": it.get("camid", ""),
            "title": title,
            "short_title": re.sub(r"^\([^)]+\)\s*", "", title),
            "province": prov or "กรุงเทพมหานคร",
            "organization": it.get("organization") or "Longdo Traffic",
            "hls_url": it.get("hls_url") or "",
            "vdourl": it.get("vdourl") or "",
            "imgurl": it.get("imgurl") or "",
            "latitude": float(it.get("latitude") or 0),
            "longitude": float(it.get("longitude") or 0),
            "geocode": str(it.get("geocode") or ""),
            "lastupdate": it.get("lastupdate") or ""
        })
    return {"total": len(formatted), "items": formatted}


def _save(data):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _load():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def longdo_cameras(fallback=()):
    """{total, items} from Longdo; the last good copy while Longdo fails; `fallback` items when there is none."""
    if _cache["data"] is not None and time.time() < _cache["next_try"]:
        return _cache["data"]
    if not _lock.acquire(blocking=_cache["data"] is None):
        return _cache["data"]   # another request is fetching: keep serving the old list meanwhile
    try:
        now = time.time()
        if now >= _cache["next_try"]:   # else another thread fetched (or failed) while this one waited
            try:
                _cache["data"] = _fetch()
                _cache["next_try"] = now + FRESH_SECONDS
                _save(_cache["data"])
                return _cache["data"]
            except Exception as e:
                print(f"[Warning] Failed to fetch live Longdo cameras: {e}")
                _cache["next_try"] = now + RETRY_SECONDS
                if _cache["data"] is None:
                    _cache["data"] = _load()
        if _cache["data"] is not None:
            return _cache["data"]
        items = list(fallback)
        return {"total": len(items), "items": items}
    finally:
        _lock.release()
