"""
The northern water explained in plain Thai, and which Bangkok districts it will reach, and when.

The "น้ำเหนือ → ภาคกลาง" tab: the AI model (local_llm.default, LOCAL_LLM_* in .env) reads north_flow's
outlook, the 10-minute discharge at each gauge and every district's own gauges, and writes as JSON by
REPORT_SCHEMA: a short plain summary for the public (easy), one or two sentences per gauge (points), and
which districts to watch, how badly, in which time window and why (districts).

Facts it gets (built by facts(), compact):
    north      headline and warnings of north_flow, the Chao Phraya gauges from Nakhon Sawan to Ayutthaya
               with their 4-day peak and travel time, and HII's 7-day level forecast at Nonthaburi
               (สะพานนวลฉวี, the last gauge above Bangkok) against its bank
    points     every gauge: the hourly RID discharge, the 10-minute estimate and its 10 min / 1 h change
    roads      the roads most exposed once the water reaches Nonthaburi and Bangkok (road_candidates), for a
               second call that picks and explains them (ROADS_PROMPT). Nonthaburi's come from river_roads:
               roads beside the Chao Phraya with the chance the river tops the bank next to them
    tide       today's sea tide at the river mouth
    around     river gauges in Nonthaburi, Pathum Thani and Nakhon Pathom that are over or near the bank
    districts  per district: where it lies (river bank, northern edge, eastern / western fields), its canal
               and river gauges against the bank, water on its roads, 24 h rain, and a rule score with the
               reasons behind it (_score)

Districts must be Bangkok's 50 (the schema enum); any other name is dropped. Without the model, or when
it fails, the rule-based report stands in so the card always has one. Runs every POLL_SECONDS; the model
is called again only when the facts changed or the report is older than MAX_AGE.
"""
import hashlib
import json
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.agents.flood_agent import ZONE_DISTRICTS
from backend.core import local_llm
from backend.water.north_flow import RIVERS, STATIONS, STATUS_TH

POLL_SECONDS = int(os.getenv("NORTH_IMPACT_SECONDS", "1800"))   # not below MAX_AGE: then every run writes a new report
MAX_AGE = int(os.getenv("NORTH_IMPACT_MAX_AGE", "1800"))
REPLY_TOKENS = int(os.getenv("NORTH_IMPACT_REPLY_TOKENS", "5000"))
BKK_TZ = timezone(timedelta(hours=7))
LEVELS = ("normal", "watch", "warning", "critical")
LEVEL_TH = {"normal": "ยังไม่กระทบ", "watch": "เฝ้าระวัง", "warning": "เตือนภัย", "critical": "วิกฤต"}
DISTRICT_LEVELS = ("สูง", "ปานกลาง", "เฝ้าระวัง")
DISTRICTS = [d for ds in ZONE_DISTRICTS.values() for d in ds.split()]
POINT_CODES = [code for code, *_ in STATIONS]

# Where each district lies relative to the way the northern water arrives
TAGS = {
    "river": ("ริมแม่น้ำเจ้าพระยา", {"บางซื่อ", "ดุสิต", "พระนคร", "สัมพันธวงศ์", "บางรัก", "สาทร", "ยานนาวา",
                                    "บางคอแหลม", "คลองเตย", "บางพลัด", "บางกอกน้อย", "บางกอกใหญ่", "ธนบุรี",
                                    "คลองสาน", "ราษฎร์บูรณะ", "ทุ่งครุ"}),
    "north": ("ติดนนทบุรี/ปทุมธานี", {"ดอนเมือง", "สายไหม", "คลองสามวา", "หนองจอก", "บางพลัด", "ตลิ่งชัน",
                                     "ทวีวัฒนา"}),
    "east": ("ทุ่งฝั่งตะวันออก", {"หนองจอก", "คลองสามวา", "มีนบุรี", "ลาดกระบัง"}),
    "west": ("ฝั่งตะวันตกติดนครปฐม/นนทบุรี", {"ทวีวัฒนา", "ตลิ่งชัน", "หนองแขม"}),
}
AROUND = ("นนทบุรี", "ปทุมธานี", "นครปฐม")
# Districts outside Bangkok the Chao Phraya runs through (road_service names them the way ThaiWater does)
RIVER_AMPHOE = {"ปากเกร็ด", "เมืองนนทบุรี", "บางกรวย", "เมืองปทุมธานี", "สามโคก", "พระประแดง", "เมืองสมุทรปราการ"}
# Bridges and elevated roads stay dry whatever the river does
ELEVATED = ("ทางพิเศษ", "ทางด่วน", "โทลล์เวย์", "ทางยกระดับ", "ลอยฟ้า", "มอเตอร์เวย์")
ROAD_LEVELS = DISTRICT_LEVELS

