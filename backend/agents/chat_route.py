"""
Route questions ("จากบางนาไปสีลม", "ไปลาดกระบังทางไหนดี"): read the start and the destination from the conversation
and plan the trip with flood_route.FloodRouter. Moved out of chat_service.py (Oct 2026).
"""
import json
import re

from backend.core import local_llm

llm = local_llm.chat_client


TRIP_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["origin", "destination"],
               "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}}}
TRIP_PROMPT = """ดึงต้นทางและปลายทางของการเดินทางจากข้อความล่าสุดของผู้ใช้ (ใช้บทสนทนาก่อนหน้าช่วยตีความ เช่น "แล้วถ้าไปลาดกระบังล่ะ")
- เขียนชื่อสถานที่แบบที่ค้นบนแผนที่ได้ ขยายชื่อย่อ เช่น ม.เกษตร → มหาวิทยาลัยเกษตรศาสตร์, อนุสาวรีย์ → อนุสาวรีย์ชัยสมรภูมิ, จุฬา → จุฬาลงกรณ์มหาวิทยาลัย
- ไม่ใส่คำว่า แถว ย่าน ที่ บริเวณ และไม่ใส่คำอื่นของประโยค
- ไม่บอกต้นทาง หรือต้นทางคือ ที่นี่ / ตรงนี้ / บ้าน / ที่ทำงาน ให้ origin เป็น ""
- ไม่ใช่คำถามเรื่องการเดินทาง ให้ทั้งสองเป็น \"\""""
_TAIL = re.compile(r"\s*(ยังไง|อย่างไร|ทางไหน|เส้นไหน|ดีไหม|ดี|ควร|เลี่ยง|โดย|ใช้เวลา|กี่|ไหม|มั้ย|หน่อย|ครับ|ค่ะ|คะ|นะ|ล่ะ|ตอนนี้|บ้าง|\?).*$")


def _trip_by_pattern(question):
    """(origin, destination) from "จาก A ไป B" / "ไป B", or ("", "")."""
    q = (question or "").replace("ไปยัง", "ไป").replace("ไปที่", "ไป").replace("นำทางไป", "ไป")
    m = re.search(r"จาก\s*(.+?)\s*(?:ไป|ถึง)\s*(.+)", q)
    if m:
        return _TAIL.sub("", m[1]).strip(), _TAIL.sub("", m[2]).strip()
    m = re.search(r"ไป\s*(.+)", q)
    return ("", _TAIL.sub("", m[1]).strip()) if m else ("", "")


def extract_trip(history):
    """(origin, destination) of the trip the last user message asks about. A plain "จาก A ไป B" / "ไป B" is read
    by pattern (fast, and spelled as typed); the model reads the rest, and follow-ups such as "แล้วถ้าไปลาดกระบังล่ะ"
    that take the start from earlier in the conversation."""
    origin, dest = _trip_by_pattern(history[-1]["content"])
    follow_up = not origin and any(m["role"] == "user" for m in history[:-1])
    if dest and (origin or not follow_up) or not llm.enabled():
        return origin, dest
    convo = "\n".join(f"{'ผู้ใช้' if m['role'] == 'user' else 'ผู้ช่วย'}: {m['content'][:300]}" for m in history[-3:])
    try:
        raw = llm.chat([{"role": "system", "content": TRIP_PROMPT}, {"role": "user", "content": convo}],
                       max_tokens=120, temperature=0, json_schema=TRIP_SCHEMA, timeout=40)
        got = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        return (got.get("origin") or "").strip(), (got.get("destination") or "").strip()
    except Exception as e:  # noqa: BLE001 - keep what the pattern read
        print(f"[Chat] trip extraction failed: {str(e)[:160]}")
        return origin, dest


def plan_route(router, history, location=None):
    """{"route": ...} on success, {"ask": text} when the bot must ask back, {"error": text} when the map fails,
    or None when the question names no destination."""
    origin_text, dest_text = extract_trip(history)
    if not dest_text:
        return None
    try:
        dest = router.geocode(dest_text)
        if not dest:
            return {"ask": f"หา \"{dest_text}\" บนแผนที่ไม่เจอ ลองพิมพ์ชื่อให้ชัดขึ้น เช่น ชื่อห้าง ชื่อสถานี ชื่อถนน หรือชื่อเขต"}
        if router.is_here(origin_text) or origin_text in ("บ้าน", "ที่ทำงาน"):
            if not location:
                return {"ask": f"จะเริ่มเดินทางจากที่ไหนไป {dest['name']}? พิมพ์ต้นทาง เช่น \"จากบางนาไป{dest['name']}\" "
                               "หรือกดปุ่ม \"ใช้ตำแหน่งของฉัน\" แล้วถามใหม่", "need_location": True}
            origin = {"name": "ตำแหน่งของคุณ", "label": "ตำแหน่งของคุณ", "lat": location["lat"], "lng": location["lng"]}
        else:
            origin = router.geocode(origin_text)
            if not origin:
                return {"ask": f"หา \"{origin_text}\" บนแผนที่ไม่เจอ ลองพิมพ์ชื่อให้ชัดขึ้น เช่น ชื่อห้าง ชื่อสถานี ชื่อถนน หรือชื่อเขต"}
        return {"route": router.plan(origin, dest)}
    except Exception as e:  # noqa: BLE001 - Nominatim / Valhalla down: answer from the live data instead
        print(f"[Chat] route failed: {str(e)[:200]}")
        return {"error": "คำนวณเส้นทางไม่ได้ตอนนี้ (ระบบแผนที่ไม่ตอบ) ให้แนะนำจากสภาพจราจรและน้ำท่วมที่มีแทน และบอกว่าเป็นการประเมินคร่าว ๆ"}
