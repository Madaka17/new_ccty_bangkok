"""Real global active-fault traces from the GEM Global Active Faults Database
(GAF-DB): https://github.com/GEMScienceTools/gem-global-active-faults

Data license: CC BY-SA (Styron & Pagani, 2020, Earthquake Spectra 36(1_suppl))
-- see the "note" text returned alongside the data and cite the source if you
redistribute this further.

The shapefile (~16,000 fault traces / ~178,000 vertices) is downloaded once,
simplified (Douglas-Peucker) and cached to disk as compact JSON so normal
server starts just load the cache instead of re-downloading ~41MB and
re-parsing every time.
"""
import json
import os
import threading
import time
import urllib.request

from . import db as dbmod

RAW_DIR = os.path.join(dbmod.BASE_DIR, "data", "gem_faults_raw")
CACHE_PATH = os.path.join(dbmod.BASE_DIR, "data", "gem_faults.json")
BASE_URL = "https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/master/shapefile/gem_active_faults"
SOURCE_NOTE = ("GEM Global Active Faults Database (GAF-DB), CC BY-SA -- "
               "Styron & Pagani (2020), Earthquake Spectra 36(1_suppl), 160-180")
SIMPLIFY_EPSILON_DEG = 0.02  # ~2 km at the equator; only applied to longer traces

_lock = threading.Lock()
_state = {"ready": False, "building": False, "count": 0, "error": None}


def get_state():
    with _lock:
        return dict(_state)


def get_cached():
    if not os.path.exists(CACHE_PATH):
        return None
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _download(name):
    os.makedirs(RAW_DIR, exist_ok=True)
    dest = os.path.join(RAW_DIR, name)
    if os.path.exists(dest):
        return dest
    req = urllib.request.Request(f"{BASE_URL[:BASE_URL.rfind('/')]}/{name}",
                                  headers={"User-Agent": "enviro-seismic-command/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        out.write(resp.read())
    return dest


def _perp_dist(p, a, b):
    (ay, ax), (by_, bx), (py, px) = a, b, p
    dx, dy = bx - ax, by_ - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _rdp(points, epsilon):
    """Iterative Douglas-Peucker on a list of (lat, lng) tuples."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = points[start], points[end]
        dmax, idx = -1.0, -1
        for i in range(start + 1, end):
            d = _perp_dist(points[i], a, b)
            if d > dmax:
                dmax, idx = d, i
        if dmax > epsilon:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))
    return [p for p, k in zip(points, keep) if k]


def _build():
    import shapefile  # local import: only needed the (rare) time we actually build the cache

    with _lock:
        _state["building"] = True
    try:
        shp = _download("gem_active_faults.shp")
        shx = _download("gem_active_faults.shx")
        dbf = _download("gem_active_faults.dbf")
        reader = shapefile.Reader(shp=shp, shx=shx, dbf=dbf, encoding="ISO-8859-1")

        faults = []
        for sr in reader.iterShapeRecords():
            pts = sr.shape.points
            if len(pts) < 2:
                continue
            latlng = [(round(lat, 4), round(lng, 4)) for lng, lat in pts]
            if len(latlng) > 6:
                latlng = _rdp(latlng, SIMPLIFY_EPSILON_DEG)
            rec = sr.record.as_dict()
            name = (rec.get("name") or "").strip() or (rec.get("fs_name") or "").strip() or None
            faults.append({
                "name": name,
                "slip_type": (rec.get("slip_type") or "").strip() or None,
                "points": [list(p) for p in latlng],
            })

        payload = {
            "source": SOURCE_NOTE,
            "url": "https://github.com/GEMScienceTools/gem-global-active-faults",
            "count": len(faults),
            "built_at": time.time(),
            "faults": faults,
        }
        tmp_path = CACHE_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp_path, CACHE_PATH)

        with _lock:
            _state["ready"] = True
            _state["count"] = len(faults)
            _state["error"] = None
    except Exception as exc:
        with _lock:
            _state["error"] = str(exc)
    finally:
        with _lock:
            _state["building"] = False


def ensure_built_async():
    cached = get_cached()
    if cached is not None:
        with _lock:
            _state["ready"] = True
            _state["count"] = cached.get("count", 0)
        return
    with _lock:
        if _state["building"]:
            return
    threading.Thread(target=_build, daemon=True).start()
