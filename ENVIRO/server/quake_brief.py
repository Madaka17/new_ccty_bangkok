"""AI earthquake brief: the latest real earthquakes worldwide and near Thailand, and what they mean for Thailand.

Every REFRESH_SECONDS this builds a set of facts from the live catalogs world_quakes already merges (USGS,
EMSC, GEOFON, TMD) over the last WINDOW_DAYS, with nothing guessed:
  - the events: time, place, magnitude, depth, the catalog that reported it, the nearest plate boundary
    (Bird 2003, PB2002) and the nearest mapped active fault (GEM GAF-DB, see world_faults.py)
  - the shaking each Thai province could have felt: predict_mmi() (seismology.py) at the distance to its
    provincial capital, plus AMPLIFY_MMI on the Bangkok basin's soft clay
  - what that level of shaking does to buildings (db.LEVELS) and the standing hazard from Thailand's own
    active faults (risk_scores, db.FAULTS)
then an AI model writes the Thai summary from those facts only: the OpenAI-compatible LOCAL_LLM_* endpoint
the host site (BKK StreetSmart) uses, read from this process's environment or that site's .env one folder
up. Without a model, or when the call fails, a Thai template writes it instead. The impact level is always
the computed one, never the model's.

Served by /api/world/brief.
"""
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from . import db as dbmod
from . import world_faults
from . import world_quakes
from .geo import haversine_km
from .seismology import FELT_MMI_THRESHOLD, mmi_roman, predict_mmi

WINDOW_DAYS = 7
GLOBAL_MIN_MAG = 4.5         # "worldwide": every event this size or bigger
NEAR_KM, NEAR_MIN_MAG = 2000, 4.5    # "near Thailand": this size within this far of a Thai provincial capital,
LOCAL_KM, LOCAL_MIN_MAG = 300, 3.0   # or smaller ones close by
MAX_WORLD, MAX_NEAR, MAX_PROVINCES = 5, 8, 10
DEFAULT_DEPTH_KM = 10
# Bangkok's soft clay amplifies shaking, long-period shaking from distant large quakes most (2025 Myanmar M7.7,
# ~1,000 km away, shook high-rises in Bangkok). +1 MMI is about twice the ground motion on the Wald et al.
# (1999) scale predict_mmi() uses: a deliberately simple allowance, not a site-response model.
AMPLIFY_MMI = 1.0
FAR_FIELD_MAG, FAR_FIELD_KM = 6.5, 1500   # this big within this far of Bangkok: tall buildings may sway
FAULT_NEAR_KM, PLATE_NEAR_KM = 30, 400

REFRESH_SECONDS = 300        # the catalogs themselves are polled every 5 minutes
AI_SECONDS = 900             # rewrite at least this often even when the events have not changed
AI_TIMEOUT = 150

PB2002_URL = "https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/PB2002_boundaries.json"
PB2002_PATH = os.path.join(dbmod.BASE_DIR, "data", "pb2002_boundaries.json")
DOTENV_PATH = os.path.join(os.path.dirname(dbmod.BASE_DIR), ".env")
ICT = timezone(timedelta(hours=7))