SYSTEM_PROMPT = """คุณคือนักวิเคราะห์ผลกระทบน้ำเหนือต่อกรุงเทพมหานคร (ศูนย์ปฏิบัติการ BKK StreetSmart)
หน้าที่: อ่านข้อมูลสดที่แนบมา แล้วประเมินว่าเขตใดของกรุงเทพฯ จะได้รับผลกระทบจากน้ำเหนือในอีก 1-7 วัน เมื่อใด และเพราะอะไร ส่งเป็น JSON

ข้อมูล
- north: น้ำเหนือจากนครสวรรค์ (C.2) ถึงอยุธยา (C.35) ปริมาณน้ำ ลบ.ม./วินาที, pct = % ของความจุลำน้ำ, peak = ค่าสูงสุดที่คาดใน 4 วัน (in_h = อีกกี่ชั่วโมง),
  from_c2_h = เวลาเดินทางจากนครสวรรค์, nonthaburi_hii = สสน. คาดระดับน้ำ 7 วันที่สะพานนวลฉวี (สถานีสุดท้ายก่อนเข้ากรุงเทพฯ) เทียบตลิ่ง
- points: ทุกจุดวัดจากภาคเหนือลงมา q = ปริมาณน้ำที่กรมชลประทานรายงาน (รายชั่วโมง เวลา q_time),
  now_10min = ค่าตอนนี้ (ประมาณทุก 10 นาทีจากระดับน้ำ ใหม่กว่า q ไม่ใช่ค่าคาดการณ์) พร้อม change_10m / change_1h = เพิ่ม(+)/ลด(-) ใน 10 นาที / 1 ชั่วโมง
  peak = ค่าคาดการณ์เดียวที่ใช้บอกอนาคต ถ้าจุดไหนไม่มี peak ห้ามบอกว่าจะเพิ่มถึงเท่าไร
- tide: น้ำทะเลหนุนวันนี้ที่ปากแม่น้ำ (ม.รทก.)
- around: สถานีแม่น้ำในนนทบุรี ปทุมธานี นครปฐม ที่ล้นหรือใกล้ตลิ่ง
- districts: รายเขต tags = ทำเล, gauges = สถานีคลอง/แม่น้ำในเขตที่ล้นหรือใกล้ตลิ่ง (bank = ห่างจากตลิ่ง), road_cm = น้ำบนถนนสูงสุด, rain_24h_mm,
  rule_level/rule_reasons = การประเมินตามเกณฑ์ของระบบ (ใช้เป็นจุดเริ่ม ปรับได้ถ้ามีเหตุผลจากข้อมูล)

หลักการ
- น้ำเหนือเข้ากรุงเทพฯ 2 ทาง: ตามแม่น้ำเจ้าพระยา (เขตริมแม่น้ำ โดยเฉพาะชุมชนนอกแนวคันกั้นน้ำ เสี่ยงเมื่อระดับที่นนทบุรีใกล้/เกินตลิ่ง และหนักขึ้นช่วงน้ำทะเลหนุน)
  และทางบกจากทุ่งปทุมธานี/นนทบุรี/นครปฐมที่น้ำล้น (เขตขอบเหนือ ทุ่งตะวันออก ฝั่งตะวันตก)
- ระบุเวลาเป็นช่วงวันที่หรือจำนวนวัน โดยคำนวณจาก peak.in_h, from_c2_h และวันที่ในคาดการณ์ สสน. ห้ามเดาวันที่ที่ไม่มีข้อมูลรองรับ
- ใช้เฉพาะเขต ชื่อสถานี และตัวเลขที่อยู่ในข้อมูล ห้ามแต่งตัวเลข ถ้าข้อมูลไม่พอให้บอกว่าไม่พอ
- districts: 3-12 เขตที่ควรจับตา เรียงจากเสี่ยงมากไปน้อย level = สูง / ปานกลาง / เฝ้าระวัง
  when = ช่วงเวลาสั้น ๆ เช่น "ตอนนี้" "อีก 2-3 วัน" "ราว 5 ต.ค.", cause = น้ำมาทางไหน 1 ประโยคสั้นภาษาง่าย,
  evidence = ตัวเลขที่ใช้, advice = สิ่งที่ประชาชนในเขตควรทำ 1 ประโยคสั้น
- watch_points: 2-4 สถานีหรือตัวเลขที่ประชาชนควรติดตามต่อ พร้อมค่าที่ต้องระวัง (ไม่ใช่รายชื่อเขต)
- title: หัวข้อเดียวไม่เกิน 10 คำ บอกสถานการณ์ตอนนี้ให้คนทั่วไปเข้าใจทันที เช่น "น้ำเหนือกำลังมา อยุธยาล้นตลิ่งแล้ว"
- easy: 3 ประโยคสั้นสำหรับคนทั่วไปที่ไม่รู้เรื่องน้ำ ประโยคละไม่เกิน 20 คำ ตามลำดับ
  (1) ตอนนี้น้ำเหนือมากแค่ไหน กำลังขึ้นหรือลง (2) น้ำจะถึงอยุธยา/นนทบุรี/กรุงเทพฯ เมื่อไร (3) ใครควรเตรียมตัว
  เขียนเหมือนพูดกับชาวบ้าน ใช้ชื่อจังหวัด/เขต ห้ามใช้รหัสสถานี ชื่อย่อหน่วยงาน (เช่น สสน.) และหน่วยวัด (ลบ.ม./วินาที, ม.รทก.)
  ตัวเลขใช้ได้เฉพาะเปอร์เซ็นต์ จำนวนวัน และวันที่ ไม่ต้องบอกวิธีรับมือ (อยู่ใน actions แล้ว)
- actions: 2-3 สิ่งที่ประชาชนควรทำตอนนี้ ข้อละประโยคสั้นไม่เกิน 15 คำ เหมาะกับสถานการณ์ในข้อมูล
- points: ทุกจุดใน points จุดละ 1-2 ประโยค เหมือนอธิบายให้ชาวบ้านฟัง: เริ่มด้วยแม่น้ำและจังหวัด แล้วบอกว่าน้ำเต็มลำน้ำกี่เปอร์เซ็นต์
  (ยังรับได้อีก/ใกล้เต็ม/ล้นแล้ว) กำลังขึ้นหรือลง เร็วหรือช้า (ใช้ now_10min ถ้ามี) และถ้ามี peak ให้บอกว่าจะเพิ่มถึงเท่าไรในอีกกี่ชั่วโมง/วัน
  ใส่ตัวเลขปริมาณน้ำได้ 1 ค่า ไม่ต้องใส่ระดับเทียบตลิ่งถ้ามีเปอร์เซ็นต์แล้ว ห้ามใส่ชื่อสถานี
  ตัวอย่าง: "แม่น้ำเจ้าพระยาที่นครสวรรค์ น้ำเต็มลำน้ำราว 62% ยังรับได้อีก กำลังเพิ่มช้า ๆ และคาดว่าจะเพิ่มถึงราว 2,700 ลบ.ม./วินาที ในอีกราว 11 ชั่วโมง"
- level ภาพรวม: normal = น้ำเหนือยังไม่กระทบกรุงเทพฯ, watch = ต้องจับตา, warning = คาดว่าบางเขตได้รับผลกระทบ, critical = ท่วมเป็นวงกว้าง
- ภาษาไทย กระชับ ข้อความล้วน ไม่ใช้ Markdown ห้ามเขียนชื่อฟิลด์ภาษาอังกฤษในข้อความ"""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "string", "enum": list(LEVELS)},
        "summary": {"type": "string"},
        "timeline": {"type": "array", "items": {"type": "object", "properties": {
            "when": {"type": "string"}, "event": {"type": "string"}},
            "required": ["when", "event"], "additionalProperties": False}},
        "districts": {"type": "array", "items": {"type": "object", "properties": {
            "district": {"type": "string", "enum": DISTRICTS}, "level": {"type": "string", "enum": list(DISTRICT_LEVELS)},
            "when": {"type": "string"}, "cause": {"type": "string"}, "evidence": {"type": "string"},
            "advice": {"type": "string"}},
            "required": ["district", "level", "when", "cause", "evidence", "advice"], "additionalProperties": False}},
        "watch_points": {"type": "array", "items": {"type": "string"}},
        "title": {"type": "string"},
        "easy": {"type": "array", "items": {"type": "string"}},
        "actions": {"type": "array", "items": {"type": "string"}},
        "points": {"type": "array", "items": {"type": "object", "properties": {
            "code": {"type": "string", "enum": POINT_CODES}, "text": {"type": "string"}},
            "required": ["code", "text"], "additionalProperties": False}},
    },
    "required": ["level", "title", "easy", "actions", "summary", "timeline", "points", "districts", "watch_points"],
    "additionalProperties": False,
}

