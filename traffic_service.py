"""
Traffic data service for the Bangkok metropolitan area.

- Pulls Longdo Traffic vector tiles (green / yellow / red road segments),
  decodes them and aggregates congestion per named road.
- Names come from the Longdo base-map vector tiles (road layer), cached on disk
  once so the join works offline.
- Also acts as a tile proxy + disk cache so the web map keeps working when the
  internet drops (last good tiles are served).
"""
import gzip
import json
import math
import os
import threading
import time
import urllib.request

import mapbox_vector_tile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
TRAFFIC_TILE_DIR = os.path.join(CACHE_DIR, "traffic_tiles")
BASE_TILE_DIR = os.path.join(CACHE_DIR, "longdo_base")
OSM_TILE_DIR = os.path.join(CACHE_DIR, "osm")
HISTORY_FILE = os.path.join(CACHE_DIR, "traffic_history.json")

TRAFFIC_TILE_URL = "https://msv.longdo.com/maps/traffic/{z}/{x}/{y}.pbf"
BASE_TILE_URL = "https://msv.longdo.com/maps/longdo/{z}/{x}/{y}.pbf"
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "BKK-Traffic-CCTV/2.0 (personal dashboard)"

# Bangkok + inner metropolitan area (lon_min, lat_min, lon_max, lat_max)
BBOX = (100.30, 13.50, 100.95, 14.05)
ANALYSIS_ZOOM = 12
REFRESH_SECONDS = 180
TRAFFIC_TILE_TTL = 120

COLOR_CLASS = {
    "54C00C": "green",
    "FEDE04": "yellow",
    "FF2020": "red",
}
ROAD_TYPES = {
    "nu:motorway", "nu:trunk", "nu:primary", "nu:secondary", "nu:tertiary",
    "nu:motorway_link", "nu:trunk_link", "nu:primary_link", "nu:expressway",
}
MAX_HISTORY = 288  # 288 x 3 min = 14.4 h

for d in (TRAFFIC_TILE_DIR, BASE_TILE_DIR, OSM_TILE_DIR):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------- tile math
def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_lonlat(x, y, z):
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def bbox_tiles(z):
    x0, y0 = lonlat_to_tile(BBOX[0], BBOX[3], z)
    x1, y1 = lonlat_to_tile(BBOX[2], BBOX[1], z)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def classify_color(hex_color):
    if not hex_color:
        return None
    hex_color = hex_color.upper()
    if hex_color in COLOR_CLASS:
        return COLOR_CLASS[hex_color]
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    except ValueError:
        return None
    if g > r and g > b:
        return "green"
    if r > 200 and g > 150:
        return "yellow"
    if r > g and r > b:
        return "red"
    return None


def seg_length_km(points):
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(points, points[1:]):
        dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
        dy = (lat2 - lat1) * 110.57
        total += math.hypot(dx, dy)
    return total


# ---------------------------------------------------------------- fetching
def http_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_traffic_tile(z, x, y):
    """Return (bytes, is_stale). Bytes are gzip-compressed pbf. Cached with TTL, stale on failure."""
    path = os.path.join(TRAFFIC_TILE_DIR, f"{z}_{x}_{y}.pbf")
    fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < TRAFFIC_TILE_TTL
    if fresh:
        with open(path, "rb") as f:
            return f.read(), False
    try:
        data = http_get(TRAFFIC_TILE_URL.format(z=z, x=x, y=y))
        if data and data[:2] != b"\x1f\x8b":
            data = gzip.compress(data)
        with open(path, "wb") as f:
            f.write(data)
        return data, False
    except Exception:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read(), True
        return b"", True


def get_base_tile(z, x, y):
    path = os.path.join(BASE_TILE_DIR, f"{z}_{x}_{y}.pbf")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    data = http_get(BASE_TILE_URL.format(z=z, x=x, y=y), timeout=20)
    with open(path, "wb") as f:
        f.write(data)
    return data


