"""
Flood situation in every province, for the "น้ำท่วมรายจังหวัด" tab of the Water page.

Every REFRESH_SECONDS it reads the national snapshot of the Thai Water portal (api-v3.thaiwater.net
/public/thailand, no key, refreshed by HII every hour): about 800 river gauges with their level as a share of
the bank (situation_level 5 = over the bank, 4 = high) and about 4,600 rain gauges. With the Department of
Highways' open flood tickets on highways (flood_feeds.hdms_floods, every province) and the floods people
report (the reports callable server.py passes: Longdo Traffic in every province, this site's own report
form, Traffy Fondue in Bangkok), each province gets:

    level   critical / flood / watch / normal  (see _level)
    counts  gauges over the bank, high, rising; flooded highways; heavy-rain gauges; people's reports
    points  the gauges over the bank or high, the flooded highways and the reports, for the map
    summary one line built from the numbers, always there

A report is placed in the province its text names, else in the province of the nearest gauge.

The AI model (local_llm.default, LOCAL_LLM_* in .env) then writes an overview and, for each province that is
not normal, a short analysis and advice, as JSON by REPORT_SCHEMA. It runs again only when the picture changed
(the signature of the levels and counts) or the report is older than AI_MAX_AGE. Without the model the page
shows the built summaries only.

The Department of Disaster Prevention's daily list of affected households has no open API and is not read.
"""
import json
import os
import re
import threading
import time
from datetime import datetime

from backend.core import local_llm, thai_regions
from backend.water.flood_feeds import hdms_floods
from backend.water.water_service import _ntw_get, _num, _ts

REFRESH_SECONDS = int(os.getenv("PROVINCE_FLOOD_SECONDS", "1800"))
AI_MAX_AGE = int(os.getenv("PROVINCE_FLOOD_AI_MAX_AGE", "3600"))
AI_PROVINCES = 30            # at most this many provinces go to the model, worst first
STALE_HOURS = 24             # a gauge that has not reported for this long is left out
RISING_M = 0.02              # water up this much since the previous reading counts as rising
HEAVY_MM, EXTREME_MM = 35, 90
REPORTS_FLOOD = 5            # this many reports from people make a province at least "flood" (one: "watch")
LEVELS = ("critical", "flood", "watch", "normal")
LABELS = {"critical": "วิกฤต", "flood": "น้ำล้นตลิ่ง/ท่วม", "watch": "เฝ้าระวัง", "normal": "ปกติ"}
RANK = {lv: i for i, lv in enumerate(LEVELS)}
STATION_CODE = re.compile(r"\s*\([A-Z0-9.\-]+\)")   # "วัดท่าเจดีย์ (TTC06)" -> "วัดท่าเจดีย์"

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์สถานการณ์น้ำท่วมระดับประเทศ (ศูนย์ปฏิบัติการ BKK StreetSmart)
อ่านข้อมูลสดรายจังหวัดที่แนบมา แล้วเขียนเป็น JSON ตาม schema:
- overview: ภาพรวมทั้งประเทศ 3-5 ประโยค ภาคไหนหนัก น้ำกำลังขึ้นหรือลด ควรจับตาที่ไหนต่อ
- provinces: ทุกจังหวัดในข้อมูล จังหวัดละ 1 รายการ
  summary: สถานการณ์ตอนนี้ 1-2 ประโยค
  analysis: วิเคราะห์ 2-3 ประโยค ว่าน้ำมาจากไหน (แม่น้ำสายไหนล้น ฝนตกหนักที่ไหน) และมีแนวโน้มเป็นอย่างไร
  advice: คำแนะนำประชาชนในจังหวัดนั้น 1-2 ประโยค

ข้อมูลแต่ละจังหวัด: level (critical วิกฤต / flood น้ำล้นตลิ่ง / watch เฝ้าระวัง), overflow = จุดวัดน้ำที่ล้นตลิ่ง,
high = จุดวัดน้ำสูง, rising = จุดที่น้ำกำลังขึ้น, gauges = จุดวัดสำคัญ (แม่น้ำ, % ของตลิ่ง, แนวโน้ม),
rain = ฝนสะสม 24 ชม. สูงสุดในจังหวัด, heavy_rain = จำนวนจุดที่ฝนเกิน 35 มม., highways = ทางหลวงที่น้ำท่วมตอนนี้,
reports = จำนวนเรื่องที่ประชาชนแจ้งว่าน้ำท่วม (ยังไม่ได้ยืนยัน), report_places = ตัวอย่างที่แจ้ง

