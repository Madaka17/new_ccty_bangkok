"""
Two NASA satellite feeds for the traffic map, both public and keyless:

- FIRMS (firms.modaps.eosdis.nasa.gov): fire hotspots seen by the VIIRS instruments on Suomi NPP, NOAA-20 and
  NOAA-21, from the 48-hour South-East Asia files NASA publishes for download. A hotspot is a ~375 m pixel much
  hotter than its surroundings: a forest fire, field burning or a factory flare. Kept: Thailand and the land
  along its borders (where haze crosses into the north), "nominal" or "high" confidence only. The three
  satellites see the same fire, so a fire is counted once per ~1 km cell (0.01 degree) per day window.
  Analysis: the last 24 hours against the 24 before, per region and province, and near Bangkok.
- EONET (eonet.gsfc.nasa.gov): open natural events NASA tracks (tropical storms with their tracks, floods,
  volcanoes, wildfires, dust and haze) from India to the western Pacific. Storms get their distance to Thailand
  and whether that distance is shrinking.

Both are read in a background thread every REFRESH_S and kept on disk; a failed read keeps the last good one.
Served by /api/nasa/fires and /api/nasa/events.
"""
import csv
import io
import json
import math
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone

from backend.core import thai_regions
from backend.core.instance import DATA_DIR
from backend.traffic.area_traffic import area_traffic

FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/{}/csv/{}_SouthEast_Asia_48h.csv"
FIRMS_FILES = (("suomi-npp-viirs-c2", "SUOMI_VIIRS_C2"), ("noaa-20-viirs-c2", "J1_VIIRS_C2"), ("noaa-21-viirs-c2", "J2_VIIRS_C2"))
FIRE_BBOX = (5.0, 96.0, 23.0, 107.0)        # min lat, min lng, max lat, max lng: Thailand and its border lands
FIRE_CELL = 0.01                             # degrees (~1 km): one fire per cell per window
NEAR_BKK_KM = 150
# India to the western Pacific (min lng, max lat, max lng, min lat): typhoons that reach Thailand start out there
EONET = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=30&bbox=60,40,180,-15"
NEAR_STORM_KM = 1500                         # a storm this close to Thailand is worth watching
EONET_KINDS = {"severeStorms": "พายุ", "floods": "น้ำท่วม", "volcanoes": "ภูเขาไฟ", "wildfires": "ไฟป่า",
               "dustHaze": "ฝุ่นและหมอกควัน", "landslides": "ดินถล่ม"}
