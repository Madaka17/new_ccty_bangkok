"""
Flood analyst agent.

Reads every flood source the server already keeps and has the AI model (local_llm.default, set by
LOCAL_LLM_* in .env) write one situation report for Bangkok: overall level, districts at risk and why,
roads to avoid, a 1-6 h outlook and what the public and the operator team should do. The report comes
back as JSON by REPORT_SCHEMA.

    road sensors      BMA drainage sensors: water on the road surface, rising / falling (flood_service)
    rivers / canals   gauges near or over the bank, main stations, tide (water_service)
    rain outlook      per-zone rain / storm forecast, watch level and the 1-6 h risk score (analytics_service)
    citizen reports   Traffy Fondue flood complaints by district (flood_feeds)
    weather warnings  TMD heavy-rain / storm warnings (flood_feeds)
    road risk         per-road class by the official thresholds (road_service)
    BMA events        flood reports from the BMA traffic centre (bma_events)

A small model gets every source at once, trimmed to the top rows so it fits an 8k context. It may not
report below the level the fixed thresholds already give (_rules), and only roads with water measured on
them stay in roads_to_avoid.

Runs on a timer (AGENT_SECONDS) and on demand (POST /api/flood/agent/run, operator only). A timed run is
skipped when the facts have not changed and the last report is younger than MAX_AGE. With the local
server off, the Thai rule-based report stands in, so the dashboard card always has something to show.
"""
import hashlib
import json
import os
import threading
import time

import local_llm

AGENT_SECONDS = int(os.getenv("FLOOD_AGENT_SECONDS", "300"))
MAX_AGE = int(os.getenv("FLOOD_AGENT_MAX_AGE", "300"))   # re-run an unchanged picture at least this often
REPLY_TOKENS = int(os.getenv("FLOOD_AGENT_REPLY_TOKENS", "2500"))
HISTORY_KEEP = 48
LEVELS = ("normal", "watch", "warning", "critical")
LEVEL_TH = {"normal": "ปกติ", "watch": "เฝ้าระวัง", "warning": "เตือนภัย", "critical": "วิกฤต"}
SOURCES = ("get_road_sensors", "get_rivers_canals", "get_rain_outlook", "get_citizen_reports",
           "get_weather_warnings", "get_road_risk", "get_bma_events")

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์สถานการณ์น้ำท่วมของศูนย์ปฏิบัติการ BKK StreetSmart (กรุงเทพฯ และปริมณฑล)
หน้าที่: อ่านข้อมูลสดทุกแหล่งที่แนบมา วิเคราะห์ แล้วส่งรายงานสถานการณ์เป็น JSON

วิธีวิเคราะห์
- แหล่งข้อมูล: get_road_sensors (น้ำบนถนน ซม.), get_rivers_canals (แม่น้ำ/คลอง % ของตลิ่ง), get_rain_outlook
  (ฝนรายโซนและคะแนนเสี่ยง 1-6 ชม.), get_citizen_reports (Traffy), get_weather_warnings (กรมอุตุฯ),
  get_road_risk (ถนนเสี่ยง), get_bma_events (ศูนย์จราจร กทม.)
- เชื่อมโยงหลายแหล่ง: เขตที่ฝนตกหนัก + คลองสูง + ประชาชนแจ้งหลายเรื่อง = เสี่ยงสูงกว่าสัญญาณเดียว
  แนวโน้มน้ำที่กำลังเพิ่ม (rising) และฝนที่ยังจะตกใน 1-6 ชม. ทำให้ระดับสูงขึ้น
- ใช้ตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งจุด ถนน หรือค่า ถ้าแหล่งใดมี error ให้ใส่ใน data_gaps
- ไม่มีเซ็นเซอร์ ≠ ไม่ท่วม: ปริมณฑลไม่มีเซ็นเซอร์บนถนน ให้ใช้ฝน คลอง และรายงานประชาชนแทน