def get_osm_tile(z, x, y):
    """Raster base map tile, cached forever (offline after first view)."""
    path = os.path.join(OSM_TILE_DIR, str(z), str(x), f"{y}.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    data = http_get(OSM_TILE_URL.format(z=z, x=x, y=y))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return data


def decode_tile(raw, z, x, y):
    if not raw:
        return {}
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True})


def feature_lonlat(geom, z, x, y, extent=4096):
    """Convert MVT geometry (tile px, y down) to list of lon/lat linestrings."""
    n = 2 ** z
    lines = []
    if geom["type"] == "LineString":
        parts = [geom["coordinates"]]
    elif geom["type"] == "MultiLineString":
        parts = geom["coordinates"]
    else:
        return lines
    for part in parts:
        pts = []
        for px, py in part:
            lon = (x + px / extent) / n * 360.0 - 180.0
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n))))
            pts.append((lon, lat))
        if len(pts) >= 2:
            lines.append(pts)
    return lines


# ---------------------------------------------------------------- road index
class RoadIndex:
    """Grid index of named road segments for nearest-road lookup."""

    CELL = 0.004  # ~ 440 m

    def __init__(self):
        self.grid = {}
        self.count = 0

    def _key(self, lon, lat):
        return (int(lon / self.CELL), int(lat / self.CELL))

    def add(self, name, points):
        for a, b in zip(points, points[1:]):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            self.grid.setdefault(self._key(*mid), []).append((name, a, b))
            self.count += 1

    @staticmethod
    def _dist(p, a, b):
        # point-to-segment distance in km (equirectangular)
        cosl = math.cos(math.radians(p[1]))
        px, py = p[0] * cosl, p[1]
        ax, ay = a[0] * cosl, a[1]
        bx, by = b[0] * cosl, b[1]
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            t = 0
        else:
            t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        cx, cy = ax + t * dx, ay + t * dy
        return math.hypot((px - cx) * 111.32, (py - cy) * 110.57)

    def nearest(self, lon, lat, max_km=0.06):
        kx, ky = self._key(lon, lat)
        best, best_d = None, max_km
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for name, a, b in self.grid.get((kx + i, ky + j), ()):
                    d = self._dist((lon, lat), a, b)
                    if d < best_d:
                        best, best_d = name, d
        return best


