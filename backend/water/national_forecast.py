"""
7-day water and flood outlook for the whole country, for the first four tabs of the Water page:
ระดับน้ำทั่วประเทศ (dams), คาดการณ์น้ำท่วม (provinces), ถนนน้ำท่วม (roads) and สรุปสถานการณ์ (summary).

Every REFRESH_SECONDS it reads:
  - Thai Water's dam report (/analyst/dam): the 35 large dams of the Royal Irrigation Department (storage,
    inflow, release, daily) and about 450 medium reservoirs (storage only), in 67 provinces;
  - each large dam's daily storage, inflow and release since 1 January (/analyst/dam_yearly_graph), once a day;
  - Open-Meteo's 7-day rain forecast at every large dam and at the middle of every province's rain gauges;
  - province_flood's picture of today (river gauges, flooded highways, people's reports per province);
  - OpenStreetMap main roads (motorway / trunk / primary, Overpass API) within ROAD_NEAR_M of every gauge over
    the bank or high and rising, and of every large dam heading over FULL_WARN_PCT, once per ROADS_TTL.

The numbers are computed, not guessed by the model:
  - a large dam's storage in d days = today's + d x its average net inflow (inflow - release) of the last
    NET_DAYS days, as a share of its normal storage (the share RID reports). That assumes the dam keeps
    releasing as it did; more rain or a change of release moves it. The rain forecast at the dam is shown
    beside it, not folded in: there is no catchment area here to turn millimetres into cubic metres;
  - a province's flood risk index (0-100) for each of the next 7 days adds today's level, its large dams'
    storage that day, full medium reservoirs, the rain of the 3 days up to that day, rising gauges and a large
    dam over 100% that day in the basin of a high gauge there (see day_index). 80+ เสี่ยงสูงมาก, 60-79 เสี่ยงสูง,
    40-59 เฝ้าระวัง.

The Qwen model behind LOCAL_LLM_* (local_llm.default) then reads those numbers, sets each province's and
road's risk from a fixed list and writes the plain-Thai outlook: four requests (water, provinces, roads,
summary), run again only when the picture changed or the report is older than AI_MAX_AGE. Without the model
the page shows the computed levels and the built sentences only.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from backend.core import local_llm, thai_regions
from backend.water.water_service import OPEN_METEO, _ntw_get, _num

REFRESH_SECONDS = int(os.getenv("NATIONAL_FORECAST_SECONDS", "10800"))
AI_MAX_AGE = int(os.getenv("NATIONAL_FORECAST_AI_MAX_AGE", "21600"))
ROADS_TTL = 12 * 3600
DAYS = 7
NET_DAYS = 7                 # days of inflow - release averaged for the projection
FULL_PCT, FULL_WARN_PCT = 100, 95
MEDIUM_FULL_PCT = 100
MEDIUM_STALE_DAYS = 3        # a medium reservoir not reported for this long is left out
RAIN_HEAVY_7D = 150      # mm in 7 days at a province's middle: named as a reason
ROAD_NEAR_M = 1500
ROAD_POINTS = 40             # at most this many gauges / dams are asked about roads, worst first
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
USER_AGENT = "BKKStreetSmart/1.0 (bkksmartstreet.com)"
LEVELS = ("critical", "flood", "watch", "normal")
LABELS = {"critical": "เสี่ยงสูงมาก", "flood": "เสี่ยงสูง", "watch": "เฝ้าระวัง", "normal": "ปกติ"}
NOW_RANK = {"critical": 3, "flood": 2, "watch": 1, "normal": 0}
NOW_BASE = {"critical": 80, "flood": 60, "watch": 40, "normal": 15}   # today's situation alone: the floor of its band
INDEX_LEVELS = (("critical", 80), ("flood", 60), ("watch", 40), ("normal", 0))
CHANCES = ("high", "medium", "low")

RULES = """หลักการ
- ใช้ชื่อสถานที่ และตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งตัวเลขหรือสถานที่
- ตัวเลขคาดการณ์ของเขื่อนคำนวณจากน้ำไหลเข้าลบน้ำที่ปล่อยเฉลี่ย 7 วันล่าสุด ถ้าฝนพยากรณ์มาก น้ำอาจขึ้นเร็วกว่านี้
- ภาษาไทยง่าย ๆ ประโยคสั้น ข้อความล้วน ไม่ใช้ Markdown ไม่ใส่ชื่อฟิลด์ภาษาอังกฤษ"""

WATER_PROMPT = f"""คุณคือนักวิเคราะห์น้ำในเขื่อนระดับประเทศ อ่านข้อมูลเขื่อนและฝนพยากรณ์ 7 วันที่แนบมา แล้วเขียน JSON ตาม schema:
- outlook: ภาพรวมน้ำทั่วประเทศและ 7 วันข้างหน้า 3-5 ประโยค เขื่อนไหนน่าห่วง ภาคไหนฝนมาก
- dams: เขื่อนที่น่าห่วงไม่เกิน 10 แห่ง เขื่อนละ 1-2 ประโยค ว่าอีก 7 วันน้ำจะเป็นอย่างไร และกระทบใคร
{RULES}"""

PROVINCE_PROMPT = f"""คุณคือนักวิเคราะห์น้ำท่วมระดับประเทศ อ่านข้อมูลรายจังหวัดที่แนบมา แล้วคาดการณ์น้ำท่วม 7 วันข้างหน้าเป็น JSON ตาม schema:
- overview: ภาพรวม 3-4 ประโยค จังหวัดไหนท่วมอยู่ จังหวัดไหนจะเสี่ยงขึ้น
- provinces: ทุกจังหวัดในข้อมูล
  risk: critical (เสี่ยงสูงมาก) / flood (เสี่ยงสูง) / watch (เฝ้าระวัง) / normal (ปกติ) ใช้ peak เป็นหลัก ปรับได้ไม่เกิน 1 ขั้นถ้ามีเหตุผล
  outlook: 7 วันข้างหน้า 1-2 ประโยค น้ำมาจากไหน (เขื่อน แม่น้ำ ฝน) จะขึ้นหรือลด
  advice: คำแนะนำประชาชน 1 ประโยค
