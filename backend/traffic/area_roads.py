"""
Road cards for one province or district, for the "ถนนสายหลัก: ติดตรงไหน เลี่ยงทางไหน" card when an area is picked
in "รถติดแค่ไหนตอนนี้". Shaped like guidance_service's corridor cards, but built for any area of Thailand:

  * roads        - every Longdo traffic line whose middle falls in the area, named by the nearest road of the
                   Longdo base map; one card per named road with at least MIN_KM inside the area
  * status       - the same km-weighted score and thresholds as the corridors
  * hotspots     - the red pieces merged per ~1 km cell (as traffic_service does), named by the nearest other
                   road there ("ใกล้ ถนน X")
  * alternatives - other roads of the area within ALT_KM whose traffic moves (green first)
  * incidents    - accidents, closed roads and floods (passed in by server.py) within INCIDENT_KM of the road
  * action / signal - guidance_service's Thai template (no AI: an answer per area on demand would be too many calls)

Tiles: zoom 11 outside Bangkok (the ones area_traffic.py reads for the whole country every 5 minutes, so read from
the disk cache) and zoom 12 for Bangkok (the ones traffic_service.py reads every minute). Answers are kept
CACHE_SECONDS per area.
"""
import math
import os
import threading
import time

import shapely

from backend.core import thai_regions
from backend.traffic.area_traffic import BANGKOK, TILE_MAX_AGE, area_traffic
from backend.traffic.guidance_service import FREE_FLOW, LEVEL_TH, GuidanceService
from backend.traffic.traffic_service import (BASE_TILE_DIR, ROAD_TYPES, RoadIndex, classify_color, decode_tile,
                                             feature_lonlat, get_base_tile, get_traffic_tile, lonlat_to_tile,
                                             seg_length_km)

CACHE_SECONDS = 300
MIN_KM = 1.0            # a road with less than this inside the area gets no card
TOP = 24                # cards per area
ALT_KM = 8.0            # an alternative's centre is at most this far from the road's centre
INCIDENT_KM = 0.3       # an event this close to the road counts as on it
HOTSPOT_LABEL_KM = 0.5  # the road named in a hotspot label is at most this far away
NOT_A_ROAD = ("จุดกลับรถ",)   # U-turn points carry names on the base map: never a card or an alternative
WARM_RPS = 3            # base tiles a second while warm() fills the disk cache

_lock = threading.Lock()
_cache = {}             # (province code, district code) -> (time, answer)