# ---------------------------------------------------------------- service
class TrafficService:
    def __init__(self):
        self.lock = threading.Lock()
        self.road_index = None
        self.summary = {"ready": False, "updated_at": None, "roads": [], "history": []}
        self.history = self._load_history()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.online = True

    def start(self):
        self.thread.start()

    # ---- persistence
    def _load_history(self):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)[-MAX_HISTORY:]
        except Exception:
            return []

    def _save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[-MAX_HISTORY:], f)
        except Exception:
            pass

    # ---- road names
    def _build_road_index(self):
        idx = RoadIndex()
        z = ANALYSIS_ZOOM
        for x, y in bbox_tiles(z):
            try:
                tile = decode_tile(get_base_tile(z, x, y), z, x, y)
            except Exception as e:
                print(f"[Traffic] base tile {z}/{x}/{y} failed: {e}")
                continue
            layer = tile.get("road")
            if not layer:
                continue
            for feat in layer["features"]:
                props = feat["properties"]
                name = props.get("name_l") or props.get("name_e")
                if not name or props.get("type") not in ROAD_TYPES:
                    continue
                for line in feature_lonlat(feat["geometry"], z, x, y, layer.get("extent", 4096)):
                    idx.add(name, line)
        print(f"[Traffic] Road index ready: {idx.count} segments")
        return idx

    # ---- traffic aggregation
    def refresh(self):
        z = ANALYSIS_ZOOM
        roads = {}
        totals = {"green": 0.0, "yellow": 0.0, "red": 0.0}
        stale_tiles = 0
        for x, y in bbox_tiles(z):
            raw, stale = get_traffic_tile(z, x, y)
            stale_tiles += 1 if stale else 0
            try:
                tile = decode_tile(raw, z, x, y)
            except Exception:
                continue
            layer = tile.get("traffic")
            if not layer:
                continue
            for feat in layer["features"]:
                props = feat["properties"]
                for line in feature_lonlat(feat["geometry"], z, x, y, layer.get("extent", 4096)):
                    km = seg_length_km(line)
                    if km <= 0:
                        continue
                    mid = line[len(line) // 2]
                    name = self.road_index.nearest(*mid) if self.road_index else None
                    for cls in (classify_color(props.get("fillcolor")), classify_color(props.get("fillcolor_r"))):
                        if not cls:
                            continue
                        totals[cls] += km
                        if name:
                            r = roads.setdefault(name, {"name": name, "green": 0.0, "yellow": 0.0, "red": 0.0})
                            r[cls] += km

        total_km = sum(totals.values())
        road_list = []
        for r in roads.values():
            length = r["green"] + r["yellow"] + r["red"]
            if length < 0.3:
                continue
            score = (r["green"] * 1.0 + r["yellow"] * 0.5) / length
            road_list.append({
                "name": r["name"],
                "length_km": round(length, 1),
                "red_km": round(r["red"], 1),
                "green_pct": round(100 * r["green"] / length),
                "yellow_pct": round(100 * r["yellow"] / length),
                "red_pct": round(100 * r["red"] / length),
                "flow": round(100 * score),
                "level": "โล่ง" if score >= 0.75 else ("ปานกลาง" if score >= 0.45 else "ติดขัด"),
            })
        road_list.sort(key=lambda r: (-r["red_km"], r["flow"]))

        flow_index = round(100 * (totals["green"] + 0.5 * totals["yellow"]) / total_km) if total_km else None
        now = time.time()
        with self.lock:
            self.online = stale_tiles < len(bbox_tiles(z)) / 2
            if flow_index is not None and not stale_tiles:
                self.history.append({"t": int(now), "flow": flow_index,
                                     "red_pct": round(100 * totals["red"] / total_km)})
                self.history = self.history[-MAX_HISTORY:]
                self._save_history()
            self.summary = {
                "ready": True,
                "online": self.online,
                "updated_at": int(now),
                "total_km": round(total_km, 1),
                "green_pct": round(100 * totals["green"] / total_km) if total_km else 0,
                "yellow_pct": round(100 * totals["yellow"] / total_km) if total_km else 0,
                "red_pct": round(100 * totals["red"] / total_km) if total_km else 0,
                "flow_index": flow_index,
                "roads": road_list,
                "road_count": len(road_list),
            }
        print(f"[Traffic] refreshed: {len(road_list)} roads, flow index {flow_index}, stale tiles {stale_tiles}")

    def _loop(self):
        try:
            self.road_index = self._build_road_index()
        except Exception as e:
            print(f"[Traffic] road index failed: {e}")
        while True:
            try:
                self.refresh()
            except Exception as e:
                print(f"[Traffic] refresh error: {e}")
            time.sleep(REFRESH_SECONDS)

    # ---- queries
    def get_summary(self, top=8):
        with self.lock:
            s = dict(self.summary)
            roads = s.get("roads", [])
            s["congested"] = roads[:top]
            s["free_flow"] = sorted([r for r in roads if r["flow"] >= 85], key=lambda r: -r["length_km"])[:top]
            s["history"] = list(self.history)
            s.pop("roads", None)
            return s

    def get_roads(self, query=None, limit=50):
        with self.lock:
            roads = list(self.summary.get("roads", []))
        if query:
            q = query.strip().lower()
            roads = [r for r in roads if q in r["name"].lower()]
        return roads[:limit]

    def find_roads_in_text(self, text, limit=6):
        """Match road names mentioned in a free-text question."""
        with self.lock:
            roads = list(self.summary.get("roads", []))
        t = text.lower()
        hits = []
        for r in roads:
            name = r["name"].lower()
            key = name.replace("ถนน", "").replace("ถ.", "").strip()
            if key and len(key) >= 3 and key in t:
                hits.append(r)
        return hits[:limit]


traffic = TrafficService()
