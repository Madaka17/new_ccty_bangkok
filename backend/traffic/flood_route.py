"""
Driving route from A to B that keeps out of flooded roads, for the chat bot's "how do I get there" answers.

  - Places: OpenStreetMap Nominatim search inside the Bangkok metro box (no key; its policy asks for at most
    one request a second and an identifying User-Agent), cached on disk for GEOCODE_TTL.
  - Route: the FOSSGIS Valhalla server (no key), car costing, with alternates.
  - Water: `hazards()` gives every flooded spot the site knows (BMA road sensors, the flood cameras, Longdo /
    DOH / BMA reports, people's reports) as {lat, lng, name, source, depth_cm, avoid}. A spot with `avoid`
    that lies on the route becomes a small square in Valhalla's `exclude_polygons` and the route is asked
    again, up to MAX_ROUNDS times. Only the spots the route touches go in, because the public server caps
    the polygons' total perimeter. Spots at the start or the end cannot be avoided and are only reported;
    shallow water (no `avoid`) is reported, not avoided. Expressways and tollways run on viaducts, so water
    under them does not count.
  - Jams: the congested stretches (hotspots) of the live traffic roads that the route runs along are listed,
    and an alternate costs JAM_MIN_PER_KM minutes per km of jam, so a slightly longer clear road can win.

Valhalla's times are free-flow, so the minutes given are a range: its time plus the jam delay, to 30% more.
"""
import json
import math
import os
import re
import threading
import time
import urllib.parse

import requests

from backend.core.instance import CACHE_DIR

NOMINATIM = "https://nominatim.openstreetmap.org/search"
VALHALLA = os.getenv("ROUTE_VALHALLA_URL", "https://valhalla1.openstreetmap.de/route")
USER_AGENT = "BKK-StreetSmart/1.0 github.com/Madaka17/new_ccty_bangkok"
VIEWBOX = "99.9,14.4,101.2,13.3"     # Bangkok and the provinces around it (lon/lat, west-north-east-south)
GEOCODE_TTL = 7 * 86400
GEOCODE_FILE = os.path.join(CACHE_DIR, "geocode.json")
HIT_KM = 0.12          # a hazard this close to the route line is on the route
END_KM = 0.4           # a hazard this close to the start or the end cannot be avoided
BOX_KM = 0.15          # half the side of the square drawn around an avoided spot
MAX_ROUNDS = 3
MAX_AVOID = 12         # squares in one request: 12 x 1.2 km stays under the public server's perimeter cap
JAM_NEAR_KM = 0.08
JAM_MIN_PER_KM = 3     # minutes a km of jam adds (about 10 km/h instead of 30)
SLOWEST_KMH = 20      # a whole trip's average is not slower than this before the jams are added
LINE_POINTS = 300      # points of the route line sent to the browser
TIMEOUT = 20
RAISED_WORDS = ("ทางพิเศษ", "ทางยกระดับ", "โทลล์เวย์", "ดอนเมืองโทลล์เวย์")

