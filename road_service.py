"""
Per-road flooding outlook for Bangkok and the five surrounding provinces.

Four live measurements already exist in this server, each of them incomplete on its own:

    traffic_service   every named road with its live flow, red kilometres and a centre point
    flood_service     ~250 sensors reading centimetres of water ON the road - Bangkok only
    water_service     ~180 rain gauges (24 h millimetres) and ~70 river / canal gauges
                      (% of bank capacity) across all six provinces

This module joins them by position: each road takes the flood sensors that sit on it (by name, or
within NEAR_FLOOD_KM of its centre), the nearest rain gauge within NEAR_RAIN_KM and the nearest
river or canal gauge within NEAR_GAUGE_KM. That is also what makes the provinces usable: they have
no road sensors, so a road in Nonthaburi is judged from the rain that fell on it and the canal next
to it, and the row says as much.

There is no invented scoring here. Every reading is put into the class its own authority publishes,
and the road takes the class of what was actually measured on it:

    water on the road   สำนักการระบายน้ำ กทม. for the sensor itself (<=5 / 5-10 / >10 cm) and
                        กรมป้องกันและบรรเทาสาธารณภัย for what a driver can do at that depth
                        (<20 passable, 20-40 short distances only, 60-80 high-clearance vehicles,
                        >80 do not drive through)
    rain in 24 h        กรมอุตุนิยมวิทยา: 0.1-10 light, 10.1-35 moderate, 35.1-90 heavy,
                        >=90.1 very heavy
    canal / river       คลังข้อมูลน้ำแห่งชาติ: >=100% of bank = over the bank, 80-99% = high

A road with its own sensor takes the road-water class directly, because that is a measurement of
the road. A road without one cannot be said to be flooded at all, so it is only ever raised to
"watch": its rain and canal classes are halved and capped there, and the row is marked
`measured: false`. Every class and the exact number behind it stay on the row.

Gemini writes the short Thai read of the top roads, at most once every AI_INTERVAL and only when
the picture changed; without a key a deterministic template says the same things from the numbers.
Served by /api/roads/*.
"""
import json
import math
import os
import threading
import time

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - the template covers the no-key case
    genai = None
    genai_types = None

