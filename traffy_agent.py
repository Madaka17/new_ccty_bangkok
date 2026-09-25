"""
AI analyst for the flood reports people send through Traffy Fondue (flood_feeds.TraffyReports, 6 h window).

Every AGENT_SECONDS the numbers are worked out here (per district, depth, hour, state), then the AI model
(local_llm.default: the Qwen model behind LOCAL_LLM_* in .env) reads them with the newest report texts and
writes one Thai analysis as JSON by REPORT_SCHEMA for the flood tab of the City Analytics page: where the
reports cluster, what people describe (road, home, drain), which reports need a team first and what to do.

The model runs only when the set of reports changed or the analysis is older than MAX_AGE. Without the
model the Thai rule-based report stands in. Served by /api/traffy/analysis.
"""
import collections
import hashlib
import json
import os
import re
import threading
import time

import local_llm
from flood_agent import DISTRICT_ZONE

AGENT_SECONDS = int(os.getenv("TRAFFY_AGENT_SECONDS", "600"))
MAX_AGE = int(os.getenv("TRAFFY_AGENT_MAX_AGE", "1800"))
REPLY_TOKENS = int(os.getenv("TRAFFY_AGENT_REPLY_TOKENS", "2500"))
TEXTS = 120            # newest report texts the model reads
TEXT_CHARS = 160
LEVELS = ("สูง", "ปานกลาง", "ต่ำ")
# Depth levels, shallow to deep. Traffy's depth field is free text ("หน้าแข้งค่ะ", "20-30cm", "ในบ้านเท่าเอว"),
# so it is read by keyword and by centimetres into one of these; anything else is "ไม่ระบุ".
DEPTHS = ("ข้อเท้า", "หน้าแข้ง", "หัวเข่า", "ต้นขา", "เอวขึ้นไป")
DEPTH_WORDS = [("เอวขึ้นไป", ("เอว", "เมตร")), ("ต้นขา", ("ต้นขา", "ก้น")),
               ("หัวเข่า", ("เข่า", "หัวเขา", "มิดล้อ")), ("หน้าแข้ง", ("แข้ง", "แข่ง", "เข้ง", "น่อง", "ล้อ")),
               ("ข้อเท้า", ("ข้อเท้า", "ตาตุ่ม", "ฟุตบาท"))]
DEPTH_CM = [(10, "ข้อเท้า"), (30, "หน้าแข้ง"), (50, "หัวเข่า"), (70, "ต้นขา")]

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์เรื่องร้องเรียนน้ำท่วมของศูนย์ปฏิบัติการ BKK StreetSmart (กรุงเทพฯ และปริมณฑล)
หน้าที่: อ่านสถิติและข้อความที่ประชาชนแจ้งน้ำท่วมผ่าน Traffy Fondue ใน 6 ชั่วโมงล่าสุด วิเคราะห์ แล้วส่งรายงานเป็น JSON

ข้อมูลที่ได้รับ
- stats: จำนวนเรื่องทั้งหมด รายเขต รายชั่วโมง ระดับน้ำที่แจ้ง (ข้อเท้า < หน้าแข้ง < หัวเข่า < ต้นขา < เอวขึ้นไป) และสถานะเรื่อง
- reports: เรื่องล่าสุด (id, เขต, ระดับน้ำ, คำที่ผู้แจ้งเขียนเรื่องความลึก, สถานะ, กี่นาทีที่แล้ว, ข้อความ)

วิธีวิเคราะห์
- ใช้ตัวเลขจาก stats เท่านั้น ห้ามนับเองจากข้อความ ห้ามแต่งเขต ถนน หรือตัวเลข
- อ่านข้อความเพื่อหาว่าประชาชนเจออะไร: น้ำท่วมถนน/ซอย น้ำเข้าบ้าน/หมู่บ้าน ท่อระบายน้ำอุดตัน น้ำท่วมขังนาน รถเสีย/สัญจรไม่ได้
- เขตที่แจ้งมาก + ระดับน้ำสูง (หัวเข่าขึ้นไป) + เรื่องยังรอรับ = ต้องส่งทีมก่อน
- แนวโน้ม: เทียบจำนวนชั่วโมงล่าสุดกับก่อนหน้า (เพิ่มขึ้น/ทรงตัว/ลดลง)

