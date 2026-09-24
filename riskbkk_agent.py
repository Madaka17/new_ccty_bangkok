"""
BMA traffic-risk analyst.

Reads the traffic layers taken from the BMA risk map (cpudapp.bangkok.go.th/riskbkk, slimmed into
web/public/riskbkk/ by local/pipeline/build_riskbkk_layers.py), works out the numbers in Python
(per district, per hour, top points) and has the AI model (local_llm.default, LOCAL_LLM_* in .env)
write one Thai analysis as JSON by REPORT_SCHEMA for the City Analytics page.

    accident          Thai RSC accident cases 2566-2568, pooled into ~110 m cells; the per-case numbers
                      (district, month, weekday, injured, dead) come from accident_stats.json
    accident_risk     BMA accident risk points 2566-2568 with cause and fix
    risk100 / _solve  the 100 traffic risk points (cases) and how far each fix has got
    friction          recurring congestion points with period, cause and fix
    construction      large building sites still under construction
    crosswalk, bus_stop, motorcycle_taxi, parking, rail_crossing   road furniture per district
    js100             JS100 / FM91 incident layer (the BMA feed stopped in Sep 2024)

The layers are a snapshot, so the analysis runs once at start when the files changed (or no report
is saved) and again on demand (POST /api/riskbkk/analysis/run, operator only). Without the model the
Thai rule-based report stands in.
"""
import collections
import hashlib
import json
import os
import threading
import time

import local_llm

REPLY_TOKENS = int(os.getenv("RISKBKK_AGENT_REPLY_TOKENS", "3000"))
LAYERS = ("accident", "accident_risk", "risk100", "risk100_solve", "friction", "construction",
          "crosswalk", "bus_stop", "motorcycle_taxi", "parking", "rail_crossing", "js100")
WEEKDAYS = ("จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์")
MONTHS = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
# district hotspot score: how much each layer's per-district count weighs
WEIGHTS = {"accident": 3, "accident_risk": 2, "risk100": 2, "friction": 2, "construction": 1}

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์ความปลอดภัยทางถนนของศูนย์ปฏิบัติการ BKK StreetSmart (กรุงเทพมหานคร)
หน้าที่: อ่านสถิติที่คำนวณจากข้อมูลจุดเสี่ยงของ กทม. (riskbkk) ที่แนบมา วิเคราะห์ แล้วส่งรายงานเป็น JSON

ข้อมูลที่ได้รับ
- accident: อุบัติเหตุปี 2566-2568 จาก Thai RSC (เคลม พ.ร.บ.) จำนวนเหตุ ผู้บาดเจ็บ ผู้เสียชีวิต แยกรายเขต รายเดือน รายวันในสัปดาห์ รายปี และจุดที่เกิดบ่อยสุด
  (by_month และ by_weekday เป็นยอดรวมทั้ง 3 ปี ไม่ใช่ค่าเฉลี่ยต่อวัน)
- accident_risk: จุดเสี่ยงอุบัติเหตุที่ กทม. ประกาศปี 2566-2568 พร้อมสาเหตุ
- risk100 / risk100_solve: 100 จุดเสี่ยงจราจร (จำนวนอุบัติเหตุ) และสถานะการแก้ไข
- friction: จุดฝืด (รถติดประจำ) ช่วงเวลาและสาเหตุ
- construction: สถานที่ก่อสร้างอาคารใหญ่ที่ยังไม่เสร็จ
- districts: ตารางรายเขต รวมทุกชั้นข้อมูล พร้อมคะแนนเสี่ยง (score)
- infrastructure: ทางม้าลาย ป้ายรถเมล์ วินมอเตอร์ไซค์ ที่จอดรถ จุดตัดทางรถไฟ รายเขต

วิธีวิเคราะห์
- ใช้ตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งจุด ถนน เขต หรือตัวเลข
- ห้ามเขียนชื่อฟิลด์ภาษาอังกฤษ (เช่น risk100, risk100_cases, friction, score) ในข้อความ ให้ใช้คำไทย:
  "100 จุดเสี่ยงจราจร", "อุบัติเหตุสะสมใน 100 จุดเสี่ยง", "จุดฝืด", "คะแนนความเสี่ยง"
