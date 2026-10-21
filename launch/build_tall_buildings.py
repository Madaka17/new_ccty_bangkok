"""
Tall buildings of greater Bangkok as a static GeoJSON snapshot, so the map's skyline shows at every zoom.

OpenFreeMap's zoom-13 tiles carry almost no building heights; they exist only in the zoom-14 tiles. This script
fetches every z14 tile over greater Bangkok, keeps the building parts at least `min_height` metres tall and writes
them to web\\public\\buildings_tall_bkk.geojson (served as /buildings_tall_bkk.geojson, source "tall" in mapStyle.js).

    .venv\\Scripts\\python.exe launch\\build_tall_buildings.py          min height 30 m (default)
    .venv\\Scripts\\python.exe launch\\build_tall_buildings.py 50        keep only buildings of 50 m and taller

Output: Polygon features with properties h (render_height) and b (render_min_height), in metres, rounded to 0.1.
Coordinates are rounded to 5 decimals. If more than 5% of the tiles fail to download, the script exits non-zero
and leaves the existing file untouched. Run it again when the map needs a fresher snapshot (building data changes
slowly; a few runs per year is plenty).

Source and licence: © OpenStreetMap contributors, via OpenFreeMap vector tiles (OpenMapTiles schema). The data is
licensed under the Open Database Licence (ODbL); keep the attribution where the layer is shown.
"""
import gzip
import json
import math
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import mapbox_vector_tile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "buildings_tall_bkk.geojson"
TILEJSON = "https://tiles.openfreemap.org/planet"
Z = 14
W, S, E, N = 100.30, 13.55, 100.95, 14.05  # greater Bangkok
THREADS = 4
RETRIES = 3
MAX_FAIL_RATIO = 0.05
UA = "BKKStreetSmart/1.0"  # OpenFreeMap answers 403 without a browser-like User-Agent
DEFAULT_MIN_H = 30.0


def http_get(url, gzipped=False):
    headers = {"User-Agent": UA}
    if gzipped:
        headers["Accept-Encoding"] = "gzip"
    req = urllib.request.Request(url, headers=headers)
    raw = urllib.request.urlopen(req, timeout=30).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def tile_x(lon):
    return int((lon + 180) / 360 * 2**Z)


def tile_y(lat):
    r = math.radians(lat)
    return int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * 2**Z)


def to_lonlat(x, y, px, py, extent):
    n = 2**Z
    lon = (x + px / extent) / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1 - py / extent) / n))))
    return [round(lon, 5), round(lat, 5)]


def fetch_tile(template, tile):
    x, y = tile
    url = template.format(z=Z, x=x, y=y)
    last_err = None
    for attempt in range(RETRIES):
        try:
            return tile, http_get(url, gzipped=True), None
        except Exception as err:  # network error, 403/429, bad gzip: retry, then count as failed
            last_err = err
            time.sleep(2 * (attempt + 1))
    return tile, None, last_err


def split_polygons(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def main():
    min_h = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MIN_H

    template = json.loads(http_get(TILEJSON))["tiles"][0]
    xs = range(tile_x(W), tile_x(E) + 1)
    ys = range(tile_y(N), tile_y(S) + 1)
    tiles = [(x, y) for x in xs for y in ys]

    features, buildings, with_height, failed = [], 0, 0, 0
    started = time.time()
    with ThreadPoolExecutor(THREADS) as pool:
        for (x, y), raw, err in pool.map(lambda t: fetch_tile(template, t), tiles):
            if raw is None:
                failed += 1
                print(f"tile {Z}/{x}/{y} failed: {err}", file=sys.stderr)
                continue
            decoded = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": False})
            layer = decoded.get("building")
            if not layer:
                continue
            extent = layer.get("extent", 4096)
            for f in layer["features"]:
                buildings += 1
                props = f["properties"]
                h = props.get("render_height") or 0
                if h >= 10:
                    with_height += 1
                if h < min_h:
                    continue
                b = round(props.get("render_min_height") or 0, 1)
                for poly in split_polygons(f["geometry"]):
                    rings = [[to_lonlat(x, y, px, py, extent) for px, py in ring] for ring in poly]
                    features.append({
                        "type": "Feature",
                        "properties": {"h": round(h, 1), "b": b},
                        "geometry": {"type": "Polygon", "coordinates": rings},
                    })

    fail_ratio = failed / len(tiles)
    if fail_ratio > MAX_FAIL_RATIO:
        print(f"{failed} of {len(tiles)} tiles failed ({fail_ratio:.1%}, limit {MAX_FAIL_RATIO:.0%}); "
              f"{OUT.name} not written", file=sys.stderr)
        return 1

    text = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"), ensure_ascii=False)
    tmp = OUT.with_suffix(".geojson.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"tiles {len(tiles)} failed {failed} in {time.time() - started:.0f}s; buildings {buildings}, "
          f">=10 m {with_height}, >={min_h:g} m pieces {len(features)}; "
          f"{OUT.relative_to(ROOT)} {len(text.encode('utf-8')) / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