# Short names people type that Nominatim gets wrong on its own
ALIASES = {
    "อนุสาวรีย์ชัย": "อนุสาวรีย์ชัยสมรภูมิ", "อนุสาวรีย์": "อนุสาวรีย์ชัยสมรภูมิ", "วงเวียนใหญ่": "วงเวียนใหญ่ ธนบุรี",
    "ม.เกษตร": "มหาวิทยาลัยเกษตรศาสตร์", "เกษตร": "มหาวิทยาลัยเกษตรศาสตร์", "จุฬา": "จุฬาลงกรณ์มหาวิทยาลัย",
    "ม.ธรรมศาสตร์": "มหาวิทยาลัยธรรมศาสตร์ ท่าพระจันทร์", "มธ.": "มหาวิทยาลัยธรรมศาสตร์ ท่าพระจันทร์",
    "สุวรรณภูมิ": "ท่าอากาศยานสุวรรณภูมิ", "สนามบินสุวรรณภูมิ": "ท่าอากาศยานสุวรรณภูมิ",
    "ดอนเมือง": "ท่าอากาศยานดอนเมือง", "สนามบินดอนเมือง": "ท่าอากาศยานดอนเมือง",
    "หมอชิต": "สถานีขนส่งผู้โดยสารกรุงเทพ (จตุจักร)", "เอกมัย": "สถานีขนส่งผู้โดยสารกรุงเทพ (เอกมัย)",
    "สายใต้ใหม่": "สถานีขนส่งผู้โดยสารกรุงเทพ (ถนนบรมราชชนนี)", "หัวลำโพง": "สถานีรถไฟกรุงเทพ",
    "บางซื่อ": "สถานีกลางกรุงเทพอภิวัฒน์", "สนามหลวง": "ท้องสนามหลวง", "ราชดำเนิน": "ถนนราชดำเนินกลาง",
}
# Words around a place name that are not part of it
_FILLER = re.compile(r"^(แถว|ย่าน|ที่|บริเวณ|ตรง|ไปที่|ไป|จาก)\s*|\s*(หน่อย|ครับ|ค่ะ|คะ|นะ|ด้วย)$")
HERE = ("ที่นี่", "ตรงนี้", "ตำแหน่งฉัน", "ตำแหน่งของฉัน", "ตำแหน่งปัจจุบัน", "ที่อยู่ตอนนี้", "here")


def km(lat1, lng1, lat2, lng2):
    dlat = (lat2 - lat1) * 110.57
    dlng = (lng2 - lng1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlng)