ข้อมูลแต่ละจังหวัด: now = สถานการณ์วันนี้, days = คะแนนเสี่ยงน้ำท่วมรายวัน 7 วัน (0-100: 80 ขึ้นไป = สูงมาก, 60-79 = สูง, 40-59 = เฝ้าระวัง),
peak = คะแนนสูงสุดใน 7 วัน, why = เหตุผลที่คำนวณไว้,
overflow / high / rising = จุดวัดน้ำล้นตลิ่ง / สูง / กำลังขึ้น, dams = เขื่อนใหญ่ (% วันนี้ และ % ใน 7 วัน),
medium_full = อ่างเก็บน้ำขนาดกลางที่เต็ม, rain7 = ฝนพยากรณ์ 7 วัน (มม.), highways = ทางหลวงน้ำท่วม, reports = คนแจ้งน้ำท่วม
{RULES}"""

ROAD_PROMPT = f"""คุณคือนักวิเคราะห์ถนนน้ำท่วมระดับประเทศ อ่านข้อมูลที่แนบมา แล้วเขียน JSON ตาม schema:
- overview: ภาพรวม 2-3 ประโยค ถนนไหนท่วมอยู่ ถนนไหนควรระวังใน 7 วัน
- roads: ถนนเสี่ยงทุกสายในข้อมูล chance: high / medium / low ว่าจะมีน้ำท่วมใน 7 วันข้างหน้า note: เหตุผล 1 ประโยค
ข้อมูล: flooded = ถนนที่ท่วมอยู่ (กรมทางหลวงแจ้ง), risk_roads = ถนนสายหลักที่อยู่ใกล้จุดน้ำสูง/ล้นตลิ่ง หรือใกล้เขื่อนที่น้ำเกือบเต็ม
(near = อยู่ใกล้อะไร, pct = % ของตลิ่งหรือของเขื่อน, province_risk = ความเสี่ยงจังหวัด 7 วัน)
{RULES}"""

SUMMARY_PROMPT = f"""คุณคือผู้สรุปสถานการณ์น้ำท่วมของประเทศให้ประชาชนอ่าน อ่านตัวเลขและบทวิเคราะห์ที่แนบมา แล้วเขียน JSON ตาม schema:
- headline: 1 ประโยคสั้น บอกว่าตอนนี้น่าห่วงแค่ไหน
- summary: 5-7 ประโยค สรุปน้ำในเขื่อน จังหวัดที่ท่วม ถนนที่ท่วม และ 7 วันข้างหน้า
- actions: สิ่งที่ประชาชนควรทำ 3-5 ข้อ ข้อละ 1 ประโยค
{RULES}"""

WATER_SCHEMA = {
    "type": "object",
    "properties": {
        "outlook": {"type": "string"},
        "dams": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "note": {"type": "string"}},
                                            "required": ["name", "note"], "additionalProperties": False}},
    },
    "required": ["outlook", "dams"], "additionalProperties": False,
}
PROVINCE_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "provinces": {"type": "array", "items": {
            "type": "object",
            "properties": {"province": {"type": "string"}, "risk": {"type": "string", "enum": list(LEVELS)},
                           "outlook": {"type": "string"}, "advice": {"type": "string"}},
            "required": ["province", "risk", "outlook", "advice"], "additionalProperties": False}},
    },
    "required": ["overview", "provinces"], "additionalProperties": False,
}
ROAD_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "roads": {"type": "array", "items": {
            "type": "object",
            "properties": {"road": {"type": "string"}, "province": {"type": "string"},
                           "chance": {"type": "string", "enum": list(CHANCES)}, "note": {"type": "string"}},
            "required": ["road", "province", "chance", "note"], "additionalProperties": False}},
    },
    "required": ["overview", "roads"], "additionalProperties": False,
}
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"headline": {"type": "string"}, "summary": {"type": "string"},
                   "actions": {"type": "array", "items": {"type": "string"}}},
    "required": ["headline", "summary", "actions"], "additionalProperties": False,
}


def _th(block):
    return ((block or {}).get("th") or "").strip() if isinstance(block, dict) else ""


def _province(x):
    geo = (x.get("dam") or {}).get("geocode") or x.get("geocode") or {}
    return thai_regions.normalize(_th(geo.get("province_name")))


def parse_large(rows):
    """dam_daily rows -> the newest row per large dam: {id, name, province, basin, lat, lng, date, storage,
    normal, max, pct, inflow, released}."""
    newest = {}
    for x in rows:
        dam = x.get("dam") or {}
        if dam.get("id") is None or not x.get("dam_date"):
            continue
        if dam["id"] not in newest or x["dam_date"] > newest[dam["id"]]["dam_date"]:
            newest[dam["id"]] = x
    out, names = [], set()
    for x in sorted(newest.values(), key=lambda x: x["dam_date"], reverse=True):
        dam = x["dam"]
        if _th(dam.get("dam_name")) in names:   # a few dams are listed twice, under two ids: keep the newest
            continue
        names.add(_th(dam.get("dam_name")))
        normal = _num(dam.get("normal_storage")) or _num(dam.get("max_storage"))
        storage = _num(x.get("dam_storage"))
        if not normal or storage is None:
            continue
        out.append({"id": dam["id"], "name": _th(dam.get("dam_name")), "province": _province(x),
                    "basin": _th((x.get("basin") or {}).get("basin_name")),
                    "lat": _num(dam.get("dam_lat")), "lng": _num(dam.get("dam_long")), "date": x["dam_date"],
                    "storage": storage, "normal": normal, "max": _num(dam.get("max_storage")),
                    "pct": round(100 * storage / normal, 1),
                    "inflow": _num(x.get("dam_inflow")), "released": _num(x.get("dam_released"))})
    return out


def parse_medium(rows, today=None):
    """dam_medium rows reported in the last MEDIUM_STALE_DAYS days -> [{name, province, pct, storage, lat, lng}]."""
    today = today or date.today()
    cutoff = (today - timedelta(days=MEDIUM_STALE_DAYS)).isoformat()
    out = []
    for x in rows:
        pct = _num(x.get("dam_storage_percent"))
        if pct is None or str(x.get("dam_date") or "") < cutoff:
            continue
        dam = x.get("dam") or {}
        out.append({"name": _th(dam.get("dam_name")), "province": _province(x), "pct": pct,
                    "storage": _num(x.get("dam_storage")), "lat": _num(dam.get("dam_lat")), "lng": _num(dam.get("dam_long"))})
    return out


def _series(graph):
    """dam_yearly_graph reply -> [(date 'YYYY-MM-DD', value)] for the days that have a value."""
    data = (graph or {}).get("data")
    rows = ((data or {}).get("graph_data") or [{}])[0].get("data") or [] if isinstance(data, dict) else []
    return [(r["date"][:10], r["value"]) for r in rows if r.get("value") is not None]


def project(dam, history):
    """Adds net (mcm/day), days[] (pct for day 1..DAYS) and full_day (0 = full today, else the first day
    >= FULL_PCT, else None).
    history: {"dam_inflow": [(date, v)], "dam_released": [(date, v)]}."""
    inflow = dict(history.get("dam_inflow") or [])
    released = dict(history.get("dam_released") or [])
    days = sorted(set(inflow) & set(released))[-NET_DAYS:]
    if days:
        net = sum(inflow[d] - released[d] for d in days) / len(days)
    else:
        net = (dam["inflow"] or 0) - (dam["released"] or 0)
    # A full dam spills or releases more, so storage stops at its maximum (or today's level when already above)
    top = max(dam["max"] or dam["normal"], dam["storage"])
    pcts = [round(100 * min(top, max(0.0, dam["storage"] + net * d)) / dam["normal"], 1) for d in range(1, DAYS + 1)]
    full = 0 if dam["pct"] >= FULL_PCT else next((i + 1 for i, p in enumerate(pcts) if p >= FULL_PCT), None)
    return {**dam, "net": round(net, 2), "net_days": len(days), "days": pcts, "pct_7d": pcts[-1], "full_day": full}


def rain_forecast(points):
    """[(key, lat, lng)] -> {key: [mm day 1..7]} from Open-Meteo daily precipitation_sum, 50 places per request."""
    out = {}
    for i in range(0, len(points), 50):
        chunk = points[i:i + 50]
        q = urllib.parse.urlencode({
            "latitude": ",".join(f"{p[1]:.3f}" for p in chunk), "longitude": ",".join(f"{p[2]:.3f}" for p in chunk),
            "daily": "precipitation_sum", "forecast_days": DAYS, "timezone": "Asia/Bangkok",
        })
        req = urllib.request.Request(f"{OPEN_METEO}?{q}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=40) as resp:
            blocks = json.loads(resp.read().decode("utf-8"))
        if isinstance(blocks, dict):
            blocks = [blocks]
        for p, b in zip(chunk, blocks):
            out[p[0]] = [round(_num(v) or 0.0, 1) for v in ((b.get("daily") or {}).get("precipitation_sum") or [])]
    return out


def province_middles(rain_points):
    """{province: (lat, lng)}: the middle of each province's rain gauges."""
    acc = {}
    for r in rain_points:
        if r.get("province"):
            a = acc.setdefault(r["province"], [0.0, 0.0, 0])
            a[0] += r["lat"]
            a[1] += r["lng"]
            a[2] += 1
    return {p: (a[0] / a[2], a[1] / a[2]) for p, a in acc.items()}