AI_MODEL = os.getenv("ROAD_AI_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
AI_INTERVAL = int(os.getenv("ROAD_AI_SECONDS", "600"))
BUILD_INTERVAL = 120.0
MIN_ROAD_KM = 0.8            # shorter named pieces are junctions and service roads, not routes
NEAR_FLOOD_KM = 0.8          # a road sensor this close counts as being on the road
NEAR_RAIN_KM = 9.0           # metro rain gauges are sparse; beyond this the reading says nothing
NEAR_GAUGE_KM = 5.0
FLOOD_PROVINCE_KM = 1.5   # a road sensor further than this does not decide the road's province
TOP_AI = 8

# ---------------------------------------------------------------- published classifications
# Depth of water on the road. 0-2 are the thresholds the BMA drainage department draws its own map
# with; 3-4 are the driving advice of the Department of Disaster Prevention and Mitigation.
# (ปภ. states <20, 20-40, 60-80 and >80; 40-60 is not published separately and is kept with 20-40.)
ROAD_WATER_BANDS = (
    (5.0, 0, "ปกติ", "สนน. กทม.: ไม่เกิน 5 ซม."),
    (10.0, 1, "น้ำท่วมเล็กน้อย", "สนน. กทม.: 5-10 ซม."),
    (20.0, 2, "น้ำท่วม รถผ่านได้", "สนน. กทม.: เกิน 10 ซม. · ปภ.: ต่ำกว่า 20 ซม. รถยังผ่านได้"),
    (60.0, 3, "ควรเลี่ยงเส้นทาง", "ปภ.: 20-40 ซม. ผ่านได้ระยะสั้น ควรเลี่ยง"),
    (None, 4, "ห้ามขับผ่าน", "ปภ.: 60-80 ซม. เฉพาะรถยกสูง · เกิน 80 ซม. ห้ามผ่านเด็ดขาด"),
)
# 24 h rainfall, กรมอุตุนิยมวิทยา (tmd.go.th "เกณฑ์ปริมาณฝน")
RAIN_BANDS = (
    (0.1, 0, "ไม่มีฝน", "กรมอุตุฯ: ต่ำกว่า 0.1 มม."),
    (10.0, 1, "ฝนเล็กน้อย", "กรมอุตุฯ: 0.1-10.0 มม."),
    (35.0, 2, "ฝนปานกลาง", "กรมอุตุฯ: 10.1-35.0 มม."),
    (90.0, 3, "ฝนหนัก", "กรมอุตุฯ: 35.1-90.0 มม."),
    (None, 4, "ฝนหนักมาก", "กรมอุตุฯ: 90.1 มม. ขึ้นไป"),
)
# Water body against its bank, คลังข้อมูลน้ำแห่งชาติ / ThaiWater
GAUGE_BANDS = (
    (80.0, 0, "ปกติ", "คลังข้อมูลน้ำฯ: ต่ำกว่า 80% ของตลิ่ง"),
    (100.0, 2, "น้ำมาก", "คลังข้อมูลน้ำฯ: 80-99% ของตลิ่ง"),
    (None, 4, "ล้นตลิ่ง", "คลังข้อมูลน้ำฯ: 100% ของตลิ่งขึ้นไป"),
)

LEVEL_ORDER = ("none", "watch", "passable", "avoid", "closed")
LEVEL_TH = {
    "none": "ปกติ",
    "watch": "เฝ้าระวัง",
    "passable": "น้ำท่วม รถผ่านได้",
    "avoid": "ควรเลี่ยงเส้นทาง",
    "closed": "ห้ามขับผ่าน",
}
INFERRED_MAX = 1   # a road with no sensor of its own can never be called flooded, only "watch"


def _km(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111.0
    dlon = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def _norm(name):
    """Road names arrive from three sources with different prefixes; compare them stripped."""
    s = (name or "").strip()
    for p in ("ถนน", "ถ.", "ซอย", "ซ.", "ทางหลวงหมายเลข", "ทล."):
        if s.startswith(p):
            s = s[len(p):]
    return s.replace(" ", "").lower()


def _classify(value, bands):
    """(class, label, the published rule it came from) for one reading, or a zero class when unknown."""
    if value is None:
        return None, None, None
    for ceiling, cls, label, source in bands:
        if ceiling is None or value <= ceiling:
            return cls, label, source
    return bands[-1][1], bands[-1][2], bands[-1][3]


class RoadRisk:
    def __init__(self, traffic=None, flood=None, water=None):
        """traffic: traffic_service.traffic · flood: flood_service.flood_roads · water: water_service module."""
        self.traffic = traffic
        self.flood = flood
        self.water = water
        self.lock = threading.Lock()
        self.items = []
        self.updated_at = None
        self.error = None
        self.analysis = None
        self._ai_sig, self._ai_at, self._ai_client = None, 0.0, None
        self.thread = threading.Thread(target=self._loop, daemon=True, name="road-risk")

    def start(self):
        self.thread.start()

    # ------------------------------------------------------------ inputs
    def _rain(self):
        try:
            return [r for r in (self.water.rain_stations() if self.water else []) if r.get("lat") and r.get("lng")]
        except Exception:  # noqa: BLE001
            return []

    def _gauges(self):
        try:
            s = self.water.get_summary() if self.water else {}
        except Exception:  # noqa: BLE001
            return []
        out = []
        for key, kind in (("river", "river"), ("canals", "canal")):
            for g in s.get(key) or []:
                if g.get("lat") and g.get("lng"):
                    out.append({**g, "kind": kind})
        return out

    def _flood_points(self):
        try:
            with self.flood.lock:
                items = list(self.flood.items)
        except Exception:  # noqa: BLE001
            return []
        return [i for i in items if i.get("lat") and i.get("lng") and i.get("status") != "offline"]

    # ------------------------------------------------------------ build
    def build(self):
        roads = [r for r in (self.traffic.get_roads(limit=4000) if self.traffic else [])
                 if r.get("lat") and r.get("lng") and (r.get("length_km") or 0) >= MIN_ROAD_KM]
        rain = self._rain()
        gauges = self._gauges()
        floods = self._flood_points()
        by_name = {}
        for f in floods:
            by_name.setdefault(_norm(f.get("road")), []).append(f)

        out = []
        for r in roads:
            lat, lng = r["lat"], r["lng"]
            anchors = [(lat, lng)] + [(h["lat"], h["lon"]) for h in (r.get("hotspots") or [])]

            # sensors on this road: by name first, then anything close to the road's own points
            on_road = list(by_name.get(_norm(r["name"]), []))
            seen = {f["code"] for f in on_road}
            for f in floods:
                if f["code"] in seen:
                    continue
                if min(_km(a[0], a[1], f["lat"], f["lng"]) for a in anchors) <= NEAR_FLOOD_KM:
                    on_road.append(f)
                    seen.add(f["code"])
            wet = [f for f in on_road if f["status"] in ("flood", "slight")]
            flood_cm = max((f["level_cm"] or 0) for f in on_road) if on_road else None
            worst = max(on_road, key=lambda f: f["level_cm"] or 0) if on_road else None

            near_rain = min(rain, key=lambda s: _km(lat, lng, s["lat"], s["lng"])) if rain else None
            rain_km = _km(lat, lng, near_rain["lat"], near_rain["lng"]) if near_rain else None
            if rain_km is None or rain_km > NEAR_RAIN_KM:
                near_rain, rain_km = None, None

            near_gauge = min(gauges, key=lambda g: _km(lat, lng, g["lat"], g["lng"])) if gauges else None
            gauge_km = _km(lat, lng, near_gauge["lat"], near_gauge["lng"]) if near_gauge else None
            if gauge_km is None or gauge_km > NEAR_GAUGE_KM:
                near_gauge, gauge_km = None, None

            rain_mm = near_rain["rain_24h"] if near_rain else None
            gauge_pct = near_gauge["storage_pct"] if near_gauge else None
            red_pct = r.get("red_pct") or 0

            water_cls, water_label, water_src = _classify(flood_cm, ROAD_WATER_BANDS)
            rain_cls, rain_label, rain_src = _classify(rain_mm, RAIN_BANDS)
            gauge_cls, gauge_label, gauge_src = _classify(gauge_pct, GAUGE_BANDS)

            # Rain and the canal beside the road are circumstantial: halved and capped at "watch",
            # they can flag a road but never declare it flooded.
            around = max(rain_cls or 0, gauge_cls or 0)
            inferred = min(INFERRED_MAX, around // 2)
            measured = water_cls or 0
            # The higher of the two wins. A sensor reading zero does not clear the whole road -
            # it measures one point of it - so heavy rain around it still raises the row to watch.
            cls = max(measured, inferred)
            if on_road and measured >= inferred:
                basis = "sensor"
            elif on_road and inferred > 0:
                basis = "both"
            else:
                basis = "inferred" if inferred else ("sensor" if on_road else "none")
            level = LEVEL_ORDER[cls]

            # Province: the nearest reference point of any kind wins. The road sensors are dense
            # inside Bangkok, so a Bangkok road resolves to Bangkok even when the closest canal
            # gauge happens to sit across the provincial line.
            province, district = None, (worst or {}).get("district")
            refs = []
            if on_road:
                refs.append((0.0, "กรุงเทพมหานคร", district))
            # A road sensor only names the province when it is genuinely next to the road. The
            # sensors are Bangkok-only and dense, so a loose radius would pull every long road
            # that reaches into a province back into Bangkok.
            nearest_flood = min(floods, key=lambda f: _km(lat, lng, f["lat"], f["lng"])) if floods else None
            if nearest_flood:
                d = _km(lat, lng, nearest_flood["lat"], nearest_flood["lng"])
                if d <= FLOOD_PROVINCE_KM:
                    refs.append((d, "กรุงเทพมหานคร", nearest_flood.get("district")))
            if near_rain:
                refs.append((rain_km, near_rain.get("province"), near_rain.get("district")))
            if near_gauge:
                refs.append((gauge_km, near_gauge.get("province"), near_gauge.get("district")))
            if refs:
                _, province, near_district = min(refs, key=lambda x: x[0])
                district = district or near_district

            out.append({
                "road": r["name"],
                "lat": lat, "lng": lng,
                "province": province,
                "district": district,
                "length_km": r.get("length_km"),
                # traffic
                "flow": r.get("flow"), "red_pct": red_pct, "red_km": r.get("red_km"), "traffic_level": r.get("level"),
                # water on the road (Bangkok sensors only)
                "measured": bool(on_road),
                "sensors": len(on_road), "wet_sensors": len(wet),
                "flood_cm": flood_cm,
                "flood_at": (worst or {}).get("short_name"),
                "flood_status": (worst or {}).get("status"),
                "flood_trend": (worst or {}).get("trend"),
                "flood_started": (worst or {}).get("started"),
                # rain that fell on it
                "rain_24h": rain_mm,
                "rain_at": (near_rain or {}).get("name"),
                "rain_km": round(rain_km, 1) if rain_km else None,
                "rain_level": (near_rain or {}).get("level"),
                # the water body next to it
                "gauge_pct": gauge_pct,
                "gauge_at": (near_gauge or {}).get("name"),
                "gauge_kind": (near_gauge or {}).get("kind"),
                "gauge_level": (near_gauge or {}).get("level"),
                "gauge_km": round(gauge_km, 1) if gauge_km else None,
                "water_class": water_cls, "water_label": water_label, "water_source": water_src,
                "rain_class": rain_cls, "rain_label": rain_label, "rain_source": rain_src,
                "gauge_class": gauge_cls, "gauge_label": gauge_label, "gauge_source": gauge_src,
                "basis": basis,
                "class": cls,
                "level": level,
                "level_th": LEVEL_TH[level],
            })
        out.sort(key=lambda x: (-x["class"], -(x["flood_cm"] or 0), -(x["rain_24h"] or 0),
                                -(x["gauge_pct"] or 0), x["road"]))
        return out

    # ------------------------------------------------------------ AI read
    def _client(self):
        if self._ai_client is not None:
            return self._ai_client
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if genai is None or not key:
            return None
        try:
            self._ai_client = genai.Client(api_key=key)
        except Exception:  # noqa: BLE001
            return None
        return self._ai_client

    @staticmethod
    def _template(top, counts):
        if not top:
            return {"headline": "ยังไม่มีถนนสายใดเข้าเกณฑ์เฝ้าระวังน้ำท่วมขัง",
                    "detail": f"ประเมิน {counts['total']} สาย จากฝน 24 ชม. ระดับน้ำคลอง/แม่น้ำ และเซ็นเซอร์บนผิวถนน",
                    "roads": [], "source": "template"}
        first = top[0]
        return {
            "headline": f"{first['road']}: {first['level_th']} ({first['water_label'] or first['rain_label'] or '-'})",
            "detail": (f"ห้ามขับผ่าน {counts['closed']} สาย · ควรเลี่ยง {counts['avoid']} สาย · "
                       f"ท่วมแต่ผ่านได้ {counts['passable']} สาย · เฝ้าระวัง {counts['watch']} สาย "
                       f"จากทั้งหมด {counts['total']} สาย"),
            "roads": [{"road": t["road"],
                       "why": " · ".join(x for x in [
                           f"น้ำบนถนน {t['flood_cm']} ซม." if t.get("flood_cm") else None,
                           f"ฝน 24 ชม. {t['rain_24h']} มม." if t.get("rain_24h") else None,
                           f"{t['gauge_at']} {t['gauge_pct']}% ของตลิ่ง" if t.get("gauge_pct") else None,
                           f"{t['gauge_label']}" if t.get("gauge_label") and (t.get("gauge_class") or 0) > 0 else None,
                       ] if x) or "ไม่มีข้อมูลเด่น",
                       "advice": ""} for t in top[:5]],
            "source": "template",
        }

    def _analyse(self, items, force=False):
        counts = {"total": len(items)}
        for k in LEVEL_ORDER:
            counts[k] = sum(1 for i in items if i["level"] == k)
        top = [i for i in items if i["class"] > 0][:TOP_AI]
        sig = json.dumps([(t["road"], t["level"]) for t in top], ensure_ascii=False)
        now = time.time()
        base = self._template(top, counts)
        if not force and sig == self._ai_sig and self.analysis and now - self._ai_at < AI_INTERVAL:
            return self.analysis
        client = self._client()
        if client is None or not top:
            with self.lock:
                self.analysis = {**base, "counts": counts, "updated_at": int(now)}
            self._ai_sig, self._ai_at = sig, now
            return self.analysis
        facts = [{"road": t["road"], "province": t["province"], "district": t["district"],
                  "level": t["level_th"], "basis": t["basis"],
                  "flood_cm": t["flood_cm"], "flood_at": t["flood_at"], "flood_trend": t["flood_trend"],
                  "has_road_sensor": t["measured"],
                  "rain_24h_mm": t["rain_24h"], "rain_station": t["rain_at"], "rain_station_km": t["rain_km"],
                  "gauge_pct_of_bank": t["gauge_pct"], "gauge_name": t["gauge_at"], "gauge_km": t["gauge_km"],
                  "traffic_red_pct": t["red_pct"], "traffic_level": t["traffic_level"]} for t in top]
        prompt = (
            "คุณคือนักวิเคราะห์ความเสี่ยงน้ำท่วมขังรายถนนของศูนย์ควบคุมจราจรกรุงเทพมหานครและปริมณฑล\n"
            "ข้อมูลแต่ละสายมาจากสามแหล่งที่วัดคนละอย่าง:\n"
            "- flood_cm = ความลึกของน้ำบนผิวถนนจากเซ็นเซอร์ หน่วยเซนติเมตร มีเฉพาะในเขต กทม. "
            "ถ้า has_road_sensor เป็น false แปลว่าถนนสายนั้นไม่มีเซ็นเซอร์วัดน้ำบนถนน ห้ามสรุปว่าถนนนั้นท่วมหรือไม่ท่วม\n"
            "- rain_24h_mm = ฝนสะสม 24 ชม. ของสถานีวัดฝนที่ใกล้ที่สุด ห่าง rain_station_km กิโลเมตร\n"
            "- gauge_pct_of_bank = ระดับน้ำในคลอง/แม่น้ำที่ใกล้ที่สุด คิดเป็น % ของความจุตลิ่ง เกิน 100 คือล้นตลิ่ง\n"
            "- traffic_red_pct = สัดส่วนระยะทางที่รถติดตอนนี้\n"
            "- level = ระดับตามเกณฑ์ทางการ (สนน. กทม. + ปภ. สำหรับน้ำบนถนน, กรมอุตุฯ สำหรับฝน, "
            "คลังข้อมูลน้ำแห่งชาติ สำหรับระดับตลิ่ง) · basis = sensor คือวัดบนถนนจริง, "
            "inferred คือประเมินจากฝน/ระดับน้ำรอบข้างเท่านั้น\n"
            "เขียนภาษาไทยจากตัวเลขที่ให้เท่านั้น ห้ามแต่งชื่อถนน ตัวเลข หรือพยากรณ์ฝนที่ไม่มีในข้อมูล\n"
            "ตอบเป็น JSON object เท่านั้น:\n"
            '{"headline":"<1 ประโยค ภาพรวมว่าสายไหนน่าห่วงที่สุดและเพราะอะไร ไม่เกิน 30 คำ>",'
            '"detail":"<1-2 ประโยค บอกว่าความเสี่ยงกระจุกอยู่โซนไหน และแยกให้ชัดว่าสายไหนวัดน้ำบนถนนได้จริง สายไหนประเมินจากฝน/ระดับคลองเท่านั้น>",'
            '"roads":[{"road":"<ชื่อถนนตามข้อมูล>","why":"<เหตุผลจากตัวเลขจริง ไม่เกิน 20 คำ>",'
            '"advice":"<สิ่งที่ผู้ใช้รถควรทำกับถนนสายนี้ ไม่เกิน 15 คำ>"}]}\n'
            "roads ไม่เกิน 6 สาย เรียงจากเสี่ยงมากไปน้อย\n\n"
            + json.dumps(facts, ensure_ascii=False)
        )
        out = dict(base)
        try:
            resp = client.models.generate_content(
                model=AI_MODEL, contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.2, max_output_tokens=1500,
                                                         response_mime_type="application/json"))
            d = json.loads(resp.text or "{}")
            if isinstance(d, dict) and d.get("headline"):
                out = {
                    "headline": str(d["headline"]).strip(),
                    "detail": str(d.get("detail") or "").strip(),
                    "roads": [{"road": str(x.get("road") or "").strip(), "why": str(x.get("why") or "").strip(),
                               "advice": str(x.get("advice") or "").strip()}
                              for x in (d.get("roads") or []) if isinstance(x, dict) and x.get("road")][:6],
                    "source": AI_MODEL,
                }
        except Exception as e:  # noqa: BLE001
            print(f"[Roads] Gemini failed, using template: {str(e)[:140]}")
        with self.lock:
            self.analysis = {**out, "counts": counts, "updated_at": int(now)}
        self._ai_sig, self._ai_at = sig, now
        return self.analysis

    # ------------------------------------------------------------ loop
    def refresh(self):
        items = self.build()
        with self.lock:
            self.items = items
            self.updated_at = int(time.time())
            self.error = None
        self._analyse(items)
        return len(items)

    def _loop(self):
        time.sleep(30)     # let traffic_service and the water caches fill first
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[Roads] build failed: {e}")
            time.sleep(BUILD_INTERVAL)

    # ------------------------------------------------------------ api
    def status(self, level=None, province=None, q=None, measured=None, limit=200):
        with self.lock:
            items = list(self.items)
            updated, error, analysis = self.updated_at, self.error, self.analysis
        if level:
            items = [i for i in items if i["level"] == level]
        if province:
            items = [i for i in items if (i.get("province") or "") == province]
        if measured is not None:
            items = [i for i in items if i["measured"] is measured]
        if q:
            qq = q.strip().lower()
            items = [i for i in items if qq in i["road"].lower() or qq in (i.get("district") or "").lower()]
        counts = {k: 0 for k in LEVEL_TH}
        provinces = {}
        with self.lock:
            for i in self.items:
                counts[i["level"]] += 1
                p = i.get("province")
                if p:
                    d = provinces.setdefault(p, {"province": p, "roads": 0, "flooded": 0, "watch": 0, "max_class": 0})
                    d["roads"] += 1
                    if i["class"] >= 2:
                        d["flooded"] += 1
                    elif i["class"] == 1:
                        d["watch"] += 1
                    d["max_class"] = max(d["max_class"], i["class"])
        return {
            "updated_at": updated, "error": error, "total": len(self.items), "counts": counts,
            "level_th": LEVEL_TH,
            "provinces": sorted(provinces.values(), key=lambda p: (-p["max_class"], -p["flooded"], -p["watch"])),
            "analysis": analysis,
            "items": items[:limit],
            "note": ("ระดับตามเกณฑ์ทางการ: น้ำบนผิวถนนใช้เกณฑ์สำนักการระบายน้ำ กทม. (5/10 ซม.) "
                     "ร่วมกับคำแนะนำการขับขี่ของ ปภ. (20/60/80 ซม.) · ฝน 24 ชม. ใช้เกณฑ์กรมอุตุนิยมวิทยา "
                     "(10/35/90 มม.) · ระดับคลองและแม่น้ำใช้เกณฑ์คลังข้อมูลน้ำแห่งชาติ (80%/100% ของตลิ่ง) · "
                     "ถนนที่ไม่มีเซ็นเซอร์วัดน้ำบนผิวถนนจะไม่ถูกระบุว่าท่วม แต่ขึ้นได้สูงสุดแค่ 'เฝ้าระวัง' "
                     "จากฝนและระดับน้ำรอบข้าง"),
            "standards": {
                "water": [{"upto_cm": b[0], "class": b[1], "label": b[2], "source": b[3]} for b in ROAD_WATER_BANDS],
                "rain": [{"upto_mm": b[0], "class": b[1], "label": b[2], "source": b[3]} for b in RAIN_BANDS],
                "gauge": [{"upto_pct": b[0], "class": b[1], "label": b[2], "source": b[3]} for b in GAUGE_BANDS],
            },
        }


road_risk = RoadRisk()
