"""
Flood risk in each of Bangkok's 50 districts, for the "เขตเสี่ยงน้ำท่วมในกรุงเทพมหานคร" tab of the Water page.

Every REFRESH_SECONDS, per district:
    canals   the canal gauges in it (ThaiWater / BMA through water_service.get_map): how many, how many over or
             near the bank, the fullest one (% of the bank) and whether the water is rising
    main     its ThaiWater gauges (the Chao Phraya and the main canals: kind "river" in water_service) against
             the bank, and for riverside districts north_route's Nonthaburi-Bangkok outlook (HII's 7-day level
             forecast at สะพานนวลฉวี against the bank)
    roads    the BMA road water sensors in it with water on the road (flood_service.flood_roads), deepest first
    rain     the highest 24 h rain at its rain gauges, and Open-Meteo's forecast for the next 24 h and 3 days at
             the middle of the district (config/thailand_districts.geojson)
    reports  flood reports from Traffy Fondue in the last hours
and a score 0-100 from those (see score()) with the reasons: 60+ เสี่ยงสูง, 35-59 ปานกลาง, 15-34 เฝ้าระวัง.

The Qwen model behind LOCAL_LLM_* (local_llm.default) then reads every district's figures and writes an
overview and, for each district, one or two plain sentences on how much water there is and where it is going.
It runs again only when the picture changed or the report is older than AI_MAX_AGE; without it the page shows
the computed figures and reasons.

Served by /api/flood/bkk-districts.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from backend.agents.flood_agent import ZONE_DISTRICTS
from backend.core import local_llm
from backend.core.instance import BASE_DIR
from backend.water.water_service import OPEN_METEO, _num

REFRESH_SECONDS = int(os.getenv("BKK_DISTRICTS_SECONDS", "1800"))
RAIN_TTL = 3 * 3600          # Open-Meteo for 50 places: about 400 location-calls a day at this rate
AI_MAX_AGE = int(os.getenv("BKK_DISTRICTS_AI_MAX_AGE", "10800"))
REPORT_HOURS = 12
GEO_FILE = os.path.join(BASE_DIR, "config", "thailand_districts.geojson")
USER_AGENT = "BKKStreetSmart/1.0 (bkksmartstreet.com)"
ZONE_OF = {d: z for z, ds in ZONE_DISTRICTS.items() for d in ds.split()}
DISTRICTS = list(ZONE_OF)
RIVERSIDE = {"บางซื่อ", "ดุสิต", "พระนคร", "สัมพันธวงศ์", "บางรัก", "สาทร", "ยานนาวา", "บางคอแหลม", "คลองเตย",
             "บางพลัด", "บางกอกน้อย", "บางกอกใหญ่", "ธนบุรี", "คลองสาน", "ราษฎร์บูรณะ", "ทุ่งครุ"}
FAULTY_PCT = 200            # a canal reading above this share of its bank is a sensor fault, not water
LEVELS = (("high", 60, "เสี่ยงสูง"), ("medium", 35, "ปานกลาง"), ("watch", 15, "เฝ้าระวัง"), ("normal", 0, "ปกติ"))

PROMPT = """คุณคือนักวิเคราะห์น้ำท่วมของกรุงเทพมหานคร อ่านข้อมูลน้ำรายเขตที่แนบมา แล้วเขียน JSON ตาม schema:
- overview: ภาพรวมทั้งกรุงเทพฯ 3-4 ประโยค เขตไหนน่าห่วง น้ำในคลองและแม่น้ำเป็นอย่างไร ฝนจะตกเพิ่มไหม
- districts: ทุกเขตในข้อมูล summary: 1-2 ประโยค บอกปริมาณน้ำในเขตนั้น (คลองเต็มกี่ % แม่น้ำห่างตลิ่งเท่าไร น้ำบนถนน ฝน)
  และแนวโน้มว่าจะขึ้นหรือลด advice: คำแนะนำ 1 ประโยคสั้น (เขตปกติให้เว้นว่างได้)