def day_index(p, d, full_basins):
    """Flood risk index 0-100 of province p on day d (1..DAYS): today's situation, its large dams' projected
    storage that day, full medium reservoirs, the rain of the 3 days up to that day, rising rivers (first 3
    days) and a large dam over 100% that day in the basin of one of its high gauges."""
    idx = NOW_BASE.get(p["now"], 15)
    pcts = [x["days"][d - 1] for x in p["dams"]]
    if pcts:
        idx += min(15, max(0, (max(pcts) - 80) * 0.75))
    idx += min(6, 1.5 * p["medium_full"])
    idx += min(20, 0.2 * sum(p["rain7"][max(0, d - 3):d]))
    if d <= 3 and p["counts"].get("rising", 0) >= 2:
        idx += 4
    if p["basins"] & full_basins[d - 1]:
        idx += 6
    return min(100, round(idx))


def level_of(idx):
    return next(lv for lv, floor in INDEX_LEVELS if idx >= floor)


def reasons(p):
    """Short plain-Thai reasons behind a province's 7-day index."""
    why = []
    if any(d["full_day"] == 0 for d in p["dams"]):
        why.append("เขื่อนใหญ่เต็มแล้ว")
    elif any(d["full_day"] for d in p["dams"]):
        why.append("เขื่อนใหญ่จะเต็มใน 7 วัน")
    elif any(d["pct_7d"] >= FULL_WARN_PCT for d in p["dams"]):
        why.append("เขื่อนใหญ่ใกล้เต็ม")
    if p["medium_full"] >= 3:
        why.append(f"อ่างเก็บน้ำกลางเต็ม {p['medium_full']} แห่ง")
    if p["counts"].get("rising", 0) >= 2:
        why.append("น้ำในแม่น้ำกำลังขึ้น")
    rain7 = sum(p["rain7"])
    if rain7 >= RAIN_HEAVY_7D:
        why.append(f"ฝน 7 วัน {round(rain7)} มม.")
    if p["basin_dam_full"]:
        why.append("เขื่อนต้นน้ำในลุ่มน้ำเดียวกันจะเต็ม")
    return why