# Provincial capitals (6-region grouping). soft = on the Bangkok basin's soft clay (AMPLIFY_MMI).
PROVINCES = [
    ("เชียงราย", "ภาคเหนือ", 19.91, 99.83), ("เชียงใหม่", "ภาคเหนือ", 18.79, 98.98), ("น่าน", "ภาคเหนือ", 18.78, 100.78),
    ("พะเยา", "ภาคเหนือ", 19.17, 99.90), ("แพร่", "ภาคเหนือ", 18.14, 100.14), ("แม่ฮ่องสอน", "ภาคเหนือ", 19.30, 97.97),
    ("ลำปาง", "ภาคเหนือ", 18.29, 99.49), ("ลำพูน", "ภาคเหนือ", 18.58, 99.01), ("อุตรดิตถ์", "ภาคเหนือ", 17.63, 100.10),
    ("กาฬสินธุ์", "ภาคตะวันออกเฉียงเหนือ", 16.43, 103.51), ("ขอนแก่น", "ภาคตะวันออกเฉียงเหนือ", 16.44, 102.84),
    ("ชัยภูมิ", "ภาคตะวันออกเฉียงเหนือ", 15.81, 102.03), ("นครพนม", "ภาคตะวันออกเฉียงเหนือ", 17.41, 104.78),
    ("นครราชสีมา", "ภาคตะวันออกเฉียงเหนือ", 14.97, 102.10), ("บึงกาฬ", "ภาคตะวันออกเฉียงเหนือ", 18.36, 103.65),
    ("บุรีรัมย์", "ภาคตะวันออกเฉียงเหนือ", 14.99, 103.10), ("มหาสารคาม", "ภาคตะวันออกเฉียงเหนือ", 16.18, 103.30),
    ("มุกดาหาร", "ภาคตะวันออกเฉียงเหนือ", 16.54, 104.72), ("ยโสธร", "ภาคตะวันออกเฉียงเหนือ", 15.79, 104.15),
    ("ร้อยเอ็ด", "ภาคตะวันออกเฉียงเหนือ", 16.05, 103.65), ("เลย", "ภาคตะวันออกเฉียงเหนือ", 17.49, 101.72),
    ("ศรีสะเกษ", "ภาคตะวันออกเฉียงเหนือ", 15.12, 104.32), ("สกลนคร", "ภาคตะวันออกเฉียงเหนือ", 17.16, 104.15),
    ("สุรินทร์", "ภาคตะวันออกเฉียงเหนือ", 14.88, 103.49), ("หนองคาย", "ภาคตะวันออกเฉียงเหนือ", 17.88, 102.74),
    ("หนองบัวลำภู", "ภาคตะวันออกเฉียงเหนือ", 17.20, 102.44), ("อำนาจเจริญ", "ภาคตะวันออกเฉียงเหนือ", 15.86, 104.63),
    ("อุดรธานี", "ภาคตะวันออกเฉียงเหนือ", 17.41, 102.79), ("อุบลราชธานี", "ภาคตะวันออกเฉียงเหนือ", 15.24, 104.85),
    ("กรุงเทพมหานคร", "ภาคกลาง", 13.756, 100.502), ("กำแพงเพชร", "ภาคกลาง", 16.48, 99.52), ("ชัยนาท", "ภาคกลาง", 15.19, 100.13),
    ("นครนายก", "ภาคกลาง", 14.21, 101.21), ("นครปฐม", "ภาคกลาง", 13.82, 100.06), ("นครสวรรค์", "ภาคกลาง", 15.70, 100.14),
    ("นนทบุรี", "ภาคกลาง", 13.86, 100.52), ("ปทุมธานี", "ภาคกลาง", 14.02, 100.53), ("พระนครศรีอยุธยา", "ภาคกลาง", 14.35, 100.57),
    ("พิจิตร", "ภาคกลาง", 16.44, 100.35), ("พิษณุโลก", "ภาคกลาง", 16.82, 100.26), ("เพชรบูรณ์", "ภาคกลาง", 16.42, 101.16),
    ("ลพบุรี", "ภาคกลาง", 14.80, 100.65), ("สมุทรปราการ", "ภาคกลาง", 13.60, 100.60), ("สมุทรสงคราม", "ภาคกลาง", 13.41, 100.00),
    ("สมุทรสาคร", "ภาคกลาง", 13.55, 100.27), ("สระบุรี", "ภาคกลาง", 14.53, 100.91), ("สิงห์บุรี", "ภาคกลาง", 14.89, 100.40),
    ("สุโขทัย", "ภาคกลาง", 17.01, 99.82), ("สุพรรณบุรี", "ภาคกลาง", 14.47, 100.12), ("อ่างทอง", "ภาคกลาง", 14.59, 100.45),
    ("อุทัยธานี", "ภาคกลาง", 15.38, 100.02),
    ("จันทบุรี", "ภาคตะวันออก", 12.61, 102.10), ("ฉะเชิงเทรา", "ภาคตะวันออก", 13.69, 101.07), ("ชลบุรี", "ภาคตะวันออก", 13.36, 100.98),
    ("ตราด", "ภาคตะวันออก", 12.24, 102.52), ("ปราจีนบุรี", "ภาคตะวันออก", 14.05, 101.37), ("ระยอง", "ภาคตะวันออก", 12.68, 101.28),
    ("สระแก้ว", "ภาคตะวันออก", 13.82, 102.07),
    ("กาญจนบุรี", "ภาคตะวันตก", 14.02, 99.53), ("ตาก", "ภาคตะวันตก", 16.88, 99.13), ("ประจวบคีรีขันธ์", "ภาคตะวันตก", 11.81, 99.80),
    ("เพชรบุรี", "ภาคตะวันตก", 13.11, 99.94), ("ราชบุรี", "ภาคตะวันตก", 13.54, 99.82),
    ("กระบี่", "ภาคใต้", 8.09, 98.91), ("ชุมพร", "ภาคใต้", 10.49, 99.18), ("ตรัง", "ภาคใต้", 7.56, 99.61),
    ("นครศรีธรรมราช", "ภาคใต้", 8.43, 99.96), ("นราธิวาส", "ภาคใต้", 6.43, 101.82), ("ปัตตานี", "ภาคใต้", 6.87, 101.25),
    ("พังงา", "ภาคใต้", 8.45, 98.53), ("พัทลุง", "ภาคใต้", 7.62, 100.08), ("ภูเก็ต", "ภาคใต้", 7.89, 98.40),
    ("ยะลา", "ภาคใต้", 6.54, 101.28), ("ระนอง", "ภาคใต้", 9.96, 98.64), ("สงขลา", "ภาคใต้", 7.19, 100.60),
    ("สตูล", "ภาคใต้", 6.62, 100.07), ("สุราษฎร์ธานี", "ภาคใต้", 9.14, 99.33),
]
SOFT_CLAY = {"กรุงเทพมหานคร", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ", "สมุทรสาคร"}
BANGKOK = (13.756, 100.502)

# PB2002 plate codes (Bird 2003)
PLATES = {
    "AF": "แอฟริกา", "AM": "อามูร์", "AN": "แอนตาร์กติก", "AP": "Altiplano", "AR": "อาระเบีย", "AS": "ทะเลอีเจียน",
    "AT": "อานาโตเลีย", "AU": "ออสเตรเลีย", "BH": "Birds Head", "BR": "Balmoral Reef", "BS": "ทะเลบันดา", "BU": "พม่า",
    "CA": "แคริบเบียน", "CL": "Caroline", "CO": "โคโคส", "CR": "Conway Reef", "EA": "Easter", "EU": "ยูเรเชีย",
    "FT": "Futuna", "GP": "Galapagos", "IN": "อินเดีย", "JF": "ฮวนเดฟูกา", "JZ": "Juan Fernandez", "KE": "เคอร์มาเดก",
    "MA": "มาเรียนา", "MN": "Manus", "MO": "Maoke", "MS": "ทะเลโมลุกกะ", "NA": "อเมริกาเหนือ", "NB": "North Bismarck",
    "ND": "North Andes", "NH": "นิวเฮบริดีส", "NI": "Niuafo'ou", "NZ": "นัซกา", "OK": "โอค็อตสค์", "ON": "โอกินาวา",
    "PA": "แปซิฟิก", "PM": "ปานามา", "PS": "ทะเลฟิลิปปิน", "RI": "Rivera", "SA": "อเมริกาใต้", "SB": "South Bismarck",
    "SC": "สโกเชีย", "SL": "Shetland", "SO": "โซมาเลีย", "SS": "ทะเลโซโลมอน", "SU": "ซุนดา", "SW": "Sandwich",
    "TI": "ติมอร์", "TO": "ตองกา", "WL": "Woodlark", "YA": "แยงซี",
}

AI_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["headline", "world", "thailand", "buildings", "advice"],
    "properties": {
        "headline": {"type": "string"}, "world": {"type": "string"}, "thailand": {"type": "string"},
        "buildings": {"type": "string"}, "advice": {"type": "array", "items": {"type": "string"}},
    },
}

