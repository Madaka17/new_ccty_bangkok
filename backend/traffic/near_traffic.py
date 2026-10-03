"""
Traffic on the roads around one position, for the "ใกล้ฉัน" button of the "รถติดแค่ไหนตอนนี้" card.

Reads the Longdo Traffic tiles at zoom 12 that cover a circle of `radius_km` (two to four tiles; the 60-second
tile cache of traffic_service applies), names each line by the nearest road of the Longdo base map (base tiles
are cached on disk for good), and adds up the km of green / yellow / red per road inside the circle. The score
is the one used everywhere else: 100 x (green + half the yellow) / all km. Roads are listed by km of red.

Answers are kept CACHE_SECONDS per ~1 km cell, so many people in one place cost one set of tile reads.
"""
import math
import threading
import time

from backend.traffic.traffic_service import (ROAD_TYPES, RoadIndex, classify_color, decode_tile, feature_lonlat,
                                             get_base_tile, get_traffic_tile, lonlat_to_tile, seg_length_km)

ZOOM = 12
CACHE_SECONDS = 60
MIN_KM = 0.3            # a road with less than this inside the circle is left out of the list
TOP_ROADS = 12

_lock = threading.Lock()
_cache = {}             # (lat cell, lng cell, radius) -> (time, answer)


def distance_km(lat1, lng1, lat2, lng2):
    dy = (lat2 - lat1) * 110.57
    dx = (lng2 - lng1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _tiles(lat, lng, radius_km):
    dlat = radius_km / 110.57
    dlng = radius_km / (111.32 * math.cos(math.radians(lat)))
    x0, y0 = lonlat_to_tile(lng - dlng, lat + dlat, ZOOM)
    x1, y1 = lonlat_to_tile(lng + dlng, lat - dlat, ZOOM)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def _road_index(tiles):
    idx = RoadIndex()
    for x, y in tiles:
        try:
            tile = decode_tile(get_base_tile(ZOOM, x, y), ZOOM, x, y)
        except Exception:
            continue
        layer = tile.get("road")
        if not layer:
            continue
        for feat in layer["features"]:
            props = feat["properties"]
            name = props.get("name_l") or props.get("name_e")
            if name and props.get("type") in ROAD_TYPES:
                for line in feature_lonlat(feat["geometry"], ZOOM, x, y, layer.get("extent", 4096)):
                    idx.add(name, line)
    return idx


def _score(g, y, r):
    total = g + y + r
    return round(100 * (g + 0.5 * y) / total) if total else None


def analyse(lat, lng, radius_km=3.0):
    key = (round(lat, 2), round(lng, 2), radius_km)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    tiles = _tiles(lat, lng, radius_km)
    index = _road_index(tiles)
    totals = [0.0, 0.0, 0.0]
    roads = {}
    stale = 0
    for x, y in tiles:
        raw, was_stale = get_traffic_tile(ZOOM, x, y)
        stale += was_stale
        try:
            layer = decode_tile(raw, ZOOM, x, y).get("traffic")
        except Exception:
            continue
        for feat in (layer or {}).get("features", []):
            props = feat["properties"]
            colors = [c for c in (classify_color(props.get("fillcolor")), classify_color(props.get("fillcolor_r"))) if c]
            if not colors:
                continue
            for line in feature_lonlat(feat["geometry"], ZOOM, x, y, layer.get("extent", 4096)):
                mid = line[len(line) // 2]
                dist = distance_km(lat, lng, mid[1], mid[0])
                km = seg_length_km(line)
                if dist > radius_km or km <= 0:
                    continue
                name = (index.nearest(*mid) or "").strip()
                for c in colors:
                    k = ("green", "yellow", "red").index(c)
                    totals[k] += km
                    if name:
                        r = roads.setdefault(name, {"name": name, "km": [0.0, 0.0, 0.0], "dist": dist})
                        r["km"][k] += km
                        r["dist"] = min(r["dist"], dist)
    road_list = []
    for r in roads.values():
        g, y, red = r["km"]
        if g + y + red < MIN_KM:
            continue
        flow = _score(g, y, red)
        road_list.append({"name": r["name"], "flow": flow, "red_km": round(red, 1), "total_km": round(g + y + red, 1),
                          "distance_km": round(r["dist"], 1)})
    road_list.sort(key=lambda r: (-r["red_km"], r["flow"]))   # the most km of red first
    g, y, red = totals
    answer = {
        "updated_at": int(time.time()), "radius_km": radius_km, "online": stale < len(tiles) / 2 if tiles else False,
        "flow": _score(g, y, red), "total_km": round(g + y + red, 1), "green_km": round(g, 1),
        "yellow_km": round(y, 1), "red_km": round(red, 1), "road_count": len(road_list), "roads": road_list[:TOP_ROADS],
    }
    with _lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[key] = (time.time(), answer)
    return answer
