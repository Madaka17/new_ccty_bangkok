"""
Water Forecast analyst.

Fills the "วิเคราะห์และคาดการณ์สถานการณ์น้ำท่วม" card on the Water Forecast page. Every POLL_SECONDS it
takes the live flood facts FloodAgent already gathers (road sensors, rivers / canals with tide and dams,
rain outlook, Traffy reports, TMD warnings, road risk, BMA events) and has the AI model (local_llm.default,
LOCAL_LLM_* in .env) write the card's four tabs as JSON by REPORT_SCHEMA: outlook by zone, the three
waters (upstream / tide / rain), measures for the city and a guide for the public.

The model runs again only when the facts changed (FloodAgent's signature) or the report is older than
MAX_AGE, so an unchanged picture does not call it every poll. Without the model the card keeps the
last AI report and says so.
"""
import json
import os
import threading
import time

from backend.core import local_llm

POLL_SECONDS = int(os.getenv("WATER_AGENT_SECONDS", "600"))
MAX_AGE = int(os.getenv("WATER_AGENT_MAX_AGE", "600"))
REPLY_TOKENS = int(os.getenv("WATER_AGENT_REPLY_TOKENS", "3500"))
LEVELS = ("normal", "watch", "warning", "critical")

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์และพยากรณ์สถานการณ์น้ำของกรุงเทพฯ และปริมณฑล (ศูนย์ปฏิบัติการ BKK StreetSmart)
หน้าที่: อ่านข้อมูลสดทุกแหล่งที่แนบมา แล้วเขียนบทวิเคราะห์และคาดการณ์น้ำท่วมพร้อมแนวทางป้องกัน เป็น JSON

แหล่งข้อมูล
- get_road_sensors: น้ำบนผิวถนน (ซม.) และแนวโน้ม
- get_rivers_canals: แม่น้ำ/คลอง % ของตลิ่ง สถานีหลัก (ม.รทก.) น้ำทะเลหนุน (tide) เขื่อน (dams)
- get_rain_outlook: ฝนรายโซน ฝนสะสม 6/24 ชม. คะแนนเสี่ยง 1-6 ชม. และแนวโน้มฝน 3 วัน
- get_citizen_reports (Traffy), get_weather_warnings (กรมอุตุฯ), get_road_risk, get_bma_events

หลักการ
- ใช้ชื่อสถานี เขต ถนน และตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งตัวเลขหรือสถานที่
- วิเคราะห์ "3 น้ำ": น้ำเหนือ (เขื่อน/แม่น้ำตอนบน), น้ำทะเลหนุน (tide/สถานีปากแม่น้ำ), น้ำฝนในพื้นที่ (ฝน/คลอง/ถนน)
  ถ้าแหล่งใดไม่มีข้อมูล ให้บอกตรง ๆ ว่าไม่มีข้อมูล อย่าเดา
  status ของแต่ละน้ำเป็นคำไทยสั้น ๆ: ปกติ / เฝ้าระวัง / สูง / วิกฤต / ไม่มีข้อมูล
