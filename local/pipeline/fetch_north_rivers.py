"""
Rebuild config/north_rivers.json, the river centre lines the เส้นทางน้ำเหนือ map draws the water along, from
OpenStreetMap (Overpass API): the Ping, Wang, Yom, Nan, Khwae Noi, Chao Phraya, Sakae Krang and Pa Sak, from the north
down to Bangkok, as lists of [lat, lng] simplified to ~60 m. Some stretches (the Ping below Bhumibol) are
mapped as waterway=canal, so canals with those names are taken too. north_route.py joins them into one network and
finds the stretch of river between each pair of gauges.

Run once, or when the rivers change:  .venv\\Scripts\\python local\\pipeline\\fetch_north_rivers.py
Data © OpenStreetMap contributors, ODbL 1.0.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_river_areas import LICENSE, ROOT, overpass, simplify  # noqa: E402

NAMES = ["แม่น้ำปิง", "แม่น้ำวัง", "แม่น้ำยม", "แม่น้ำน่าน", "แม่น้ำเจ้าพระยา", "แม่น้ำสะแกกรัง", "แม่น้ำป่าสัก", "แม่น้ำแควน้อย"]
QUERY = ('[out:json][timeout:280];way["waterway"~"^(river|canal)$"]["name"~"^(' + "|".join(NAMES) + ')$"]'
         '(13.75,98.40,19.95,101.60);out tags geom;')
TOLERANCE = 0.0006    # degrees, ~60 m


def main():
    print("Overpass: rivers ...")
    ways = overpass(QUERY).get("elements") or []
    lines = []
    for w in ways:
        pts = [[round(p["lat"], 5), round(p["lon"], 5)] for p in w.get("geometry") or []]
        if len(pts) >= 2:
            lines.append({"name": (w.get("tags") or {}).get("name", ""), "line": simplify(pts, TOLERANCE)})
    out = {"source": "OpenStreetMap waterway=river centre lines via Overpass API", "license": LICENSE,
           "names": NAMES, "lines": lines}
    path = os.path.join(ROOT, "config", "north_rivers.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    by = {}
    for x in lines:
        by[x["name"]] = by.get(x["name"], 0) + 1
    print(f"{len(lines)} ways, {sum(len(x['line']) for x in lines)} points -> {path} ({os.path.getsize(path) // 1024} KB)", by)


if __name__ == "__main__":
    main()
