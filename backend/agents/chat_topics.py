"""
What a chat question is about: its topics (traffic, flood, weather, predict, accident, air), whether it asks for
a route, and the "how to answer" note added after it. Moved out of chat_service.py (Oct 2026).
"""
import re

from backend.agents.chat_context import FLOOD_WORDS


# How to answer each kind of question, added after the question itself
ANSWER_STYLE = {
    "route": "ผู้ใช้ถามเส้นทาง: ประโยคแรกบอกเส้นทางแนะนำเป็นชื่อถนนตามลำดับ ระยะทาง และเวลาโดยประมาณ จากหัวข้อ \"เส้นทางที่ระบบคำนวณ\" "
             "จากนั้นบอกจุดน้ำท่วมที่เส้นนี้อ้อมให้ (ถ้ามี) จุดน้ำท่วมหรือรถติดที่ยังอยู่บนเส้นทาง แล้วปิดท้ายว่ากดปุ่ม \"นำทางใน Google Maps\" ใต้ข้อความได้ "
             "ห้ามแนะนำถนนที่ไม่อยู่ในเส้นทางที่คำนวณ",
    "avoid": "ผู้ใช้ถามถนนที่ควรเลี่ยง: ตอบเป็นรายการ 3-5 สาย เรียงจากหนักสุด แต่ละสายบอกว่าทำไม (ติดยาวกี่ กม. ช่วงไหน หรือน้ำท่วมกี่ ซม.) "
             "และทางเลี่ยง 1 เส้นถ้ามีในข้อมูล",
    "traffic": "ผู้ใช้ถามเรื่องจราจร: ตอบสภาพของถนน/พื้นที่ที่ถามก่อน (ติดขัด/ชะลอตัว/คล่องตัว ติดยาวกี่ กม.) แล้วแนะนำทางเลี่ยงถ้าติด",
    "flood": "ผู้ใช้ถามเรื่องน้ำท่วม: ตอบท่วม/ไม่ท่วมก่อน ระบุถนน/เขตและความลึก (ซม.) แล้วบอกแนวโน้มและสิ่งที่ควรทำ 1-2 ข้อ",
    "weather": "ผู้ใช้ถามเรื่องอากาศ: ตอบตามวันที่ถาม (ไม่ระบุคือวันนี้) ว่าฝนตกไหม ช่วงกี่โมง มากน้อยแค่ไหน อุณหภูมิต่ำสุด-สูงสุด "
               "และประกาศเตือนของกรมอุตุฯ ถ้ามี ถ้าถามเขตให้ใช้พยากรณ์ของโซนที่เขตนั้นอยู่",
    "predict": "ผู้ใช้ถามการคาดการณ์: บอกสิ่งที่คาดว่าจะเกิด ที่ไหน เมื่อไร จากผลวิเคราะห์ที่แนบมา ระบุว่าเป็นการคาดการณ์ "
               "และบอกสัญญาณที่ควรติดตาม 1 ข้อ",
    "accident": "ผู้ใช้ถามเรื่องอุบัติเหตุ: ระบุจุด เวลา แหล่งที่มา และเส้นเลี่ยง ถ้าถามสถิติให้ระบุปี พ.ศ.",
    "air": "ผู้ใช้ถามเรื่องฝุ่น: ตอบค่าฝุ่นของพื้นที่ที่ถามก่อน บอกว่าดี/ปานกลาง/มีผลต่อสุขภาพ แล้วคำแนะนำ 1 ข้อ",
}