เกณฑ์ระดับ
- normal: ไม่มีถนนท่วมเกิน 10 ซม. ไม่มีคลองล้น ฝนคาดการณ์ต่ำ
- watch: น้ำขังเล็กน้อยบางจุด หรือฝนหนัก/คลองใกล้เต็มในบางพื้นที่
- warning: ถนนท่วม 20 ซม.ขึ้นไป (ปภ.: ควรเลี่ยง) หรือคลอง/แม่น้ำล้นตลิ่ง หรือโซนเฝ้าระวังสีแดง หรือประชาชนแจ้งถี่ในเขตเดียว
- critical: ถนนท่วมเกิน 60 ซม. (ห้ามขับผ่าน) หลายจุด หรือหลายเขตพร้อมกันและฝนยังตกต่อ

รูปแบบรายงาน (ภาษาไทย กระชับ ข้อความล้วน ไม่ใช้ Markdown)
- headline ไม่เกิน 1 ประโยค summary 2-4 ประโยค
- districts เรียงจากเสี่ยงมากไปน้อย สูงสุด 8 เขต ใส่เฉพาะเขตที่ระดับ watch ขึ้นไป
- roads_to_avoid สูงสุด 8 สาย เฉพาะที่มีค่าวัดน้ำบนถนนจริง
- actions.public 2-4 ข้อสำหรับประชาชน actions.operators 2-4 ข้อสำหรับทีมปฏิบัติการ (เช่น เปิดกล้องจุดไหน ส่งทีมสูบน้ำเขตไหน)
- ถ้าผู้ใช้ถามคำถามเฉพาะ ให้ตอบใน answer ถ้าไม่มีคำถามให้ answer เป็นสตริงว่าง"""

_LEVEL_ENUM = {"type": "string", "enum": list(LEVELS)}
REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["overall_level", "headline", "summary", "districts", "roads_to_avoid", "outlook",
                 "actions", "confidence", "data_gaps", "answer"],
    "properties": {
        "overall_level": _LEVEL_ENUM,
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "districts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "level", "reason", "outlook"],
            "properties": {"name": {"type": "string"}, "level": _LEVEL_ENUM,
                           "reason": {"type": "string"}, "outlook": {"type": "string"}}}},
        "roads_to_avoid": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["road", "district", "depth_cm", "advice"],
            "properties": {"road": {"type": "string"}, "district": {"type": "string"},
                           "depth_cm": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                           "advice": {"type": "string"}}}},
        "outlook": {"type": "string"},
        "actions": {"type": "object", "additionalProperties": False, "required": ["public", "operators"],
                    "properties": {"public": {"type": "array", "items": {"type": "string"}},
                                   "operators": {"type": "array", "items": {"type": "string"}}}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "data_gaps": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
    },
}


def _round(v, n=1):
    return round(v, n) if isinstance(v, (int, float)) else v


class FloodAgent:
    def __init__(self, data_dir, sources):
        """sources: {name: callable} for flood, water, forecast, traffy, tmd, road_risk, bma_events (any may fail)."""
        self.sources = sources
        self.path = os.path.join(data_dir, "cache", "flood_agent.json")
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()   # one analysis at a time, timer or button
        self.report, self.history, self._sig = None, [], None
        self.running, self.error = False, None
        self._load()

    # ------------------------------------------------------------ persistence
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.report, self.history, self._sig = d.get("report"), d.get("history", []), d.get("sig")
        except (OSError, ValueError):
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"report": self.report, "history": self.history, "sig": self._sig}, f, ensure_ascii=False)
        except OSError as e:
            print(f"[FloodAgent] save failed: {e}")

    def _call(self, name, *args):
        fn = self.sources.get(name)
        if not fn:
            return None
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001 - one broken source must not stop the others
            print(f"[FloodAgent] source {name} failed: {str(e)[:120]}")
            return None

    # ------------------------------------------------------------ tools (compact JSON for the model)
    def tool_road_sensors(self, district=None):
        f = self._call("flood")
        if not f:
            return {"error": "เซ็นเซอร์น้ำบนถนนโหลดไม่สำเร็จ"}
        wet = [s for s in f.get("wet") or [] if not district or (s.get("district") or "") == district]
        return {
            "feed_time": f.get("feed_time"), "counts": f.get("counts"), "thresholds_cm": f.get("thresholds"),
            "districts": (f.get("districts") or [])[:15],
            "wet": [{"name": s.get("short_name") or s.get("name"), "road": s.get("road"), "district": s.get("district"),
                     "cm": s.get("level_cm"), "trend": s.get("trend"), "delta_cm": s.get("delta_cm"),
                     "kind": s.get("kind"), "started": s.get("started"), "max_cm": s.get("max_cm")} for s in wet[:30]],
        }

    def tool_rivers_canals(self):
        w = self._call("water")
        if not w:
            return {"error": "ข้อมูลแม่น้ำ/คลองโหลดไม่สำเร็จ"}
        alert = [r for r in (w.get("river") or []) + (w.get("canals") or []) if r.get("level") in ("overflow", "high")]
        alert.sort(key=lambda r: (r.get("level") != "overflow", -(r.get("storage_pct") or 0)))
        ntw = w.get("ntw") or {}
        return {
            "updated_at": w.get("updated_at"), "stale": w.get("stale"),
            "river_counts": w.get("river_counts"), "canal_counts": w.get("canal_counts"), "canal_total": w.get("canal_total"),
            "alert_stations": [{"name": r.get("name"), "district": r.get("district"), "province": r.get("province"),
                                "level": r.get("level"), "pct_of_bank": _round(r.get("storage_pct")),
                                "trend": r.get("trend")} for r in alert[:20]],
            "main_stations": [{"name": s.get("name"), "msl": s.get("msl"), "warning": s.get("warning"),
                               "critical": s.get("critical")} for s in w.get("official_stations") or []],
            "tide": (w.get("tide") or [])[:4],
            "dams": ntw.get("dams") or [],
            "errors": w.get("errors") or {},
        }

    def tool_rain_outlook(self):
        w = self._call("water") or {}
        pred = {p.get("zone"): p for p in ((self._call("forecast") or {}).get("prediction") or [])}
        zones = []
        for z in w.get("weather") or []:
            p = pred.get(z.get("name")) or {}
            zones.append({"zone": z.get("name"), "areas": z.get("areas"), "watch": z.get("watch"),
                          "rain_observed_mm": z.get("rain_observed_mm"), "rain_6h_mm": z.get("rain_6h"),
                          "rain_24h_mm": z.get("rain_24h"), "prob_24h": z.get("prob_24h"),
                          "peak_at": z.get("peak_at"), "peak_mm_h": z.get("peak_mm"),
                          "storm_at": z.get("storm_at"), "gust_max_kmh": _round(z.get("gust_max"), 0),
                          "risk_1_6h": [{"h": h.get("h"), "score": h.get("score"), "cum_mm": h.get("cum_mm")}
                                        for h in p.get("hours") or []],
                          "peak_risk": p.get("peak_score")})
        observed = [{"district": x.get("district"), "province": x.get("province"), "mm": x.get("mm")}
                    for x in w.get("rain_warnings") or [] if x.get("kind") == "observed" and x.get("mm")]
        if not zones and not observed:
            return {"error": "พยากรณ์ฝนโหลดไม่สำเร็จ"}
        return {"zones": zones, "heavy_rain_observed_24h": observed[:10],
                "rain_outlook_3d": (w.get("ntw") or {}).get("rain_outlook") or [],
                "risk_model": "คะแนน 1-6 ชม. = ฐาน(น้ำสูง 25 / ล้น-ถนนท่วม 45 / ฝนที่ตกแล้ว มม.÷3) + 2.5×ฝนสะสมคาดการณ์ + 10 ถ้าโอกาสฝน ≥ 70%"}

    def tool_citizen_reports(self, hours=3, district=None):
        t = self._call("traffy")
        if t is None:
            return {"error": "Traffy Fondue โหลดไม่สำเร็จ"}
        hours = max(1, min(6, int(hours or 3)))
        cutoff = time.time() - hours * 3600
        items = [r for r in t.get("items") or [] if (r.get("ts") or 0) >= cutoff
                 and (not district or r.get("district") == district)]
        by = {}
        for r in items:
            d = by.setdefault(r.get("district") or "-", {"district": r.get("district") or "-", "reports": 0, "depths": {}})
            d["reports"] += 1
            if r.get("depth"):
                d["depths"][r["depth"]] = d["depths"].get(r["depth"], 0) + 1
        return {"hours": hours, "total": len(items), "updated_at": t.get("updated_at"), "error": t.get("error"),
                "by_district": sorted(by.values(), key=lambda d: -d["reports"])[:15],
                "latest": [{"district": r.get("district"), "depth": r.get("depth"), "state": r.get("state"),
                            "min_ago": int((time.time() - r["ts"]) / 60), "text": (r.get("text") or "")[:140]}
                           for r in items[:10]]}

    def tool_weather_warnings(self):
        t = self._call("tmd")
        if t is None:
            return {"error": "ประกาศกรมอุตุฯ โหลดไม่สำเร็จ"}
        return {"active": [{"title": w.get("title"), "date": w.get("date"), "mentions_bangkok": w.get("bkk"),
                            "summary": (w.get("summary") or "")[:400]} for w in (t.get("active") or [])[:5]],
                "error": t.get("error")}

    def tool_road_risk(self, province=None):
        r = self._call("road_risk")
        if not r:
            return {"error": "ความเสี่ยงรายถนนโหลดไม่สำเร็จ"}
        items = [i for i in r.get("items") or [] if (i.get("class") or 0) >= 1
                 and (not province or i.get("province") == province)]
        items.sort(key=lambda i: (-(i.get("class") or 0), -(i.get("flood_cm") or 0), -(i.get("rain_24h") or 0)))
        return {"counts": r.get("counts"), "provinces": (r.get("provinces") or [])[:8],
                "roads": [{"road": i.get("road"), "district": i.get("district"), "province": i.get("province"),
                           "level": i.get("level_th"), "measured_on_road": i.get("measured"),
                           "flood_cm": i.get("flood_cm"), "rain_24h_mm": i.get("rain_24h"),
                           "canal": i.get("gauge_at"), "canal_pct": i.get("gauge_pct")} for i in items[:25]]}

    def tool_bma_events(self):
        ev = self._call("bma_events")
        if ev is None:
            return {"error": "รายงานศูนย์จราจร กทม. โหลดไม่สำเร็จ"}
        items = ev.get("items") if isinstance(ev, dict) else ev
        return {"events": [{"title": e.get("title"), "min_ago": int((time.time() - (e.get("ts") or time.time())) / 60),
                            "detail": (e.get("desc") or e.get("description") or "")[:160]} for e in (items or [])[:12]]}

    def _run_tool(self, name, args):
        args = args or {}
        fn = {
            "get_road_sensors": lambda: self.tool_road_sensors(args.get("district") or None),
            "get_rivers_canals": self.tool_rivers_canals,
            "get_rain_outlook": self.tool_rain_outlook,
            "get_citizen_reports": lambda: self.tool_citizen_reports(args.get("hours") or 3, args.get("district") or None),
            "get_weather_warnings": self.tool_weather_warnings,
            "get_road_risk": lambda: self.tool_road_risk(args.get("province") or None),
            "get_bma_events": self.tool_bma_events,
        }.get(name)
        if fn is None:
            return {"error": f"unknown tool {name}"}, True
        try:
            return fn(), False
        except Exception as e:  # noqa: BLE001 - a broken source shows up as an error entry
            return {"error": str(e)[:200]}, True

    def _all_facts(self):
        """Every source with default arguments: the model prompt, the rule-based report and the change signature."""
        return {name: self._run_tool(name, {})[0] for name in SOURCES}

    def facts(self):
        """The same facts, compacted, for other agents (water_agent) that read the same sources.
        Tide and dams stay in: the three-waters analysis needs them even though this agent's own prompt drops them."""
        facts = self._all_facts()
        compact = self._compact(facts)
        river = facts.get("get_rivers_canals") or {}
        if isinstance(compact.get("get_rivers_canals"), dict):
            compact["get_rivers_canals"].update({k: river[k] for k in ("tide", "dams") if river.get(k)})
        return compact, self._signature(facts)

    @staticmethod
    def _signature(facts):
        """What would change the report: wet stations (5 cm steps), alert gauges, watch levels, reports, warnings."""
        road = facts.get("get_road_sensors") or {}
        river = facts.get("get_rivers_canals") or {}
        rain = facts.get("get_rain_outlook") or {}
        cit = facts.get("get_citizen_reports") or {}
        tmd = facts.get("get_weather_warnings") or {}
        key = {
            "wet": sorted((s.get("name"), int((s.get("cm") or 0) // 5)) for s in road.get("wet") or []),
            "gauges": sorted((s.get("name"), s.get("level")) for s in river.get("alert_stations") or []),
            "zones": sorted((z.get("zone"), z.get("watch"), (z.get("peak_risk") or 0) // 20) for z in rain.get("zones") or []),
            "traffy": sorted((d["district"], d["reports"] // 3) for d in cit.get("by_district") or []),
            "tmd": sorted(w.get("title") or "" for w in tmd.get("active") or []),
        }
        return hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    # ------------------------------------------------------------ model
    @staticmethod
    def _compact(facts):
        """Shorter facts for a small local context window: top rows only, no prose fields the model can skip."""
        cut = {"wet": 12, "districts": 8, "alert_stations": 10, "zones": 8, "by_district": 8, "latest": 4,
               "roads": 10, "events": 5, "active": 3, "provinces": 5, "heavy_rain_observed_24h": 6}
        drop = {"risk_model", "tide", "dams", "errors", "thresholds_cm", "feed_time", "updated_at", "stale"}

        def trim(v):
            if isinstance(v, dict):
                return {k: trim(x[:cut[k]] if k in cut and isinstance(x, list) else x)
                        for k, x in v.items() if k not in drop and x not in (None, [], {}, "")}
            if isinstance(v, list):
                return [trim(x) for x in v]
            return v
        return trim(facts)

    def _run_local(self, facts, question):
        """Every fact pasted in at once, the report back as JSON by REPORT_SCHEMA."""
        prompt = (f"ข้อมูลสดทุกแหล่ง (JSON):\n{json.dumps(self._compact(facts), ensure_ascii=False, separators=(',', ':'), default=str)}\n\n"
                  f"{'คำถามจากผู้ใช้: ' + question if question else ''}\n"
                  f"เวลาปัจจุบัน {time.strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\n"
                  "ส่งรายงานเป็น JSON ตาม schema เท่านั้น")
        text = local_llm.default.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                              max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=REPORT_SCHEMA)
        return json.loads(text[text.find("{"):text.rfind("}") + 1])

    @staticmethod
    def _rules(facts, question):
        """Thai template from the same facts, so the card still works without any key."""
        road = facts.get("get_road_sensors") or {}
        river = facts.get("get_rivers_canals") or {}
        rain = facts.get("get_rain_outlook") or {}
        cit = facts.get("get_citizen_reports") or {}
        wet = road.get("wet") or []
        deep = [s for s in wet if (s.get("cm") or 0) > 20]
        closed = [s for s in wet if (s.get("cm") or 0) > 60]
        over = [s for s in river.get("alert_stations") or [] if s.get("level") == "overflow"]
        red = [z for z in rain.get("zones") or [] if z.get("watch") == "red"]
        busy = [d for d in cit.get("by_district") or [] if d["reports"] >= 3 and d["district"] != "-"]
        if len(closed) >= 2:
            level = "critical"
        elif deep or over or red or busy:
            level = "warning"
        elif wet or any(z.get("watch") in ("orange", "yellow") for z in rain.get("zones") or []):
            level = "watch"
        else:
            level = "normal"
        dist = {}

        def bump(name, lv, why):
            if not name or name == "-":
                return
            d = dist.setdefault(name, {"name": name, "level": "watch", "reason": [], "outlook": ""})
            if LEVELS.index(lv) > LEVELS.index(d["level"]):
                d["level"] = lv
            d["reason"].append(why)

        for s in wet:
            bump(s.get("district"), "warning" if (s.get("cm") or 0) > 20 else "watch", f"{s.get('name')} {s.get('cm') or 0:.0f} ซม.")
        for s in over:
            bump(s.get("district"), "warning", f"{s.get('name')} ล้นตลิ่ง")
        for d in busy:
            bump(d["district"], "warning", f"ประชาชนแจ้ง {d['reports']} เรื่อง")
        districts = sorted(dist.values(), key=lambda d: -LEVELS.index(d["level"]))[:8]
        for d in districts:
            d["reason"] = " · ".join(d["reason"][:3])
        top = max(rain.get("zones") or [{}], key=lambda z: z.get("peak_risk") or 0)
        outlook = (f"{top['zone']} เสี่ยงสุดใน 6 ชม. (คะแนน {top.get('peak_risk')}/100 ฝนสะสม 6 ชม. {top.get('rain_6h_mm')} มม.)"
                   if top.get("zone") else "ไม่มีพยากรณ์ฝน")
        c = road.get("counts") or {}
        return {
            "overall_level": level,
            "headline": f"{LEVEL_TH[level]}: ถนนน้ำท่วม {c.get('flood', 0)} จุด ท่วมเล็กน้อย {c.get('slight', 0)} จุด"
                        + (f" คลองล้นตลิ่ง {len(over)} จุด" if over else ""),
            "summary": outlook,
            "districts": districts,
            "roads_to_avoid": [{"road": s.get("road") or s.get("name"), "district": s.get("district") or "",
                                "depth_cm": s.get("cm"), "advice": "ห้ามขับผ่าน" if (s.get("cm") or 0) > 60 else "ควรเลี่ยง"}
                               for s in deep[:8]],
            "outlook": outlook,
            "actions": {"public": ["เลี่ยงถนนที่มีน้ำเกิน 20 ซม.", "ย้ายรถขึ้นที่สูงถ้าอยู่ในเขตเสี่ยง"],
                        "operators": [f"เปิดกล้องตรวจจุด {', '.join(s.get('name') for s in deep[:3])}" if deep
                                      else "ติดตามเซ็นเซอร์ทุก 15 นาที"]},
            "confidence": "low",
            "data_gaps": [k for k, v in facts.items() if isinstance(v, dict) and v.get("error")],
            "answer": "โหมดออฟไลน์ตอบคำถามเฉพาะไม่ได้ เชื่อมต่อโมเดล AI ไม่ได้ตอนนี้" if question else "",
        }

    # ------------------------------------------------------------ run
    def run(self, question=None, force=False):
        """One analysis. Timed runs (no question, not forced) are skipped when nothing changed."""
        question = (question or "").strip()[:300] or None
        if not self.run_lock.acquire(blocking=False):
            return {**(self.report or {}), "busy": True}
        try:
            with self.lock:
                self.running = True
            facts = self._all_facts()
            sig = self._signature(facts)
            age = time.time() - ((self.report or {}).get("generated_at") or 0)
            if not question and not force and self.report and sig == self._sig and age < MAX_AGE:
                return self.report
            started, report, source, err = time.time(), None, None, None
            if local_llm.default.enabled():
                try:
                    report, source = self._run_local(facts, question), "local"
                except Exception as e:  # noqa: BLE001 - server off, model unloaded, context too small, bad JSON
                    err = f"{local_llm.default.model}: {str(e)[:160]}"
                    print(f"[FloodAgent] local model failed: {e}")
            if report is None:
                report, source = self._rules(facts, question), "rules"
            if report.get("overall_level") not in LEVELS:
                report["overall_level"] = "watch"
            if source == "local":
                # a small model under-calls the level; never report below what the fixed thresholds already say
                floor = self._rules(facts, None)["overall_level"]
                if LEVELS.index(floor) > LEVELS.index(report["overall_level"]):
                    report["overall_level"] = floor
                # and keep only roads with water actually measured on them
                report["roads_to_avoid"] = [r for r in report.get("roads_to_avoid") or [] if (r.get("depth_cm") or 0) > 0]
            steps = [{"tool": k, "input": {}, "error": bool(isinstance(v, dict) and v.get("error"))} for k, v in facts.items()]
            report.update({"source": source, "model": local_llm.default.model if source == "local" else None,
                           "generated_at": int(time.time()), "took_s": round(time.time() - started, 1),
                           "steps": steps, "question": question, "level_th": LEVEL_TH[report["overall_level"]]})
            with self.lock:
                self.error = err
                if not question:     # an ad-hoc question does not replace the standing report
                    self.report, self._sig = report, sig
                    self.history = (self.history + [{"ts": report["generated_at"], "level": report["overall_level"],
                                                     "headline": report.get("headline", "")}])[-HISTORY_KEEP:]
                    self._save()
            return report
        finally:
            with self.lock:
                self.running = False
            self.run_lock.release()

    def status(self):
        with self.lock:
            return {"report": self.report, "history": list(self.history), "running": self.running,
                    "error": self.error, "interval_s": AGENT_SECONDS}

    def _loop(self):
        time.sleep(90)    # let the pollers fill their first answers
        while True:
            try:
                self.run()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[FloodAgent] run failed: {e}")
            time.sleep(AGENT_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="FloodAgent").start()
