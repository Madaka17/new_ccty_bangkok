"""
Per-road flooding outlook for Bangkok and the five surrounding provinces.

Four live measurements already exist in this server, each of them incomplete on its own:

    traffic_service   every named road with its live flow, red kilometres and a centre point
    flood_service     ~250 sensors reading centimetres of water ON the road - Bangkok only
    water_service     ~180 rain gauges (24 h millimetres) and ~70 river / canal gauges
                      (% of bank capacity) across all six provinces

This module joins them by position: each road takes the flood sensors that sit on it (by name, or
within NEAR_FLOOD_KM of its centre), the nearest rain gauge within NEAR_RAIN_KM and the nearest
river or canal gauge within NEAR_GAUGE_KM, and gets a 0-100 risk score from what they say. That is
also what makes the provinces usable: they have no road sensors, so a road in Nonthaburi is judged
from the rain that fell on it and the canal next to it, and the row says as much.

A risk score is a ranking aid, not a measurement. The parts that make it up are kept on every row
(flood_cm, rain_24h, gauge_pct, red_pct) so a person can see why a road is where it is, and rows
built without a road sensor are marked `measured: false`.

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

# Risk weights. Water measured on the road dominates; rain and canal level are the only signals
# the provinces have, so they have to be able to raise a row on their own.
W_FLOOD, W_RAIN, W_GAUGE, W_TRAFFIC = 55.0, 25.0, 15.0, 5.0
FLOOD_FULL_CM = 25.0         # cm that scores the whole flood weight
RAIN_FULL_MM = 80.0          # mm in 24 h that scores the whole rain weight
LEVELS = (("high", 60), ("medium", 35), ("low", 15), ("none", 0))
LEVEL_TH = {"high": "เสี่ยงสูง", "medium": "เฝ้าระวัง", "low": "เสี่ยงต่ำ", "none": "ปกติ"}


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


def _level(score):
    for key, floor in LEVELS:
        if score >= floor:
            return key
    return "none"


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

            score = 0.0
            if flood_cm:
                score += W_FLOOD * min(1.0, flood_cm / FLOOD_FULL_CM)
            if rain_mm:
                score += W_RAIN * min(1.0, rain_mm / RAIN_FULL_MM)
            if gauge_pct:
                score += W_GAUGE * min(1.0, max(0.0, (gauge_pct - 70.0) / 40.0))
            score += W_TRAFFIC * min(1.0, red_pct / 100.0)
            score = round(min(100.0, score), 1)

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
                "score": score,
                "level": _level(score),
                "level_th": LEVEL_TH[_level(score)],
            })
        out.sort(key=lambda x: (-x["score"], -(x["flood_cm"] or 0), x["road"]))
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
        if not top or top[0]["score"] < 15:
            return {"headline": "ยังไม่มีถนนสายใดเข้าเกณฑ์เฝ้าระวังน้ำท่วมขัง",
                    "detail": f"ประเมิน {counts['total']} สาย จากฝน 24 ชม. ระดับน้ำคลอง/แม่น้ำ และเซ็นเซอร์บนผิวถนน",
                    "roads": [], "source": "template"}
        first = top[0]
        return {
            "headline": f"{first['road']} เสี่ยงที่สุดขณะนี้ (คะแนน {first['score']})",
            "detail": f"เสี่ยงสูง {counts['high']} สาย · เฝ้าระวัง {counts['medium']} สาย จากทั้งหมด {counts['total']} สาย",
            "roads": [{"road": t["road"],
                       "why": " · ".join(x for x in [
                           f"น้ำบนถนน {t['flood_cm']} ซม." if t.get("flood_cm") else None,
                           f"ฝน 24 ชม. {t['rain_24h']} มม." if t.get("rain_24h") else None,
                           f"{t['gauge_at']} {t['gauge_pct']}% ของตลิ่ง" if t.get("gauge_pct") else None,
                           f"เส้นทางติดขัด {t['red_pct']}%" if (t.get("red_pct") or 0) >= 40 else None,
                       ] if x) or "ไม่มีข้อมูลเด่น",
                       "advice": ""} for t in top[:5]],
            "source": "template",
        }

    def _analyse(self, items, force=False):
        counts = {"total": len(items)}
        for k in ("high", "medium", "low", "none"):
            counts[k] = sum(1 for i in items if i["level"] == k)
        top = [i for i in items if i["score"] >= 15][:TOP_AI]
        sig = json.dumps([(t["road"], t["level"], round(t["score"])) for t in top], ensure_ascii=False)
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
        facts = [{"road": t["road"], "province": t["province"], "district": t["district"], "score": t["score"],
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
                    d = provinces.setdefault(p, {"province": p, "roads": 0, "high": 0, "medium": 0, "max_score": 0.0})
                    d["roads"] += 1
                    if i["level"] in ("high", "medium"):
                        d[i["level"]] += 1
                    d["max_score"] = max(d["max_score"], i["score"])
        return {
            "updated_at": updated, "error": error, "total": len(self.items), "counts": counts,
            "level_th": LEVEL_TH,
            "provinces": sorted(provinces.values(), key=lambda p: (-p["high"], -p["max_score"])),
            "analysis": analysis,
            "items": items[:limit],
            "note": ("คะแนนเสี่ยงรวมจากน้ำบนผิวถนน (เฉพาะ กทม.), ฝนสะสม 24 ชม., ระดับน้ำคลอง/แม่น้ำใกล้เคียง "
                     "และสภาพจราจร · สายที่ไม่มีเซ็นเซอร์บนถนนจะประเมินจากฝนและระดับน้ำรอบข้างเท่านั้น"),
        }


road_risk = RoadRisk()