- เชื่อมโยงหลายชั้นข้อมูล: เขตที่อุบัติเหตุสูง + มีจุดเสี่ยงประกาศ + จุดฝืด + ก่อสร้าง = ต้องจัดการก่อน
- หาแพทเทิร์นเวลา (เดือน/วันในสัปดาห์/แนวโน้มรายปี) จาก accident และช่วงรถติดจาก friction
- ชี้จุดเสี่ยงที่ยังแก้ไม่เสร็จ (risk100_solve) และจุดที่อุบัติเหตุสูงที่สุด
- ระบุข้อจำกัดข้อมูล: Thai RSC นับเฉพาะเหตุที่มีผู้บาดเจ็บเคลม พ.ร.บ. และไม่มีเวลาเกิดเหตุ,
  ชั้นเหตุจราจรจากวิทยุ จส.100/FM91 (js100 ไม่เกี่ยวกับ 100 จุดเสี่ยง) หยุดอัปเดตตั้งแต่ ก.ย. 2567

รูปแบบรายงาน (ภาษาไทย กระชับ ข้อความล้วน ไม่ใช้ Markdown)
- headline: 1 ประโยค สรุปภาพรวมความเสี่ยงจราจรของกรุงเทพฯ
- summary: 2-4 ประโยค
- key_findings: 4-6 ข้อ แต่ละข้อมี title สั้น และ detail ที่อ้างตัวเลข
- hotspots: 5-8 เขตที่ควรจัดการก่อน level (สูง/ปานกลาง/ต่ำ) และ reasons อ้างตัวเลขจาก districts
- time_patterns: 1-3 ประโยค เดือน วันในสัปดาห์ และแนวโน้มรายปีที่เสี่ยง
- recommendations: police (ตำรวจ/จราจร), engineering (สำนักการจราจรและขนส่ง/วิศวกรรม), public (ประชาชน) อย่างละ 2-4 ข้อ
- data_caveats: ข้อจำกัดของข้อมูล 1-3 ข้อ"""

_STR_LIST = {"type": "array", "items": {"type": "string"}}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "detail": {"type": "string"}}, "required": ["title", "detail"],
            "additionalProperties": False}},
        "hotspots": {"type": "array", "items": {"type": "object", "properties": {
            "district": {"type": "string"}, "level": {"type": "string", "enum": ["สูง", "ปานกลาง", "ต่ำ"]},
            "reasons": {"type": "string"}}, "required": ["district", "level", "reasons"], "additionalProperties": False}},
        "time_patterns": {"type": "string"},
        "recommendations": {"type": "object", "properties": {
            "police": _STR_LIST, "engineering": _STR_LIST, "public": _STR_LIST},
            "required": ["police", "engineering", "public"], "additionalProperties": False},
        "data_caveats": _STR_LIST,
    },
    "required": ["headline", "summary", "key_findings", "hotspots", "time_patterns", "recommendations", "data_caveats"],
    "additionalProperties": False,
}


def _info(f, label):
    """Value of a 'label: value' line in a slim feature's info list."""
    for line in f["properties"].get("info") or []:
        if line.startswith(label + ": "):
            return line[len(label) + 2:]
    return ""


