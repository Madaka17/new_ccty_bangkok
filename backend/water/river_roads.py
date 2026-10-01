"""
Every Nonthaburi road, which stretches of it the Chao Phraya reaches first if it tops its bank in the next
7 days, and the chance of that.

River: the OpenStreetMap centre line of the Chao Phraya and the Lat Kret channel (config/chao_phraya.json).
Area: Nonthaburi province and its 52 sub-districts from OpenStreetMap (config/nonthaburi_areas.json; both
files come from local/pipeline/fetch_river_areas.py). Roads: every named road segment in traffic_service's
road index (Longdo base map, tertiary and up) whose middle lies in the province.

Each road is cut into stretches of about STRETCH_DEG (~330 m cells). A stretch keeps its distance to the
river centre line, its ตำบล / อำเภอ and the nearest cross road, so a row can say "ช่วงตัดถนน X ต.Y" rather
than a coordinate. The road's stretches are ranked by chance, then by distance: the first is where it
floods first, the second next. A road with no stretch within NEAR_KM stays in the list at 0%: overtopping
alone does not reach it.

The river's chance of going over the bank comes from HII's 7-day forecast at สะพานนวลฉวี, the Nonthaburi
gauge: each day's highest forecast level. The true peak is taken as normal around it with a spread (sigma)
per lead day:
  - from HII's own record once there is enough of it: every refresh logs the day's forecast peaks
    (cache/hii_1132_forecasts.json); once a day has passed, its observed peak gives the error at each lead;
  - until then, how far the observed daily peak moved over the same number of days in the last 30 days.
    A forecast should do better than that, so this spread is wide and errs on the side of warning.
P(day) = 1 - Φ((bank - peak) / sigma). The 7-day chance is the likeliest day's: errors on neighbouring
days run the same way, so multiplying the days as if independent would overstate it.

A road's chance is that 7-day chance × how close it runs to the river (CLOSENESS). Those weights are an assumption:
there is no road elevation or flood-wall data here, and the bank is the gauge's own, not the local one.
Both are said on the page.
"""
import json
import math
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

from backend.core.instance import DATA_DIR
from backend.water import water_service as ws

GAUGE_ID = 1132                                   # สะพานนวลฉวี, Pak Kret
RIVER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "chao_phraya.json")
LOG_FILE = os.path.join(DATA_DIR, "cache", "hii_1132_forecasts.json")
AREAS_FILE = os.path.join(os.path.dirname(RIVER_FILE), "nonthaburi_areas.json")
STRETCH_DEG = 0.003                               # ~330 m cells a road is cut into
CROSS_KM = 0.08                                   # another road this close to a stretch is its cross road
TOP_STRETCHES = 5
NEAR_KM = 2.0
CLOSENESS = ((0.2, 1.0), (0.5, 0.6), (1.0, 0.3), (2.0, 0.1))   # (within km, weight)
MIN_LOGGED = 5                                    # logged errors per lead day before they replace the fallback
LOG_DAYS = 60
TTL = 600
CELL = 0.01


def _km(a, b):
    """Equirectangular km between (lat, lng) points; fine at these distances."""
    cos = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[1] - b[1]) * 111.32 * cos, (a[0] - b[0]) * 110.57)


def _closest_on_segment(p, a, b):
    cos = math.cos(math.radians(p[0]))
    ax, ay, bx, by, px, py = a[1] * cos, a[0], b[1] * cos, b[0], p[1] * cos, p[0]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == 0 and dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return (ay + t * dy, (ax + t * dx) / cos)