ROADS_PROMPT = """คุณคือนักวิเคราะห์ถนนเสี่ยงน้ำท่วมของกรุงเทพฯ และนนทบุรี (ศูนย์ปฏิบัติการ BKK StreetSmart)
คำถาม: ถ้าน้ำเหนือมาถึงนนทบุรีและกรุงเทพฯ ตามที่คาดการณ์ ถนนสายไหนเสี่ยงน้ำท่วม เมื่อไร และผู้ใช้ถนนควรทำอย่างไร

ข้อมูล
- scenario: น้ำเหนือที่อยุธยา ค่าคาดการณ์ สสน. ที่สะพานนวลฉวี นนทบุรี เทียบตลิ่ง (margin_m บวก = สูงกว่าตลิ่ง) และน้ำทะเลหนุน
- roads: ถนนที่ระบบคัดมาแล้ว พร้อม reasons ถนนนนทบุรีมี p = โอกาสน้ำท่วมถนนช่วงติดแม่น้ำ (0-1) และ distance_m = ระยะจากแม่น้ำ
  คิดจากโอกาสที่แม่น้ำเจ้าพระยาที่สะพานนวลฉวีจะสูงกว่าตลิ่ง (คาดการณ์ สสน. + ความไม่แน่นอน) คูณน้ำหนักตามระยะห่างจากแม่น้ำ
  ให้บอกโอกาสเป็นเปอร์เซ็นต์ใน why ของถนนนนทบุรี (ริมแม่น้ำ/ใกล้สถานีแม่น้ำ, มีจุดวัดน้ำท่วมของ กทม. = จุดที่เคยท่วมบ่อย,
  น้ำบนถนนตอนนี้ ซม., คลองข้างถนนใกล้เต็ม/ล้น, ฝน 24 ชม., เขตที่เสี่ยง) และ rule_level = การประเมินตามเกณฑ์

หลักการ
- เลือก 5-15 สายที่เสี่ยงจริงจากรายการ roads เท่านั้น เรียงจากเสี่ยงมากไปน้อย level = สูง / ปานกลาง / เฝ้าระวัง
  ถ้ามีถนนในนนทบุรีในรายการ ให้เลือกไว้อย่างน้อย 2 สาย เพราะผู้ใช้ถามถึงนนทบุรีด้วย
- ถนนริมแม่น้ำเสี่ยงช่วงระดับน้ำที่นนทบุรีใกล้/เกินตลิ่งและช่วงน้ำทะเลหนุน ถนนที่คลองข้างเต็มจะระบายน้ำฝนไม่ทัน
- why: 1-2 ประโยคภาษาง่ายว่าทำไมเสี่ยง อ้างตัวเลขจาก reasons
- when: ช่วงเวลาที่ควรระวัง จากข้อมูลเท่านั้น (ตอนนี้ / ช่วงน้ำขึ้นเช้า / ราววันที่ในคาดการณ์ สสน.)
- advice: คำแนะนำผู้ใช้ถนนสั้น ๆ เช่น ขับช้า เลี่ยงช่วงน้ำขึ้น ไม่ขับฝ่าน้ำเกิน 20 ซม. ห้ามแนะนำถนนหรือสถานที่ที่ไม่อยู่ในข้อมูล
- summary: 1-2 ประโยคภาพรวมว่าถนนย่านไหนน่าห่วงที่สุด
- ภาษาไทย ข้อความล้วน ไม่ใช้ Markdown ห้ามแต่งตัวเลข"""

NB_PROMPT = """คุณคือนักวิเคราะห์น้ำท่วมถนนในจังหวัดนนทบุรี (ศูนย์ปฏิบัติการ BKK StreetSmart)
คำถาม: ถ้าแม่น้ำเจ้าพระยาที่นนทบุรีล้นตลิ่งใน 7 วันนี้ ถนนสายไหนจะท่วม และแต่ละสายช่วงไหนเสี่ยงที่สุด รองลงมา

ข้อมูล
- river: โอกาสที่ระดับน้ำที่สะพานนวลฉวีจะสูงกว่าตลิ่ง (p7, 0-1) วันที่เสี่ยงที่สุด ระดับที่คาดและตลิ่ง
- roads: ถนนที่เสี่ยง เรียงจากโอกาสมากไปน้อย p = โอกาสของช่วงที่เสี่ยงที่สุด (0-1), stretches = ช่วงของถนนเรียงจากเสี่ยงมากไปน้อย
  แต่ละช่วงมี place (ช่วงตัดถนน/ตำบล/อำเภอ), distance_m (ห่างแม่น้ำ), p
- counts: จำนวนถนนทั้งหมดในนนทบุรีแยกตามระดับ

หลักการ
- roads: ทุกสายในรายการ เขียน text 1-2 ประโยคภาษาง่าย: ช่วงไหนเสี่ยงที่สุด (ใช้ place และระยะห่าง) โอกาสกี่เปอร์เซ็นต์
  ช่วงไหนรองลงมา และผู้ใช้ถนนควรทำอะไร ใช้ชื่อสถานที่และตัวเลขจากข้อมูลเท่านั้น
- summary: 2-3 ประโยคภาพรวมว่าอำเภอ/ตำบลไหนน่าห่วงที่สุด มีถนนเสี่ยงกี่สาย และวันที่ควรระวัง
- ปัดเปอร์เซ็นต์เป็นจำนวนเต็ม ใช้ชื่อถนน ตำบล อำเภอ ตามข้อมูลทุกตัวอักษร แม้ชื่อบางชื่อจะถูกตัดท้าย ห้ามเดาหรือเติมชื่อ
- บอกตรง ๆ ว่าโอกาสเป็นการประเมินจากค่าคาดการณ์และระยะห่างจากแม่น้ำ ไม่รวมแนวกั้นน้ำ
- ภาษาไทย ข้อความล้วน ไม่ใช้ Markdown"""