BANGKOK = (13.756, 100.502)
CACHE_FILE = os.path.join(DATA_DIR, "cache", "nasa_feeds.json")
REFRESH_S = 3600
TIMEOUT = 60
USER_AGENT = "BKK-StreetSmart/1.0 (bkksmartstreet.com)"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _km(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- FIRMS
def parse_firms(text, now):
    """Hotspots of the last 48 hours inside FIRE_BBOX: dicts with lat, lng, ts, frp, conf."""
    out = []
    lat0, lng0, lat1, lng1 = FIRE_BBOX
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lng = float(row["latitude"]), float(row["longitude"])
            ts = datetime.strptime(row["acq_date"] + row["acq_time"].zfill(4), "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc).timestamp()
        except (KeyError, ValueError):
            continue
        conf = (row.get("confidence") or "").strip().lower()[:1]     # VIIRS: l(ow) / n(ominal) / h(igh)
        if conf not in ("n", "h") or not (lat0 <= lat <= lat1 and lng0 <= lng <= lng1) or now - ts > 48 * 3600:
            continue
        try:
            frp = float(row.get("frp") or 0)
        except ValueError:
            frp = 0.0
        out.append({"lat": lat, "lng": lng, "ts": int(ts), "frp": frp, "conf": conf})
    return out


def analyse_fires(points, now, locate=area_traffic.locate):
    """One fire per ~1 km cell per window (the newest sighting), with its province, and the numbers the map
    shows: last 24 h against the 24 h before, per region and province, near Bangkok, and across the border."""
    windows = {"now": {}, "prev": {}}
    for p in sorted(points, key=lambda p: p["ts"]):
        age = now - p["ts"]
        cell = (round(p["lat"] / FIRE_CELL), round(p["lng"] / FIRE_CELL))
        windows["now" if age <= 24 * 3600 else "prev"][cell] = p
    provinces = {}
    for win in windows.values():
        for p in win.values():
            if "province" not in p:
                p["province"] = locate(p["lat"], p["lng"])[0] if thai_regions.in_thailand(p["lat"], p["lng"]) else ""
    fires = list(windows["now"].values())
    th = [p for p in fires if p["province"]]
    for p in th:
        provinces[p["province"]] = provinces.get(p["province"], 0) + 1
    regions = {}
    for name, n in provinces.items():
        region = thai_regions.region_of(name)
        regions[region] = regions.get(region, 0) + n
    prev_th = sum(1 for p in windows["prev"].values() if p["province"])
    return {
        "updated_at": int(now),
        "th_24h": len(th),
        "th_prev_24h": prev_th,
        "border_24h": len(fires) - len(th),
        "near_bkk_24h": sum(1 for p in th if _km(p["lat"], p["lng"], *BANGKOK) <= NEAR_BKK_KM),
        "near_bkk_km": NEAR_BKK_KM,
        "strong_24h": sum(1 for p in th if p["frp"] >= 20),
        "regions": sorted(({"region": r, "count": n} for r, n in regions.items()), key=lambda r: -r["count"]),
        "provinces": sorted(({"province": p, "region": thai_regions.region_of(p), "count": n} for p, n in provinces.items()),
                            key=lambda r: -r["count"])[:10],
        # [lat, lng, fire radiative power (MW), confidence h/n, unix time, province or ""]
        "points": [[round(p["lat"], 4), round(p["lng"], 4), round(p["frp"], 1), p["conf"], p["ts"], p["province"]] for p in fires],
    }


def read_fires():
    now = time.time()
    points, ok = [], 0
    for folder, name in FIRMS_FILES:
        try:
            points += parse_firms(_get(FIRMS.format(folder, name)).decode("utf-8", "replace"), now)
            ok += 1
        except Exception as e:
            print(f"[NASA] FIRMS {name} failed: {e}")
    if not ok:
        return None
    return {**analyse_fires(points, now), "satellites": ok}


# ---------------------------------------------------------------- EONET
def km_to_thailand(lat, lng):
    """Great-circle distance from a point to the nearest edge of Thailand (its nearest district); 0 inside."""
    import shapely
    from shapely.ops import nearest_points
    area_traffic._load_districts()
    here = shapely.Point(lng, lat)
    if area_traffic.locate(lat, lng)[0]:
        return 0
    district = area_traffic.tree.geometries[int(area_traffic.tree.nearest(here))]
    edge = nearest_points(district, here)[0]
    return round(_km(lat, lng, edge.y, edge.x))


def _point_of(geom):
    """(lat, lng) of an EONET geometry: the point itself, or the middle of a polygon's first ring."""
    c = geom.get("coordinates") or []
    if geom.get("type") == "Point" and len(c) >= 2:
        return c[1], c[0]
    if geom.get("type") == "Polygon" and c and c[0]:
        ring = c[0]
        return sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)
    return None


def parse_events(data, dist=km_to_thailand):
    out = []
    for ev in data.get("events") or []:
        kind = next((c["id"] for c in ev.get("categories") or [] if c.get("id") in EONET_KINDS), None)
        geoms = [g for g in ev.get("geometry") or [] if _point_of(g)]
        if not kind or not geoms:
            continue
        geoms.sort(key=lambda g: g.get("date") or "")
        track = [_point_of(g) for g in geoms]
        last = geoms[-1]
        km = dist(*track[-1])
        # Moving towards Thailand: the distance a day earlier (or the first fix) was larger
        trend = None
        if kind == "severeStorms" and len(track) >= 2:
            before = dist(*track[-min(len(track), 5)])
            trend = "closer" if km < before - 25 else "away" if km > before + 25 else "steady"
        out.append({
            "id": ev.get("id"), "title": ev.get("title"), "kind": kind, "kind_th": EONET_KINDS[kind],
            "lat": round(track[-1][0], 3), "lng": round(track[-1][1], 3), "date": last.get("date"),
            "magnitude": last.get("magnitudeValue"), "unit": last.get("magnitudeUnit"),
            "km_to_thailand": km, "trend": trend,
            "track": [[round(a, 3), round(b, 3)] for a, b in track] if kind == "severeStorms" else [],
            "link": next((s.get("url") for s in ev.get("sources") or [] if s.get("url")), ev.get("link")),
        })
    out.sort(key=lambda e: e["km_to_thailand"])
    return out


def read_events():
    items = parse_events(json.loads(_get(EONET)))
    near = [e for e in items if e["kind"] == "severeStorms" and e["km_to_thailand"] <= NEAR_STORM_KM]
    return {"updated_at": int(time.time()), "items": items, "near_storms": len(near), "near_km": NEAR_STORM_KM}


# ---------------------------------------------------------------- service
class NasaFeeds:
    def __init__(self):
        self._data = {"fires": None, "events": None}
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                self._data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def fires(self):
        return self._data["fires"]

    def events(self):
        return self._data["events"]

    def refresh(self):
        for key, read in (("fires", read_fires), ("events", read_events)):
            try:
                value = read()
            except Exception as e:
                print(f"[NASA] {key} failed: {e}")
                continue
            if value is not None:
                self._data[key] = value
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        fires, events = self._data["fires"] or {}, self._data["events"] or {}
        print(f"[NASA] fires in Thailand 24 h: {fires.get('th_24h')} · events: {len(events.get('items') or [])}")

    def _loop(self):
        while True:
            self.refresh()
            time.sleep(REFRESH_S)

    def start(self):
        threading.Thread(target=self._loop, name="nasa-feeds", daemon=True).start()


nasa_feeds = NasaFeeds()