class River:
    """The centre line, indexed by 0.01° cells for nearest-point lookups."""

    def __init__(self, lines):
        self.lines = lines
        self.grid = defaultdict(list)
        for line in lines:
            for a, b in zip(line, line[1:]):
                for la in np.arange(min(a[0], b[0]), max(a[0], b[0]) + CELL, CELL):
                    for ln in np.arange(min(a[1], b[1]), max(a[1], b[1]) + CELL, CELL):
                        self.grid[(int(la / CELL), int(ln / CELL))].append((tuple(a), tuple(b)))

    def nearest(self, p, max_km=NEAR_KM):
        """(km, point on the centre line) for the closest part of the river within max_km, else (None, None)."""
        r = int(max_km / (CELL * 100)) + 1
        k = (int(p[0] / CELL), int(p[1] / CELL))
        best = (None, None)
        for i in range(-r, r + 1):
            for j in range(-r, r + 1):
                for a, b in self.grid.get((k[0] + i, k[1] + j), ()):
                    c = _closest_on_segment(p, a, b)
                    d = _km(p, c)
                    if d <= max_km and (best[0] is None or d < best[0]):
                        best = (d, c)
        return best


_river = None
_river_lock = threading.Lock()


def river():
    global _river
    with _river_lock:
        if _river is None:
            with open(RIVER_FILE, "r", encoding="utf-8") as f:
                _river = River(json.load(f)["lines"])
        return _river


def closeness(km):
    return next((w for limit, w in CLOSENESS if km <= limit), 0.0)


def _inside(p, ring):
    lat, lng = p
    hit = False
    for (a_lat, a_lng), (b_lat, b_lng) in zip(ring, ring[1:] + ring[:1]):
        if (a_lat > lat) != (b_lat > lat) and lng < (b_lng - a_lng) * (lat - a_lat) / (b_lat - a_lat) + a_lng:
            hit = not hit
    return hit


class Areas:
    """Nonthaburi and its ตำบล, with bounding boxes so a lookup tests only the rings that can hold the point."""

    def __init__(self, data):
        def box(rings):
            pts = [p for r in rings for p in r]
            return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))
        self.province = data["province"]["rings"]
        self.box = box(self.province)
        self.tambon = [(t["name"], t["amphoe"], t["rings"], box(t["rings"])) for t in data["tambon"]]

    def in_province(self, p):
        b = self.box
        return b[0] <= p[0] <= b[1] and b[2] <= p[1] <= b[3] and any(_inside(p, r) for r in self.province)

    def tambon_of(self, p):
        for name, amphoe, rings, b in self.tambon:
            if b[0] <= p[0] <= b[1] and b[2] <= p[1] <= b[3] and any(_inside(p, r) for r in rings):
                return name, amphoe
        return "", ""


_areas = None


def areas():
    global _areas
    with _river_lock:
        if _areas is None:
            with open(AREAS_FILE, "r", encoding="utf-8") as f:
                _areas = Areas(json.load(f))
        return _areas


def _cross_road(road_index, name, p):
    """The nearest other named road within CROSS_KM of a point, for naming a stretch."""
    lng, lat = p[1], p[0]
    k = road_index._key(lng, lat)
    best = (None, CROSS_KM)
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for n, a, b in road_index.grid.get((k[0] + i, k[1] + j), ()):
                if n == name or n.startswith("สะพาน") or "จุดกลับรถ" in n:
                    continue
                d = road_index._dist((lng, lat), a, b)
                if d < best[1]:
                    best = (n, d)
    return best[0]


def road_stretches(road_index):
    """{road name: [stretch]} for every road whose segments lie in Nonthaburi. A stretch is one ~330 m cell
    of the road: {"lat", "lng", "km" (to the river centre line, None past NEAR_KM), "tambon", "amphoe", "cross"}."""
    rv, ar = river(), areas()
    cells = defaultdict(lambda: {"n": 0, "lat": 0.0, "lng": 0.0, "km": None})
    for segs in road_index.grid.values():
        for name, a, b in segs:
            mid = ((a[1] + b[1]) / 2, (a[0] + b[0]) / 2)          # index points are (lng, lat)
            if not ar.in_province(mid):
                continue
            c = cells[(name, int(mid[0] / STRETCH_DEG), int(mid[1] / STRETCH_DEG))]
            c["n"] += 1
            c["lat"] += mid[0]
            c["lng"] += mid[1]
            d, _ = rv.nearest(mid)
            if d is not None and (c["km"] is None or d < c["km"]):
                c["km"] = d
    out = defaultdict(list)
    for (name, _, _), c in cells.items():
        p = (c["lat"] / c["n"], c["lng"] / c["n"])
        tambon, amphoe = ar.tambon_of(p)
        out[name].append({"lat": round(p[0], 5), "lng": round(p[1], 5), "km": round(c["km"], 2) if c["km"] is not None else None,
                          "tambon": tambon, "amphoe": amphoe, "cross": _cross_road(road_index, name, p)})
    return out


