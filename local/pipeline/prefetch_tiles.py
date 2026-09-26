"""
Download base-map tiles for the Bangkok area into cache/osm so the traffic map
works fully offline. Run once (takes a few minutes):

    .venv\Scripts\python prefetch_tiles.py            # zoom 10-14 (~1,300 tiles)
    .venv\Scripts\python prefetch_tiles.py --max 15   # add zoom 15 (~3,500 more)

Be polite to the OpenStreetMap tile servers: this script is rate-limited and
skips tiles already cached.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # project root
from backend.traffic.traffic_service import BBOX, bbox_tiles, get_osm_tile, get_traffic_tile, get_base_tile, ANALYSIS_ZOOM, OSM_TILE_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=10)
    ap.add_argument("--max", type=int, default=14)
    ap.add_argument("--delay", type=float, default=0.15)
    args = ap.parse_args()

    print(f"Area: {BBOX}")
    total = 0
    for z in range(args.min, args.max + 1):
        tiles = bbox_tiles(z)
        done = 0
        for x, y in tiles:
            path = os.path.join(OSM_TILE_DIR, str(z), str(x), f"{y}.png")
            if os.path.exists(path):
                done += 1
                continue
            try:
                get_osm_tile(z, x, y)
                done += 1
                total += 1
                time.sleep(args.delay)
            except Exception as e:
                print(f"  z{z} {x}/{y} failed: {e}")
        print(f"zoom {z}: {done}/{len(tiles)} tiles cached")

    print("Caching Longdo base tiles for road names + latest traffic tiles...")
    for x, y in bbox_tiles(ANALYSIS_ZOOM):
        try:
            get_base_tile(ANALYSIS_ZOOM, x, y)
            get_traffic_tile(ANALYSIS_ZOOM, x, y)
        except Exception as e:
            print(f"  {x}/{y} failed: {e}")
    print(f"Done. Downloaded {total} new base tiles.")


if __name__ == "__main__":
    sys.exit(main())