def build_provinces(today, dams, medium, rain):
    """today: province_flood provinces; dams: projected large dams; medium: medium reservoirs;
    rain: {province: [mm x7]}. Returns provinces with a daily index for the next DAYS days, worst first."""
    # basins with a large dam over 100% on each day
    full_basins = [{x["basin"] for x in dams if x["basin"] and x["days"][d] >= FULL_PCT} for d in range(DAYS)]
    by = {p["province"]: p for p in today}
    names = set(by) | {d["province"] for d in dams if d["province"]} | {m["province"] for m in medium if m["province"]}
    out = []
    for name in names:
        t = by.get(name, {})
        gauges = t.get("gauges") or []
        p = {
            "province": name, "region": thai_regions.region_of(name), "now": t.get("level", "normal"),
            "now_label": t.get("label", "ปกติ"), "now_summary": t.get("summary", ""),
            "counts": t.get("counts") or {}, "center": t.get("center"),
            "dams": [{k: d[k] for k in ("name", "pct", "pct_7d", "full_day", "net", "days")} for d in dams if d["province"] == name],
            "medium_full": sum(m["pct"] >= MEDIUM_FULL_PCT for m in medium if m["province"] == name),
            "medium_count": sum(m["province"] == name for m in medium),
            "rain7": rain.get(name) or [0.0] * DAYS,
            "basins": {g["basin"] for g in gauges if g.get("basin") and g.get("level", 0) >= 4},
            "highways": t.get("highways") or [], "reports": t.get("reports") or [],
        }
        p["basin_dam_full"] = bool(p["basins"] & full_basins[-1])
        p["days"] = []
        for d in range(1, DAYS + 1):
            idx = day_index(p, d, full_basins)
            p["days"].append({"day": d, "date": (date.today() + timedelta(days=d)).isoformat(), "index": idx,
                              "level": level_of(idx), "rain": p["rain7"][d - 1]})
        p["basins"] = sorted(p["basins"])
        p["score"] = max(x["index"] for x in p["days"])
        p["level"] = level_of(p["score"])
        p["label"] = LABELS[p["level"]]
        p["why"] = reasons(p)
        out.append(p)
    out.sort(key=lambda p: (-p["score"], -NOW_RANK.get(p["now"], 0), -p["counts"].get("overflow", 0), p["province"]))
    return out