# ---------------------------------------------------------------- the river's chance
def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _daily_peaks(points):
    """{date: highest value} from [{"t", "v"}] in Bangkok days."""
    out = {}
    for p in points:
        d = datetime.fromtimestamp(p["t"], ws.BKK_TZ).date()
        out[d] = max(out.get(d, -99.0), p["v"])
    return out


def persistence_sigma(observed_peaks, lead):
    """How far the observed daily peak moved over `lead` days in the record (sample std of the change)."""
    days = sorted(observed_peaks)
    moves = [observed_peaks[b] - observed_peaks[a] for a, b in zip(days, days[lead:])
             if (b - a).days == lead]
    return float(np.std(moves, ddof=1)) if len(moves) >= 3 else None


def _load_log():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_log(log):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f)
    except OSError as e:
        print(f"[RiverRoads] log save failed: {e}")


def logged_errors(log, observed_peaks):
    """{lead days: [observed - forecast]} from logged forecasts whose day has an observed peak."""
    out = defaultdict(list)
    for issued, targets in log.items():
        d0 = datetime.strptime(issued, "%Y-%m-%d").date()
        for target, peak in targets.items():
            d = datetime.strptime(target, "%Y-%m-%d").date()
            if d in observed_peaks and d < max(observed_peaks):     # only days that are over
                out[(d - d0).days].append(observed_peaks[d] - peak)
    return out


def day_chances(forecast_peaks, bank, sigma_for):
    """[{date, peak, sigma, p}] per forecast day and the 7-day chance (the likeliest day's)."""
    today = datetime.now(ws.BKK_TZ).date()
    days = []
    for d in sorted(forecast_peaks):
        lead = (d - today).days
        if lead < 0:
            continue
        sigma = sigma_for(max(1, lead))
        peak = forecast_peaks[d]
        p = 1 - _phi((bank - peak) / sigma) if sigma else float(peak >= bank)
        days.append({"date": d.isoformat(), "lead": lead, "peak": round(peak, 2), "sigma": round(sigma, 3) if sigma else None,
                     "p": round(p, 3)})
    return days, max((d["p"] for d in days), default=0.0)


def river_chance():
    """The gauge's forecast days with their chance of going over the bank, and how the spread was set."""
    fore, levels = ws._load_official_forecast(GAUGE_ID)
    bank = levels.get("bank")
    if not fore or bank is None:
        raise RuntimeError("HII forecast for สะพานนวลฉวี unavailable")
    observed = ws._load_observed(GAUGE_ID, days=31)
    obs_peaks = _daily_peaks(observed)
    fc_peaks = _daily_peaks(fore)

    today = datetime.now(ws.BKK_TZ).date()
    log = _load_log()
    log[today.isoformat()] = {d.isoformat(): v for d, v in fc_peaks.items() if d >= today}
    cut = (today - timedelta(days=LOG_DAYS)).isoformat()
    log = {k: v for k, v in log.items() if k >= cut}
    _save_log(log)
    errors = logged_errors(log, obs_peaks)

    sources = {}

    def sigma_for(lead):
        e = errors.get(lead) or []
        if len(e) >= MIN_LOGGED:
            sources[lead] = "hii"
            return float(np.sqrt(np.mean(np.square(e))))
        sources[lead] = "persistence"
        s = persistence_sigma(obs_peaks, lead)
        return max(0.03, s) if s is not None else 0.15

    days, p7 = day_chances(fc_peaks, bank, sigma_for)
    worst = max(days, key=lambda d: d["p"]) if days else None
    return {"gauge": "สะพานนวลฉวี", "province": "นนทบุรี", "bank": bank,
            "now": observed[-1]["v"] if observed else None, "now_t": observed[-1]["t"] if observed else None,
            "observed_peaks": [{"date": d.isoformat(), "peak": round(v, 2)} for d, v in sorted(obs_peaks.items())[-7:]],
            "days": days, "p7": p7, "likeliest": worst,
            "sigma_source": "hii" if sources and all(v == "hii" for v in sources.values()) else "persistence",
            "logged_days": len(log)}