def _km(lat1, lng1, lat2, lng2):
    dy = (lat2 - lat1) * 110.57
    dx = (lng2 - lng1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _tiles(geom, z):
    minx, miny, maxx, maxy = geom.bounds
    x0, y0 = lonlat_to_tile(minx, maxy, z)
    x1, y1 = lonlat_to_tile(maxx, miny, z)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def _road_index(tiles, z):
    idx = RoadIndex()
    for x, y in tiles:
        try:
            tile = decode_tile(get_base_tile(z, x, y), z, x, y)
        except Exception:
            continue
        layer = tile.get("road")
        if not layer:
            continue
        for feat in layer["features"]:
            props = feat["properties"]
            name = props.get("name_l") or props.get("name_e")
            if name and props.get("type") in ROAD_TYPES:
                for line in feature_lonlat(feat["geometry"], z, x, y, layer.get("extent", 4096)):
                    idx.add(name.strip(), line)
    return idx


def _other_road(index, lng, lat, road):
    """The nearest road other than `road` within HOTSPOT_LABEL_KM of a point, or None."""
    kx, ky = index._key(lng, lat)
    best, best_d = None, HOTSPOT_LABEL_KM
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for name, a, b in index.grid.get((kx + i, ky + j), ()):
                if name != road:
                    d = index._dist((lng, lat), a, b)
                    if d < best_d:
                        best, best_d = name, d
    return best


def _status(flow, incidents):
    if incidents:
        return "incident", "red", 1
    if flow is None:
        return "unknown", "neutral", 5
    if flow < 45:
        return "congested", "red", 1
    if flow < 75:
        return "moderate", "yellow", 2
    return "free", "green", 4


def warm():
    """Fetch the zoom-11 base tiles of the whole country once, in the background (they stay on disk for good), so
    the first answer for a province does not wait about a minute for its road names."""
    def run():
        try:
            area_traffic._load_districts()
        except Exception:
            return
        for x, y in area_traffic.tiles:
            if os.path.exists(os.path.join(BASE_TILE_DIR, f"11_{x}_{y}.pbf")):
                continue
            try:
                get_base_tile(11, x, y)
            except Exception:
                pass
            time.sleep(1 / WARM_RPS)
    threading.Thread(target=run, daemon=True, name="area-roads-warm").start()


def analyse(pcode, acode="", events=()):
    """Cards for a province (acode "") or one district, None when the area is unknown.
    `events`: [{"kind", "title", "lat", "lng"}] of accidents, closed roads and floods."""
    key = (pcode, acode)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        answer = _build(pcode, acode, events)
        if answer is not None:
            if len(_cache) > 200:
                _cache.clear()
            _cache[key] = (time.time(), answer)
        return answer


def _build(pcode, acode, events):
    geom = area_traffic.geometry(pcode, acode)
    if geom is None:
        return None
    province = thai_regions.PROVINCES.get(pcode, ("", ""))[0]
    bangkok = pcode == BANGKOK
    district = area_traffic.district_name(acode) if acode else ""
    label = f"{'เขต' if bangkok else 'อ.'}{district} {province}" if acode else province
    z = 12 if bangkok else 11
    tiles = _tiles(geom, z)
    index = _road_index(tiles, z)
    shapely.prepare(geom)

    roads, stale = {}, 0
    for x, y in tiles:
        raw, was_stale = get_traffic_tile(z, x, y, max_age=TILE_MAX_AGE)
        stale += was_stale
        try:
            layer = decode_tile(raw, z, x, y).get("traffic")
        except Exception:
            continue
        for feat in (layer or {}).get("features", []):
            props = feat["properties"]
            colors = [c for c in (classify_color(props.get("fillcolor")), classify_color(props.get("fillcolor_r"))) if c]
            if not colors:
                continue
            for line in feature_lonlat(feat["geometry"], z, x, y, layer.get("extent", 4096)):
                mid = line[len(line) // 2]
                km = seg_length_km(line)
                if km <= 0 or not shapely.contains_xy(geom, *mid):
                    continue
                name = index.nearest(*mid)
                if not name:
                    continue
                r = roads.setdefault(name, {"km": [0.0, 0.0, 0.0], "lat": 0.0, "lng": 0.0, "w": 0.0, "spots": {}})
                for c in colors:
                    r["km"][("green", "yellow", "red").index(c)] += km
                    r["lat"] += mid[1] * km
                    r["lng"] += mid[0] * km
                    r["w"] += km
                    if c == "red":
                        sp = r["spots"].setdefault((round(mid[1] * 100), round(mid[0] * 100)), {"lat": 0.0, "lng": 0.0, "km": 0.0})
                        sp["km"] += km
                        sp["lat"] += mid[1] * km
                        sp["lng"] += mid[0] * km

    rows = []
    for name, r in roads.items():
        g, y, red = r["km"]
        total = g + y + red
        if total < MIN_KM or name.startswith(NOT_A_ROAD):
            continue
        flow = round(100 * (g + 0.5 * y) / total)
        rows.append({"name": name, "flow": flow, "red_km": round(red, 1), "length_km": round(total, 1),
                     "level": "โล่ง" if flow >= 75 else "ปานกลาง" if flow >= 45 else "ติดขัด",
                     "lat": r["lat"] / r["w"], "lng": r["lng"] / r["w"], "spots": r["spots"]})

    items = []
    for row in rows:
        spots = []
        for sp in sorted(row["spots"].values(), key=lambda s: -s["km"])[:3]:
            if sp["km"] < 0.2:
                continue
            lat, lng = sp["lat"] / sp["km"], sp["lng"] / sp["km"]
            near = _other_road(index, lng, lat, row["name"])
            where = "" if acode else area_traffic.locate(lat, lng)[1]
            text = f"ใกล้ {near}" if near else row["name"]
            if where:
                text += f" ({'เขต' if bangkok else 'อ.'}{where})"
            spots.append({"road": row["name"], "km": round(sp["km"], 1), "lat": round(lat, 5), "lon": round(lng, 5),
                          "label": text, "camera": None})
        alts = [{"name": o["name"], "flow": o["flow"], "level": o["level"], "red_km": o["red_km"],
                 "recommended": o["flow"] >= FREE_FLOW, "_d": _km(row["lat"], row["lng"], o["lat"], o["lng"])}
                for o in rows if o["name"] != row["name"]]
        alts = sorted((a for a in alts if a["_d"] <= ALT_KM), key=lambda a: (not a["recommended"], a["_d"]))[:3]
        for a in alts:
            del a["_d"]
        alts.sort(key=lambda a: -a["flow"])
        on_road = [e for e in events
                   if (index.distance_to_road(row["name"], e["lng"], e["lat"], INCIDENT_KM) is not None)]
        status, tone, priority = _status(row["flow"], on_road)
        if acode:
            zone = label
        else:
            amphoe = area_traffic.locate(row["lat"], row["lng"])[1]
            zone = f"{'เขต' if bangkok else 'อ.'}{amphoe} {province}" if amphoe else province
        item = {
            "id": f"{pcode}-{acode}-{row['name']}", "name": row["name"], "zone": zone, "search_road": row["name"],
            "status": status, "status_label": LEVEL_TH.get(status, "ไม่มีข้อมูล"), "tone": tone, "priority": priority,
            "flow": row["flow"], "red_km": row["red_km"], "length_km": row["length_km"],
            "hotspots": spots, "alternatives": alts,
            "incidents": [{"kind": e["kind"], "title": e["title"]} for e in on_road[:2]],
        }
        item.update(GuidanceService._template_text(item))
        items.append(item)
    # Worst first; among equals the road with the most km of red, then the longest
    items.sort(key=lambda i: (i["priority"], -(i["red_km"] or 0), -i["length_km"]))
    return {"updated_at": int(time.time()), "area": label, "province": province, "amphoe": district,
            "online": stale < len(tiles) / 2 if tiles else False, "road_count": len(items), "items": items[:TOP]}