หลักการ
- ใช้ชื่อสถานที่ แม่น้ำ และตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งตัวเลข จำนวนผู้ประสบภัย หรือสถานที่
- % ของตลิ่ง: เกิน 100 = ล้นตลิ่ง ใช้คำนี้แทนตัวเลขเมื่อทำได้
- ภาษาไทยง่าย ๆ กระชับ ข้อความล้วน ไม่ใช้ Markdown ไม่ใส่รหัสสถานี ไม่ใส่ชื่อฟิลด์ภาษาอังกฤษ"""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "provinces": {"type": "array", "items": {
            "type": "object",
            "properties": {"province": {"type": "string"}, "summary": {"type": "string"},
                           "analysis": {"type": "string"}, "advice": {"type": "string"}},
            "required": ["province", "summary", "analysis", "advice"], "additionalProperties": False}},
    },
    "required": ["overview", "provinces"],
    "additionalProperties": False,
}


def _name(block, key="th"):
    return ((block or {}).get(key) or "").strip() if isinstance(block, dict) else ""


def _rows(snapshot, block):
    return ((snapshot.get(block) or {}).get("data") or {}).get("data") or []


def parse_gauges(rows, now=None):
    """Thai Water river gauges -> [{province, amphoe, name, river, lat, lng, pct, level, trend, ts, station_id, msl,
    bank, basin}], fresh ones only. bank is the lower bank (min_bank, else the lower of left and right)."""
    now = now or time.time()
    out = []
    for x in rows:
        geo, st = x.get("geocode") or {}, x.get("station") or {}
        province = thai_regions.normalize(_name(geo.get("province_name")))
        ts = _ts(x.get("waterlevel_datetime"))
        lat, lng = _num(st.get("tele_station_lat")), _num(st.get("tele_station_long"))
        if not province or not ts or now - ts > STALE_HOURS * 3600 or lat is None or lng is None:
            continue
        msl, prev = _num(x.get("waterlevel_msl")), _num(x.get("waterlevel_msl_previous"))
        banks = [b for b in (_num(st.get("left_bank")), _num(st.get("right_bank"))) if b is not None]
        bank = _num(st.get("min_bank")) or (min(banks) if banks else None)
        trend = 0 if msl is None or prev is None else (1 if msl - prev >= RISING_M else -1 if prev - msl >= RISING_M else 0)
        out.append({
            "province": province, "amphoe": _name(geo.get("amphoe_name")),
            "name": STATION_CODE.sub("", _name(st.get("tele_station_name"))), "river": (x.get("river_name") or "").strip(),
            "lat": lat, "lng": lng, "pct": _num(x.get("storage_percent")),
            "level": int(x.get("situation_level") or 0), "trend": trend, "ts": ts,
            "station_id": st.get("id"), "msl": msl, "bank": bank, "basin": _name((x.get("basin") or {}).get("basin_name")),
        })
    return out


def parse_rain_points(rows, now=None):
    """Thai Water rain gauges -> [{name, province, amphoe, lat, lng, rain_24h, rain_1h, ts}] for the water map,
    readings of the last STALE_HOURS only."""
    now = now or time.time()
    out = []
    for x in rows:
        geo, st = x.get("geocode") or {}, x.get("station") or {}
        mm, ts = _num(x.get("rain_24h")), _ts(x.get("rainfall_datetime"))
        lat, lng = _num(st.get("tele_station_lat")), _num(st.get("tele_station_long"))
        if mm is None or lat is None or lng is None or not ts or now - ts > STALE_HOURS * 3600:
            continue
        out.append({"name": STATION_CODE.sub("", _name(st.get("tele_station_name"))),
                    "province": thai_regions.normalize(_name(geo.get("province_name"))), "amphoe": _name(geo.get("amphoe_name")),
                    "lat": lat, "lng": lng, "rain_24h": mm, "rain_1h": _num(x.get("rain_1h")), "ts": ts})
    return out


def parse_dams(rows):
    """Thai Water large dams (35, the Royal Irrigation Department's daily report) for the water map."""
    out = []
    for x in rows:
        dam = x.get("dam") or {}
        lat, lng = _num(dam.get("dam_lat")), _num(dam.get("dam_long"))
        if lat is None or lng is None:
            continue
        out.append({"name": _name(dam.get("dam_name")), "date": x.get("dam_date"), "lat": lat, "lng": lng,
                    "storage": _num(x.get("dam_storage")), "max_storage": _num(dam.get("max_storage")),
                    "storage_pct": _num(x.get("dam_storage_percent")), "inflow": _num(x.get("dam_inflow")),
                    "released": _num(x.get("dam_released"))})
    return out


def parse_rain(rows):
    """Thai Water rain gauges -> province -> {max_mm, place, heavy, extreme}."""
    out = {}
    for x in rows:
        province = thai_regions.normalize(_name((x.get("geocode") or {}).get("province_name")))
        mm = _num(x.get("rain_24h"))
        if not province or mm is None:
            continue
        r = out.setdefault(province, {"max_mm": 0, "place": "", "heavy": 0, "extreme": 0})
        if mm > r["max_mm"]:
            r["max_mm"], r["place"] = mm, _name((x.get("station") or {}).get("tele_station_name"))
        r["heavy"] += mm >= HEAVY_MM
        r["extreme"] += mm >= EXTREME_MM
    return out


def _level(overflow, rising_over, high, highways, rain, reports=0):
    if overflow >= 3 or rising_over >= 1 or highways >= 3:
        return "critical"
    if overflow or highways or reports >= REPORTS_FLOOD:
        return "flood"
    if high or rain.get("extreme") or rain.get("heavy", 0) >= 3 or reports:
        return "watch"
    return "normal"


def _anchors(snapshot):
    """(lat, lng, province) of every river and rain gauge, to place a report by its nearest one."""
    out = []
    for block in ("waterlevel", "rain"):
        for x in _rows(snapshot, block):
            st = x.get("station") or {}
            province = thai_regions.normalize(_name((x.get("geocode") or {}).get("province_name")))
            lat, lng = _num(st.get("tele_station_lat")), _num(st.get("tele_station_long"))
            if province and lat is not None and lng is not None:
                out.append((lat, lng, province))
    return out


def place_report(r, anchors):
    """Province of a report: the one its text names, else the one of the nearest gauge."""
    named = thai_regions.find_in_text(f"{r.get('title') or ''} {r.get('text') or ''}")
    if named:
        return named
    lat, lng = r.get("lat"), r.get("lng")
    if lat is None or lng is None or not anchors:
        return ""
    return min(anchors, key=lambda a: (a[0] - lat) ** 2 + (a[1] - lng) ** 2)[2]


def _summary(p):
    parts = []
    c = p["counts"]
    if c["overflow"]:
        top = p["gauges"][0]
        where = f"{top['river']} ที่ {top['name']}" if top["river"] and top["river"] != top["name"] else top["name"]
        parts.append(f"น้ำล้นตลิ่ง {c['overflow']} จุด (มากสุด {where})")
    if c["high"]:
        parts.append(f"น้ำสูงใกล้ตลิ่ง {c['high']} จุด")
    if c["rising"]:
        parts.append(f"น้ำกำลังขึ้น {c['rising']} จุด")
    if c["highways"]:
        parts.append(f"ทางหลวงน้ำท่วม {c['highways']} จุด")
    if c["reports"]:
        parts.append(f"คนแจ้งน้ำท่วม {c['reports']} เรื่อง")
    if p["rain"]["max_mm"] >= HEAVY_MM:
        parts.append(f"ฝน 24 ชม. สูงสุด {round(p['rain']['max_mm'])} มม. ที่ {p['rain']['place']}")
    return " · ".join(parts) or "ระดับน้ำปกติ"


def build(snapshot, highways, reports=(), now=None):
    """Per-province picture from the Thai Water snapshot, the open HDMS flood tickets and people's flood
    reports, worst first."""
    gauges = parse_gauges(_rows(snapshot, "waterlevel"), now)
    rain = parse_rain(_rows(snapshot, "rain"))
    by = {}

    def slot(province):
        return by.setdefault(province, {"gauges": [], "highways": [], "reports": []})

    for g in gauges:
        slot(g["province"])["gauges"].append(g)
    for h in highways:
        province = thai_regions.normalize(h.get("province"))
        if province and h.get("active"):
            slot(province)["highways"].append(h)
    anchors = _anchors(snapshot) if reports else []
    for r in reports:
        province = place_report(r, anchors)
        if province:
            slot(province)["reports"].append(r)
    provinces = []
    for name in set(by) | set(rain):
        g = by.get(name, {}).get("gauges", [])
        hw = by.get(name, {}).get("highways", [])
        rep = sorted(by.get(name, {}).get("reports", []), key=lambda x: -(x.get("ts") or 0))
        over = [x for x in g if x["level"] >= 5]
        high = [x for x in g if x["level"] == 4]
        r = rain.get(name, {"max_mm": 0, "place": "", "heavy": 0, "extreme": 0})
        level = _level(len(over), sum(x["trend"] > 0 for x in over), len(high), len(hw), r, len(rep))
        watch = sorted(over + high, key=lambda x: -(x["pct"] or 0))
        pts = watch or g
        p = {
            "province": name, "region": thai_regions.region_of(name), "level": level, "label": LABELS[level],
            "counts": {"gauges": len(g), "overflow": len(over), "high": len(high),
                       "rising": sum(x["trend"] > 0 for x in over + high), "highways": len(hw),
                       "heavy_rain": r["heavy"], "reports": len(rep)},
            "rain": r,
            "gauges": watch[:12],
            "highways": [{k: h.get(k) for k in ("title", "place", "amphoe", "depth_cm", "closure", "ts", "lat", "lng")} for h in hw[:12]],
            "reports": [{k: x.get(k) for k in ("source", "title", "text", "depth", "ts", "lat", "lng")} for x in rep[:12]],
            "center": [round(sum(x["lng"] for x in pts) / len(pts), 4), round(sum(x["lat"] for x in pts) / len(pts), 4)] if pts else None,
        }
        p["summary"] = _summary(p)
        provinces.append(p)
    provinces.sort(key=lambda p: (RANK[p["level"]], -p["counts"]["overflow"], -p["counts"]["highways"],
                                  -p["counts"]["reports"], -p["counts"]["high"], -p["rain"]["max_mm"]))
    return provinces


def _facts(provinces):
    """Compact facts for the model: the provinces that are not normal, worst first."""
    out = []
    for p in provinces:
        if p["level"] == "normal" or len(out) >= AI_PROVINCES:
            continue
        out.append({
            "province": p["province"], "region": p["region"], "level": p["level"],
            "overflow": p["counts"]["overflow"], "high": p["counts"]["high"], "rising": p["counts"]["rising"],
            "gauges": [{"place": f"{g['name']} อ.{g['amphoe']}".strip(), "river": g["river"], "pct": g["pct"],
                        "trend": {1: "ขึ้น", -1: "ลด", 0: "ทรงตัว"}[g["trend"]]} for g in p["gauges"][:4]],
            "rain_mm": round(p["rain"]["max_mm"]), "rain_place": p["rain"]["place"], "heavy_rain": p["rain"]["heavy"],
            "highways": [f"{h['place']} {h['depth_cm'] or ''}".strip() for h in p["highways"][:3]],
            "reports": p["counts"]["reports"], "report_places": [x["title"] for x in p["reports"][:3]],
        })
    return out


class ProvinceFlood:
    def __init__(self, data_dir, reports=None):
        self.path = os.path.join(data_dir, "province_flood.json")
        self.reports = reports or (lambda: [])   # people's flood reports: [{source, title, text, depth, ts, lat, lng}]
        self.lock = threading.Lock()
        self.provinces, self.updated_at, self.error = [], None, None
        self.ai, self.ai_sig, self.ai_error, self.ai_running = None, None, None, False
        self.anchors = []      # (lat, lng, province) of every gauge, from the last refresh, for place()
        self.all_gauges = []   # every fresh river gauge in the country, for the water map
        self.all_rain = []     # every rain gauge with a reading in the last STALE_HOURS
        self.all_dams = []     # the 35 large dams
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.provinces, self.updated_at = d.get("provinces") or [], d.get("updated_at")
            self.all_gauges = d.get("all_gauges") or []
            self.all_rain, self.all_dams = d.get("all_rain") or [], d.get("all_dams") or []
            self.ai, self.ai_sig = d.get("ai"), d.get("ai_sig")
        except (OSError, ValueError):
            pass

    def refresh(self):
        try:
            reports = list(self.reports())
        except Exception as e:  # noqa: BLE001 - the gauges still make a picture without them
            print(f"[ProvinceFlood] reports: {e}")
            reports = []
        snapshot = _ntw_get("/public/thailand")
        provinces = build(snapshot, hdms_floods.national(), reports)
        anchors = _anchors(snapshot)
        all_gauges = parse_gauges(_rows(snapshot, "waterlevel"))
        all_rain, all_dams = parse_rain_points(_rows(snapshot, "rain")), parse_dams(_rows(snapshot, "dam"))
        with self.lock:
            self.provinces, self.updated_at, self.error, self.anchors = provinces, int(time.time()), None, anchors
            self.all_gauges, self.all_rain, self.all_dams = all_gauges, all_rain, all_dams
        self._save()
        print(f"[ProvinceFlood] {sum(p['level'] != 'normal' for p in provinces)} of {len(provinces)} provinces not normal")

    def analyse(self):
        with self.lock:
            facts = _facts(self.provinces)
        sig = json.dumps([(f["province"], f["level"], f["overflow"], f["high"], f["rising"], len(f["highways"]), f["reports"]) for f in facts],
                         ensure_ascii=False)
        age = time.time() - ((self.ai or {}).get("generated_at") or 0)
        if not facts or (sig == self.ai_sig and age < AI_MAX_AGE):
            return
        if not local_llm.default.enabled():
            with self.lock:
                self.ai_error = "ยังไม่ได้ตั้งค่าโมเดล AI (LOCAL_LLM_MODEL)"
            return
        with self.lock:
            self.ai_running = True
        started = time.time()
        prompt = (f"ข้อมูลน้ำรายจังหวัด (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}\n\n"
                  f"เวลาปัจจุบัน {datetime.now().strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\nส่งเป็น JSON ตาม schema เท่านั้น")
        try:
            text = local_llm.default.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                                          max_tokens=6000, temperature=0.2, json_schema=REPORT_SCHEMA)
            report = json.loads(text[text.find("{"):text.rfind("}") + 1])
        except Exception as e:  # noqa: BLE001 - model down or bad JSON: keep the last report
            with self.lock:
                self.ai_error, self.ai_running = f"{local_llm.default.model}: {str(e)[:160]}", False
            print(f"[ProvinceFlood] model failed: {e}")
            return
        known = {f["province"] for f in facts}
        report = {"overview": report.get("overview") or "",
                  "provinces": {p["province"]: {k: p.get(k) or "" for k in ("summary", "analysis", "advice")}
                                for p in report.get("provinces") or [] if p.get("province") in known},
                  "model": local_llm.default.model, "generated_at": int(time.time()), "took_s": round(time.time() - started, 1)}
        with self.lock:
            self.ai, self.ai_sig, self.ai_error, self.ai_running = report, sig, None, False
        self._save()

    def _save(self):
        with self.lock:
            data = {"provinces": self.provinces, "updated_at": self.updated_at, "ai": self.ai, "ai_sig": self.ai_sig,
                    "all_gauges": self.all_gauges, "all_rain": self.all_rain, "all_dams": self.all_dams}
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(self.path + ".tmp", self.path)
        except OSError as e:
            print(f"[ProvinceFlood] save failed: {e}")

    def gauges(self):
        """Every fresh river gauge in the country from the last refresh (see parse_gauges)."""
        with self.lock:
            return list(self.all_gauges)

    def rain_points(self):
        with self.lock:
            return list(self.all_rain)

    def dams(self):
        with self.lock:
            return list(self.all_dams)

    def place(self, title, text, lat, lng):
        """Province of a report (see place_report), or "" before the first refresh."""
        with self.lock:
            anchors = self.anchors
        return place_report({"title": title, "text": text, "lat": lat, "lng": lng}, anchors)

    def status(self):
        with self.lock:
            return {"updated_at": self.updated_at, "error": self.error, "provinces": self.provinces,
                    "counts": {lv: sum(p["level"] == lv for p in self.provinces) for lv in LEVELS},
                    "ai": self.ai, "ai_error": self.ai_error, "ai_running": self.ai_running,
                    "interval_s": REFRESH_SECONDS}

    def _loop(self):
        time.sleep(60)    # let the HDMS poller fill its first answer
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001 - keep the last good answer
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[ProvinceFlood] refresh failed: {e}")
            try:
                self.analyse()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[ProvinceFlood] analysis failed: {e}")
            time.sleep(REFRESH_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="ProvinceFlood").start()
