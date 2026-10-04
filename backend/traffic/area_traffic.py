"""
Traffic in every province and district (amphoe; khet in Bangkok), for the "รถติดแค่ไหนตอนนี้" card.

Every REFRESH_SECONDS it reads the Longdo Traffic vector tiles at zoom ZOOM over the whole country (about 1,500
tiles: main and secondary roads, the same green / yellow / red lines the map shows), puts each line in the
district its middle falls in, and adds up the km of each colour per district, per province and for the country.
The score is the one the Bangkok summary uses: 100 x (green km + half the yellow km) / all km, both directions.

Bangkok's khet are read at zoom 12 instead (the tiles traffic_service.py already fetches every minute for its
own summary, so read from the shared disk cache): at zoom 11 the small inner khet have almost no road left.

District boundaries: config/thailand_districts.geojson, 928 districts from OpenGISData-Thailand
(github.com/chingchai/OpenGISData-Thailand, districts.geojson), simplified to about 100 m.

Load on Longdo: at most MAX_RPS tiles a second. A tile already fetched in the last TILE_MAX_AGE seconds (by this
server or by the other instance, which shares the tile cache) is read from disk instead.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import shapely
from shapely.geometry import box, shape

from backend.core import thai_regions
from backend.core.instance import BASE_DIR, DATA_DIR
from backend.traffic.traffic_service import (ANALYSIS_ZOOM, bbox_tiles, classify_color, decode_tile, feature_lonlat,
                                             get_traffic_tile, lonlat_to_tile, seg_length_km, tile_to_lonlat)

DISTRICTS_FILE = os.path.join(BASE_DIR, "config", "thailand_districts.geojson")
STATE_FILE = os.path.join(DATA_DIR, "cache", "area_traffic.json")
ZOOM = 11
BANGKOK = "10"          # province code whose khet use the zoom-12 tiles of the Bangkok summary
REFRESH_SECONDS = int(os.getenv("AREA_TRAFFIC_SECONDS", "300"))
TILE_MAX_AGE = REFRESH_SECONDS - 60
MAX_RPS = 6
WORKERS = 4
MIN_KM = 1.0            # less road than this in an area: no score ("ข้อมูลน้อย")
HISTORY = 16            # snapshots kept for the change against about an hour ago


def _stats(g, y, r, prev=None):
    total = g + y + r
    flow = round(100 * (g + 0.5 * y) / total) if total >= MIN_KM else None
    out = {"flow": flow, "total_km": round(total, 1), "green_km": round(g, 1), "yellow_km": round(y, 1),
           "red_km": round(r, 1), "red_pct": round(100 * r / total) if total else 0}
    if prev is not None:
        out["flow_1h"] = prev
    return out


class AreaTraffic:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"ready": False}
        self.history = []        # [{"t", "flows": {area key: flow}}]
        self.names = []          # per district: (code, district, province code)
        self.tree = None
        self.tiles = []
        self._load_state()

    # ---- setup
    def _load_districts(self):
        with self.lock:
            if self.tree is not None:
                return
            self._read_districts()

    def _read_districts(self):
        with open(DISTRICTS_FILE, encoding="utf-8") as f:
            feats = json.load(f)["features"]
        geoms = []
        for ft in feats:
            p = ft["properties"]
            self.names.append((p["amp_code"], p["amp_th"], p["pro_code"]))
            geoms.append(shape(ft["geometry"]))
        tree = shapely.STRtree(geoms)
        # Tiles that touch at least one district
        minx, miny, maxx, maxy = shapely.total_bounds(geoms)
        x0, y0 = lonlat_to_tile(minx, maxy, ZOOM)
        x1, y1 = lonlat_to_tile(maxx, miny, ZOOM)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                lon0, lat1 = tile_to_lonlat(x, y, ZOOM)
                lon1, lat0 = tile_to_lonlat(x + 1, y + 1, ZOOM)
                if len(tree.query(box(lon0, lat0, lon1, lat1), predicate="intersects")):
                    self.tiles.append((x, y))
        self.tree = tree
        print(f"[AreaTraffic] {len(geoms)} districts, {len(self.tiles)} tiles at zoom {ZOOM}")

    def _load_state(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            self.state, self.history = saved["state"], saved.get("history", [])
        except (OSError, ValueError, KeyError):
            pass

    def _save_state(self):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"state": self.state, "history": self.history}, f, ensure_ascii=False)
        except OSError:
            pass

    # ---- one pass over the country
    def _fetch(self, xy, z=ZOOM):
        x, y = xy
        raw, stale = get_traffic_tile(z, x, y, max_age=TILE_MAX_AGE)
        lines = []
        try:
            tile = decode_tile(raw, z, x, y)
        except Exception:
            return lines, True
        layer = tile.get("traffic")
        if not layer:
            return lines, stale
        for feat in layer["features"]:
            props = feat["properties"]
            colors = [c for c in (classify_color(props.get("fillcolor")), classify_color(props.get("fillcolor_r"))) if c]
            if not colors:
                continue
            for line in feature_lonlat(feat["geometry"], z, x, y, layer.get("extent", 4096)):
                km = seg_length_km(line)
                if km > 0:
                    lines.append((line[len(line) // 2], km, colors))
        return lines, stale

    def refresh(self):
        started = time.time()
        lines, stale = [], 0
        fine = []   # Bangkok at zoom 12
        for xy in bbox_tiles(ANALYSIS_ZOOM):
            fine += self._fetch(xy, ANALYSIS_ZOOM)[0]
        with ThreadPoolExecutor(WORKERS) as pool:
            futures = []
            for i, xy in enumerate(self.tiles):
                # Pace the requests: at most MAX_RPS a second (tiles read from disk wait too, which is harmless)
                time.sleep(max(0.0, started + i / MAX_RPS - time.time()))
                futures.append(pool.submit(self._fetch, xy))
            for fut in futures:
                got, was_stale = fut.result()
                lines += got
                stale += was_stale
        # District of each line, by the point in its middle
        km = {}   # district index -> [green, yellow, red]
        for group, in_bangkok in ((lines, False), (fine, True)):
            if not group:
                continue
            pts = shapely.points([mid for mid, _, _ in group])
            line_idx, district_idx = self.tree.query(pts, predicate="within")
            for li, di in zip(line_idx, district_idx):
                if (self.names[di][2] == BANGKOK) != in_bangkok:
                    continue
                _, length, colors = group[li]
                acc = km.setdefault(int(di), [0.0, 0.0, 0.0])
                for c in colors:
                    acc[("green", "yellow", "red").index(c)] += length
        self._publish(km, stale)
        print(f"[AreaTraffic] {len(lines)} lines in {len(km)} districts, {stale} stale tiles, {time.time() - started:.0f}s")

    def _publish(self, km, stale):
        prev = self._hour_ago()
        provinces = {}
        for i, (code, name, pcode) in enumerate(self.names):
            g, y, r = km.get(i, (0.0, 0.0, 0.0))
            p = provinces.setdefault(pcode, {"sum": [0.0, 0.0, 0.0], "amphoes": []})
            p["sum"] = [a + b for a, b in zip(p["sum"], (g, y, r))]
            p["amphoes"].append({"code": code, "name": name, **_stats(g, y, r, prev.get(code))})
        out, flows = [], {}
        for pcode, p in provinces.items():
            province = thai_regions.PROVINCES.get(pcode, ("", ""))[0]
            p["amphoes"].sort(key=lambda a: a["name"])
            item = {"code": pcode, "province": province, "region": thai_regions.region_of(province),
                    **_stats(*p["sum"], prev.get(pcode)), "amphoes": p["amphoes"]}
            out.append(item)
            flows[pcode] = item["flow"]
            flows.update({a["code"]: a["flow"] for a in p["amphoes"]})
        out.sort(key=lambda p: p["province"])
        total = [sum(p["sum"][k] for p in provinces.values()) for k in range(3)]
        now = int(time.time())
        with self.lock:
            self.state = {"ready": True, "updated_at": now, "online": stale < len(self.tiles) / 2,
                          "tiles": len(self.tiles), "stale_tiles": stale, "zoom": ZOOM,
                          "national": _stats(*total, prev.get("TH")), "provinces": out}
            flows["TH"] = self.state["national"]["flow"]
            if stale < len(self.tiles) / 2:
                self.history = (self.history + [{"t": now, "flows": flows}])[-HISTORY:]
            self._save_state()

    def _hour_ago(self):
        """Flows of the snapshot taken 50-75 minutes ago, {} when there is none."""
        now = time.time()
        old = [h for h in self.history if 3000 <= now - h["t"] <= 4500]
        return min(old, key=lambda h: abs(now - h["t"] - 3600))["flows"] if old else {}

    def locate(self, lat, lng):
        """(province, district) at a position, ("", "") outside every district."""
        try:
            self._load_districts()
            hit = self.tree.query(shapely.Point(float(lng), float(lat)), predicate="within")
        except Exception:
            return "", ""
        if not len(hit):
            return "", ""
        _, name, pcode = self.names[int(hit[0])]
        return thai_regions.PROVINCES.get(pcode, ("", ""))[0], name

    def geometry(self, pcode, acode=""):
        """Outline of one district (acode) or of a whole province, None when the code is unknown."""
        self._load_districts()
        geoms = self.tree.geometries
        parts = [geoms[i] for i, (code, _, p) in enumerate(self.names) if p == pcode and (not acode or code == acode)]
        return shapely.union_all(parts) if parts else None

    def district_name(self, acode):
        self._load_districts()
        return next((name for code, name, _ in self.names if code == acode), "")

    # ---- thread
    def _loop(self):
        try:
            self._load_districts()
        except Exception as e:
            print(f"[AreaTraffic] district boundaries failed: {e}")
            return
        while True:
            started = time.time()
            try:
                self.refresh()
            except Exception as e:
                print(f"[AreaTraffic] refresh error: {e}")
            time.sleep(max(30.0, REFRESH_SECONDS - (time.time() - started)))

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="area-traffic").start()

    def status(self):
        with self.lock:
            return self.state


area_traffic = AreaTraffic()
