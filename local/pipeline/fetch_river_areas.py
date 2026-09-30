"""
Rebuild the two static map files the northern-water analysis reads, from OpenStreetMap (Overpass API):

    config/chao_phraya.json       centre line of the Chao Phraya (Pathum Thani to the sea) and the Lat Kret
                                  channel, as lists of [lat, lng]
    config/nonthaburi_areas.json  Nonthaburi province, its 6 districts (อำเภอ) and 52 sub-districts (ตำบล)
                                  as outer rings of [lat, lng], simplified to ~30 m

Run once, or when the boundaries change:  .venv\\Scripts\\python local\\pipeline\\fetch_river_areas.py
The public Overpass servers are often busy; the script retries both mirrors. Data © OpenStreetMap
contributors, ODbL 1.0.
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOSTS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
LICENSE = "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"
RIVER_Q = ('[out:json][timeout:170];way["waterway"="river"]["name"~"^แม่น้ำเจ้าพระยา$|^แม่น้ำลัดเกร็ด$"]'
           '(13.50,100.40,14.10,100.62);out tags geom;')
AREAS_Q = ('[out:json][timeout:270];rel["ISO3166-2"="TH-12"]->.p;.p map_to_area->.a;'
           '(.p;rel(area.a)["boundary"="administrative"]["admin_level"~"^(6|8)$"];);out geom;')
TOLERANCE = 0.0003    # degrees, ~30 m


def overpass(query, tries=4):
    body = urllib.parse.urlencode({"data": query}).encode()
    for i in range(tries):
        for host in HOSTS:
            try:
                req = urllib.request.Request(host, data=body, headers={"User-Agent": "BKK-StreetSmart/2.0 (map data)"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read().decode("utf-8"))
            except Exception as e:  # noqa: BLE001 - busy server: try the other one, then again
                print(f"  {host}: {str(e)[:80]}")
        time.sleep(15 * (i + 1))
    sys.exit("Overpass unreachable")


def simplify(pts, tol=TOLERANCE):
    """Douglas-Peucker on [lat, lng] points."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[1] - a[1], b[0] - a[0]
    norm = math.hypot(dx, dy) or 1e-12
    far, idx = 0.0, 0
    for i, p in enumerate(pts[1:-1], 1):
        d = abs(dy * (p[1] - a[1]) - dx * (p[0] - a[0])) / norm if norm > 1e-12 else math.hypot(p[0] - a[0], p[1] - a[1])
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [a, b]
    return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)


def rings(relation):
    """Join a relation's outer ways end to end into closed rings of [lat, lng]."""
    ways = [[[round(p["lat"], 6), round(p["lon"], 6)] for p in m["geometry"]]
            for m in relation.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry")]
    out = []
    while ways:
        ring = ways.pop(0)
        grown = True
        while grown and ring[0] != ring[-1]:
            grown = False
            for i, w in enumerate(ways):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += w[::-1][1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = w[::-1][:-1] + ring
                else:
                    continue
                ways.pop(i)
                grown = True
                break
        if len(ring) >= 4:
            out.append([[round(p[0], 5), round(p[1], 5)] for p in simplify(ring)])
    return out


def inside(p, ring):
    lat, lng = p
    hit = False
    for (a_lat, a_lng), (b_lat, b_lng) in zip(ring, ring[1:] + ring[:1]):
        if (a_lat > lat) != (b_lat > lat) and lng < (b_lng - a_lng) * (lat - a_lat) / (b_lat - a_lat) + a_lng:
            hit = not hit
    return hit


def main():
    print("river ...")
    river = overpass(RIVER_Q)["elements"]
    with open(os.path.join(ROOT, "config", "chao_phraya.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "แม่น้ำเจ้าพระยา (ปทุมธานี-ปากแม่น้ำ) และแม่น้ำลัดเกร็ด",
                   "source": f"OpenStreetMap waterway=river centre lines, fetched {time.strftime('%Y-%m-%d')} via Overpass API",
                   "license": LICENSE,
                   "lines": [[[round(p["lat"], 5), round(p["lon"], 5)] for p in w["geometry"]] for w in river]},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {len(river)} ways")

    print("areas ...")
    rels = overpass(AREAS_Q)["elements"]
    province = next(r for r in rels if r["tags"].get("admin_level") == "4")
    amphoe = [{"name": r["tags"]["name"].replace("อำเภอ", ""), "rings": rings(r)} for r in rels if r["tags"].get("admin_level") == "6"]
    tambon = []
    for r in rels:
        if r["tags"].get("admin_level") != "8":
            continue
        rs = rings(r)
        if not rs:
            continue
        c = (sum(p[0] for p in rs[0]) / len(rs[0]), sum(p[1] for p in rs[0]) / len(rs[0]))
        home = next((a["name"] for a in amphoe if any(inside(c, ring) for ring in a["rings"])), "")
        tambon.append({"name": r["tags"]["name"].replace("ตำบล", ""), "amphoe": home, "rings": rs})
    with open(os.path.join(ROOT, "config", "nonthaburi_areas.json"), "w", encoding="utf-8") as f:
        json.dump({"source": f"OpenStreetMap boundary=administrative, fetched {time.strftime('%Y-%m-%d')} via Overpass API",
                   "license": LICENSE, "province": {"name": "นนทบุรี", "rings": rings(province)},
                   "amphoe": amphoe, "tambon": tambon}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  {len(amphoe)} อำเภอ, {len(tambon)} ตำบล")


if __name__ == "__main__":
    main()