_lock = threading.Lock()
_brief = None
_plates = None
_faults = None
_dotenv = None


def get():
    with _lock:
        return _brief


# ------------------------------------------------------------ geometry
def _seg_km(lat, lng, a, b):
    """Distance (km) from (lat, lng) to segment a-b, on a flat projection around the point."""
    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.57

    def xy(p):
        return ((p[1] - lng + 540) % 360 - 180) * kx, (p[0] - lat) * ky
    (ax, ay), (bx, by) = xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def _nearest(lat, lng, lines, max_km):
    """(line, km) of the closest of `lines` [(bbox, points, payload)] within max_km, else (None, None)."""
    dlat = max_km / 110.57
    dlng = max_km / max(1.0, 111.32 * math.cos(math.radians(lat)))
    best, best_km = None, max_km
    for (minlat, maxlat, minlng, maxlng), pts, payload in lines:
        if lat < minlat - dlat or lat > maxlat + dlat or lng < minlng - dlng or lng > maxlng + dlng:
            continue
        for a, b in zip(pts, pts[1:]):
            km = _seg_km(lat, lng, a, b)
            if km < best_km:
                best, best_km = payload, km
    return (best, round(best_km)) if best is not None else (None, None)


def _bbox(pts):
    lats, lngs = [p[0] for p in pts], [p[1] for p in pts]
    return min(lats), max(lats), min(lngs), max(lngs)