# Tie order matters: a route question that also names a place goes to traffic first
TOPIC_WORDS = {
    "traffic": ("ถนน", "จราจร", "รถ", "ติด", "ทาง", "เส้น", "ไป", "โล่ง", "แยก", "ซอย", "สะพาน", "ด่วน", "flow", "กล้อง",
                "ใช้เวลา", "นานไหม", "กี่นาที", "เดินทาง", "จาก", "เลี่ยง"),
    "flood": FLOOD_WORDS,
    "weather": ("อากาศ", "พยากรณ์", "ฝน", "ฝนจะตก", "ฝนตก", "ร้อน", "อุณหภูมิ", "องศา", "ฟ้าผ่า", "ฟ้าคะนอง", "พายุ",
                "ลมแรง", "ลมกระโชก", "เมฆ", "แดด", "หนาว", "พกร่ม"),
    "predict": ("คาดการณ์", "ทำนาย", "แนวโน้ม", "พยากรณ์", "จะท่วม", "จะติด", "จะตก", "อีกกี่", "ล่วงหน้า", "พรุ่งนี้",
                "มะรืน", "สัปดาห์หน้า", "อาทิตย์หน้า", "คืนนี้", "เย็นนี้", "น้ำเหนือ", "เมื่อไหร่", "เมื่อไร", "อนาคต",
                "จะเป็นยังไง", "จะหนักไหม", "จะลด", "จะสูง"),
    "accident": ("อุบัติเหตุ", "ชน", "รถคว่ำ", "เสียชีวิต", "บาดเจ็บ", "เหตุการณ์", "ปิดถนน", "หมวก", "ย้อนศร",
                 "ฝ่าฝืน", "จุดเสี่ยง", "black spot"),
    "air": ("ฝุ่น", "PM", "pm", "AQI", "aqi", "มลพิษ"),
}
ALL_TOPICS = ["traffic", "flood", "weather", "predict", "accident", "air"]
OVERVIEW_WORDS = ("ภาพรวม", "สรุป", "เมือง", "สถานการณ์", "วันนี้", "ตอนนี้", "กรุงเทพ", "กทม", "ประเทศ", "ทั่วไทย", "จังหวัด")
# Place names and words that contain a topic word but are not about it (สี"ลม", ท่า"น้ำ", "น้ำ"มัน, ท่า"อากาศ"ยาน)
NOT_TOPIC = {"สีลม": " ", "ท่าน้ำ": " ", "น้ำมัน": " ", "น้ำใจ": " ", "น้ำหอม": " ", "ลมหายใจ": " ", "ทางด่วน": " ทาง ",
             "ท่าอากาศยาน": " ", "คุณภาพอากาศ": " ฝุ่น ", "ชนบท": " "}
AVOID_WORDS = ("เลี่ยง", "ห้ามผ่าน", "อย่าไป", "ไม่ควรไป", "ควรหลีก")
ROUTE_WORDS = ("นำทาง", "เส้นทาง", "ไปยังไง", "ไปทางไหน", "ไปอย่างไร", "ไปเส้นไหน", "ขับไป", "ขับรถไป", "เดินทางไป",
               "ไปไง", "ทางไป")


def _normalise(question):
    q = question or ""
    for w, to in NOT_TOPIC.items():
        q = q.replace(w, to)
    return q


def question_topics(question):
    """Topics the question is about, most matched first ([] for a general question)."""
    q = _normalise(question)
    hits = {k: sum(w in q for w in words) for k, words in TOPIC_WORDS.items()}
    return [k for k in sorted(hits, key=lambda k: -hits[k]) if hits[k]]


def wants_route(question):
    """A question about getting from A to B (or to B from here)."""
    q = _normalise(question)
    return (any(w in q for w in ROUTE_WORDS) or bool(re.search(r"จาก.+ไป", q))
            or bool(re.search(r"ไป.+(ทางไหน|เส้นไหน|ยังไง|อย่างไร|ใช้เวลา|กี่นาที)", q)))


def answer_style(question, topics, route=False):
    """The "how to answer" note: the route, the roads to avoid, or the main topics (at most two)."""
    keys = ["route"] if route else []
    if not route and any(w in (question or "") for w in AVOID_WORDS) and {"traffic", "flood"} & set(topics):
        keys.append("avoid")
    for k in topics:
        if len(keys) >= 2:
            break
        if k not in keys and not (keys and k == "traffic"):
            keys.append(k)
    return " / ".join(ANSWER_STYLE[k] for k in keys if k in ANSWER_STYLE)