ข้อมูลแต่ละเขต: score = คะแนนเสี่ยงที่คำนวณไว้ (60 ขึ้นไป สูง, 35-59 ปานกลาง, 15-34 เฝ้าระวัง), canals = คลอง (จำนวนจุดวัด, ล้นตลิ่ง, ใกล้ล้น,
คลองที่เต็มที่สุดกี่ %, กำลังขึ้นกี่จุด), main = จุดวัดน้ำหลักที่ใกล้ตลิ่งที่สุด (ต่ำกว่าตลิ่งกี่ เมตร ติดลบ = ล้น), road_cm = น้ำบนถนนลึกสุด,
rain24 = ฝน 24 ชม. ที่ตกแล้ว, rain_next24 / rain_3d = ฝนพยากรณ์, reports = คนแจ้งน้ำท่วมผ่าน Traffy
หลักการ
- ใช้ชื่อสถานที่ และตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งตัวเลขหรือสถานที่
- ภาษาไทยง่าย ๆ ประโยคสั้น ข้อความล้วน ไม่ใช้ Markdown ไม่ใส่ชื่อฟิลด์ภาษาอังกฤษ"""

SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "districts": {"type": "array", "items": {
            "type": "object", "properties": {"district": {"type": "string", "enum": DISTRICTS},
                                             "summary": {"type": "string"}, "advice": {"type": "string"}},
            "required": ["district", "summary", "advice"], "additionalProperties": False}},
    },
    "required": ["overview", "districts"], "additionalProperties": False,
}


def middles():
    """{district: (lat, lng)}: the middle of each Bangkok district's outline."""
    with open(GEO_FILE, encoding="utf-8") as f:
        feats = json.load(f)["features"]
    out = {}
    for ft in feats:
        p = ft["properties"]
        name = (p.get("amp_th") or "").removeprefix("เขต")
        if p.get("pro_code") != "10" or name not in ZONE_OF:
            continue
        g = ft["geometry"]
        ring = g["coordinates"][0] if g["type"] == "Polygon" else max((poly[0] for poly in g["coordinates"]), key=len)
        out[name] = (sum(c[1] for c in ring) / len(ring), sum(c[0] for c in ring) / len(ring))
    return out