def _level(p):
    return "สูง" if p >= 0.6 else "ปานกลาง" if p >= 0.3 else "เฝ้าระวัง" if p >= 0.1 else "ต่ำ"


def _place(s):
    """ช่วงตัดถนน X ต.Y อ.Z, from whatever the stretch has."""
    bits = [f"ช่วงตัด{s['cross']}" if s.get("cross") else "", f"ต.{s['tambon']}" if s.get("tambon") else "",
            f"อ.{s['amphoe']}" if s.get("amphoe") else ""]
    return " ".join(b for b in bits if b) or "ช่วงกลางถนน"


def rank_road(name, stretches, p7):
    """One road: its stretches ranked by chance then distance, the riskiest first, and the road's own chance."""
    for s in stretches:
        w = closeness(s["km"]) if s["km"] is not None else 0.0
        s["p"] = round(p7 * w, 3)
        s["level"] = _level(s["p"])
        s["place"] = _place(s)
    ranked = sorted(stretches, key=lambda s: (-s["p"], s["km"] if s["km"] is not None else 99))
    top = ranked[0]
    near = [s for s in ranked if s["km"] is not None]
    return {"road": name, "p": top["p"], "level": top["level"],
            "km": min((s["km"] for s in near), default=None),        # closest the road gets to the river
            "lat": top["lat"], "lng": top["lng"],
            "amphoe": sorted({s["amphoe"] for s in stretches if s["amphoe"]}),
            "stretches_total": len(stretches), "stretches_at_risk": sum(1 for s in stretches if s["p"] >= 0.1),
            "stretches": [{**s, "rank": i + 1} for i, s in enumerate(ranked[:TOP_STRETCHES])]}


def _build(traffic):
    chance = river_chance()
    if not traffic or not traffic.road_index:
        raise RuntimeError("road index not ready")
    roads = []
    for name, stretches in road_stretches(traffic.road_index).items():
        if name.startswith("สะพาน") or any(k in name for k in ("ทางพิเศษ", "ทางด่วน", "โทลล์เวย์", "ทางยกระดับ", "ลอยฟ้า", "จุดกลับรถ")):
            continue
        roads.append(rank_road(name, stretches, chance["p7"]))
    roads.sort(key=lambda x: (-x["p"], x["km"] if x["km"] is not None else 99, x["road"]))
    with open(RIVER_FILE, "r", encoding="utf-8") as f:
        rv = json.load(f)
    box = areas().box
    line = [[p for p in l if box[0] - 0.02 <= p[0] <= box[1] + 0.02] for l in rv["lines"]]
    counts = {lv: sum(1 for r in roads if r["level"] == lv) for lv in ("สูง", "ปานกลาง", "เฝ้าระวัง", "ต่ำ")}
    return {"updated_at": int(time.time()), "river": chance, "roads": roads, "counts": counts, "total": len(roads),
            "river_line": [l for l in line if len(l) > 1], "river_license": rv["license"],
            "areas_license": "เขตตำบล/อำเภอ © OpenStreetMap contributors, ODbL",
            "assumptions": {"closeness": [{"within_km": k, "weight": w} for k, w in CLOSENESS],
                            "bank": "ตลิ่งของสถานีสะพานนวลฉวี ไม่ใช่ตลิ่ง/แนวกั้นน้ำของแต่ละจุด",
                            "stretch_m": round(STRETCH_DEG * 111000),
                            "sigma": "ความคลาดเคลื่อนจากประวัติการคาดการณ์ของ สสน. เมื่อเก็บครบ ไม่งั้นใช้การเปลี่ยนแปลงของระดับน้ำสูงสุดรายวันจริงย้อนหลัง 30 วัน"}}


def get(traffic):
    data, stale = ws._cache.get("river_roads", TTL, lambda: _build(traffic))
    return {**data, "stale": stale}