def _overpass(points):
    """[(key, lat, lng)] -> {key: [{road, ref, kind}]}: main roads within ROAD_NEAR_M of each point."""
    out = {}
    for i in range(0, len(points), 5):
        chunk = points[i:i + 5]
        parts = "".join(f'way["highway"~"^(motorway|trunk|primary)$"](around:{ROAD_NEAR_M},{p[1]:.5f},{p[2]:.5f});' for p in chunk)
        q = urllib.parse.urlencode({"data": f"[out:json][timeout:60];({parts});out tags center;"}).encode()
        ways = None
        for url in OVERPASS:   # the main server often answers 504 when busy: try the other one
            try:
                req = urllib.request.Request(url, data=q, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=90) as resp:
                    ways = json.loads(resp.read().decode("utf-8")).get("elements") or []
                break
            except Exception as e:  # noqa: BLE001 - next server, else this chunk is skipped
                print(f"[NationalForecast] overpass {url.split('/')[2]}: {e}")
        if ways is None:
            continue
        for w in ways:
            c, tags = w.get("center") or {}, w.get("tags") or {}
            if "lat" not in c:
                continue
            key = min(chunk, key=lambda p: (p[1] - c["lat"]) ** 2 + (p[2] - c["lon"]) ** 2)[0]
            road = tags.get("name") or tags.get("name:th") or ""
            ref = tags.get("ref") or ""
            label = f"ทางหลวง {ref}" + (f" ({road})" if road else "") if ref else road
            if label and all(r["road"] != label for r in out.setdefault(key, [])):
                out[key].append({"road": label, "kind": tags.get("highway")})
        time.sleep(2)   # Overpass asks for a pause between requests
    return out