class RiskAgent:
    def __init__(self, data_dir, layer_dir):
        self.path = os.path.join(data_dir, "riskbkk_analysis.json")
        self.layer_dir = layer_dir
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.result, self.sig, self.running, self.error = None, None, False, None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.result, self.sig = d.get("result"), d.get("sig")
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------ facts
    def _accident_stats(self):
        try:
            with open(os.path.join(self.layer_dir, "accident_stats.json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _layers(self):
        out = {}
        for name in LAYERS:
            try:
                with open(os.path.join(self.layer_dir, f"{name}.geojson"), "r", encoding="utf-8") as f:
                    out[name] = json.load(f)["features"]
            except (OSError, ValueError):
                out[name] = []
        return out

    def _signature(self):
        parts = []
        for name in LAYERS + ("accident_stats",):
            try:
                st = os.stat(os.path.join(self.layer_dir, f"{name}.json" if name == "accident_stats" else f"{name}.geojson"))
                parts.append(f"{name}:{st.st_size}:{int(st.st_mtime)}")
            except OSError:
                parts.append(f"{name}:-")
        return hashlib.sha1("|".join(parts).encode()).hexdigest()

    @staticmethod
    def _stats(L, acc=None):
        """Every number the report needs, worked out here so the model only has to read and explain.
        L: the slim layers; acc: accident_stats.json (the accident layer is cells, not cases)."""
        acc = acc or {}
        by_d = collections.defaultdict(lambda: collections.Counter())
        for name, feats in L.items():
            if name == "accident":
                continue
            for f in feats:
                d = f["properties"].get("district") or "-"
                by_d[d][name] += 1
        for d, row in (acc.get("by_district") or {}).items():
            by_d[d]["accident"] = row["cases"]
            by_d[d]["injured"] = row["injured"]
            by_d[d]["dead"] = row["dead"]
        risk_cases = collections.Counter()
        for f in L["risk100"]:
            try:
                risk_cases[f["properties"].get("district") or "-"] += int(_info(f, "จำนวนอุบัติเหตุ").split()[0])
            except (ValueError, IndexError):
                pass
        top = {k: max((c[k] for c in by_d.values()), default=0) or 1 for k in WEIGHTS}
        districts = []
        for d, c in by_d.items():
            if d == "-":
                continue
            score = sum(w * c[k] / top[k] for k, w in WEIGHTS.items()) / sum(WEIGHTS.values()) * 100
            districts.append({"district": d, "score": round(score), "accidents": c["accident"],
                              "injured": c["injured"], "dead": c["dead"],
                              "risk_points_2566_68": c["accident_risk"], "risk100_points": c["risk100"],
                              "risk100_cases": risk_cases[d], "friction": c["friction"], "construction": c["construction"],
                              "crosswalk": c["crosswalk"], "bus_stop": c["bus_stop"], "motorcycle_taxi": c["motorcycle_taxi"]})
        districts.sort(key=lambda r: -r["score"])

        risk100 = sorted(L["risk100"], key=lambda f: -int((_info(f, "จำนวนอุบัติเหตุ").split() or ["0"])[0] or 0))
        solve = collections.Counter(_info(f, "สถานะ") for f in L["risk100_solve"])
        periods = collections.Counter()
        for f in L["friction"]:
            for part in _info(f, "ช่วงติด").split("/"):
                if part.strip():
                    periods[part.split("(")[0].strip()] += 1
        risk_years = collections.Counter(_info(f, "ปี") for f in L["accident_risk"])
        return {
            "counts": {**{k: len(v) for k, v in L.items()}, "accident": acc.get("cases", 0)},
            "districts": districts,
            "accident": {
                "period": "ปี 2566 - 2568 (Thai RSC)",
                "cases": acc.get("cases", 0), "injured": acc.get("injured", 0), "dead": acc.get("dead", 0),
                "by_month": [{"month": MONTHS[i], "n": n} for i, n in enumerate(acc.get("by_month") or [])],
                "by_weekday": [{"day": WEEKDAYS[i], "n": n} for i, n in enumerate(acc.get("by_weekday") or [])],
                "by_year": [{"year": int(y), "n": n} for y, n in (acc.get("by_year") or {}).items()],
                "top_places": acc.get("top_cells") or [],
            },
            "accident_risk": {"by_year": [{"year": y, "n": n} for y, n in sorted(risk_years.items())],
                              "points": [{"name": f["properties"]["title"], "district": f["properties"].get("district"),
                                          "year": _info(f, "ปี"), "cause": _info(f, "สาเหตุ")[:140]}
                                         for f in L["accident_risk"][-12:]]},
            "risk100": {"total_cases": sum(risk_cases.values()),
                        "top": [{"name": f["properties"]["title"], "district": f["properties"].get("district"),
                                 "cases": _info(f, "จำนวนอุบัติเหตุ")} for f in risk100[:10]],
                        "solve_status": dict(solve),
                        "not_done": [{"name": f["properties"]["title"][:80], "district": f["properties"].get("district"),
                                      "status": _info(f, "สถานะ")}
                                     for f in L["risk100_solve"] if not f["properties"].get("done")][:10]},
            "friction": {"periods": dict(periods.most_common(6)),
                         "points": [{"name": f["properties"]["title"][:80], "district": f["properties"].get("district"),
                                     "cause": _info(f, "สาเหตุ")[:140]} for f in L["friction"][:10]]},
            "construction": {"n": len(L["construction"])},
            "js100": {"n": len(L["js100"]), "note": "ชั้นข้อมูลนี้หยุดอัปเดตตั้งแต่ ก.ย. 2567"},
        }

    # ------------------------------------------------------------ report
    def _run_local(self, stats):
        facts = {**stats, "districts": stats["districts"][:15]}
        prompt = (f"สถิติจากข้อมูลจุดเสี่ยง กทม. (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}\n\n"
                  "ส่งรายงานเป็น JSON ตาม schema เท่านั้น")
        text = local_llm.default.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                                      max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=REPORT_SCHEMA)
        return json.loads(text[text.find("{"):text.rfind("}") + 1])

    @staticmethod
    def _rules(stats):
        """Thai template from the same numbers, so the card still has something without the model."""
        top = stats["districts"][:6]
        acc = stats["accident"]
        peak_m = max(acc["by_month"], key=lambda r: r["n"])["month"] if acc["by_month"] else None
        peak_d = max(acc["by_weekday"], key=lambda r: r["n"])["day"] if acc["by_weekday"] else "-"
        solve = stats["risk100"]["solve_status"]
        return {
            "headline": f"เขตที่ควรจัดการก่อน: {', '.join(d['district'] for d in top[:3])}",
            "summary": (f"อุบัติเหตุปี 2566-2568 {acc['cases']:,} เหตุ บาดเจ็บ {acc['injured']:,} เสียชีวิต {acc['dead']:,} คน จุดเสี่ยงประกาศ {stats['counts']['accident_risk']} จุด "
                        f"จุดฝืด {stats['counts']['friction']} จุด 100 จุดเสี่ยงแก้เสร็จ {solve.get('ดำเนินการแล้วเสร็จ', 0)} จุด"),
            "key_findings": [{"title": d["district"], "detail": f"อุบัติเหตุ {d['accidents']} เหตุ · จุดเสี่ยง {d['risk_points_2566_68']} · จุดฝืด {d['friction']}"}
                             for d in top[:4]],
            "hotspots": [{"district": d["district"], "level": "สูง" if d["score"] >= 50 else "ปานกลาง" if d["score"] >= 25 else "ต่ำ",
                          "reasons": f"คะแนน {d['score']} · อุบัติเหตุ {d['accidents']} · จุดเสี่ยง {d['risk_points_2566_68']} · จุดฝืด {d['friction']}"}
                         for d in top],
            "time_patterns": f"อุบัติเหตุมากที่สุดเดือน {peak_m} และวัน{peak_d}" if peak_m else "",
            "recommendations": {"police": ["กวดขันวินัยจราจรในเขตคะแนนสูง"],
                                "engineering": ["เร่งแก้ 100 จุดเสี่ยงที่ยังไม่เสร็จ"],
                                "public": ["ระวังเป็นพิเศษในช่วงเวลาและเขตที่เสี่ยง"]},
            "data_caveats": ["Thai RSC นับเฉพาะเหตุที่มีผู้บาดเจ็บเคลม พ.ร.บ. และไม่มีเวลาเกิดเหตุ", "ชั้น จส.100 หยุดอัปเดตตั้งแต่ ก.ย. 2567",
                             "โหมดออฟไลน์: ไม่ได้ใช้โมเดล AI"],
        }

    def run(self, force=False):
        if not self.run_lock.acquire(blocking=False):
            return {**self.status(), "busy": True}
        try:
            sig = self._signature()
            if self.result and self.result.get("source") == "local" and sig == self.sig and not force:
                return self.status()
            with self.lock:
                self.running = True
            started, err = time.time(), None
            stats = self._stats(self._layers(), self._accident_stats())
            report, source = None, "rules"
            if local_llm.default.enabled():
                try:
                    report, source = self._run_local(stats), "local"
                except Exception as e:  # noqa: BLE001 - server off, bad JSON, context too small
                    err = f"{local_llm.default.model}: {str(e)[:160]}"
                    print(f"[RiskAgent] model failed: {e}")
            if report is None:
                report = self._rules(stats)
            result = {"report": report, "stats": stats, "source": source,
                      "model": local_llm.default.model if source == "local" else None,
                      "generated_at": int(time.time()), "took_s": round(time.time() - started, 1)}
            with self.lock:
                self.result, self.sig, self.error = result, sig, err
                try:
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump({"result": result, "sig": sig}, f, ensure_ascii=False)
                except OSError as e:
                    print(f"[RiskAgent] save failed: {e}")
            return self.status()
        finally:
            with self.lock:
                self.running = False
            self.run_lock.release()

    def status(self):
        with self.lock:
            return {**(self.result or {}), "running": self.running, "error": self.error}

    def start(self):
        """One run in the background at start; it returns at once when the layers and report are unchanged."""
        threading.Thread(target=self.run, daemon=True, name="RiskAgent").start()