def _load_plates():
    """PB2002 boundaries as [(bbox, [(lat, lng)], {"name", "subduction"})], downloaded once to data/."""
    global _plates
    if _plates is not None:
        return _plates
    try:
        if not os.path.exists(PB2002_PATH):
            req = urllib.request.Request(PB2002_URL, headers={"User-Agent": "enviro-seismic-command/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            with open(PB2002_PATH, "wb") as f:
                f.write(raw)
        with open(PB2002_PATH, "r", encoding="utf-8") as f:
            features = json.load(f)["features"]
    except Exception as e:  # noqa: BLE001 - try again on the next refresh
        print(f"[QuakeBrief] plate boundaries unavailable: {e}")
        return []
    lines = []
    for feat in features:
        props, geom = feat.get("properties") or {}, feat.get("geometry") or {}
        name = str(props.get("Name") or "")
        codes = [c for c in re.split(r"[-/\\]", name) if c]
        if len(codes) != 2:
            continue
        # PB2002 writes a subduction zone with a slash (the side the slab dips under), other boundaries with "-"
        label = {"name": f"แผ่น{PLATES.get(codes[0], codes[0])}–แผ่น{PLATES.get(codes[1], codes[1])}",
                 "subduction": "/" in name or "\\" in name or "subduction" in str(props.get("Type") or "").lower()}
        parts = geom.get("coordinates") or []
        if geom.get("type") == "LineString":
            parts = [parts]
        for part in parts:
            pts = [(c[1], c[0]) for c in part]
            if len(pts) >= 2:
                lines.append((_bbox(pts), pts, label))
    _plates = lines
    return _plates


def _load_faults():
    """GEM active faults as [(bbox, [(lat, lng)], {"name", "slip_type"})], once world_faults has built its cache."""
    global _faults
    if _faults is not None:
        return _faults
    cached = world_faults.get_cached()
    if not cached:
        return []
    _faults = [(_bbox(f["points"]), f["points"], {"name": f["name"], "slip_type": f["slip_type"]})
               for f in cached["faults"] if f.get("name") and len(f["points"]) >= 2]
    return _faults


# ------------------------------------------------------------ facts
# Who feels shaking of this MMI (USGS), so the text does not claim "people felt it" at MMI II
FELT_TH = (
    (6.0, "ทุกคนรู้สึก เดินลำบาก เฟอร์นิเจอร์เคลื่อน อาคารที่ไม่แข็งแรงอาจเสียหาย"),
    (5.0, "เกือบทุกคนรู้สึก ของชิ้นเล็กตกหล่น ภาชนะอาจแตก"),
    (4.0, "คนในอาคารส่วนใหญ่รู้สึก จาน หน้าต่าง และประตูสั่น"),
    (3.0, "คนในอาคารรู้สึกได้ โดยเฉพาะชั้นบน แต่หลายคนอาจไม่รู้ว่าเป็นแผ่นดินไหว"),
    (FELT_MMI_THRESHOLD, "รู้สึกได้เฉพาะบางคนที่อยู่นิ่ง โดยเฉพาะชั้นบนของอาคารสูง คนส่วนใหญ่ไม่รู้สึก"),
)


def _felt_th(mmi):
    return next((text for floor, text in FELT_TH if mmi >= floor), "คนไม่รู้สึก มีเพียงเครื่องมือที่ตรวจวัดได้")


def _level(mmi):
    """The db.LEVELS row for this intensity: (lv, name, mmi_min, mmi_max, roman, damage text, ..., advisory, ...)."""
    for row in reversed(dbmod.LEVELS):
        if mmi >= row[2]:
            return row
    return dbmod.LEVELS[0]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _events(quakes, now_ms):
    """The window's events with numeric fields (TMD's may come as text). world_quakes has already merged the
    same event reported by several catalogs into one."""
    cutoff = now_ms - WINDOW_DAYS * 86400 * 1000
    rows = []
    for q in quakes:
        mag, lat, lng = _num(q.get("magnitude")), _num(q.get("lat")), _num(q.get("lng"))
        if None not in (mag, lat, lng) and (q.get("time_ms") or 0) >= cutoff:
            rows.append({**q, "magnitude": mag, "lat": lat, "lng": lng, "depth_km": _num(q.get("depth_km"))})
    return rows


def _public(e):
    """The fields the page and the model see for one event."""
    depth = e["depth_km"]
    mmi_th = e.get("max_mmi_th")
    return {
        "id": e["id"], "time": datetime.fromtimestamp(e["time_ms"] / 1000, ICT).strftime("%d/%m/%Y %H:%M"),
        "time_ms": e["time_ms"],
        # Whether anyone in Thailand would feel it, in words (near events only: world events carry no MMI)
        "felt_in_th": mmi_th is not None and mmi_th >= FELT_MMI_THRESHOLD,
        "felt_th": _felt_th(mmi_th) if mmi_th is not None else None,
        "place": e.get("place") or "-", "lat": round(e["lat"], 2), "lng": round(e["lng"], 2),
        "magnitude": round(e["magnitude"], 1), "depth_km": round(depth) if depth is not None else None,
        "source": e.get("source"), "url": e.get("url"),
        "dist_bkk_km": round(haversine_km(e["lat"], e["lng"], *BANGKOK)),
        "nearest_province": e["nearest_province"], "dist_th_km": round(e["dist_th_km"]),
        "max_mmi_th": e.get("max_mmi_th"), "max_mmi_th_where": e.get("max_mmi_th_where"),
    }


def _tectonics(ev):
    plate, plate_km = _nearest(ev["lat"], ev["lng"], _load_plates(), PLATE_NEAR_KM)
    fault, fault_km = _nearest(ev["lat"], ev["lng"], _load_faults(), FAULT_NEAR_KM)
    ev["plate"] = {**plate, "dist_km": plate_km} if plate else None
    ev["fault"] = {**fault, "dist_km": fault_km} if fault else None
    return ev


def build_facts(now_ms=None):
    now_ms = now_ms or time.time() * 1000
    events = _events(world_quakes.get_state()["quakes"], now_ms)
    for e in events:
        d, p = min((haversine_km(e["lat"], e["lng"], lat, lng), name) for name, _, lat, lng in PROVINCES)
        e["dist_th_km"], e["nearest_province"] = d, p

    near = [e for e in events if (e["dist_th_km"] <= NEAR_KM and e["magnitude"] >= NEAR_MIN_MAG)
            or (e["dist_th_km"] <= LOCAL_KM and e["magnitude"] >= LOCAL_MIN_MAG)]
    # Strongest predicted shaking per province over every nearby event
    provinces = {}
    for e in near:
        e["max_mmi_th"], e["max_mmi_th_where"] = 0.0, None
        for name, region, lat, lng in PROVINCES:
            dist = haversine_km(e["lat"], e["lng"], lat, lng)
            mmi = predict_mmi(e["magnitude"], dist, e.get("depth_km") or DEFAULT_DEPTH_KM)
            # Only shaking that is felt at all gets the soft-clay allowance: otherwise a small quake 1,700 km
            # away would rank Bangkok first on the +1 alone
            if name in SOFT_CLAY and mmi >= FELT_MMI_THRESHOLD:
                mmi = min(12.0, mmi + AMPLIFY_MMI)
            mmi = round(mmi, 1)
            if mmi > e["max_mmi_th"]:
                e["max_mmi_th"], e["max_mmi_th_where"] = mmi, name
            if mmi > provinces.get(name, {}).get("mmi", 0):
                provinces[name] = {"province": name, "region": region, "mmi": mmi, "event_id": e["id"],
                                   "event": f"M{e['magnitude']:.1f} {e.get('place') or ''}".strip(),
                                   "dist_km": round(dist), "soft_clay": name in SOFT_CLAY}
    for p in provinces.values():
        row = _level(p["mmi"])
        p.update(roman=mmi_roman(p["mmi"]), level=row[0], level_name=row[1], felt=p["mmi"] >= FELT_MMI_THRESHOLD,
                 felt_th=_felt_th(p["mmi"]))
    ranking = sorted((p for p in provinces.values() if p["mmi"] >= FELT_MMI_THRESHOLD), key=lambda p: -p["mmi"])
    top_mmi = ranking[0]["mmi"] if ranking else 1.0
    lv = _level(top_mmi)

    near.sort(key=lambda e: (-e["max_mmi_th"], -e["magnitude"]))
    world = sorted((e for e in events if e["magnitude"] >= GLOBAL_MIN_MAG), key=lambda e: -e["magnitude"])
    far_field = [_public(e) for e in near if e["magnitude"] >= FAR_FIELD_MAG
                 and haversine_km(e["lat"], e["lng"], *BANGKOK) <= FAR_FIELD_KM]

    conn = dbmod.get_conn()
    risk = [dict(r) for r in conn.execute("SELECT region, score FROM risk_scores ORDER BY score DESC").fetchall()]
    conn.close()

    return {
        "window_days": WINDOW_DAYS,
        "world": {
            "count": len(world), "count_m6": sum(1 for e in world if e["magnitude"] >= 6.0),
            "top": [_tectonics(_public(e)) for e in world[:MAX_WORLD]],
        },
        "near": [_tectonics(_public(e)) for e in near[:MAX_NEAR]],
        "near_count": len(near),
        "provinces": ranking[:MAX_PROVINCES],
        "bangkok": provinces.get("กรุงเทพมหานคร"),
        "level": {"lv": lv[0], "name": lv[1], "mmi": top_mmi, "roman": mmi_roman(top_mmi),
                  "damage": lv[5], "advisory": lv[11]},
        "far_field": far_field,
        "standing_hazard": risk,
        "thai_faults": [{"name": n, "province": p} for n, p, *_ in dbmod.FAULTS],
        "soft_clay": sorted(SOFT_CLAY), "amplify_mmi": AMPLIFY_MMI,
        # False while a dataset is still downloading/building: a null plate/fault then means "unknown", not "none"
        "tectonics_ready": bool(_load_plates()) and bool(_load_faults()),
    }


# ------------------------------------------------------------ writing
def _where(e):
    return f"{e['place']} ({e['lat']}, {e['lng']})"


def _template(f):
    """Deterministic Thai brief, used without a model or when the call fails."""
    w, near, lv, ranking = f["world"], f["near"], f["level"], f["provinces"]
    if ranking:
        top = ranking[0]
        headline = f"แรงสั่นที่คาดว่าถึงไทยสูงสุดในรอบ {f['window_days']} วัน: MMI {top['roman']} ที่{top['province']} จาก {top['event']}"
    elif near:
        headline = f"มีแผ่นดินไหวใกล้ไทย {f['near_count']} ครั้งในรอบ {f['window_days']} วัน แต่คาดว่าไม่รู้สึกแรงสั่นในไทย"
    else:
        headline = f"ไม่มีแผ่นดินไหวที่คาดว่าส่งผลต่อไทยในรอบ {f['window_days']} วัน"

    if w["top"]:
        big = w["top"][0]
        plate = f" บน{'เขตมุดตัว' if big['plate']['subduction'] else 'แนวรอยต่อ'}{big['plate']['name']}" if big.get("plate") else ""
        world = (f"ทั่วโลกมีแผ่นดินไหวขนาด {GLOBAL_MIN_MAG} ขึ้นไป {w['count']} ครั้ง (ขนาด 6 ขึ้นไป {w['count_m6']} ครั้ง) "
                 f"ใหญ่ที่สุด M{big['magnitude']} ที่ {_where(big)} ลึก {big['depth_km'] if big['depth_km'] is not None else '-'} กม.{plate}")
    else:
        world = f"ไม่มีรายงานแผ่นดินไหวขนาด {GLOBAL_MIN_MAG} ขึ้นไปทั่วโลกในรอบ {f['window_days']} วัน"

    parts = []
    if ranking:
        parts.append("จังหวัดที่คาดว่าได้รับแรงสั่นมากที่สุด: " +
                     ", ".join(f"{p['province']} (MMI {p['roman']})" for p in ranking[:5]))
    if f["standing_hazard"]:
        parts.append("พื้นที่เสี่ยงสูงจากรอยเลื่อนมีพลังในประเทศ: " +
                     ", ".join(f"{r['region']} ({r['score']})" for r in f["standing_hazard"][:4]))
    parts.append("กรุงเทพฯ และปริมณฑลตั้งอยู่บนชั้นดินเหนียวอ่อน ซึ่งขยายแรงสั่นจากแผ่นดินไหวใหญ่ที่อยู่ไกลได้")

    buildings = f"ระดับ {lv['lv']} ({lv['name']}): {lv['damage']}"
    if f["far_field"]:
        e = f["far_field"][0]
        buildings += (f" · M{e['magnitude']} ที่ {e['place']} อยู่ห่างกรุงเทพฯ {e['dist_bkk_km']:,} กม. "
                      "คลื่นคาบยาวจากเหตุการณ์ขนาดนี้อาจทำให้อาคารสูงใน กทม. โยกไหว ควรตรวจรอยร้าวของอาคาร")

    return {"headline": headline, "world": world, "thailand": " · ".join(parts), "buildings": buildings,
            "advice": [lv["advisory"], "ติดตามประกาศทางการจากกรมอุตุนิยมวิทยาและกรมป้องกันและบรรเทาสาธารณภัย"]}


def _env(name, default=""):
    """This process's environment first, else the host site's .env; `default` only when neither has the name."""
    global _dotenv
    if name in os.environ:
        return os.environ[name].strip()
    if _dotenv is None:
        _dotenv = {}
        try:
            with open(DOTENV_PATH, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        _dotenv[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    return _dotenv.get(name, default)


def _ask(prompt):
    """(reply dict, model) from the LOCAL_LLM_* endpoint; (None, None) when no model is set."""
    model = _env("LOCAL_LLM_MODEL")
    if not model:
        return None, None
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1600,
            "temperature": 0.2, **json.loads(_env("LOCAL_LLM_EXTRA") or "{}"),
            "response_format": {"type": "json_schema", "json_schema": {"name": "reply", "strict": True, "schema": AI_SCHEMA}}}
    reasoning = _env("LOCAL_LLM_REASONING", "none")
    if reasoning:
        body["reasoning_effort"] = reasoning
    # A User-Agent of its own: the gateway's Cloudflare refuses urllib's default one (403, error 1010)
    headers = {"Content-Type": "application/json", "User-Agent": "enviro-seismic-command/1.0"}
    if _env("LOCAL_LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + _env("LOCAL_LLM_API_KEY")
    url = _env("LOCAL_LLM_URL", "http://localhost:1234/v1").rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    # The gateway allows 3 requests in flight per key and BKK StreetSmart shares the key: a 429 is retried
    for wait in (5, 15, None):
        try:
            with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as resp:
                text = json.load(resp)["choices"][0]["message"].get("content") or ""
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or wait is None:
                raise
            time.sleep(wait)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    return json.loads(text[text.find("{"):text.rfind("}") + 1]), model


def write_brief(f):
    base = _template(f)
    prompt = (
        "คุณคือผู้เชี่ยวชาญด้านธรณีฟิสิกส์และระบบเตือนภัยพิบัติ เขียนสรุปรายงานแผ่นดินไหวล่าสุดเป็นภาษาไทย "
        "สำหรับประชาชนทั่วไปในประเทศไทย จากข้อมูล JSON ข้างล่างเท่านั้น\n"
        "ความหมายของข้อมูล: world = แผ่นดินไหวขนาด 4.5 ขึ้นไปทั่วโลก, near = เหตุการณ์ใกล้ไทยเรียงตามแรงสั่นที่คาดว่าถึงไทย, "
        "plate = แนวรอยต่อแผ่นเปลือกโลกที่ใกล้ศูนย์กลางที่สุด (subduction = เขตมุดตัว, dist_km = ระยะห่าง), "
        "fault = รอยเลื่อนมีพลังที่ใกล้ที่สุด, max_mmi_th = ความรุนแรง MMI สูงสุดที่คาดว่าถึงไทย, "
        "provinces = จังหวัดที่คาดว่ารู้สึกแรงสั่น เรียงจากมากไปน้อย (soft_clay = อยู่บนชั้นดินเหนียวอ่อน บวกเพิ่มแล้ว amplify_mmi), "
        "level = ระดับผลกระทบสูงสุดต่อไทยและผลต่ออาคาร, far_field = เหตุการณ์ใหญ่ที่อาจทำให้อาคารสูงใน กทม. โยกไหว, "
        "standing_hazard = คะแนนความเสี่ยงประจำพื้นที่จากรอยเลื่อนมีพลังในประเทศ (เต็ม 100), thai_faults = รอยเลื่อนมีพลังในไทย\n"
        "กติกา: ห้ามแต่งตัวเลข ชื่อสถานที่ ชื่อรอยเลื่อน หรือแนวรอยต่อที่ไม่มีในข้อมูล "
        "place และ event เป็นภาษาอังกฤษจากฟีด ให้แปลเป็นภาษาไทยทุกครั้งที่ใช้ในข้อความ ห้ามคัดลอกภาษาอังกฤษมาตรง ๆ "
        "เช่น '45 km SW of Bengkulu, Indonesia' เขียนว่า 'ห่างเมืองเบงกูลู อินโดนีเซีย ไปทางตะวันตกเฉียงใต้ 45 กม.' "
        "และ 'OFF W COAST OF NORTHERN SUMATRA' เขียนว่า 'นอกชายฝั่งตะวันตกของเกาะสุมาตราตอนเหนือ' "
        "แปลเฉพาะสิ่งที่มีใน place ห้ามเดาเพิ่มว่าอยู่ใกล้ชายแดนหรือประเทศใด "
        "ถ้า plate หรือ fault เป็น null ให้บอกว่าไม่อยู่ใกล้แนวที่ทราบ "
        "ยกเว้น tectonics_ready เป็น false ให้ไม่กล่าวถึงแนวรอยต่อและรอยเลื่อนเลย "
        "ค่า MMI เป็นค่าประมาณจากแบบจำลองตามระยะทาง ไม่ใช่ค่าที่วัดได้จริง "
        "felt = คนรู้สึกแรงสั่นหรือไม่ ถ้า felt เป็น false ต้องเขียนว่าคนไม่รู้สึกแรงสั่น ห้ามเขียนว่ารู้สึก "
        "felt_th = ใครรู้สึกได้ที่ระดับนั้น ให้เขียนตาม felt_th ห้ามเขียนให้แรงกว่า "
        "เช่น ที่ MMI II ห้ามเขียนว่าประชาชนในพื้นที่รู้สึก ให้เขียนว่ารู้สึกได้เฉพาะบางคนที่อยู่นิ่ง "
        "ห้ามพยากรณ์ว่าจะเกิดแผ่นดินไหวเมื่อใด "
        "ห้ามใช้ Markdown\n"
        "ตอบเป็น JSON object เท่านั้น:\n"
        '{"headline":"<1 ประโยค สรุปสิ่งที่สำคัญที่สุดสำหรับคนไทยตอนนี้ ไม่เกิน 35 คำ>",'
        '"world":"<2-3 ประโยค เหตุการณ์ใหญ่ทั่วโลกและใกล้ภูมิภาค: พิกัด ขนาด ความลึก และแนวรอยต่อแผ่นเปลือกโลกที่เกี่ยวข้อง>",'
        '"thailand":"<2-3 ประโยค จัดอันดับภาคหรือจังหวัดที่ได้รับผลกระทบมากที่สุด ทั้งจากเหตุการณ์ครั้งนี้ '
        'รอยเลื่อนมีพลังในประเทศ และผลกระทบระยะไกลต่อชั้นดินอ่อนใน กทม.>",'
        '"buildings":"<2-3 ประโยค ประเมินระดับความเสี่ยงและความเสียหายต่อโครงสร้างอาคาร ตาม level และ far_field>",'
        '"advice":["<คำแนะนำสั้น ปฏิบัติได้จริง ตรงกับระดับ 2-3 ข้อ>"]}\n\n'
        + json.dumps(f, ensure_ascii=False)
    )
    out, source = dict(base), "template"
    try:
        d, model = _ask(prompt)
        if isinstance(d, dict) and str(d.get("headline") or "").strip():
            out = {k: str(d.get(k) or "").strip() or base[k] for k in ("headline", "world", "thailand", "buildings")}
            out["advice"] = [str(a).strip() for a in (d.get("advice") or []) if str(a).strip()][:4] or base["advice"]
            source = model
    except Exception as e:  # noqa: BLE001
        print(f"[QuakeBrief] AI brief failed, using template: {str(e)[:160]}")
    return {**out, "source": source, "facts": f, "updated_at": int(time.time())}


def run_forever(stop_event: threading.Event):
    global _brief
    last_sig, last_at = None, 0.0
    while not stop_event.is_set():
        try:
            if world_quakes.get_state()["checked_at"]:
                facts = build_facts()
                sig = json.dumps([e["id"] for e in facts["near"] + facts["world"]["top"]])
                if sig != last_sig or time.time() - last_at >= AI_SECONDS:
                    brief = write_brief(facts)
                    with _lock:
                        _brief = brief
                    last_sig, last_at = sig, time.time()
        except Exception as e:  # noqa: BLE001 - one bad round must not kill the thread
            print(f"[QuakeBrief] refresh failed: {e}")
        stop_event.wait(REFRESH_SECONDS if _brief else 30)