def decode(shape, precision=6):
    """Valhalla's encoded polyline -> [(lat, lng)]."""
    coords, i, lat, lng, f = [], 0, 0, 0, 10 ** precision
    while i < len(shape):
        vals = []
        for _ in range(2):
            result, shift = 0, 0
            while True:
                b = ord(shape[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        lat += vals[0]
        lng += vals[1]
        coords.append((lat / f, lng / f))
    return coords


class Line:
    """A route line in local km, for "how far is this point from the route, and how far along".
    `raised` holds the segments (index k = pts[k] to pts[k + 1]) that run above the street."""

    def __init__(self, pts, raised=()):
        self.pts = pts
        self.raised = set(raised)
        self.lat0 = sum(p[0] for p in pts) / len(pts)
        self.cos = math.cos(math.radians(self.lat0))
        self.xy = [self._xy(p) for p in pts]
        self.along = [0.0]
        for a, b in zip(self.xy, self.xy[1:]):
            self.along.append(self.along[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        lats, lngs = [p[0] for p in pts], [p[1] for p in pts]
        self.box = (min(lats), max(lats), min(lngs), max(lngs))

    def _xy(self, p):
        return (p[1] * 111.32 * self.cos, p[0] * 110.57)

    def near(self, lat, lng, max_km, ground=False):
        """(distance km, km from the start) of the closest point within max_km, or None.
        ground=True leaves out the raised segments: water on the street below does not reach them."""
        pad = max_km / 100.0
        if not (self.box[0] - pad <= lat <= self.box[1] + pad and self.box[2] - pad <= lng <= self.box[3] + pad):
            return None
        px, py = self._xy((lat, lng))
        best = None
        for k, (a, b) in enumerate(zip(self.xy, self.xy[1:])):
            if ground and k in self.raised:
                continue
            dx, dy = b[0] - a[0], b[1] - a[1]
            seg = dx * dx + dy * dy
            t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / seg))
            d = math.hypot(px - a[0] - t * dx, py - a[1] - t * dy)
            if d <= max_km and (best is None or d < best[0]):
                best = (d, self.along[k] + t * math.sqrt(seg))
        return best

    def sample(self, n):
        """n points spread evenly along the line (by distance), for map-app waypoints."""
        total, out, k = self.along[-1], [], 0
        for j in range(1, n + 1):
            want = total * j / (n + 1)
            while k < len(self.along) - 1 and self.along[k + 1] < want:
                k += 1
            out.append(self.pts[k])
        return out


def _raised(trip):
    """Line segments on expressways and tollways, which run on viaducts above the flooded streets."""
    out = []
    for m in trip["legs"][0].get("maneuvers") or []:
        names = " ".join(m.get("street_names") or [])
        if m.get("toll") or any(w in names for w in RAISED_WORDS):
            out += range(m.get("begin_shape_index", 0), m.get("end_shape_index", 0))
    return out


def _street(names):
    """The first real name of a maneuver's street ("3", "3701" are route numbers)."""
    return next((n for n in names if not n.isdigit()), None)


def _road_key(name):
    return (name or "").replace("ถนน", "").replace("ถ.", "").replace(" ", "").strip()


# ---------------------------------------------------------------- flood sources
def sensor_spots(status):
    """BMA road sensors, from FloodRoads.status(): its wet stations (key "wet"), to avoid when deep enough to
    stop a car, otherwise only mentioned."""
    return [{"lat": s["lat"], "lng": s["lng"], "name": s.get("short_name") or s.get("road") or s.get("name"),
             "source": "เซ็นเซอร์น้ำ กทม.", "depth_cm": s.get("level_cm"), "avoid": s.get("status") == "flood"}
            for s in status["wet"] if s.get("lat") and s.get("lng")]


def gather(sources):
    """[(name, read)] -> (spots, missing): every source's flooded spots. A source that fails is named in
    `missing` and the spots of the others are kept, so the route is still checked against them; spots is None
    when no source could be read."""
    spots, missing = [], []
    for name, read in sources:
        try:
            spots += list(read())
        except Exception as e:  # noqa: BLE001 - one feed down must not drop the rest
            print(f"[Route] {name} unavailable: {str(e)[:160]}")
            missing.append(name)
    return (None if len(missing) == len(sources) else spots), missing


class FloodRouter:
    def __init__(self, hazards=None, jams=None):
        self.hazards = hazards or (lambda: [])
        self.jams = jams or (lambda: [])
        self._lock = threading.Lock()
        self._last_nominatim = 0.0
        self._geo = self._load()

    # ------------------------------------------------------------ places
    def _load(self):
        try:
            with open(GEOCODE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            tmp = GEOCODE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._geo, f, ensure_ascii=False)
            os.replace(tmp, GEOCODE_FILE)
        except OSError as e:
            print(f"[Route] geocode cache not saved: {e}")

    @staticmethod
    def clean(text):
        q = (text or "").strip(" ?.,\"'")
        for _ in range(3):
            q = _FILLER.sub("", q).strip()
        return ALIASES.get(q, q)

    @staticmethod
    def is_here(text):
        t = (text or "").strip().lower()
        return not t or any(w in t for w in HERE)

    def geocode(self, text):
        """{name, label, lat, lng} for a place name in the Bangkok area, or None."""
        q = self.clean(text)
        if len(q) < 2:
            return None
        now = time.time()
        with self._lock:
            hit = self._geo.get(q)
            if hit and now - hit["ts"] < GEOCODE_TTL:
                return hit["place"]
            wait = self._last_nominatim + 1.1 - now
            if wait > 0:
                time.sleep(wait)
            self._last_nominatim = time.time()
        params = {"q": q, "format": "jsonv2", "countrycodes": "th", "limit": 1, "accept-language": "th",
                  "viewbox": VIEWBOX, "bounded": 1}
        r = requests.get(NOMINATIM, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        place = None
        if rows:
            parts = [p.strip() for p in rows[0]["display_name"].split(",")]
            place = {"name": q, "label": ", ".join(parts[:3]), "lat": float(rows[0]["lat"]), "lng": float(rows[0]["lon"])}
        with self._lock:
            self._geo[q] = {"ts": time.time(), "place": place}
            self._save()
        return place

    # ------------------------------------------------------------ routes
    def _valhalla(self, a, b, avoid):
        body = {"locations": [{"lat": a["lat"], "lon": a["lng"]}, {"lat": b["lat"], "lon": b["lng"]}],
                "costing": "auto", "alternates": 2, "units": "kilometers", "language": "th-TH",
                "directions_type": "maneuvers"}
        if avoid:
            body["exclude_polygons"] = [self._square(h) for h in avoid]
        r = requests.post(VALHALLA, json=body, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        data = r.json()
        if "trip" not in data:
            raise RuntimeError(data.get("error") or f"HTTP {r.status_code}")
        return [data["trip"]] + [x["trip"] for x in data.get("alternates") or []]

    @staticmethod
    def _square(h):
        dlat = BOX_KM / 110.57
        dlng = BOX_KM / (111.32 * math.cos(math.radians(h["lat"])))
        w, e, s, n = h["lng"] - dlng, h["lng"] + dlng, h["lat"] - dlat, h["lat"] + dlat
        return [[w, s], [e, s], [e, n], [w, n], [w, s]]

    @staticmethod
    def _roads(trip):
        """Named roads along the trip, in order, with their km (short links left out)."""
        out = []
        for m in trip["legs"][0].get("maneuvers") or []:
            name = _street(m.get("street_names") or [])
            if not name:
                continue
            if out and out[-1]["name"] == name:
                out[-1]["km"] += m.get("length") or 0
            else:
                out.append({"name": name, "km": m.get("length") or 0})
        merged = {}
        for r in out:
            merged[r["name"]] = merged.get(r["name"], 0) + r["km"]
        order = []
        for r in out:
            if r["name"] not in order and merged[r["name"]] >= 0.5:
                order.append(r["name"])
        return [{"name": n, "km": round(merged[n], 1)} for n in order]

    def _score(self, trip, hazards, jam_spots, a, b):
        line = Line(decode(trip["legs"][0]["shape"]), _raised(trip))
        roads = self._roads(trip)
        keys = [_road_key(r["name"]) for r in roads]
        blocked, wet, ends = [], [], []
        for h in hazards:
            hit = line.near(h["lat"], h["lng"], HIT_KM, ground=True)
            if not hit:
                continue
            spot = dict(h, at_km=round(hit[1], 1))
            if min(km(h["lat"], h["lng"], a["lat"], a["lng"]), km(h["lat"], h["lng"], b["lat"], b["lng"])) <= END_KM:
                ends.append(spot)
            elif h.get("avoid"):
                blocked.append(spot)
            else:
                wet.append(spot)
        jams = {}
        for j in jam_spots:
            k = _road_key(j["road"])
            if not k or not any(k in x or (x and x in k) for x in keys):
                continue
            hit = line.near(j["lat"], j["lng"], JAM_NEAR_KM)
            if hit:
                cur = jams.setdefault(j["road"], {"road": j["road"], "km": 0.0, "at_km": round(hit[1], 1)})
                cur["km"] = round(cur["km"] + j["km"], 1)
        jams = sorted(jams.values(), key=lambda x: x["at_km"])
        s = trip["summary"]
        jam_km = sum(x["km"] for x in jams)
        # Unnamed service roads (an airport's, a mall's) can take Valhalla's time far past any real drive
        minutes = min(s["time"] / 60, s["length"] * 60 / SLOWEST_KMH) + jam_km * JAM_MIN_PER_KM
        return {"trip": trip, "line": line, "roads": roads, "blocked": sorted(blocked, key=lambda x: x["at_km"]),
                "wet": sorted(wet, key=lambda x: x["at_km"]), "ends": ends, "jams": jams,
                "km": round(s["length"], 1), "minutes": minutes, "cost": minutes}

    def plan(self, origin, destination):
        """Route between two {lat, lng[, name, label]} places, around the floods. Raises on a routing error.
        `hazards()` returns the spots, or (spots, names of the sources that could not be read) from gather()."""
        missing = []
        try:
            got = self.hazards()
            spots, missing = got if isinstance(got, tuple) else (got, [])
            if spots is None:
                raise RuntimeError(f"no flood source could be read ({', '.join(missing)})")
            hazards = [h for h in spots if h.get("lat") is not None and h.get("lng") is not None]
        except Exception as e:  # noqa: BLE001 - route anyway, the answer says the water was not checked
            print(f"[Route] hazards unavailable: {e}")
            hazards, missing = None, []
        try:
            jam_spots = list(self.jams())
        except Exception as e:  # noqa: BLE001
            print(f"[Route] jams unavailable: {e}")
            jam_spots = []
        trips = self._valhalla(origin, destination, [])
        scored = [self._score(t, hazards or [], jam_spots, origin, destination) for t in trips]
        fastest = scored[0]
        avoid = []
        best = None
        for _ in range(MAX_ROUNDS):
            clear = [s for s in scored if not s["blocked"]]
            if clear:
                best = min(clear, key=lambda s: s["cost"])
                break
            ids = {(h["lat"], h["lng"]) for h in avoid}
            new = [h for h in min(scored, key=lambda s: s["cost"])["blocked"] if (h["lat"], h["lng"]) not in ids]
            if not new or len(avoid) >= MAX_AVOID:
                break
            avoid += new[:MAX_AVOID - len(avoid)]
            try:
                trips = self._valhalla(origin, destination, avoid)
            except Exception as e:  # noqa: BLE001 - no way round: keep the routes we have
                print(f"[Route] no route around {len(avoid)} flood spots: {e}")
                break
            scored = [self._score(t, hazards or [], jam_spots, origin, destination) for t in trips]
        if best is None:
            best = min(scored, key=lambda s: (len(s["blocked"]), s["cost"]))
        return self._result(origin, destination, best, fastest, avoid, hazards is not None and not missing, missing)

    @staticmethod
    def _spot(h):
        return {k: h.get(k) for k in ("name", "source", "depth_cm", "depth_text", "lat", "lng", "at_km", "avoid")}

    def _result(self, origin, destination, best, fastest, avoid, checked, missing=()):
        line = best["line"]
        step = max(1, len(line.pts) // LINE_POINTS)
        pts = line.pts[::step] + ([line.pts[-1]] if (len(line.pts) - 1) % step else [])
        low = round(best["minutes"])
        detour = best is not fastest
        out = {
            # flood_checked: every flood source was read; flood_missing: the ones that were not while the
            # route was still checked against the others (empty when none could be read)
            "origin": origin, "destination": destination, "flood_checked": checked, "flood_missing": list(missing),
            "km": best["km"], "minutes": [low, max(low + 5, round(low * 1.3))],
            "roads": best["roads"][:8], "line": [[round(p[0], 5), round(p[1], 5)] for p in pts],
            "flood_on_route": [self._spot(h) for h in best["blocked"]],
            "wet_on_route": [self._spot(h) for h in best["wet"]],
            "flood_at_ends": [self._spot(h) for h in best["ends"]],
            "avoided": [self._spot(h) for h in fastest["blocked"]] if detour else [],
            "jams": best["jams"][:6],
            "fastest": None,
        }
        if detour:
            out["fastest"] = {"km": fastest["km"], "minutes": round(fastest["minutes"]),
                              "roads": [r["name"] for r in fastest["roads"][:5]],
                              "floods": [self._spot(h) for h in fastest["blocked"][:6]]}
        out["google_maps"] = self.maps_link(origin, destination, line.sample(3) if (detour or avoid) else [])
        return out

    @staticmethod
    def maps_link(a, b, via):
        q = {"api": 1, "origin": f"{a['lat']:.5f},{a['lng']:.5f}", "destination": f"{b['lat']:.5f},{b['lng']:.5f}",
             "travelmode": "driving"}
        if via:
            q["waypoints"] = "|".join(f"{p[0]:.5f},{p[1]:.5f}" for p in via)
        return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(q)