รูปแบบรายงาน (ภาษาไทย กระชับ ข้อความล้วน ไม่ใช้ Markdown)
- headline ไม่เกิน 1 ประโยค summary 2-4 ประโยค trend 1 ประโยค
- hotspots สูงสุด 6 เขต เรียงจากเร่งด่วนมากไปน้อย district เป็นชื่อเขตล้วนไม่มีคำว่า "เขต" issues บอกสิ่งที่ประชาชนเจอในเขตนั้น
- themes 2-5 ข้อ ปัญหาที่พบซ้ำจากข้อความ พร้อมตัวอย่างสั้น
- urgent สูงสุด 5 เรื่อง ใช้ id จาก reports เท่านั้น พร้อมเหตุผลสั้น
- actions 2-4 ข้อสำหรับทีมปฏิบัติการ"""

REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "summary", "trend", "hotspots", "themes", "urgent", "actions"],
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "trend": {"type": "string"},
        "hotspots": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["district", "level", "issues"],
            "properties": {"district": {"type": "string"}, "level": {"type": "string", "enum": list(LEVELS)},
                           "issues": {"type": "string"}}}},
        "themes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["title", "detail"],
            "properties": {"title": {"type": "string"}, "detail": {"type": "string"}}}},
        "urgent": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "reason"],
            "properties": {"id": {"type": "string"}, "reason": {"type": "string"}}}},
        "actions": {"type": "array", "items": {"type": "string"}},
    },
}


def _depth_level(raw):
    """One of DEPTHS from Traffy's free-text depth, or "ไม่ระบุ". The deepest word wins
    ("ข้อเท้าเกือบหน้าแข้ง" -> หน้าแข้ง); numbers are centimetres (the top of a range), or metres when 3 or less."""
    raw = (raw or "").strip().replace("เซนติเมตร", "ซม")   # "เมตร" alone means metres
    for level, words in DEPTH_WORDS:
        if any(w in raw for w in words):
            return level
    nums = [] if "/" in raw else [float(n) for n in re.findall(r"\d+(?:\.\d+)?", raw)]   # "1/3ล้อ" is no depth
    if nums:
        cm = max(nums)
        cm = cm * 100 if cm <= 3 else cm
        return next((lv for top, lv in DEPTH_CM if cm <= top), "เอวขึ้นไป")
    return "ไม่ระบุ"


def _depth_rank(level):
    return DEPTHS.index(level) if level in DEPTHS else -1


class TraffyAgent:
    def __init__(self, data_dir, source):
        """source: callable returning flood_feeds.TraffyReports.status() ({items, total, ...})."""
        self.source = source
        self.path = os.path.join(data_dir, "cache", "traffy_agent.json")
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.result, self.sig, self.running, self.error = None, None, False, None
        self.fed = False        # the Traffy feed has answered since start
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.result, self.sig = d.get("result"), d.get("sig")
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------ facts
    def _items(self):
        """(reports, ready). ready is False until the Traffy poller has answered once (right after a
        restart), so an empty list then is not taken as a quiet 6 h."""
        try:
            st = self.source() or {}
        except Exception as e:  # noqa: BLE001 - feed down: nothing to analyse
            print(f"[TraffyAgent] source failed: {e}")
            return [], False
        return st.get("items") or [], bool(st.get("updated_at"))

    @staticmethod
    def _signature(items):
        return hashlib.sha1("|".join(sorted(f"{r.get('id')}:{r.get('state')}" for r in items)).encode()).hexdigest()

    @staticmethod
    def _stats(items, now):
        """Every number the report shows, worked out here so the model only reads and explains."""
        by_d = collections.defaultdict(lambda: {"reports": 0, "deep": 0, "waiting": 0, "depths": collections.Counter()})
        hours = [0] * 6                      # index 0 = the last hour
        depths, states = collections.Counter(), collections.Counter()
        for r in items:
            d = by_d[r.get("district") or "-"]
            d["reports"] += 1
            dep = _depth_level(r.get("depth"))
            d["depths"][dep] += 1
            depths[dep] += 1
            states[r.get("state") or "-"] += 1
            if _depth_rank(dep) >= DEPTHS.index("หัวเข่า"):
                d["deep"] += 1
            if r.get("state") == "รอรับเรื่อง":
                d["waiting"] += 1
            h = int((now - (r.get("ts") or now)) // 3600)
            if 0 <= h < 6:
                hours[h] += 1
        districts = [{"district": k, "zone": DISTRICT_ZONE.get(k, "ปริมณฑล"), "reports": v["reports"],
                      "deep_reports": v["deep"], "waiting": v["waiting"], "depths": dict(v["depths"].most_common())}
                     for k, v in by_d.items() if k != "-"]
        districts.sort(key=lambda d: (-d["reports"], -d["deep_reports"]))
        return {"total": len(items), "last_hour": hours[0], "previous_hour": hours[1],
                "by_hour": [{"hours_ago": i, "reports": n} for i, n in enumerate(hours)],
                "depths": dict(depths.most_common()), "states": dict(states.most_common()),
                "districts": districts}

    @staticmethod
    def _texts(items, now):
        newest = sorted(items, key=lambda r: -(r.get("ts") or 0))[:TEXTS]
        return [{"id": r.get("id"), "district": r.get("district"), "depth": _depth_level(r.get("depth")),
                 "depth_text": (r.get("depth") or "")[:40], "state": r.get("state"),
                 "minutes_ago": int((now - (r.get("ts") or now)) // 60), "text": (r.get("text") or "")[:TEXT_CHARS]}
                for r in newest]

    # ------------------------------------------------------------ report
    def _run_local(self, stats, texts):
        facts = {"stats": {**stats, "districts": stats["districts"][:15]}, "reports": texts}
        prompt = (f"เรื่องแจ้งน้ำท่วมจาก Traffy Fondue (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}\n\n"
                  "ส่งรายงานเป็น JSON ตาม schema เท่านั้น")
        text = local_llm.default.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                                      max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=REPORT_SCHEMA)
        return json.loads(text[text.find("{"):text.rfind("}") + 1])

    @staticmethod
    def _rules(stats, items):
        """Thai template from the same numbers, so the card still has something without the model."""
        top = stats["districts"][:6]
        last, prev = stats["last_hour"], stats["previous_hour"]
        trend = "เพิ่มขึ้น" if last > prev * 1.2 else "ลดลง" if last < prev * 0.8 else "ทรงตัว"
        deep = sorted((r for r in items if _depth_rank(_depth_level(r.get("depth"))) >= DEPTHS.index("หัวเข่า")),
                      key=lambda r: (-_depth_rank(_depth_level(r.get("depth"))), -(r.get("ts") or 0)))
        return {
            "headline": (f"ประชาชนแจ้งน้ำท่วม {stats['total']} เรื่องใน 6 ชม. มากสุดที่{top[0]['district']}"
                         if top else "ไม่มีเรื่องแจ้งน้ำท่วมใน 6 ชม."),
            "summary": f"ชั่วโมงล่าสุด {last} เรื่อง ระดับน้ำหัวเข่าขึ้นไป {len(deep)} เรื่อง รอรับเรื่อง {stats['states'].get('รอรับเรื่อง', 0)} เรื่อง",
            "trend": f"แนวโน้ม{trend}: ชั่วโมงล่าสุด {last} เรื่อง ชั่วโมงก่อนหน้า {prev} เรื่อง",
            "hotspots": [{"district": d["district"],
                          "level": "สูง" if d["deep_reports"] or d["reports"] >= 20 else "ปานกลาง" if d["reports"] >= 8 else "ต่ำ",
                          "issues": f"{d['reports']} เรื่อง · หัวเข่าขึ้นไป {d['deep_reports']} · รอรับ {d['waiting']}"}
                         for d in top],
            "themes": [],
            "urgent": [{"id": r["id"], "reason": f"น้ำระดับ{_depth_level(r.get('depth'))} ที่{r.get('district') or '-'}"} for r in deep[:5]],
            "actions": ["ส่งทีมสูบน้ำไปเขตที่แจ้งมากและน้ำลึก", "ตอบรับเรื่องที่ยังรอรับในเขตเร่งด่วน"],
        }

    @staticmethod
    def _tidy(report, stats, items):
        """Hotspots get their zone and count from the numbers; urgent keeps only real ids, with the report attached."""
        by_d = {d["district"]: d for d in stats["districts"]}
        for h in report.get("hotspots") or []:
            name = (h.get("district") or "").strip()
            name = name[3:].strip() if name.startswith("เขต") else name
            d = by_d.get(name) or {}
            h.update({"district": name, "zone": DISTRICT_ZONE.get(name, "ปริมณฑล"), "reports": d.get("reports", 0),
                      "deep_reports": d.get("deep_reports", 0), "waiting": d.get("waiting", 0)})
            if h.get("level") not in LEVELS:
                h["level"] = "ปานกลาง"
        by_id = {r.get("id"): r for r in items}
        urgent = []
        for u in report.get("urgent") or []:
            r = by_id.get(u.get("id"))
            if r:
                urgent.append({**u, "district": r.get("district"), "depth": _depth_level(r.get("depth")), "state": r.get("state"),
                               "ts": r.get("ts"), "text": r.get("text"), "url": r.get("url")})
        report["urgent"] = urgent[:5]
        return report

    def run(self, force=False):
        if not self.run_lock.acquire(blocking=False):
            return {**self.status(), "busy": True}
        try:
            items, ready = self._items()
            if not ready:
                return self.status()     # keep the last analysis until the feed has loaded
            self.fed = True
            sig = self._signature(items)
            age = time.time() - ((self.result or {}).get("generated_at") or 0)
            if not force and self.result and self.result.get("source") == "local" and sig == self.sig and age < MAX_AGE:
                return self.status()
            with self.lock:
                self.running = True
            now, err = time.time(), None
            stats = self._stats(items, now)
            report, source = None, "rules"
            if items and local_llm.default.enabled():
                try:
                    report, source = self._run_local(stats, self._texts(items, now)), "local"
                except Exception as e:  # noqa: BLE001 - server off, bad JSON, context too small
                    err = f"{local_llm.default.model}: {str(e)[:160]}"
                    print(f"[TraffyAgent] model failed: {e}")
            if report is None:
                report = self._rules(stats, items)
            result = {"report": self._tidy(report, stats, items), "stats": stats, "source": source,
                      "model": local_llm.default.model if source == "local" else None,
                      "generated_at": int(time.time()), "took_s": round(time.time() - now, 1)}
            with self.lock:
                self.result, self.sig, self.error = result, sig, err
                try:
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump({"result": result, "sig": sig}, f, ensure_ascii=False)
                except OSError as e:
                    print(f"[TraffyAgent] save failed: {e}")
            return self.status()
        finally:
            with self.lock:
                self.running = False
            self.run_lock.release()

    def status(self):
        with self.lock:
            return {**(self.result or {}), "running": self.running, "error": self.error, "interval_s": AGENT_SECONDS}

    def _loop(self):
        time.sleep(60)    # let the Traffy poller fill its first answer
        while True:
            try:
                self.run()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[TraffyAgent] run failed: {e}")
            time.sleep(AGENT_SECONDS if self.fed else 30)   # feed not loaded yet: try again soon

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="TraffyAgent").start()
