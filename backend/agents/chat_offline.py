"""
The assistant's answers without the model (offline mode): a short summary from the live data for the question's
main topic, or the planned route. Moved out of chat_service.py (Oct 2026).
"""
from backend.agents.chat_context import (WATCH_TH, accident_stats_context, air_context, flow_th, incident_context,
                                         weather_context)
from backend.agents.chat_topics import question_topics


def _flood_reply(w):
    if not w:
        return "ยังโหลดข้อมูลน้ำท่วม/ฝนไม่สำเร็จ ลองใหม่อีกครั้งนะ"
    out = []
    roads = w.get("flood_roads") or {}
    out.append(f"• น้ำท่วมถนน กทม. ตอนนี้: ท่วม {roads.get('flooding', 0)} จุด ท่วมเล็กน้อย {roads.get('slight', 0)} จุด")
    out += [f"  - {r['name']} เขต{r['district']} {r['depth_cm']:.0f} ซม." for r in (roads.get("items") or [])[:3]]
    over = [r["name"] for r in w.get("river", []) + w.get("canals", []) if r["level"] == "overflow"][:3]
    if over:
        out.append("• ล้นตลิ่ง: " + ", ".join(over))
    zones = w.get("weather") or []
    if zones:
        out.append("• เฝ้าระวังรายพื้นที่ (24 ชม.):")
        for z in zones[:5]:
            extra = f" พายุ {z['storm_at']} น." if z.get("storm_at") else ""
            out.append(f"  - {WATCH_TH.get(z['watch'], z['watch'])} {z['name']}: ฝน {z['rain_24h']} มม. ลม {z['gust_max']:.0f} กม./ชม.{extra}")
    worst = zones[0] if zones else None
    if worst and worst["watch"] in ("orange", "red"):
        out.append(f"แนะนำ: {worst['name']} เลี่ยงถนนลุ่มต่ำ ย้ายรถขึ้นที่สูง เตรียมกระสอบทราย และไม่จอดใต้ต้นไม้ช่วงพายุ")
    else:
        out.append("แนะนำ: สถานการณ์ปกติ ติดตามฝนช่วงบ่าย-เย็นและเช็กท่อระบายน้ำหน้าบ้านไว้ก่อน")
    return "\n".join(out)


ACCIDENT_WORDS = ("อุบัติเหตุ", "ชน", "รถคว่ำ", "เสียชีวิต", "บาดเจ็บ", "เหตุการณ์", "ปิดถนน")


def _accident_reply(extra):
    ex = extra or {}
    lines = incident_context(ex.get("incidents"), ex.get("bma_events")) + accident_stats_context(ex.get("rsc"), ex.get("camera_risk"))
    return "\n".join(lines) if lines else "ยังไม่มีข้อมูลอุบัติเหตุตอนนี้"


OFFLINE_NOTE = "(โหมดออฟไลน์: เชื่อมต่อโมเดล AI ไม่ได้ตอนนี้ ตอบจากข้อมูลสดแทน)"
TRAFFIC_WORDS = ("ถนน", "จราจร", "รถ", "ติด", "ทาง", "เส้น", "ไป", "โล่ง", "แยก", "ซอย", "สะพาน", "ด่วน")


def route_reply(r):
    """The planned route as a short Thai answer, without the model."""
    out = [f"เส้นทางแนะนำ: {' → '.join(x['name'] for x in r['roads'][:6]) or 'ตามแผนที่'}",
           f"ระยะ {r['km']} กม. ใช้เวลาประมาณ {r['minutes'][0]}-{r['minutes'][1]} นาที"]
    if r.get("avoided"):
        out.append(f"เส้นนี้อ้อมจุดน้ำท่วม {len(r['avoided'])} จุด: " + ", ".join(h["name"] for h in r["avoided"][:3]))
    if r.get("flood_on_route") or r.get("flood_at_ends"):
        out.append("ระวังน้ำท่วมที่: " + ", ".join(h["name"] for h in (r.get("flood_on_route") or []) + (r.get("flood_at_ends") or [])))
    if r.get("jams"):
        out.append("รถติดช่วง: " + ", ".join(f"{j['road']} {j['km']} กม." for j in r["jams"][:3]))
    if not r.get("flood_checked"):
        out.append("ตอนนี้ยังตรวจจุดน้ำท่วมบนเส้นทางไม่ได้ครบ ดูแผนที่น้ำท่วมก่อนออกเดินทาง")
    out.append("กดปุ่ม \"นำทางใน Google Maps\" ด้านล่างเพื่อเริ่มนำทาง")
    return "\n".join(out)


def _weather_reply(extra):
    lines = weather_context((extra or {}).get("weather_outlook"), None, (extra or {}).get("tmd"))
    return "\n".join(lines) if lines else "ยังไม่มีข้อมูลพยากรณ์อากาศตอนนี้"


def rule_based_reply(traffic, question, water=None, extra=None):
    if (extra or {}).get("route"):
        return route_reply(extra["route"]) + "\n" + OFFLINE_NOTE
    topics = question_topics(question)
    if not topics:
        return ("โหมดออฟไลน์ตอบได้เฉพาะสรุปจราจร น้ำท่วม/ฝน อากาศ อุบัติเหตุ และฝุ่นจากข้อมูลสด" + chr(10) +
                "เชื่อมต่อโมเดล AI ไม่ได้ตอนนี้ ลองถามใหม่อีกครั้งในอีกสักครู่")
    if topics[0] == "accident":
        return _accident_reply(extra) + "\n" + OFFLINE_NOTE
    if topics[0] == "flood" or (topics[0] == "predict" and "traffic" not in topics):
        return _flood_reply(water) + "\n" + OFFLINE_NOTE
    if topics[0] == "weather":
        return _weather_reply(extra) + "\n" + OFFLINE_NOTE
    if topics[0] == "air":
        lines = air_context((extra or {}).get("air"), question)
        return ("\n".join(lines) if lines else "ยังไม่มีข้อมูลฝุ่นตอนนี้") + "\n" + OFFLINE_NOTE
    s = traffic.get_summary(top=5)
    if not s.get("ready"):
        return "ผู้ช่วยกำลังโหลดข้อมูลจราจรอยู่ รอสักครู่แล้วถามใหม่นะ"
    mentioned = traffic.find_roads_in_text(question)
    out = []
    if mentioned:
        for r in mentioned:
            jam = f" ติดยาว {r['red_km']} กม." if r.get("red_km") else ""
            out.append(f"• {r['name']}: {flow_th(r['flow'])}{jam}")
    else:
        out.append(f"ภาพรวมตอนนี้: {flow_th(s['flow_index'])} (ถนนที่ติดขัด {s['red_pct']}% ของระยะที่มีข้อมูล)")
        out.append("ถนนที่ควรเลี่ยง (ติดมากสุด):")
        out += [f"• {r['name']} ติดยาว {r['red_km']} กม." for r in s["congested"][:4]]
    worst = min(mentioned or s["congested"][:1] or [None], key=lambda r: r["flow"] if r else 0)
    if worst and worst["flow"] < 45:
        out.append(f"แนะนำ: เลี่ยง {worst['name']} ไปก่อนนะ")
    else:
        out.append("แนะนำ: ไปได้เลย ทางค่อนข้างสะดวก")
    out.append(OFFLINE_NOTE)
    return "\n".join(out)