TH_MONTHS = ("", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")


def _day(ts):
    d = datetime.fromtimestamp(ts, BKK_TZ)
    return f"{d.day} {TH_MONTHS[d.month]}"


def _in_days(hours):
    return f"~{hours} ชม." if hours < 36 else f"~{hours / 24:.1f} วัน".replace(".0 ", " ")


def _ahead(hours):
    """Hours ahead in plain words for the public: hours within a day, whole days after that."""
    return f"{max(1, round(hours))} ชม." if hours < 24 else f"{round(hours / 24)} วัน"


# ---------------------------------------------------------------- facts + rule score
def _north_facts(north):
    by = {s["code"]: s for s in north.get("stations") or []}
    main = []
    for code in ("C.2", "C.13", "C.3", "C.7A", "C.35", "S.26"):
        s = by.get(code)
        if not s or s.get("q") is None:
            continue
        row = {"code": code, "province": s["province"], "q": s["q"], "pct": s.get("pct"), "status": s["status"],
               "change_24h": s.get("change_24h"), "from_c2_h": s.get("from_c2_h")}
        if s.get("peak"):
            row["peak"] = {k: s["peak"].get(k) for k in ("q", "pct", "in_h")}
        main.append(row)
    bkk = north.get("bangkok")
    hii = None
    if bkk:
        hii = {"now_msl": bkk.get("now_msl"), "bank": bkk.get("bank"), "peak_msl": bkk.get("peak_msl"),
               "peak_day": _day(bkk["peak_t"]), "over_bank_from": _day(bkk["over_bank_t"]) if bkk.get("over_bank_t") else None}
    return {"headline": (north.get("headline") or {}).get("text"), "alerts": [a["text"] for a in north.get("alerts") or []][:8],
            "chao_phraya": main, "nonthaburi_hii": hii}


def _hhmm(ts):
    return datetime.fromtimestamp(ts, BKK_TZ).strftime("%H:%M") if ts else None


def _point_facts(north):
    """Every gauge with a reading, upstream first: hourly RID discharge and the 10-minute estimate."""
    out = []
    for s in north.get("stations") or []:
        if s.get("status") == "offline":
            continue
        row = {"code": s["code"], "place": s["province"], "river": RIVERS.get(s.get("river"), ""),
               "status": STATUS_TH.get(s["status"], s["status"]), "q": s.get("q"), "q_time": _hhmm(s.get("ts")),
               "pct": s.get("pct"), "change_24h": s.get("change_24h"), "below_bank_m": s.get("below_bank"),
               "from_c2_h": s.get("from_c2_h")}
        latest = s.get("q")
        if s.get("latest10"):
            l10 = s["latest10"]
            latest = l10["q"]
            row["now_10min"] = {"q": l10["q"], "time": _hhmm(l10["t"]), "change_10m": l10.get("change_10m"),
                                "change_1h": l10.get("change_1h")}
            if s.get("qmax"):
                row["pct"] = round(100 * l10["q"] / s["qmax"], 1)
        # Only a peak still ahead: the hourly outlook can sit below the fresher 10-minute figure
        if s.get("peak") and latest is not None and s["peak"]["q"] > latest * 1.03:
            row["peak"] = {k: s["peak"].get(k) for k in ("q", "pct", "in_h")}
        out.append({k: v for k, v in row.items() if v is not None})
    return out


def trend_text(p):
    """Rising / steady / falling in words, from the 10-minute 1 h change when there is one, else 24 h."""
    now = p.get("now_10min") or {}
    q = now.get("q") or p.get("q")
    if q is None:
        return ""
    if now.get("change_1h") is not None:
        ch, span, thr = now["change_1h"], "1 ชม.", max(5, 0.005 * q)
    elif p.get("change_24h") is not None:
        ch, span, thr = p["change_24h"], "24 ชม.", max(20, 0.03 * q)
    else:
        return ""
    if ch >= thr:
        return f"กำลังเพิ่มขึ้น +{ch:,.0f} ใน {span}"
    if ch <= -thr:
        return f"กำลังลดลง {ch:,.0f} ใน {span}"
    return "ทรงตัว"


def point_text(p):
    """One plain sentence for a gauge when the model is not there to write it."""
    province = p["place"]
    now = p.get("now_10min") or {}
    q = now.get("q") or p.get("q")
    if q is None:
        bb = p.get("below_bank_m")
        if bb is None:
            return f"{province}: ไม่มีข้อมูลล่าสุด"
        return f"{province}: ระดับน้ำ{'ต่ำกว่า' if bb > 0 else 'สูงกว่า'}ตลิ่ง {abs(bb):.2f} ม. (จุดนี้ไม่มีข้อมูลปริมาณน้ำ)"
    text = f"{province}: น้ำไหลผ่าน {q:,} ลบ.ม. ทุกวินาที"
    if p.get("pct") is not None:
        text += f" ประมาณ {p['pct']:.0f}% ของที่ลำน้ำรับได้ ({p['status']})"
    trend = trend_text(p)
    if trend:
        text += f" · {trend}"
    pk = p.get("peak")
    if pk and pk.get("q") and pk["q"] > q * 1.03:
        text += f" · คาดว่าจะเพิ่มถึง {pk['q']:,} ในอีก {_in_days(pk['in_h'])}"
    return text


def _score(tags, local, north, around):
    """Rule score 0-100 and the reasons, from where the district lies, the water coming down and its own gauges."""
    score, why = 0, []
    hii = north.get("nonthaburi_hii") or {}
    c35 = next((s for s in north.get("chao_phraya") or [] if s["code"] == "C.35"), None)
    c35_pct = max((c35 or {}).get("pct") or 0, ((c35 or {}).get("peak") or {}).get("pct") or 0)
    if "river" in tags and hii.get("bank") is not None and hii.get("peak_msl") is not None:
        margin = hii["peak_msl"] - hii["bank"]
        if margin >= 0:
            score += 35
            why.append(f"สสน. คาดระดับน้ำที่นนทบุรีสูงกว่าตลิ่ง {margin:.2f} ม. ราว {hii['peak_day']} (ชุมชนนอกแนวคันกั้นน้ำ)")
        elif margin > -0.3:
            score += 20
            why.append(f"สสน. คาดระดับน้ำที่นนทบุรีต่ำกว่าตลิ่งเพียง {-margin:.2f} ม. ราว {hii['peak_day']}")
    if "river" in tags and c35_pct >= 100:
        score += 10
        why.append(f"อยุธยา (C.35) ล้น/คาดล้นความจุ {c35_pct:.0f}%")
    if tags & {"north", "east"} and (c35_pct >= 100 or around["ปทุมธานี"] or around["นนทบุรี"]):
        score += 20
        why.append("น้ำล้นทุ่งเหนือกรุงเทพฯ: " + ", ".join(
            ([f"อยุธยา C.35 {c35_pct:.0f}%"] if c35_pct >= 100 else []) + around["ปทุมธานี"][:2] + around["นนทบุรี"][:2]))
    if "west" in tags and around["นครปฐม"]:
        score += 15
        why.append("สถานีนครปฐมล้นตลิ่ง: " + ", ".join(around["นครปฐม"][:2]))
    over = [g for g in local["gauges"] if g["status"] == "overflow"]
    high = [g for g in local["gauges"] if g["status"] == "high"]
    if over:
        score += min(30, 20 * len(over))
        why.append("ล้นตลิ่งแล้ว: " + ", ".join(g["name"] for g in over[:3]))
    if high:
        score += min(20, 10 * len(high))
        why.append("ใกล้ตลิ่ง: " + ", ".join(g["name"] for g in high[:3]))
    if local["road_cm"]:
        score += 20 if local["road_cm"] >= 10 else 5
        why.append(f"น้ำบนถนน {local['road_cm']:.0f} ซม.")
    if local["rain_24h_mm"] >= 35:
        score += 20 if local["rain_24h_mm"] >= 90 else 10
        why.append(f"ฝน 24 ชม. {local['rain_24h_mm']:.0f} มม.")
    score = min(100, score)
    level = "สูง" if score >= 60 else "ปานกลาง" if score >= 35 else "เฝ้าระวัง" if score >= 15 else None
    return score, level, why


def _gap(diff):
    if diff is None:
        return None
    return f"ต่ำกว่าตลิ่ง {diff:.2f} ม." if diff > 0 else f"สูงกว่าตลิ่ง {-diff:.2f} ม."


def nonthaburi_candidates(nb, limit=8):
    """Nonthaburi roads beside the river from river_roads, with the chance in the reasons."""
    if not nb:
        return []
    chance = nb.get("river") or {}
    top = chance.get("likeliest") or {}
    out = []
    for r in (nb.get("roads") or [])[:limit]:
        if r["p"] < 0.1:
            continue
        out.append({"road": r["road"], "province": "นนทบุรี", "district": "", "lat": r["lat"], "lng": r["lng"],
                    "score": round(100 * r["p"]), "rule_level": "สูง" if r["p"] >= 0.6 else "ปานกลาง" if r["p"] >= 0.3 else "เฝ้าระวัง",
                    "reasons": [f"ช่วงที่ใกล้แม่น้ำเจ้าพระยาที่สุดห่างราว {r['km'] * 1000:.0f} ม.",
                                f"โอกาสน้ำเจ้าพระยาที่นนทบุรีสูงกว่าตลิ่ง {chance.get('p7', 0):.0%}"
                                + (f" (สูงสุดวันที่ {top.get('date')} คาด {top.get('peak')} ม.รทก. ตลิ่ง {chance.get('bank')})" if top else ""),
                                f"โอกาสน้ำท่วมถนนช่วงติดแม่น้ำราว {r['p']:.0%}"],
                    "river_side": True, "flood_cm": None, "p": r["p"], "distance_m": round(r["km"] * 1000)})
    return out


def road_candidates(road_rows, facts, nonthaburi=None):
    """Roads most exposed once the northern water reaches Nonthaburi and Bangkok, with the reasons, best first.
    Score from where the road lies (a district on the Chao Phraya, the northern edge),
    the BMA flood sensors on it (placed where roads flood often) and what it carries now: water on it, a
    full canal beside it, heavy rain. Bridges and elevated roads are left out."""
    hii = facts["north"].get("nonthaburi_hii") or {}
    margin = hii["peak_msl"] - hii["bank"] if hii.get("peak_msl") is not None and hii.get("bank") is not None else None
    c35 = next((s for s in facts["north"].get("chao_phraya") or [] if s["code"] == "C.35"), None)
    north_high = max((c35 or {}).get("pct") or 0, ((c35 or {}).get("peak") or {}).get("pct") or 0) >= 100 or any(
        a["status"] == "overflow" and a["province"] in ("นนทบุรี", "ปทุมธานี") for a in facts.get("around") or [])
    district_level = {r["district"]: r["rule_level"] for r in facts["districts"] if r["rule_level"]}
    edge = TAGS["north"][1] | TAGS["east"][1] | TAGS["west"][1]
    best = {}
    nb = nonthaburi_candidates(nonthaburi)
    for r in road_rows or []:
        name = (r.get("road") or "").strip()
        if not name or name.startswith("สะพาน") or any(k in name for k in ELEVATED):
            continue
        prov, dist = r.get("province") or "", r.get("district") or ""
        if nb and prov == "นนทบุรี":
            continue        # the riverside list below covers Nonthaburi with distances and chances
        score, why = 0, []
        # By district: ThaiWater files some canal gauges as rivers, so the nearest "river" gauge proves nothing
        river_side = dist in TAGS["river"][1] if prov == "กรุงเทพมหานคร" else dist in RIVER_AMPHOE
        if river_side and margin is not None and margin > -0.3:
            score += 30 if margin >= 0 else 15
            why.append(f"อยู่ใน{'เขต' if prov == 'กรุงเทพมหานคร' else 'อำเภอ'}ริมแม่น้ำเจ้าพระยา สสน. คาดระดับน้ำที่นนทบุรี"
                       + (f"สูงกว่าตลิ่ง {margin:.2f} ม." if margin >= 0 else f"ต่ำกว่าตลิ่งเพียง {-margin:.2f} ม.")
                       + f" ราว {hii['peak_day']}")
        if north_high and ((prov == "กรุงเทพมหานคร" and dist in edge) or (prov in ("นนทบุรี", "ปทุมธานี") and not river_side)):
            score += 15
            why.append("อยู่ขอบเมืองด้านที่น้ำเหนืออาจไหลบ่าเข้ามาทางทุ่ง")
        if r.get("sensors"):
            score += 10
            why.append("มีจุดวัดน้ำท่วมของ กทม. บนถนน (จุดที่เคยท่วมบ่อย)")
        cm = r.get("flood_cm") or 0
        if cm >= 5:
            score += 30 if cm >= 10 else 15
            why.append(f"ตอนนี้มีน้ำบนถนน {cm:.0f} ซม. ที่{(r.get('flood_at') or 'จุดวัด').rstrip(' *')}")
        pct = r.get("gauge_pct")
        if r.get("gauge_kind") == "canal" and pct is not None and pct >= 80:
            score += 20 if pct >= 100 else 10
            why.append(f"คลองข้างถนน ({r.get('gauge_at')}) {'ล้นตลิ่ง' if pct >= 100 else 'ใกล้เต็ม'} {pct:.0f}% ระบายน้ำฝนได้ช้า")
        if (r.get("rain_24h") or 0) >= 35:
            score += 10
            why.append(f"ฝน 24 ชม. {r['rain_24h']:.0f} มม.")
        lv = district_level.get(dist) if prov == "กรุงเทพมหานคร" else None
        if lv in ("สูง", "ปานกลาง"):
            score += 10 if lv == "สูง" else 5
            why.append(f"เขต{dist}อยู่ในกลุ่มเสี่ยง{lv}")
        if score < 20 or not why:
            continue
        score = min(100, score)
        row = {"road": name, "province": prov, "district": dist, "lat": r.get("lat"), "lng": r.get("lng"),
               "score": score, "rule_level": "สูง" if score >= 60 else "ปานกลาง" if score >= 35 else "เฝ้าระวัง",
               "reasons": why, "river_side": river_side, "flood_cm": cm or None}
        if name not in best or best[name]["score"] < score:
            best[name] = row
    # Bangkok has the road sensors and would fill the list alone: keep room for Nonthaburi and the rest
    ranked = sorted(best.values(), key=lambda x: -x["score"])
    bkk = [r for r in ranked if r["province"] == "กรุงเทพมหานคร"][:22]
    # Nonthaburi first among them: its gauge is the one the forecast is for
    rest = sorted((r for r in ranked if r["province"] != "กรุงเทพมหานคร"), key=lambda x: (x["province"] != "นนทบุรี", -x["score"]))
    rest = (nb + rest)[:8]
    return sorted(bkk + rest, key=lambda x: -x["score"])


def rules_roads(facts):
    """The road list without the model: the rule levels, with the reasons as they are."""
    hii = facts["north"].get("nonthaburi_hii") or {}
    out = []
    for r in facts.get("roads") or []:
        if r["rule_level"] == "เฝ้าระวัง" and len(out) >= 8:
            continue
        out.append({"road": r["road"], "level": r["rule_level"],
                    "when": "ตอนนี้" if r.get("flood_cm") else f"ราว {hii['peak_day']}" if r["river_side"] and hii.get("peak_day") else "ช่วงฝนตกหนัก",
                    "why": " · ".join(r["reasons"]),
                    "advice": ("เลี่ยงช่วงน้ำขึ้นสูง ติดตามประกาศปิดถนน" if r["river_side"]
                               else "ขับช้า ไม่ขับฝ่าน้ำเกิน 20 ซม. เลี่ยงช่วงฝนตกหนัก")})
    return {"summary": "ถนนที่เข้าเกณฑ์เสี่ยงตามข้อมูลตอนนี้" if out else "ยังไม่มีถนนที่เข้าเกณฑ์เสี่ยงจากน้ำเหนือ", "roads": out[:15]}


def nb_brief(nb, limit=15):
    """The Nonthaburi road list, trimmed for the model: roads at 10% or more with their top three stretches."""
    if not nb:
        return None
    ch = nb.get("river") or {}
    roads = []
    for r in nb.get("roads") or []:
        if r["p"] < 0.1 or len(roads) >= limit:
            continue
        roads.append({"road": r["road"], "amphoe": r.get("amphoe"), "p": r["p"],
                      "stretches": [{"place": s["place"], "distance_m": round(s["km"] * 1000) if s.get("km") is not None else None,
                                     "p": s["p"]} for s in (r.get("stretches") or [])[:3]]})
    return {"river": {k: ch.get(k) for k in ("bank", "now", "p7", "likeliest")}, "counts": nb.get("counts"),
            "total": nb.get("total"), "roads": roads}


def rules_nb(brief):
    """The Nonthaburi read without the model, in the same shape."""
    if not brief or not brief["roads"]:
        return {"summary": "ยังไม่มีถนนในนนทบุรีที่เข้าเกณฑ์เสี่ยงจากน้ำเจ้าพระยา", "roads": []}
    ch = brief["river"]
    top = ch.get("likeliest") or {}
    out = []
    for r in brief["roads"]:
        s = r["stretches"]
        text = f"เสี่ยงที่สุด{s[0]['place']} ห่างแม่น้ำราว {s[0]['distance_m']} ม. โอกาส {s[0]['p']:.0%}" if s else ""
        if len(s) > 1:
            text += f" · รองลงมา{s[1]['place']} ({s[1]['p']:.0%})"
        out.append({"road": r["road"], "text": text})
    c = brief.get("counts") or {}
    return {"summary": f"ถนนในนนทบุรี {brief.get('total')} สาย เสี่ยงสูง {c.get('สูง', 0)} ปานกลาง {c.get('ปานกลาง', 0)} "
                       f"เฝ้าระวัง {c.get('เฝ้าระวัง', 0)} สาย · โอกาสน้ำเจ้าพระยาสูงกว่าตลิ่งสูงสุด {ch.get('p7', 0):.0%}"
                       + (f" วันที่ {top.get('date')}" if top else ""), "roads": out}


def build_facts(north, water_map, roads, rain, tide, road_rows=None, nonthaburi=None):
    """Everything the model and the rules read, keyed as SYSTEM_PROMPT describes."""
    nf = _north_facts(north)
    water = water_map.get("water") or []
    around = {p: [f"{w['name']} ({w['district']})" for w in water
                  if w["province"] == p and w["kind"] == "river" and w.get("status") == "overflow"] for p in AROUND}
    near = [{"name": w["name"], "district": w["district"], "province": w["province"], "status": w["status"]}
            for w in water if w["province"] in AROUND and w["kind"] == "river" and w.get("status") in ("overflow", "high")]
    road_max = {}
    for s in (roads or {}).get("wet") or []:
        road_max[s.get("district")] = max(road_max.get(s.get("district"), 0), s.get("level_cm") or 0)
    rain_max = {}
    for r in rain or []:
        if r.get("province") == "กรุงเทพมหานคร":
            rain_max[r["district"]] = max(rain_max.get(r["district"], 0), r.get("rain_24h") or 0)
    rows = []
    for d in DISTRICTS:
        tags = {k for k, (_, names) in TAGS.items() if d in names}
        gauges = [{"name": w["name"], "kind": w["kind"], "status": w["status"], "bank": _gap(w.get("diff_bank"))}
                  for w in water
                  if w["province"] == "กรุงเทพมหานคร" and w["district"] == d and w.get("status") in ("overflow", "high")]
        local = {"gauges": gauges, "road_cm": road_max.get(d, 0), "rain_24h_mm": rain_max.get(d, 0)}
        score, level, why = _score(tags, local, nf, around)
        if not tags and not level:
            continue
        rows.append({"district": d, "tags": [TAGS[k][0] for k in sorted(tags)], "gauges": gauges[:4],
                     "road_cm": local["road_cm"] or None, "rain_24h_mm": local["rain_24h_mm"] or None,
                     "rule_score": score, "rule_level": level, "rule_reasons": why})
    rows.sort(key=lambda r: -r["rule_score"])
    facts = {"north": nf, "points": _point_facts(north),
             "tide": [{"name": t.get("name"), "max": t.get("max"), "max_time": t.get("max_time")} for t in (tide or [])[:3]],
             "around": near[:12], "districts": rows}
    facts["roads"] = road_candidates(road_rows, facts, nonthaburi)
    if nonthaburi:
        ch = nonthaburi.get("river") or {}
        facts["nonthaburi_river"] = {k: ch.get(k) for k in ("bank", "now", "p7", "likeliest", "observed_peaks")}
        facts["nonthaburi"] = nb_brief(nonthaburi)
    return facts


def rules_report(facts):
    """The card without the model: the rule levels as they are, in plain Thai."""
    rows = [r for r in facts["districts"] if r["rule_level"]]
    worst = rows[0]["rule_level"] if rows else None
    level = {"สูง": "warning", "ปานกลาง": "watch", "เฝ้าระวัง": "watch"}.get(worst, "normal")
    hii = facts["north"].get("nonthaburi_hii") or {}
    c35 = next((s for s in facts["north"].get("chao_phraya") or [] if s["code"] == "C.35"), None)
    timeline = []
    if c35 and c35.get("peak"):
        timeline.append({"when": f"อีก {_in_days(c35['peak']['in_h'])}",
                         "event": f"น้ำเหนือที่อยุธยา (C.35) คาดสูงสุด {c35['peak']['q']:,} ลบ.ม./วินาที ({c35['peak']['pct']:.0f}% ของความจุลำน้ำ)"})
    if hii.get("peak_msl") is not None and hii.get("bank") is not None:
        timeline.append({"when": hii["peak_day"],
                         "event": f"สสน. คาดระดับน้ำที่สะพานนวลฉวี นนทบุรี สูงสุด {hii['peak_msl']:.2f} ม.รทก. (ตลิ่ง {hii['bank']:.2f})"})
    districts = []
    for r in rows[:12]:
        river = "ริมแม่น้ำเจ้าพระยา" in r["tags"]
        local = bool(r["gauges"] or r["road_cm"])
        districts.append({
            "district": r["district"], "level": r["rule_level"],
            "when": (f"ราว {hii['peak_day']}" if river and hii.get("peak_day") else "ตอนนี้" if local else "1-3 วัน"),
            "cause": " / ".join(r["tags"] + (["คลอง/ถนนในเขตมีน้ำสูงอยู่แล้ว"] if local else [])) or "ข้อมูลในเขต",
            "evidence": " · ".join(r["rule_reasons"]),
            "advice": ("ชุมชนริมน้ำนอกแนวคันกั้นน้ำ ยกของขึ้นที่สูง ติดตามเวลาน้ำขึ้นสูงสุด" if river
                       else "ติดตามระดับคลองในเขต เตรียมกระสอบทรายและย้ายรถขึ้นที่สูง"),
        })
    # The same three plain sentences SYSTEM_PROMPT asks the model for: the north now, when it arrives, who prepares
    points = {p["code"]: p for p in facts.get("points") or []}
    easy = []
    c2 = points.get("C.2")
    if c2 and c2.get("pct") is not None:
        trend = trend_text(c2).split(" ")[0]
        easy.append("แม่น้ำเจ้าพระยาที่นครสวรรค์" + ("ล้นตลิ่งแล้ว" if c2["pct"] >= 100 else f"มีน้ำ {c2['pct']:.0f}% ของที่แม่น้ำรับได้")
                    + (f" และน้ำ{trend}" if trend else ""))
    arrival = []
    if c35:
        arrival.append(f"อยุธยา{'ล้นตลิ่งแล้ว' if (c35.get('pct') or 0) >= 100 else 'ยังไม่ล้นตลิ่ง'}"
                       + (f" และจะสูงที่สุดในอีกราว {_ahead(c35['peak']['in_h'])}" if c35.get("peak") else ""))
    if hii.get("peak_msl") is not None and hii.get("bank") is not None:
        arrival.append(f"นนทบุรีคาดว่าจะล้นตลิ่งราว {hii['peak_day']}" if hii["peak_msl"] >= hii["bank"]
                       else "นนทบุรีคาดว่า 7 วันนี้ยังไม่ล้นตลิ่ง")
    if arrival:
        easy.append(" ส่วน".join(arrival))
    if districts:
        easy.append("เขตที่ควรเตรียมตัว: " + ", ".join(d["district"] for d in districts[:5]))
    return {
        "level": level, "title": rules_title(facts), "easy": easy,
        "actions": (["ชุมชนริมแม่น้ำและนอกแนวคันกั้นน้ำ ยกของขึ้นที่สูงและเตรียมย้ายรถ"] if districts else [])
                   + ["ติดตามประกาศของกรมชลประทาน กรุงเทพมหานคร และสำนักงานเขต", "น้ำท่วมหรือต้องการความช่วยเหลือ โทร 1784 (ปภ.) หรือ 1555 (กทม.)"],
        "points": [{"code": c, "text": point_text(p)} for c, p in points.items()],
        "summary": (facts["north"].get("headline") or "") + (f" · เขตที่ต้องจับตา {len(districts)} เขต" if districts else " · ยังไม่มีเขตที่เข้าเกณฑ์"),
        "timeline": timeline, "districts": districts,
        "watch_points": ["ระดับน้ำที่สะพานนวลฉวี นนทบุรี เทียบตลิ่ง", "ปริมาณน้ำที่อยุธยา (C.35) และท้ายเขื่อนเจ้าพระยา (C.13)", "น้ำทะเลหนุนช่วงเช้า"],
    }


def rules_title(facts):
    """One headline without the model: over the bank now, soon, or not at all along the Chao Phraya."""
    main = facts["north"].get("chao_phraya") or []
    over = [s["province"] for s in main if (s.get("pct") or 0) >= 100]
    soon = [s for s in main if (s.get("pct") or 0) < 100 and ((s.get("peak") or {}).get("pct") or 0) >= 100]
    if over:
        return "น้ำเหนือล้นตลิ่งแล้วที่" + " ".join(dict.fromkeys(over))
    if soon:
        return f"คาดว่าน้ำจะล้นตลิ่งที่{soon[0]['province']} ในอีกราว {_ahead(soon[0]['peak']['in_h'])}"
    if any((s.get("pct") or 0) >= 70 for s in main):
        return "น้ำเหนือมาก แต่ยังไม่ล้นตลิ่ง"
    return "น้ำเหนือยังอยู่ในลำน้ำ ปกติ"


def _signature(facts):
    """What would change the report: the northern warnings, the Nonthaburi forecast (5 cm steps), the rule levels."""
    hii = facts["north"].get("nonthaburi_hii") or {}
    points = []
    for p in facts.get("points") or []:
        q = (p.get("now_10min") or {}).get("q") or p.get("q") or 0
        points.append((p["code"], p.get("status"), trend_text(p).split(" ")[0], round(math.log(max(q, 1)) / math.log(1.03))))
    key = {"alerts": facts["north"].get("alerts"), "hii": round((hii.get("peak_msl") or 0) * 20), "points": points,
           "districts": [(r["district"], r["rule_level"]) for r in facts["districts"] if r["rule_level"]],
           "roads": [(r["road"], r["rule_level"]) for r in facts.get("roads") or []]}
    return hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class NorthImpactAgent:
    def __init__(self, data_dir, sources):
        """sources: {"north", "water_map", "roads", "rain", "tide", "road_risk"}: callables; any may fail.
        "roads" is the BMA road-sensor status, "road_risk" every road with its sensors, canal and rain."""
        self.sources = sources
        self.path = os.path.join(data_dir, "cache", "north_impact.json")
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.report, self.sig, self.checked_at, self.running, self.error = None, None, None, False, None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.report, self.sig = d.get("report"), d.get("sig")
        except (OSError, ValueError):
            pass

    def _call(self, name):
        try:
            return self.sources[name]()
        except Exception as e:  # noqa: BLE001 - one broken source must not stop the rest
            print(f"[NorthImpact] source {name} failed: {str(e)[:120]}")
            return None

    def facts(self):
        north = self._call("north")
        if not north:
            raise RuntimeError("ข้อมูลน้ำเหนือโหลดไม่สำเร็จ")
        return build_facts(north, self._call("water_map") or {}, self._call("roads"), self._call("rain"), self._call("tide"),
                           self._call("road_risk"), self._call("nonthaburi"))

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"report": self.report, "sig": self.sig}, f, ensure_ascii=False)
        except OSError as e:
            print(f"[NorthImpact] save failed: {e}")

    def _roads(self, facts, use_model):
        """Second call: which of the candidate roads flood when the water arrives. The rules stand in without it."""
        cands = facts.get("roads") or []
        if not cands or not use_model:
            return {**rules_roads(facts), "by": "rules"}
        hii = facts["north"].get("nonthaburi_hii") or {}
        scenario = {"nonthaburi_hii": {**hii, "margin_m": round(hii["peak_msl"] - hii["bank"], 2)}
                    if hii.get("peak_msl") is not None and hii.get("bank") is not None else None,
                    "ayutthaya": next((s for s in facts["north"].get("chao_phraya") or [] if s["code"] == "C.35"), None),
                    "tide": facts.get("tide"),
                    "note": "นอกกรุงเทพฯ ไม่มีเซ็นเซอร์วัดน้ำบนถนน ถนนในนนทบุรีและจังหวัดอื่นประเมินจากทำเล (อำเภอริมแม่น้ำ) เท่านั้น"}
        scenario["nonthaburi_river_chance"] = facts.get("nonthaburi_river")
        data = {"scenario": scenario, "roads": [{k: r[k] for k in ("road", "province", "district", "rule_level", "reasons", "p", "distance_m") if k in r}
                                                for r in cands]}
        schema = {"type": "object", "additionalProperties": False, "required": ["summary", "roads"], "properties": {
            "summary": {"type": "string"},
            "roads": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                 "required": ["road", "level", "when", "why", "advice"], "properties": {
                "road": {"type": "string", "enum": [r["road"] for r in cands]},
                "level": {"type": "string", "enum": list(ROAD_LEVELS)},
                "when": {"type": "string"}, "why": {"type": "string"}, "advice": {"type": "string"}}}}}}
        try:
            text = local_llm.default.chat(
                [{"role": "system", "content": ROADS_PROMPT},
                 {"role": "user", "content": f"ข้อมูล (JSON):\n{json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"
                                             f"เวลาปัจจุบัน {datetime.now(BKK_TZ).strftime('%Y-%m-%d %H:%M')}\nส่งเป็น JSON ตาม schema เท่านั้น"}],
                max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=schema)
            out = json.loads(text[text.find("{"):text.rfind("}") + 1])
            return {**out, "by": "ai"}
        except Exception as e:  # noqa: BLE001 - the rule list stands in
            print(f"[NorthImpact] roads model failed: {e}")
            return {**rules_roads(facts), "by": "rules"}

    def _nonthaburi(self, facts, use_model):
        """Third call: each risky Nonthaburi road, which stretch floods first and which next."""
        brief = facts.get("nonthaburi")
        if not brief or not brief["roads"] or not use_model:
            return {**rules_nb(brief), "by": "rules"}
        schema = {"type": "object", "additionalProperties": False, "required": ["summary", "roads"], "properties": {
            "summary": {"type": "string"},
            "roads": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["road", "text"],
                                                 "properties": {"road": {"type": "string", "enum": [r["road"] for r in brief["roads"]]},
                                                                "text": {"type": "string"}}}}}}
        try:
            text = local_llm.default.chat(
                [{"role": "system", "content": NB_PROMPT},
                 {"role": "user", "content": f"ข้อมูล (JSON):\n{json.dumps(brief, ensure_ascii=False, separators=(',', ':'), default=str)}\n\n"
                                             f"เวลาปัจจุบัน {datetime.now(BKK_TZ).strftime('%Y-%m-%d %H:%M')}\nส่งเป็น JSON ตาม schema เท่านั้น"}],
                max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=schema)
            out = json.loads(text[text.find("{"):text.rfind("}") + 1])
            known = {r["road"] for r in brief["roads"]}
            got = {r["road"]: r["text"] for r in out.get("roads") or [] if r.get("road") in known and r.get("text")}
            # A road the model skipped keeps its rule sentence
            fallback = {r["road"]: r["text"] for r in rules_nb(brief)["roads"]}
            return {"summary": out.get("summary") or rules_nb(brief)["summary"],
                    "roads": [{"road": r["road"], "text": got.get(r["road"]) or fallback[r["road"]], "by": "ai" if r["road"] in got else "rules"}
                              for r in brief["roads"]], "by": "ai"}
        except Exception as e:  # noqa: BLE001 - the rule sentences stand in
            print(f"[NorthImpact] nonthaburi model failed: {e}")
            return {**rules_nb(brief), "by": "rules"}

    def _finish(self, report, facts, source, model=None, took=None, error=None):
        known = {r["district"]: r for r in facts["districts"]}
        seen, districts = set(), []
        for d in report.get("districts") or []:
            name = d.get("district")
            if name not in DISTRICTS or name in seen or d.get("level") not in DISTRICT_LEVELS:
                continue
            seen.add(name)
            districts.append({**d, "tags": (known.get(name) or {}).get("tags", []),
                              "rule_level": (known.get(name) or {}).get("rule_level")})
        districts.sort(key=lambda d: DISTRICT_LEVELS.index(d["level"]))
        texts = {p.get("code"): p.get("text") for p in report.get("points") or [] if p.get("code") in POINT_CODES and p.get("text")}
        # A gauge the model skipped still gets its rule sentence
        report["points"] = [{"code": p["code"], "text": texts.get(p["code"]) or point_text(p), "by": "ai" if p["code"] in texts else "rules"}
                            for p in facts.get("points") or []]
        report["easy"] = [x for x in report.get("easy") or [] if isinstance(x, str) and x.strip()][:3]
        report["actions"] = [x for x in report.get("actions") or [] if isinstance(x, str) and x.strip()][:3]
        report["title"] = (report.get("title") or "").strip() or rules_title(facts)
        if report.get("level") not in LEVELS:
            report["level"] = "watch"
        report["status_label"] = LEVEL_TH[report["level"]]
        roads = self._roads(facts, source == "ai")
        cand = {r["road"]: r for r in facts.get("roads") or []}
        seen, road_rows = set(), []
        for r in roads.get("roads") or []:
            c = cand.get(r.get("road"))
            if not c or c["road"] in seen or r.get("level") not in ROAD_LEVELS:
                continue
            seen.add(c["road"])
            road_rows.append({**r, **{k: c.get(k) for k in ("province", "district", "lat", "lng", "reasons", "river_side", "flood_cm", "p", "distance_m")}})
        road_rows.sort(key=lambda r: ROAD_LEVELS.index(r["level"]))
        report.update({"districts": districts, "source": source, "model": model, "generated_at": int(time.time()),
                       "took_s": took, "roads": road_rows, "roads_summary": roads.get("summary") or "", "roads_by": roads.get("by"),
                       "nonthaburi": self._nonthaburi(facts, source == "ai")})
        with self.lock:
            self.report, self.sig, self.error = report, _signature(facts), error
            self._save()

    def run(self, force=False):
        if not self.run_lock.acquire(blocking=False):
            return {**self.status(), "busy": True}
        try:
            try:
                facts = self.facts()
            except Exception as e:  # noqa: BLE001 - keep the last report
                with self.lock:
                    self.error = str(e)[:200]
                return self.status()
            sig = _signature(facts)
            with self.lock:
                self.checked_at = int(time.time())
            age = time.time() - ((self.report or {}).get("generated_at") or 0)
            if not force and self.report and sig == self.sig and age < MAX_AGE:
                return self.status()
            if not local_llm.default.enabled():
                self._finish(rules_report(facts), facts, "rules", error="ยังไม่ได้ตั้งค่าโมเดล AI (LOCAL_LLM_MODEL)")
                return self.status()
            with self.lock:
                self.running = True
            started = time.time()
            first = {k: v for k, v in facts.items() if k not in ("roads", "nonthaburi_river", "nonthaburi")}
            prompt = (f"ข้อมูลสด (JSON):\n{json.dumps(first, ensure_ascii=False, separators=(',', ':'), default=str)}\n\n"
                      f"เวลาปัจจุบัน {datetime.now(BKK_TZ).strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\nส่งบทวิเคราะห์เป็น JSON ตาม schema เท่านั้น")
            try:
                text = local_llm.default.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                                              max_tokens=REPLY_TOKENS, temperature=0.2, json_schema=REPORT_SCHEMA)
                report = json.loads(text[text.find("{"):text.rfind("}") + 1])
            except Exception as e:  # noqa: BLE001 - server off, bad JSON: the rules stand in
                print(f"[NorthImpact] model failed: {e}")
                self._finish(rules_report(facts), facts, "rules", error=f"{local_llm.default.model}: {str(e)[:160]}")
                return self.status()
            self._finish(report, facts, "ai", model=local_llm.default.model, took=round(time.time() - started, 1))
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
        time.sleep(120)    # let north_flow and the water summary fill first
        while True:
            try:
                self.run()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[NorthImpact] run failed: {e}")
            time.sleep(POLL_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="NorthImpact").start()