def risk_points(today, dams):
    """Gauges over the bank (or high and rising) and large dams heading over FULL_WARN_PCT, worst first."""
    pts = []
    for p in today:
        for g in p.get("gauges") or []:
            if g.get("level", 0) >= 5 or (g.get("level") == 4 and g.get("trend", 0) > 0):
                where = g["name"] + (f" ({g['river']})" if g.get("river") and g["river"] != g["name"] else "")
                pts.append({"key": f"g:{p['province']}:{g['name']}", "lat": g["lat"], "lng": g["lng"], "province": p["province"],
                            "near": f"จุดวัดน้ำ{where}", "pct": round(g.get("pct") or 0), "kind": "gauge"})
    for d in dams:
        if d["pct_7d"] >= FULL_WARN_PCT and d["lat"] is not None:
            pts.append({"key": f"d:{d['id']}", "lat": d["lat"], "lng": d["lng"], "province": d["province"],
                        "near": f"เขื่อน{d['name']}", "pct": round(d["pct_7d"]), "kind": "dam"})
    pts.sort(key=lambda x: -x["pct"])
    return pts[:ROAD_POINTS]


def _json(text):
    return json.loads(text[text.find("{"):text.rfind("}") + 1])


class NationalForecast:
    def __init__(self, data_dir, province_flood):
        self.path = os.path.join(data_dir, "national_forecast.json")
        self.history_path = os.path.join(data_dir, "cache", "dam_history.json")
        self.province_flood = province_flood
        self.lock = threading.Lock()
        self.data = {}          # dams, medium, provinces, roads, rain_top, updated_at
        self.ai = {}            # water, provinces, roads, summary (+ generated_at, model)
        self.ai_sig, self.ai_error, self.ai_running, self.error = None, None, False, None
        self.roads_cache = {"at": 0, "keys": [], "roads": {}}
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.data, self.ai, self.ai_sig = d.get("data") or {}, d.get("ai") or {}, d.get("ai_sig")
            self.roads_cache = d.get("roads_cache") or self.roads_cache
        except (OSError, ValueError):
            pass

    def _history(self, dams):
        """{dam id: {data_type: [(date, v)]}}, fetched once a day (35 dams x 2 series)."""
        today = date.today().isoformat()
        try:
            with open(self.history_path, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("date") == today:
                return {int(k): v for k, v in cached["dams"].items()}
        except (OSError, ValueError, KeyError):
            pass
        out = {}
        for d in dams:
            out[d["id"]] = {}
            for t in ("dam_inflow", "dam_released"):
                try:
                    out[d["id"]][t] = _series(_ntw_get(f"/analyst/dam_yearly_graph?dam_id={d['id']}&data_type={t}&year={date.today().year}"))
                except Exception as e:  # noqa: BLE001 - that dam falls back to today's inflow - release
                    print(f"[NationalForecast] history {d['name']} {t}: {e}")
                    out[d["id"]][t] = []
        try:
            os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump({"date": today, "dams": out}, f, ensure_ascii=False)
        except OSError as e:
            print(f"[NationalForecast] history save failed: {e}")
        return out

    def _roads(self, today, dams, levels):
        pts = risk_points(today, dams)
        keys = [p["key"] for p in pts]
        cache = self.roads_cache
        if time.time() - cache.get("at", 0) > ROADS_TTL or set(keys) - set(cache.get("keys") or []):
            try:
                found = _overpass([(p["key"], p["lat"], p["lng"]) for p in pts]) if pts else {}
                if found or not pts:   # every chunk failed: keep the last roads and ask again next refresh
                    cache = self.roads_cache = {"at": int(time.time()), "keys": keys, "roads": found}
            except Exception as e:  # noqa: BLE001 - keep the last roads
                print(f"[NationalForecast] overpass: {e}")
        risk, seen = [], set()
        for p in pts:
            for r in (cache.get("roads") or {}).get(p["key"], [])[:3]:
                if (r["road"], p["province"]) in seen:
                    continue
                seen.add((r["road"], p["province"]))
                risk.append({"road": r["road"], "kind": r["kind"], "province": p["province"], "near": p["near"],
                             "pct": p["pct"], "near_kind": p["kind"], "lat": p["lat"], "lng": p["lng"],
                             "province_risk": levels.get(p["province"], "normal")})
        flooded = []
        for p in today:
            for h in p.get("highways") or []:
                flooded.append({"road": h.get("place") or h.get("title") or "", "province": p["province"], "amphoe": h.get("amphoe") or "",
                                "depth_cm": h.get("depth_cm"), "closure": h.get("closure") or "", "lat": h.get("lat"), "lng": h.get("lng"),
                                "ts": h.get("ts")})
        return {"flooded": flooded, "risk": risk}

    def refresh(self):
        report = _ntw_get("/analyst/dam?dam_type=1").get("data") or {}
        large = parse_large(report.get("dam_daily") or [])
        medium = parse_medium(report.get("dam_medium") or [])
        history = self._history(large)
        dams = sorted((project(d, history.get(d["id"], {})) for d in large), key=lambda d: -d["pct_7d"])
        today = self.province_flood.status().get("provinces") or []
        middles = province_middles(self.province_flood.rain_points())
        try:
            rain = rain_forecast([(f"d:{d['id']}", d["lat"], d["lng"]) for d in dams if d["lat"] is not None]
                                 + [(f"p:{p}", lat, lng) for p, (lat, lng) in middles.items()])
        except Exception as e:  # noqa: BLE001 - the dams and provinces still make a picture without rain
            print(f"[NationalForecast] rain forecast: {e}")
            rain = {}
        for d in dams:
            d["rain7"] = rain.get(f"d:{d['id']}") or [0.0] * DAYS
        provinces = build_provinces(today, dams, medium, {k[2:]: v for k, v in rain.items() if k.startswith("p:")})
        roads = self._roads(today, dams, {p["province"]: p["level"] for p in provinces})
        medium_by = {}
        for m in medium:
            s = medium_by.setdefault(m["province"], {"province": m["province"], "count": 0, "full": 0, "over80": 0})
            s["count"] += 1
            s["full"] += m["pct"] >= MEDIUM_FULL_PCT
            s["over80"] += m["pct"] >= 80
        data = {
            "updated_at": int(time.time()), "dams": dams,
            "medium": {"count": len(medium), "full": sum(m["pct"] >= MEDIUM_FULL_PCT for m in medium),
                       "over80": sum(m["pct"] >= 80 for m in medium),
                       "provinces": sorted(medium_by.values(), key=lambda s: (-s["full"], -s["over80"]))[:20],
                       "top": sorted(medium, key=lambda m: -m["pct"])[:20]},
            "provinces": provinces, "roads": roads,
            "counts": {lv: sum(p["level"] == lv for p in provinces) for lv in LEVELS},
            "now_counts": {lv: sum(p["now"] == lv for p in provinces) for lv in LEVELS},
        }
        with self.lock:
            self.data, self.error = data, None
        self._save()
        print(f"[NationalForecast] {len(dams)} large dams, {len(medium)} medium, "
              f"{sum(p['level'] != 'normal' for p in provinces)} provinces at risk, {len(roads['risk'])} risk roads")

    def _ask(self, system, facts, schema, max_tokens):
        prompt = (f"ข้อมูล (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}\n\n"
                  f"เวลาปัจจุบัน {datetime.now().strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\nส่งเป็น JSON ตาม schema เท่านั้น")
        return _json(local_llm.default.chat([{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                            max_tokens=max_tokens, temperature=0.2, json_schema=schema))

    def analyse(self):
        with self.lock:
            d = self.data
        if not d.get("provinces"):
            return
        risky = [p for p in d["provinces"] if p["level"] != "normal" or p["now"] != "normal"][:30]
        sig = json.dumps([[(x["name"], round(x["pct_7d"]), x["full_day"]) for x in d["dams"][:15]],
                          [(p["province"], p["level"], p["score"]) for p in risky],
                          len(d["roads"]["flooded"]), len(d["roads"]["risk"])], ensure_ascii=False)
        age = time.time() - (self.ai.get("generated_at") or 0)
        if sig == self.ai_sig and age < AI_MAX_AGE:
            return
        if not local_llm.default.enabled():
            with self.lock:
                self.ai_error = "ยังไม่ได้ตั้งค่าโมเดล AI (LOCAL_LLM_MODEL)"
            return
        with self.lock:
            self.ai_running = True
        started = time.time()
        try:
            water = self._ask(WATER_PROMPT, {
                "large_dams": [{"name": x["name"], "province": x["province"], "basin": x["basin"], "pct_now": x["pct"],
                                "pct_7d": x["pct_7d"], "full_in_days": x["full_day"],  # 0 = full today "net_mcm_per_day": x["net"],
                                "rain7_mm": round(sum(x["rain7"]))} for x in d["dams"][:20]],
                "large_counts": {"total": len(d["dams"]), "full_now": sum(x["full_day"] == 0 for x in d["dams"]),
                                 "full_in_7d": sum(x["full_day"] is not None and x["full_day"] > 0 for x in d["dams"]),
                                 "over80_now": sum(x["pct"] >= 80 for x in d["dams"])},
                "medium": {k: d["medium"][k] for k in ("count", "full", "over80")},
                "medium_provinces": d["medium"]["provinces"][:10],
                "rain7_top": sorted(({"province": p["province"], "mm": round(sum(p["rain7"]))} for p in d["provinces"]), key=lambda r: -r["mm"])[:10],
            }, WATER_SCHEMA, 3000)
            provinces = self._ask(PROVINCE_PROMPT, [{
                "province": p["province"], "region": p["region"], "now": p["now_label"], "peak": p["score"],
                "days": [x["index"] for x in p["days"]], "why": p["why"],
                "overflow": p["counts"].get("overflow", 0), "high": p["counts"].get("high", 0), "rising": p["counts"].get("rising", 0),
                "dams": [f"{x['name']} {round(x['pct'])}% -> {round(x['pct_7d'])}%" for x in p["dams"]],
                "medium_full": p["medium_full"], "rain7": round(sum(p["rain7"])),
                "highways": len(p["highways"]), "reports": p["counts"].get("reports", 0),
            } for p in risky], PROVINCE_SCHEMA, 8000)
            levels = {x["province"]: x.get("risk") for x in provinces.get("provinces") or []}
            roads = self._ask(ROAD_PROMPT, {
                "flooded": [f"{r['road']} {r['province']}" + (f" น้ำ {r['depth_cm']} ซม." if r["depth_cm"] else "") for r in d["roads"]["flooded"][:30]],
                "risk_roads": [{"road": r["road"], "province": r["province"], "near": r["near"], "pct": r["pct"],
                                "province_risk": levels.get(r["province"]) or r["province_risk"]} for r in d["roads"]["risk"][:40]],
            }, ROAD_SCHEMA, 5000)
            summary = self._ask(SUMMARY_PROMPT, {
                "dams": water.get("outlook"), "provinces": provinces.get("overview"), "roads": roads.get("overview"),
                "counts": {"provinces_7d": d["counts"], "provinces_now": d["now_counts"],
                           "large_dams_full_now": sum(1 for x in d["dams"] if x["full_day"] == 0),
                           "large_dams_full_in_7d": sum(1 for x in d["dams"] if x["full_day"] is not None),
                           "medium_full": d["medium"]["full"], "roads_flooded": len(d["roads"]["flooded"]),
                           "roads_at_risk": len(d["roads"]["risk"])},
            }, SUMMARY_SCHEMA, 2000)
        except Exception as e:  # noqa: BLE001 - model down or bad JSON: keep the last report
            with self.lock:
                self.ai_error, self.ai_running = f"{local_llm.default.model}: {str(e)[:160]}", False
            print(f"[NationalForecast] model failed: {e}")
            return
        known = {p["province"] for p in risky}
        ai = {
            "water": {"outlook": water.get("outlook") or "", "dams": {x["name"]: x["note"] for x in water.get("dams") or [] if x.get("name")}},
            "provinces": {"overview": provinces.get("overview") or "",
                          "items": {x["province"]: {k: x.get(k) or "" for k in ("risk", "outlook", "advice")}
                                    for x in provinces.get("provinces") or [] if x.get("province") in known}},
            "roads": {"overview": roads.get("overview") or "",
                      "items": {f"{x['road']}|{x['province']}": {"chance": x.get("chance") or "low", "note": x.get("note") or ""}
                                for x in roads.get("roads") or [] if x.get("road")}},
            "summary": {"headline": summary.get("headline") or "", "summary": summary.get("summary") or "",
                        "actions": [a for a in summary.get("actions") or [] if a][:5]},
            "model": local_llm.default.model, "generated_at": int(time.time()), "took_s": round(time.time() - started, 1),
        }
        with self.lock:
            self.ai, self.ai_sig, self.ai_error, self.ai_running = ai, sig, None, False
        self._save()

    def _save(self):
        with self.lock:
            data = {"data": self.data, "ai": self.ai, "ai_sig": self.ai_sig, "roads_cache": self.roads_cache}
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(self.path + ".tmp", self.path)
        except OSError as e:
            print(f"[NationalForecast] save failed: {e}")

    def status(self):
        with self.lock:
            return {**self.data, "ai": self.ai, "ai_error": self.ai_error, "ai_running": self.ai_running,
                    "error": self.error, "interval_s": REFRESH_SECONDS, "days": DAYS}

    def _loop(self):
        time.sleep(180)   # let province_flood make its first picture
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001 - keep the last good answer
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[NationalForecast] refresh failed: {e}")
            try:
                self.analyse()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[NationalForecast] analysis failed: {e}")
            time.sleep(REFRESH_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="NationalForecast").start()