def rain_forecast(points):
    """{district: (next 24 h mm, next 3 days mm)} from Open-Meteo, one request for every district."""
    names = list(points)
    q = urllib.parse.urlencode({
        "latitude": ",".join(f"{points[n][0]:.3f}" for n in names), "longitude": ",".join(f"{points[n][1]:.3f}" for n in names),
        "hourly": "precipitation", "forecast_days": 4, "timezone": "Asia/Bangkok",
    })
    req = urllib.request.Request(f"{OPEN_METEO}?{q}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        blocks = json.loads(resp.read().decode("utf-8"))
    if isinstance(blocks, dict):
        blocks = [blocks]
    now_h = datetime.now().strftime("%Y-%m-%dT%H:00")
    out = {}
    for n, b in zip(names, blocks):
        h = b.get("hourly") or {}
        times, mm = h.get("time") or [], h.get("precipitation") or []
        start = next((i for i, t in enumerate(times) if t >= now_h), 0)
        out[n] = (round(sum(_num(v) or 0 for v in mm[start:start + 24]), 1), round(sum(_num(v) or 0 for v in mm[start:start + 72]), 1))
    return out


def score(d):
    """Risk score 0-100 of a district and its reasons, from its own water and rain."""
    s, why = 0, []
    c = d["canals"]
    if c["overflow"]:
        s += min(35, 15 * c["overflow"])
        why.append(f"คลองล้นตลิ่ง {c['overflow']} จุด")
    if c["high"]:
        s += min(15, 5 * c["high"])
        why.append(f"คลองใกล้ล้น {c['high']} จุด")
    if c["rising"] >= 2 and (c["overflow"] or c["high"]):
        s += 5
        why.append("น้ำในคลองกำลังขึ้น")
    r = d["river"]
    if r["below_bank"] is not None:
        if r["below_bank"] <= 0:
            s += 25
            why.append(f"{r['closest']} สูงกว่าตลิ่ง {-r['below_bank']:.2f} ม.")
        elif r["below_bank"] <= 0.3:
            s += 15
            why.append(f"{r['closest']} ต่ำกว่าตลิ่งเพียง {r['below_bank']:.2f} ม.")
    if r.get("outlook_over"):
        s += 10
        why.append("คาดว่าแม่น้ำเจ้าพระยาจะสูงกว่าตลิ่งใน 7 วัน")
    if d["road_cm"]:
        s += 25 if d["road_cm"] >= 20 else 15 if d["road_cm"] >= 10 else 5
        why.append(f"น้ำบนถนน {d['road_cm']:.0f} ซม.")
    if d["rain24"] >= 35:
        s += 15 if d["rain24"] >= 90 else 8
        why.append(f"ฝน 24 ชม. {d['rain24']:.0f} มม.")
    if d["rain_next24"] >= 35:
        s += 15 if d["rain_next24"] >= 70 else 8
        why.append(f"คาดฝน 24 ชม. ข้างหน้า {d['rain_next24']:.0f} มม.")
    if d["reports"] >= 3:
        s += 10 if d["reports"] >= 8 else 5
        why.append(f"คนแจ้งน้ำท่วม {d['reports']} เรื่อง")
    return min(100, s), why


def level_of(s):
    return next((k, label) for k, floor, label in LEVELS if s >= floor)


def build(water, roads, rain, reports, forecast, river_outlook):
    """Every district's figures, worst first. water: water_service.get_map()["water"]; roads: flood_roads wet
    sensors; rain: rain gauges; reports: Traffy items; forecast: {district: (24 h, 3 d)}; river_outlook:
    north_route's Nonthaburi-Bangkok days or []."""
    now = time.time()
    over_bank_7d = any(x.get("below_bank", 99) <= 0 for x in river_outlook[1:])
    out = []
    for name in DISTRICTS:
        gs = [w for w in water if w.get("province") == "กรุงเทพมหานคร" and w.get("district") == name and w.get("status") != "offline"
              and (w.get("storage_pct") or 0) <= FAULTY_PCT]
        canals = [w for w in gs if w["kind"] == "canal"]
        rivers = [w for w in gs if w["kind"] == "river"]
        full = max(canals, key=lambda w: w.get("storage_pct") or 0, default=None)
        wet = sorted((x for x in roads if x.get("district") == name and (x.get("level_cm") or 0) > 0), key=lambda x: -(x.get("level_cm") or 0))
        rmm = [r.get("rain_24h") or 0 for r in rain if r.get("province") == "กรุงเทพมหานคร" and r.get("district") == name]
        closest = min((w for w in rivers if w.get("diff_bank") is not None), key=lambda w: w["diff_bank"], default=None)
        d = {
            "district": name, "zone": ZONE_OF[name], "riverside": name in RIVERSIDE,
            "canals": {"count": len(canals), "overflow": sum(w["status"] == "overflow" for w in canals),
                       "high": sum(w["status"] == "high" for w in canals),
                       "rising": sum((w.get("trend") or 0) > 0 for w in canals),
                       "fullest": {"name": full["name"], "pct": full.get("storage_pct")} if full and full.get("storage_pct") is not None else None,
                       "top": [{"name": w["name"], "pct": w.get("storage_pct"), "status": w["status"], "trend": w.get("trend")}
                               for w in sorted(canals, key=lambda w: -(w.get("storage_pct") or 0))[:4]]},
            "river": {"gauges": [{"name": w["name"], "below_bank": w.get("diff_bank")} for w in rivers],
                      "below_bank": closest["diff_bank"] if closest else None, "closest": closest["name"] if closest else None,
                      "outlook_over": name in RIVERSIDE and over_bank_7d},
            "road_cm": wet[0]["level_cm"] if wet else 0,
            "roads": [{"name": x.get("short_name") or x.get("name"), "cm": x.get("level_cm")} for x in wet[:4]],
            "rain24": max(rmm, default=0), "rain_next24": (forecast.get(name) or (0, 0))[0], "rain_3d": (forecast.get(name) or (0, 0))[1],
            "reports": sum(1 for r in reports if r.get("district") == name and now - (r.get("ts") or 0) <= REPORT_HOURS * 3600),
        }
        d["score"], d["why"] = score(d)
        d["level"], d["label"] = level_of(d["score"])
        out.append(d)
    out.sort(key=lambda d: (-d["score"], d["district"]))
    return out


class BkkDistricts:
    def __init__(self, data_dir, sources):
        """sources: callables water() -> get_map(), roads() -> flood_roads.status(), rain() -> rain gauges,
        reports() -> Traffy items, river() -> north_route Nonthaburi-Bangkok days."""
        self.path = os.path.join(data_dir, "bkk_districts.json")
        self.sources = sources
        self.lock = threading.Lock()
        self.data, self.ai, self.ai_sig, self.ai_error, self.ai_running, self.error = {}, {}, None, None, False, None
        self.forecast, self.forecast_at = {}, 0
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.data, self.ai, self.ai_sig = d.get("data") or {}, d.get("ai") or {}, d.get("ai_sig")
            self.forecast, self.forecast_at = d.get("forecast") or {}, d.get("forecast_at") or 0
        except (OSError, ValueError):
            pass

    def _get(self, name, default):
        try:
            return self.sources[name]() or default
        except Exception as e:  # noqa: BLE001 - one source down leaves the others
            print(f"[BkkDistricts] {name}: {e}")
            return default

    def refresh(self):
        if time.time() - self.forecast_at > RAIN_TTL:
            try:
                self.forecast, self.forecast_at = rain_forecast(middles()), time.time()
            except Exception as e:  # noqa: BLE001 - the observed rain still counts
                print(f"[BkkDistricts] rain forecast: {e}")
        water = (self._get("water", {}) or {}).get("water") or []
        roads = (self._get("roads", {}) or {}).get("wet") or []
        rows = build(water, roads, self._get("rain", []), self._get("reports", []), self.forecast, self._get("river", []))
        data = {"updated_at": int(time.time()), "districts": rows,
                "counts": {k: sum(d["level"] == k for d in rows) for k, _, _ in LEVELS},
                "totals": {"canals": sum(d["canals"]["count"] for d in rows), "canal_overflow": sum(d["canals"]["overflow"] for d in rows),
                           "canal_high": sum(d["canals"]["high"] for d in rows), "roads_wet": sum(len(d["roads"]) for d in rows),
                           "rain24_max": max((d["rain24"] for d in rows), default=0),
                           "rain_next24_max": max((d["rain_next24"] for d in rows), default=0)},
                "zones": list(ZONE_DISTRICTS)}
        with self.lock:
            self.data, self.error = data, None
        self._save()
        print(f"[BkkDistricts] {sum(d['level'] != 'normal' for d in rows)} of 50 districts above normal")

    def analyse(self):
        with self.lock:
            d = self.data
        if not d.get("districts"):
            return
        sig = json.dumps([(x["district"], x["level"]) for x in d["districts"] if x["level"] != "normal"], ensure_ascii=False)
        if sig == self.ai_sig and time.time() - (self.ai.get("generated_at") or 0) < AI_MAX_AGE:
            return
        if not local_llm.default.enabled():
            with self.lock:
                self.ai_error = "ยังไม่ได้ตั้งค่าโมเดล AI (LOCAL_LLM_MODEL)"
            return
        facts = [{
            "district": x["district"], "zone": x["zone"], "score": x["score"], "why": x["why"],
            "canals": {k: x["canals"][k] for k in ("count", "overflow", "high", "rising")}
                      | {"fullest": f"{x['canals']['fullest']['name']} {round(x['canals']['fullest']['pct'])}%" if x["canals"]["fullest"] else None},
            "main": f"{x['river']['closest']} {x['river']['below_bank']:+.2f} ม." if x["river"]["closest"] else None,
            "chao_phraya_over_in_7d": x["river"]["outlook_over"] or None,
            "road_cm": x["road_cm"] or None, "rain24": x["rain24"] or None, "rain_next24": x["rain_next24"] or None,
            "rain_3d": x["rain_3d"] or None, "reports": x["reports"] or None,
        } for x in d["districts"]]
        with self.lock:
            self.ai_running = True
        started = time.time()
        prompt = (f"ข้อมูลน้ำรายเขต (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}\n\n"
                  f"เวลาปัจจุบัน {datetime.now().strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\nส่งเป็น JSON ตาม schema เท่านั้น")
        try:
            text = local_llm.default.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": prompt}],
                                          max_tokens=9000, temperature=0.2, json_schema=SCHEMA)
            r = json.loads(text[text.find("{"):text.rfind("}") + 1])
        except Exception as e:  # noqa: BLE001 - model down or bad JSON: keep the last report
            with self.lock:
                self.ai_error, self.ai_running = f"{local_llm.default.model}: {str(e)[:160]}", False
            print(f"[BkkDistricts] model failed: {e}")
            return
        ai = {"overview": r.get("overview") or "",
              "districts": {x["district"]: {"summary": x.get("summary") or "", "advice": x.get("advice") or ""}
                            for x in r.get("districts") or [] if x.get("district") in ZONE_OF},
              "model": local_llm.default.model, "generated_at": int(time.time()), "took_s": round(time.time() - started, 1)}
        with self.lock:
            self.ai, self.ai_sig, self.ai_error, self.ai_running = ai, sig, None, False
        self._save()

    def _save(self):
        with self.lock:
            data = {"data": self.data, "ai": self.ai, "ai_sig": self.ai_sig, "forecast": self.forecast, "forecast_at": self.forecast_at}
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(self.path + ".tmp", self.path)
        except OSError as e:
            print(f"[BkkDistricts] save failed: {e}")

    def status(self):
        with self.lock:
            return {**self.data, "ai": self.ai, "ai_error": self.ai_error, "ai_running": self.ai_running,
                    "error": self.error, "interval_s": REFRESH_SECONDS}

    def _loop(self):
        time.sleep(120)   # let the water map and the road sensors make their first answers
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001 - keep the last good answer
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[BkkDistricts] refresh failed: {e}")
            try:
                self.analyse()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[BkkDistricts] analysis failed: {e}")
            time.sleep(REFRESH_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="BkkDistricts").start()