- zones: 2-4 พื้นที่ที่ควรจับตา จัดกลุ่มตามลุ่มน้ำ/ทำเล อ้างสถานีและตัวเลขใน evidence
- tone: red = วิกฤต/ล้นตลิ่ง, yellow = เสี่ยง, blue = เฝ้าระวัง, green = ปกติ
- measures: มาตรการของภาครัฐที่สอดคล้องกับสถานการณ์ตอนนี้ แบ่ง immediate (0-24 ชม.), medium (1-3 เดือน), long (โครงสร้างระยะยาว)
- public: คำแนะนำผู้ขับขี่ (drivers) และผู้อยู่อาศัยริมน้ำ/ที่ลุ่ม (residents) ที่เจาะจงพื้นที่ในข้อมูลเมื่อทำได้
- ภาษาไทย กระชับ ข้อความล้วน ไม่ใช้ Markdown ห้ามเขียนชื่อฟิลด์ภาษาอังกฤษในข้อความ"""

_ITEMS = {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "detail": {"type": "string"}},
                                     "required": ["title", "detail"], "additionalProperties": False}}
_WATER = {"type": "object", "properties": {"status": {"type": "string"}, "points": {"type": "array", "items": {"type": "string"}},
                                           "impact": {"type": "string"}},
          "required": ["status", "points", "impact"], "additionalProperties": False}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "string", "enum": list(LEVELS)},
        "status_label": {"type": "string"},
        "outlook_summary": {"type": "string"},
        "zones": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "tone": {"type": "string", "enum": ["red", "yellow", "blue", "green"]},
            "badge": {"type": "string"}, "areas": {"type": "string"}, "forecast": {"type": "string"},
            "evidence": {"type": "string"}}, "required": ["name", "tone", "badge", "areas", "forecast", "evidence"],
            "additionalProperties": False}},
        "three_waters": {"type": "object", "properties": {"upstream": _WATER, "tide": _WATER, "rain": _WATER},
                         "required": ["upstream", "tide", "rain"], "additionalProperties": False},
        "measures": {"type": "object", "properties": {"immediate": _ITEMS, "medium": _ITEMS, "long": _ITEMS},
                     "required": ["immediate", "medium", "long"], "additionalProperties": False},
        "public": {"type": "object", "properties": {"drivers": _ITEMS, "residents": _ITEMS},
                   "required": ["drivers", "residents"], "additionalProperties": False},
    },
    "required": ["level", "status_label", "outlook_summary", "zones", "three_waters", "measures", "public"],
    "additionalProperties": False,
}


class WaterAgent:
    def __init__(self, data_dir, flood_agent):
        self.path = os.path.join(data_dir, "water_agent.json")
        self.flood_agent = flood_agent
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.report, self.sig, self.checked_at, self.running, self.error = None, None, None, False, None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.report, self.sig = d.get("report"), d.get("sig")
        except (OSError, ValueError):
            pass

    def run(self, force=False):
        if not self.run_lock.acquire(blocking=False):
            return {**self.status(), "busy": True}
        try:
            facts, sig = self.flood_agent.facts()
            with self.lock:
                self.checked_at = int(time.time())
            age = time.time() - ((self.report or {}).get("generated_at") or 0)
            if not force and self.report and sig == self.sig and age < MAX_AGE:
                return self.status()
            if not local_llm.default.enabled():
                with self.lock:
                    self.error = "ยังไม่ได้ตั้งค่าโมเดล AI (LOCAL_LLM_MODEL)"
                return self.status()
            with self.lock:
                self.running = True
            started = time.time()
            prompt = (f"ข้อมูลสดทุกแหล่ง (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'), default=str)}\n\n"
                      f"เวลาปัจจุบัน {time.strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\nส่งบทวิเคราะห์เป็น JSON ตาม schema เท่านั้น")
            try:
                text = local_llm.default.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                                              max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=REPORT_SCHEMA)
                report = json.loads(text[text.find("{"):text.rfind("}") + 1])
            except Exception as e:  # noqa: BLE001 - server off, bad JSON: keep the last report
                with self.lock:
                    self.error = f"{local_llm.default.model}: {str(e)[:160]}"
                print(f"[WaterAgent] model failed: {e}")
                return self.status()
            if report.get("level") not in LEVELS:
                report["level"] = "watch"
            report.update({"model": local_llm.default.model, "generated_at": int(time.time()),
                           "took_s": round(time.time() - started, 1)})
            with self.lock:
                self.report, self.sig, self.error = report, sig, None
                try:
                    with open(self.path, "w", encoding="utf-8") as f:
                        json.dump({"report": report, "sig": sig}, f, ensure_ascii=False)
                except OSError as e:
                    print(f"[WaterAgent] save failed: {e}")
            return self.status()
        finally:
            with self.lock:
                self.running = False
            self.run_lock.release()

    def status(self):
        with self.lock:
            return {"report": self.report, "checked_at": self.checked_at, "running": self.running,
                    "error": self.error, "interval_s": POLL_SECONDS}

    def _loop(self):
        time.sleep(90)    # let the pollers fill their first answers
        while True:
            try:
                self.run()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[WaterAgent] run failed: {e}")
            time.sleep(POLL_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="WaterAgent").start()
