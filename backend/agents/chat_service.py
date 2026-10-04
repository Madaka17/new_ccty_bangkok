"""
Assistant chatbot (the "Ask AI" page) for the whole country, answered by the Qwen model behind local_llm.chat_client.

Grounded in the live data of every section of the site: road-level detail for Bangkok, and for every province
the traffic per province and district (area_traffic), the flood level per province with its AI analysis
(province_flood) and the weather of a province the question names. Provider order:
  1. AI model           - local_llm.chat_client (CHAT_LLM_*, else LOCAL_LLM_* in .env)
  2. Rule-based summary - when the model is off, so the page still works

The question is sorted into topics (traffic, flood, weather, predict, accident, air). Only those topics go
into the prompt, most relevant first, cut to what fits the model's context window, and each topic adds a
short "how to answer" note so the reply answers the question asked and nothing else.

A route question ("จากบางนาไปสีลม", "ไปลาดกระบังทางไหนดี") is planned by flood_route.FloodRouter around the
flooded spots and the jams; the model words the answer from that plan and the browser draws the route.
"""
import json
import re
import time

from backend.core import local_llm, thai_regions

llm = local_llm.chat_client

REPLY_TOKENS = 1200
HISTORY_KEEP = 6            # past messages sent with the question
HISTORY_CHARS = 800         # per past message

SYSTEM_PROMPT = """คุณคือ "ผู้ช่วยอัจฉริยะ" ของแอป BKK StreetSmart ตอบได้ทั่วประเทศไทย 77 จังหวัด

สิ่งที่สำคัญที่สุด: ตอบให้ตรงคำถาม
- ประโยคแรกตอบสิ่งที่ถามตรง ๆ เช่น ถาม "ติดไหม" ตอบติด/ไม่ติด, "ท่วมไหม" ตอบท่วม/ไม่ท่วม, "ฝนจะตกไหม" ตอบตก/ไม่ตก พร้อมช่วงเวลา,
  "ใช้เวลานานไหม" ตอบเป็นช่วงนาที, "ไปทางไหน" ตอบชื่อถนนตามลำดับ แล้วค่อยให้รายละเอียดสนับสนุน 2-4 บรรทัด
- ตอบเฉพาะเรื่องที่ถาม ห้ามเล่าหมวดอื่น (ถามรถติดอย่าเล่าฝุ่น ถามอากาศอย่าเล่าอุบัติเหตุ) ยกเว้นมันกระทบเรื่องที่ถามจริง เช่น น้ำท่วมบนเส้นทางที่ถาม
- ถ้าผู้ใช้ระบุถนน เขต อำเภอ จังหวัด หรือเวลา (คืนนี้ พรุ่งนี้ ช่วงเย็น) ให้ตอบเจาะที่นั้น ไม่ต้องสรุปทั้งประเทศ
- ถ้าไม่ระบุพื้นที่: เรื่องที่มีข้อมูลทั่วประเทศ (รถติด น้ำท่วม) บอกภาพรวมทั่วประเทศสั้น ๆ ก่อน แล้วตามด้วยกรุงเทพฯ
- ท้ายข้อความผู้ใช้มี "วิธีตอบคำถามนี้" ให้ทำตามนั้น

ข้อมูลสดที่แนบมา (ใช้ตอบเรื่องเหล่านี้ ห้ามเดาตัวเลขหรือสถานะเอง)
1) จราจร: สภาพรถรายถนน (Longdo Traffic) จำนวนรถจากกล้อง กทม. ช่วงที่ติด ทางเลี่ยงรายสายทางหลัก
2) น้ำท่วม: เซ็นเซอร์น้ำบนถนน กทม. กล้อง AI ที่เห็นน้ำท่วม รายงานจากประชาชน แม่น้ำ/คลองเทียบตลิ่ง น้ำทะเลหนุน น้ำเหนือ ระดับน้ำท่วมรายถนน
3) อากาศ: พยากรณ์ 3 วัน (ฝน ช่วงเวลา อุณหภูมิ) พยากรณ์ฝน-ลม-พายุ 24 ชม. รายโซน ประกาศเตือนกรมอุตุนิยมวิทยา
4) การคาดการณ์: ผล AI วิเคราะห์และคาดการณ์น้ำท่วม คาดการณ์น้ำเหนือรายเขต ความเสี่ยงน้ำท่วม 1-6 ชม. แนวโน้มจราจร 1 ชม.
5) อุบัติเหตุและเหตุการณ์ สถิติอุบัติเหตุ จุดเสี่ยง การฝ่าฝืน (ไม่สวมหมวก ย้อนศร) 6) ฝุ่น PM2.5 รายสถานี
7) เส้นทาง: เมื่อถามเส้นทาง ระบบคำนวณเส้นทางที่เลี่ยงจุดน้ำท่วมให้แล้วในหัวข้อ "เส้นทางที่ระบบคำนวณ" ให้ใช้ถนน ระยะ เวลาจากหัวข้อนั้นเท่านั้น
8) ทั่วประเทศ: รถติดรายจังหวัดและอำเภอ (Longdo Traffic) น้ำท่วมรายจังหวัด (ระดับน้ำเทียบตลิ่ง ทางหลวงน้ำท่วม ฝน และบทวิเคราะห์ AI) พยากรณ์อากาศของจังหวัดที่ถาม
ข้อ 1-6 ส่วนใหญ่เป็นข้อมูลละเอียดของกรุงเทพฯ (รายถนน กล้อง เซ็นเซอร์ ฝุ่น อุบัติเหตุ) ถ้าถามจังหวัดอื่นให้ใช้ข้อ 8 และบอกตรง ๆ ว่ารายละเอียดระดับถนนมีเฉพาะกรุงเทพฯ

แนวทางตอบ
- ก่อนตอบว่า "ไม่มีข้อมูล" ให้หาในข้อมูลที่แนบมาทุกหมวดก่อน ถ้าไม่มีจริงบอกตรง ๆ แล้วเสนอพื้นที่ใกล้เคียงหรือภาพรวมที่มี
- การคาดการณ์/ทำนาย: บอกว่าจะเกิดอะไร ที่ไหน เมื่อไร และบอกว่าเป็นการคาดการณ์ ไม่ใช่สิ่งที่เกิดแล้ว
  จราจรล่วงหน้าไม่มีโมเดลทำนาย ให้ประเมินจากแนวโน้ม 1 ชม. ช่วงเร่งด่วนปกติ (เช้า 07:00-09:00 เย็น 16:30-19:30 ศุกร์เย็นหนักสุด) และฝนที่คาดว่าจะตก
- เรื่องจราจรใช้คำง่าย: ติดขัด / ชะลอตัว / คล่องตัว และติดยาวกี่ กม. ห้ามพูดคะแนนหรือเปอร์เซ็นต์สี
- ใช้คำที่คนทั่วไปเข้าใจ ห้ามใส่ชื่อฟิลด์ รหัสสถานี หรือศัพท์เทคนิค (flow, ม.รทก., ลบ.ม./วินาที)
- คำถามทั่วไปที่ไม่เกี่ยวกับเมือง ตอบเต็มที่จากความรู้ของคุณ ไม่ต้องโยงกลับมาเรื่องจราจร/น้ำท่วม เรื่องที่เปลี่ยนเร็ว (ข่าว ราคา) บอกว่าอาจไม่ล่าสุด
  ถ้าให้ทำงาน เช่น แปล สรุป เขียน คำนวณ ให้ทำเลย
- เบอร์ฉุกเฉิน: 1669 แพทย์ฉุกเฉิน, 1197 จราจร, 191 ตำรวจ, 1555 กทม., 1784 ปภ., 1460 ชลประทาน
- ตอบภาษาเดียวกับผู้ใช้ (ไทยเป็นหลัก) เป็นกันเอง กระชับ ปกติไม่เกิน 6-10 บรรทัด คำถามสั้นตอบสั้น ใช้ bullet สั้น ๆ ได้
- หน้าจอแสดงข้อความล้วน: ห้ามใช้ Markdown ตัวหนา (**), หัวข้อ (#), ตาราง หรือ LaTeX"""

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

WATCH_TH = {"green": "เขียว-ปกติ", "yellow": "เหลือง-ติดตาม", "orange": "ส้ม-เฝ้าระวัง", "red": "แดง-เตือนภัย"}
FLOOD_WORDS = ("น้ำ", "ฝน", "ท่วม", "พายุ", "ลมแรง", "ลมกระโชก", "คลอง", "แม่น้ำ", "ระบายน้ำ", "เตือน", "เฝ้าระวัง", "ป้องกัน")


def _fmt_zone(z):
    bits = [f"ฝน 24 ชม. {z['rain_24h']} มม. (6 ชม.แรก {z['rain_6h']} มม., โอกาสฝน {z['prob_24h']:.0f}%)"]
    if z.get("peak_at"):
        bits.append(f"หนักสุด {z['peak_at']} น. {z['peak_mm']} มม./ชม.")
    if z.get("storm_at"):
        bits.append(f"พายุฝนฟ้าคะนองเริ่ม {z['storm_at']} น.")
    bits.append(f"ลมกระโชก {z['gust_max']:.0f} กม./ชม.")
    if z.get("rain_observed_mm"):
        bits.append(f"ฝนตกแล้ว {z['rain_observed_mm']:.0f} มม.")
    if z.get("flood_roads"):
        bits.append("น้ำท่วมถนน: " + ", ".join(f"{r['name']} {r['depth_cm']:.0f} ซม." for r in z["flood_roads"]))
    if z.get("stations_overflow"):
        bits.append("ล้นตลิ่ง: " + ", ".join(z["stations_overflow"]))
    if z.get("stations_high"):
        bits.append("ใกล้เต็ม: " + ", ".join(z["stations_high"]))
    return f"- [{WATCH_TH.get(z['watch'], z['watch'])}] {z['name']} ({z['areas']}): " + "; ".join(bits)


def water_context(w):
    """Flood / rain / storm block for the chat prompt. `w` is water_service.get_summary()."""
    if not w:
        return ["ข้อมูลน้ำท่วม/ฝน: ยังโหลดไม่สำเร็จ"]
    lines = [f"สถานการณ์น้ำและฝน (อัปเดต {time.strftime('%H:%M', time.localtime(w['updated_at']))}):"]
    roads = w.get("flood_roads") or {}
    lines.append(f"เซ็นเซอร์น้ำท่วมถนน กทม.: ท่วม {roads.get('flooding', 0)} จุด, ท่วมเล็กน้อย {roads.get('slight', 0)} จุด, ปกติ {roads.get('normal', 0)} จุด")
    for r in (roads.get("items") or [])[:6]:
        lines.append(f"  - {r['name']} เขต{r['district']}: {r['depth_cm']:.0f} ซม.")
    rc, cc = w.get("river_counts", {}), w.get("canal_counts", {})
    lines.append(f"แม่น้ำ: ล้นตลิ่ง {rc.get('overflow', 0)} สถานี ใกล้เต็ม {rc.get('high', 0)} สถานี | คลอง: ล้น {cc.get('overflow', 0)} ใกล้เต็ม {cc.get('high', 0)} จาก {w.get('canal_total', 0)}")
    for r in [x for x in w.get("river", []) + w.get("canals", []) if x["level"] in ("overflow", "high")][:8]:
        pct = f" {r['storage_pct']:.0f}% ของความจุ" if r.get("storage_pct") is not None else ""
        lines.append(f"  - {r['name']} ({r['district']} {r['province']}): {'ล้นตลิ่ง' if r['level'] == 'overflow' else 'ใกล้เต็ม'}{pct}")
    for st in w.get("official_stations", []):
        if st.get("msl") is not None and st.get("warning") is not None:
            lines.append(f"  - สถานีหลัก {st['name']}: ระดับ {st['msl']} ม.รทก. (เตือน {st['warning']} / วิกฤต {st.get('critical')})")
    obs = [x for x in w.get("rain_warnings", []) if x["kind"] == "observed" and x.get("mm")]
    if obs:
        lines.append("ฝนตกหนักแล้ว 24 ชม.: " + ", ".join(f"{x['district']} {x['province']} {x['mm']:.0f} มม." for x in obs[:6]))
    ntw = w.get("ntw") or {}
    if ntw.get("dams"):
        lines.append("เขื่อนต้นน้ำ (คลังข้อมูลน้ำแห่งชาติ): " + ", ".join(
            f"{d['name']} {d['storage_pct']:.0f}% เข้า {d['inflow'] or 0:.1f} ระบาย {d['released'] or 0:.1f} ล้าน ลบ.ม./วัน" for d in ntw["dams"]))
    if ntw.get("rain"):
        top = [r for r in ntw["rain"] if (r.get("rain_24h") or 0) >= 35][:6]
        if top:
            lines.append("สถานีวัดฝนจริง 24 ชม. สูงสุด: " + ", ".join(f"{r['district']} {r['province']} {r['rain_24h']:.0f} มม." for r in top))
    for o in ntw.get("rain_outlook") or []:
        lines.append(f"คาดการณ์ฝน 3 วัน: {o['province']} {o['text']}")
    for x in (ntw.get("storms") or []) + (ntw.get("warnings") or []):
        lines.append(f"ประกาศเตือน: {x.get('name') or x.get('text')}")
    if w.get("weather"):
        lines.append("พยากรณ์ฝน/พายุ 24 ชม.ล่วงหน้า และระดับเฝ้าระวังรายพื้นที่ (เรียงเสี่ยงมากไปน้อย):")
        lines += [_fmt_zone(z) for z in w["weather"]]
    return lines


def flow_th(flow):
    """Plain Thai for a 0-100 flow score (the same cut points as traffic_service's levels)."""
    if flow is None:
        return "ไม่มีข้อมูล"
    return "คล่องตัว" if flow >= 75 else ("ชะลอตัว" if flow >= 45 else "ติดขัด")


def _fmt_road(r):
    jam = f", ติดยาว {r['red_km']} กม." if r.get("red_km") else ""
    return f"- {r['name']}: {flow_th(r.get('flow'))}{jam} (ช่วงที่มีข้อมูล {r['length_km']} กม.)"


def _trend_th(hist):
    """"ดีขึ้น" / "แย่ลง" / "ทรงตัว" over the last hour of the city flow index."""
    if len(hist) < 2:
        return ""
    d = hist[-1]["flow"] - hist[max(0, len(hist) - 20)]["flow"]
    return "รถคล่องขึ้น" if d >= 3 else ("รถติดมากขึ้น" if d <= -3 else "ทรงตัว")


def _hhmm(ts):
    return time.strftime('%H:%M', time.localtime(ts)) if ts else "-"


def incident_context(inc, bma_events):
    """Live incidents: camera AI + Longdo accidents + BMA traffic centre feed."""
    lines = []
    cam = (inc or {}).get("camera") or []
    longdo = (inc or {}).get("longdo") or []
    lines.append(f"อุบัติเหตุ/เหตุการณ์ตอนนี้: กล้อง AI พบ {len(cam)} จุด, Longdo รายงาน {len(longdo)} จุด")
    for i in cam[:5]:
        lines.append(f"  - [กล้อง AI {_hhmm(i.get('ts'))}] {i.get('title')}: {i.get('kind')} {i.get('description', '')[:80]} (มั่นใจ {i.get('confidence', 0):.0%})")
    for i in longdo[:5]:
        lines.append(f"  - [Longdo] {i.get('title')}: {i.get('description', '')[:80]}")
    ev = bma_events or {}
    if ev.get("items"):
        counts = ", ".join(f"{k} {v}" for k, v in (ev.get("counts") or {}).items())
        lines.append(f"ศูนย์จราจร กทม. 12 ชม.ล่าสุด ({counts}):")
        for e in ev["items"][:8]:
            lines.append(f"  - [{e.get('kind')} {_hhmm(e.get('ts'))}] {e.get('title')}")
    return lines


def accident_stats_context(rsc, camera_risk):
    """ThaiRSC accident statistics for Bangkok plus the highest-risk camera spots."""
    if not rsc:
        return []
    lines = [f"สถิติอุบัติเหตุ กทม. (ThaiRSC ปี {rsc.get('year_be')}): วันนี้ เสียชีวิต {rsc['today']['dead']} บาดเจ็บ {rsc['today']['injured']}, "
             f"เมื่อวาน เสียชีวิต {rsc['yesterday']['dead']} บาดเจ็บ {rsc['yesterday']['injured']}, "
             f"สะสมปีนี้ เสียชีวิต {rsc['ytd']['dead']} บาดเจ็บ {rsc['ytd']['injured']}"]
    dists = rsc.get("districts") or []
    if dists:
        lines.append("เขตเสียชีวิตสูงสุดปีนี้: " + ", ".join(f"{d['name']} ตาย {d['dead']} เจ็บ {d['injured']}" for d in dists[:5]))
    veh = rsc.get("dead_by_vehicle") or []
    if veh:
        lines.append("เสียชีวิตแยกตามรถ: " + ", ".join(f"{v['label']} {v['pct']}%" for v in veh[:4]))
    hours = rsc.get("dead_by_hour") or []
    if hours:
        top = sorted(range(len(hours)), key=lambda h: -hours[h])[:3]
        lines.append("ช่วงเวลาเสียชีวิตสูงสุด: " + ", ".join(f"{h:02d}:00 ({hours[h]} ราย)" for h in sorted(top)))
    rows = (camera_risk or {}).get("items") or []
    if rows:
        lines.append("จุดกล้องเสี่ยงอุบัติเหตุสูงสุด (เคส/ปี ในรัศมีกล้อง):")
        for r in rows[:5]:
            lines.append(f"  - {r.get('title')} เขต{r.get('district')}: {r.get('cases_per_year')} เคส/ปี ตาย {r.get('dead')} เจ็บ {r.get('injured')}")
    return lines


def bma_count_context(analytics):
    """City-wide vehicle counts from the BMA camera sweep."""
    sm = (analytics or {}).get("summary")
    if not sm:
        return []
    lines = [f"กล้อง กทม. นับรถ: ออนไลน์ {sm.get('online_cameras')}/{sm.get('total_cameras')} ตัว รวม {sm.get('total_vehicles')} คัน "
             f"(รถยนต์ {sm.get('cars_pct')}% มอเตอร์ไซค์ {sm.get('motorcycles_pct')}% บรรทุก {sm.get('trucks_pct')}%) เฉลี่ย {sm.get('avg_per_camera')} คัน/กล้อง"]
    dists = analytics.get("districts") or []
    if dists:
        lines.append("เขตรถหนาแน่นสุด: " + ", ".join(f"{d['district']} เฉลี่ย {d['avg_vehicles']} คัน/กล้อง (หนัก {d['heavy_count']} จุด)" for d in dists[:5]))
    roads = analytics.get("major_roads") or []
    if roads:
        lines.append("ถนนรถหนาแน่นสุดจากกล้อง: " + ", ".join(f"{r['road']} {r['avg_vehicles']} คัน/กล้อง" for r in roads[:5]))
    return lines


def tide_context(water):
    tide = (water or {}).get("tide") or []
    if not tide:
        return []
    t = tide[0]
    return [f"น้ำทะเลหนุน {t.get('name')} วันที่ {t.get('date')}: สูงสุด {round(t.get('max') or 0, 2)} ม. เวลา {t.get('max_time')}, ต่ำสุด {round(t.get('min') or 0, 2)} ม. เวลา {t.get('min_time')}"]


def north_flow_context(nf):
    """Northern water on its way down the Chao Phraya (north_flow.brief()): headline, then the warnings."""
    if not nf:
        return []
    lines = [f"น้ำเหนือ → ภาคกลาง (กรมชลประทาน/ThaiWater + คาดการณ์ 4 วัน): {nf['headline']}"]
    lines += [f"  - {a}" for a in nf.get("alerts") or []]
    return lines


def _asked(question, *names):
    """True when any place name (with or without the เขต/แขวง prefix) appears in the question."""
    for n in names:
        n = (n or "").strip()
        for v in (n, n.removeprefix("เขต").removeprefix("แขวง").strip()):
            if len(v) >= 3 and v in question:
                return True
    return False


def air_context(air, question):
    """PM2.5 per station (AirBKK + Air4Thai): city average, worst stations and any station the user named."""
    items = (air or {}).get("items") or []
    if not items:
        return []
    counts = ", ".join(f"{k} {v}" for k, v in ((air or {}).get("counts") or {}).items())
    lines = [f"ฝุ่น PM2.5 รายชั่วโมง (AirBKK + Air4Thai {_hhmm(air.get('source_ts') or air.get('updated_at'))}): เฉลี่ย {air.get('avg_pm25')} µg/m³ "
             f"จาก {air.get('total')} สถานี ({counts})"]
    picked = [i for i in items if _asked(question, i.get("name"), i.get("area"))][:5]
    for i in picked + [i for i in items[:5] if i not in picked]:
        lines.append(f"  - {i.get('name')} ({i.get('area')} {i.get('province')}): PM2.5 {i.get('pm25')} µg/m³ {i.get('label')}")
    return lines


def guidance_context(guidance, question):
    """Per-corridor dispersal advice: hotspots, bypass roads with live flow, what to do."""
    items = (guidance or {}).get("items") or []
    if not items:
        return []
    picked = [i for i in items if _asked(question, i.get("name"), i.get("search_road"))
              or any(_asked(question, r.get("name")) for r in i.get("roads") or [])]
    lines = ["คำแนะนำระบายรถรายสายทางหลัก (เส้นเลี่ยงพร้อม flow สด):"]
    for i in (picked + [i for i in items if i not in picked])[:6]:
        spots = ", ".join(s.get("label") for s in (i.get("hotspots") or [])[:3] if s.get("label"))
        alts = ", ".join(f"{a['name']} ({flow_th(a.get('flow'))})" for a in (i.get("alternatives") or [])[:3])
        lines.append(f"  - {i['name']} ({i.get('zone')}): {i.get('status_label')}"
                     + (f", จุดสะสม {spots}" if spots else "") + (f", ทางเลี่ยง {alts}" if alts else "")
                     + f" | แนะนำ: {i.get('action')}")
    return lines


def road_flood_context(road_risk, flood_report, question):
    """Per-road flood level by official standards plus the AI read of the road sensors."""
    lines = []
    rr = road_risk or {}
    if rr.get("items"):
        c = rr.get("counts") or {}
        lth = rr.get("level_th") or {}
        lines.append("ระดับน้ำท่วมรายถนน (เกณฑ์ สนน.กทม./ปภ./กรมอุตุฯ): "
                     + ", ".join(f"{lth.get(k, k)} {v} สาย" for k, v in c.items() if v) + f" จาก {rr.get('total')} สาย")
        items = rr["items"]
        by_road = [i for i in items if _asked(question, i.get("road"))]
        picked = (by_road + [i for i in items if i not in by_road and _asked(question, i.get("district"))])[:8]
        top = [i for i in items if i.get("class", 0) > 0 and i not in picked][:8]
        for i in picked + top:
            why = " · ".join(x for x in [
                f"น้ำบนถนน {i['flood_cm']} ซม." if i.get("flood_cm") else None,
                f"ฝน 24 ชม. {i['rain_24h']} มม." if i.get("rain_24h") else None,
                f"{i['gauge_at']} {i['gauge_pct']}% ของตลิ่ง" if i.get("gauge_pct") else None] if x)
            lines.append(f"  - {i['road']} ({i.get('district')} {i.get('province')}): {i.get('level_th')}" + (f" ({why})" if why else ""))
        if not picked and not top:
            lines.append("  - ไม่มีถนนสายใดเข้าเกณฑ์เฝ้าระวังตอนนี้")
    fr = flood_report or {}
    if fr.get("headline"):
        lines.append(f"บทวิเคราะห์น้ำท่วมขังจากเซ็นเซอร์ถนน ({fr.get('severity')}): {fr['headline']} {fr.get('detail', '')}")
        for h in fr.get("hotspots") or []:
            lines.append(f"  - จับตา {h['where']}: {h.get('note', '')}")
        if fr.get("outlook"):
            lines.append(f"  แนวโน้ม: {fr['outlook']}")
    return lines


KIND_TH = {"wrong_way": "ย้อนศร", "no_helmet": "ไม่สวมหมวกกันน็อก"}


def patrol_context(helmet, wrongway, violations):
    """Traffic violations caught by the AI patrols (no helmet / wrong way) today."""
    lines = []
    h = (helmet or {}).get("status") or {}
    if h.get("today"):
        t = h["today"]
        lines.append(f"ตรวจหมวกกันน็อกจากกล้อง กทม. วันนี้: ตรวจ {t['captures']} ภาพ ไม่สวม {t['no_helmet']} สวม {t['helmet']} "
                     f"ไม่ชัด {t['unclear']} รอตรวจ {t['pending']} (สะสมไม่สวมทั้งหมด {h.get('total_no_helmet')})")
    for r in (helmet or {}).get("recent") or []:
        lines.append(f"  - [{_hhmm(r.get('ts'))}] ไม่สวมหมวก {r.get('title')} เขต{r.get('district')}")
    w = (wrongway or {}).get("status") or {}
    if w.get("today"):
        t = w["today"]
        lines.append(f"ตรวจย้อนศรจากกล้อง กทม. วันนี้: ตรวจ {t['captures']} ภาพ ย้อนศร {t['wrong_way']} ไม่ใช่ {t['ok']} "
                     f"ไม่ชัด {t['unclear']} รอตรวจ {t['pending']} (สะสมย้อนศรทั้งหมด {w.get('total_wrong_way')})")
    for r in (wrongway or {}).get("recent") or []:
        lines.append(f"  - [{_hhmm(r.get('ts'))}] ย้อนศร {r.get('title')} เขต{r.get('district')} (วิ่ง{r.get('heading_th')} ช่องนี้ปกติ{r.get('expected_th')})")
    v = violations or {}
    if v.get("counts"):
        lines.append("กล้อง AI ที่เปิดอยู่ พบการฝ่าฝืน 24 ชม.: " + ", ".join(f"{KIND_TH.get(k, k)} {n}" for k, n in v["counts"].items()))
    return lines


def analytics_context(a):
    """Dashboard analytics: congestion index + causes, density tiers, flood 1-6 h outlook, accident black spots."""
    return analytics_traffic(a) + analytics_flood(a) + analytics_accidents(a)


def analytics_traffic(a):
    lines = []
    t = (a or {}).get("traffic") or {}
    if t.get("ready"):
        lines.append(f"ดัชนีความแออัด (แดชบอร์ด): {t.get('congestion_index')} ({t.get('congestion_level')}), "
                     f"รายงานเหตุ 6 ชม. {t.get('reports_6h')} เรื่อง")
        for r in (t.get("top5") or [])[:5]:
            lines.append(f"  - ติดสุด {r['name']}: ติดยาว {r['red_km']} กม. สาเหตุ: {r.get('cause_text')}")
    d = (a or {}).get("density") or {}
    if d.get("ready"):
        lines.append("ความหนาแน่นถนน: " + ", ".join(
            f"{x['label']} {x['roads']} สาย ({x['km_pct']}% ของระยะ) เช่น {', '.join(x.get('examples', [])[:3])}" for x in d.get("tiers", [])))
    return lines


def analytics_flood(a):
    lines = []
    f = (a or {}).get("flood") or {}
    if f.get("ready"):
        urgent = f.get("urgent_districts") or []
        if urgent:
            lines.append("เขตน้ำเร่งด่วน: " + ", ".join(
                f"{u['district']} (ล้น {u['overflow']} ใกล้เต็ม {u['high']} ถนนท่วม {u['flood_roads']} ลึกสุด {u['max_depth_cm']} ซม.)" for u in urgent[:6]))
        pred = [p for p in f.get("prediction") or [] if p.get("peak_level")]
        if pred:
            lines.append("คาดการณ์เสี่ยงน้ำท่วม 1-6 ชม.: " + ", ".join(
                f"{p['zone']} สูงสุดชั่วโมงที่ {p['peak_h']} ระดับ {p['peak_level']} (คะแนน {p['peak_score']})" for p in pred[:6]))
    return lines


def analytics_accidents(a):
    lines = []
    acc = (a or {}).get("accidents") or {}
    spots = acc.get("black_spots") or []
    if spots:
        lines.append("จุดเสี่ยงอุบัติเหตุ (black spot) สูงสุด:")
        for b in spots[:5]:
            lines.append(f"  - {b['place']} เขต{b['district']} ({b['road_type']}): {b['cases']} เคส ตาย {b['dead']} เจ็บ {b['injured']} "
                         f"ความสำคัญ{b['priority']} มาตรการ: {' / '.join(b.get('measures', [])[:2])}")
    return lines


def weather_context(outlook, water, tmd, place="กรุงเทพฯ"):
    """Weather: 3-day forecast for `place`, the 24 h rain / wind outlook per Bangkok zone, TMD warnings."""
    lines = []
    days = (outlook or {}).get("days") or []
    if days:
        lines.append(f"พยากรณ์อากาศ{place} 3 วัน (MET Norway):")
        for d in days:
            if d["rain_mm"] >= 0.5:
                rain = f"ฝนรวม {d['rain_mm']} มม." + (f" ช่วง {d['rain_hours']} น." if d.get("rain_hours") else "")
            else:
                rain = "ไม่มีฝนหรือฝนน้อยมาก"
            temp = f", อุณหภูมิ {d['tmin']}-{d['tmax']} °C" if d.get("tmin") is not None else ""
            lines.append(f"  - {d['day']} ({d['date']}): {d['text']}, {rain}{temp}")
    zones = (water or {}).get("weather") or []
    if zones:
        lines.append("พยากรณ์ฝน/ลม/พายุ 24 ชม. รายโซน (เรียงเสี่ยงมากไปน้อย):")
        lines += [_fmt_zone(z) for z in zones]
    for o in ((water or {}).get("ntw") or {}).get("rain_outlook") or []:
        lines.append(f"คาดการณ์ฝน 3 วัน: {o['province']} {o['text']}")
    active = (tmd or {}).get("active") or []
    for w in sorted(active, key=lambda w: not w.get("bkk"))[:3]:
        lines.append(f"ประกาศกรมอุตุนิยมวิทยา {w.get('date')}: {w.get('title')} — {(w.get('summary') or '')[:300]}")
    return lines


def _cm(v):
    return f" {v:.0f} ซม." if v else ""


def predict_context(ex):
    """What the site's analysts expect next: the flood agent, the water outlook, northern water by district."""
    lines = []
    fa = (ex.get("flood_agent") or {}).get("report") or {}
    if fa.get("headline"):
        lines.append(f"AI วิเคราะห์น้ำท่วม ({fa.get('level_th') or fa.get('overall_level')}, {_hhmm(fa.get('generated_at'))}): {fa['headline']}")
        if fa.get("outlook"):
            lines.append(f"  คาดการณ์: {fa['outlook'][:400]}")
        roads = fa.get("roads_to_avoid") or []
        if roads:
            lines.append("  ถนนที่ควรเลี่ยงเพราะน้ำ: " + ", ".join(
                f"{r.get('road')} ({r.get('district')}{_cm(r.get('depth_cm'))})" for r in roads[:6]))
    wa = (ex.get("water_agent") or {}).get("report") or {}
    if wa.get("outlook_summary"):
        lines.append(f"AI คาดการณ์สถานการณ์น้ำ ({wa.get('status_label')}): {wa['outlook_summary'][:400]}")
        for z in (wa.get("zones") or [])[:5]:
            lines.append(f"  - {z.get('name')} [{z.get('badge')}]: {(z.get('forecast') or '')[:220]}")
    ni = (ex.get("north_impact") or {}).get("report") or {}
    if ni.get("title"):
        lines.append(f"คาดการณ์น้ำเหนือต่อกรุงเทพฯ ({ni.get('status_label')}): {ni['title']}")
        lines += [f"  - {t.get('when')}: {t.get('event')}" for t in (ni.get("timeline") or [])[:4]]
        dists = ni.get("districts") or []
        if dists:
            lines.append("  เขตที่จะได้รับผลกระทบ: " + "; ".join(
                f"{d.get('district')} ({d.get('level')}, {d.get('when')}) {(d.get('cause') or '')[:80]}" for d in dists[:6]))
        roads = ni.get("roads") or []
        if roads:
            lines.append("  ถนนเสี่ยงน้ำท่วม: " + "; ".join(f"{r.get('road')} ({r.get('level')}, {r.get('when')})" for r in roads[:6]))
    return lines + analytics_flood(ex.get("analytics"))


def _spot_th(h):
    depth = _cm(h.get("depth_cm")) or (f" {h['depth_text']}" if h.get("depth_text") else "")
    return f"{h.get('name')}{depth} (แหล่งข้อมูล: {h.get('source')})"


def route_context(r):
    """The planned route in plain Thai, for the model to word the answer from."""
    o, d = r["origin"], r["destination"]
    lines = ["เส้นทางที่ระบบคำนวณ (ใช้ถนน ระยะ เวลาจากส่วนนี้เท่านั้น):",
             f"จาก {o.get('label') or o.get('name')} ไป {d.get('label') or d.get('name')}: "
             f"ระยะ {r['km']} กม. ใช้เวลาประมาณ {r['minutes'][0]}-{r['minutes'][1]} นาที (รวมช่วงรถติดแล้ว)",
             "ถนนตามลำดับ: " + " → ".join(f"{x['name']} ({x['km']} กม.)" for x in r["roads"])]
    missing = r.get("flood_missing") or []
    if not r.get("flood_checked") and missing:
        lines.append(f"ตรวจน้ำท่วมได้ไม่ครบ: อ่านข้อมูลจาก {', '.join(missing)} ไม่ได้ ห้ามบอกว่าเส้นทางนี้ปลอดน้ำท่วม "
                     "ให้บอกผู้ใช้ว่าตรวจได้บางส่วน และควรดูแผนที่น้ำท่วมก่อนออกเดินทาง")
    elif not r.get("flood_checked"):
        lines.append("ตรวจจุดน้ำท่วมบนเส้นทางไม่ได้ตอนนี้ ห้ามบอกว่าอ้อมน้ำท่วมหรือเส้นทางปลอดน้ำท่วม "
                     "ให้บอกผู้ใช้ว่ายังยืนยันเรื่องน้ำท่วมไม่ได้")
    fast = r.get("fastest")
    if r.get("avoided"):
        lines.append(f"เส้นนี้อ้อมจุดน้ำท่วม {len(r['avoided'])} จุดที่เส้นทางปกติ (ผ่าน {', '.join(fast['roads'][:3])}) จะเจอ: "
                     + "; ".join(_spot_th(h) for h in r["avoided"][:5]))
    elif fast:
        lines.append(f"เลือกเส้นนี้แทนเส้นผ่าน {', '.join(fast['roads'][:3])} ({fast['km']} กม.) เพราะรถติดน้อยกว่า")
    if not r.get("avoided"):
        # without this the model takes flooded spots from the city data and says the route went round them
        lines.append("เส้นนี้ไม่ได้อ้อมจุดน้ำท่วมใด ห้ามบอกว่าอ้อมหรือหลีกเลี่ยงน้ำท่วม และห้ามยกจุดน้ำท่วมที่ไม่อยู่ในส่วนนี้มาเป็นเหตุผลของเส้นทาง")
    if r.get("flood_on_route"):
        lines.append("จุดน้ำท่วมที่เลี่ยงไม่ได้บนเส้นทาง: " + "; ".join(f"{_spot_th(h)} กม.ที่ {h['at_km']}" for h in r["flood_on_route"][:5]))
    if r.get("wet_on_route"):
        lines.append("น้ำขังเล็กน้อยบนเส้นทาง (รถเก๋งยังผ่านได้ ขับช้า ๆ): " + "; ".join(_spot_th(h) for h in r["wet_on_route"][:5]))
    if r.get("flood_at_ends"):
        lines.append("น้ำท่วมใกล้จุดต้นทาง/ปลายทาง (เลี่ยงไม่ได้): " + "; ".join(_spot_th(h) for h in r["flood_at_ends"][:4]))
    if r.get("jams"):
        lines.append("ช่วงรถติดบนเส้นทาง: " + "; ".join(f"{j['road']} ติด {j['km']} กม. (ราวกม.ที่ {j['at_km']} จากต้นทาง)" for j in r["jams"]))
    if r.get("flood_checked") and not any(r.get(k) for k in ("avoided", "flood_on_route", "wet_on_route", "flood_at_ends", "jams")):
        lines.append("ไม่พบจุดน้ำท่วมหรือช่วงรถติดบนเส้นทางนี้ตอนนี้")
    return lines


# Everyday names of provinces (and of towns people name instead of the province)
PLACE_ALIASES = {"อยุธยา": "พระนครศรีอยุธยา", "โคราช": "นครราชสีมา", "กทม": thai_regions.BANGKOK, "สุพรรณ": "สุพรรณบุรี",
                 "กาญจน์": "กาญจนบุรี", "อุบล": "อุบลราชธานี", "อุดร": "อุดรธานี", "ปราจีน": "ปราจีนบุรี",
                 "แปดริ้ว": "ฉะเชิงเทรา", "หาดใหญ่": "สงขลา", "พัทยา": "ชลบุรี", "หัวหิน": "ประจวบคีรีขันธ์"}
NATION_WORDS = ("ทั่วประเทศ", "ประเทศ", "ทั่วไทย", "จังหวัด", "ภาคเหนือ", "ภาคอีสาน", "ภาคใต้", "ภาคกลาง", "ภาคตะวันออก",
                "ภาคตะวันตก", "ต่างจังหวัด")


def named_places(question, areas=None):
    """[(province, [amphoe names asked])] the question names, at most three: provinces by name ("จ.X", the long
    names, everyday names like โคราช), then provinces of the districts it names (ปากช่อง -> นครราชสีมา)."""
    text = question or ""
    found = {}
    for alias, prov in PLACE_ALIASES.items():
        if alias in text:
            found.setdefault(prov, [])
    t = text
    for _ in range(3):
        prov = thai_regions.find_in_text(t)
        if not prov:
            break
        found.setdefault(prov, [])
        t = t.replace(prov, " ").replace("กรุงเทพ", " ")
    for p in (areas or {}).get("provinces") or []:
        for a in p.get("amphoes") or []:
            name = a.get("name") or ""
            if len(name) >= 4 and name in text:
                found.setdefault(p["province"], []).append(name)
    return list(found.items())[:3]


def _amphoe_th(province, name):
    return f"เขต{name}" if province == thai_regions.BANGKOK else f"อ.{name}"


def province_traffic_context(areas, named):
    """Traffic over the whole country from Longdo's lines: the country, the provinces asked (with their worst
    districts) and the most jammed provinces."""
    a = areas or {}
    provs = {p["province"]: p for p in a.get("provinces") or []}
    if not a.get("ready") or not provs:
        return []
    n = a.get("national") or {}
    lines = [f"รถติดทั่วประเทศ (Longdo Traffic {_hhmm(a.get('updated_at'))}): {flow_th(n.get('flow'))} "
             f"ติดขัดรวม {n.get('red_km')} กม. จากถนนที่มีข้อมูล {n.get('total_km')} กม."]
    for prov, asked in named:
        p = provs.get(prov)
        if not p:
            continue
        jam = f" ติดขัด {p['red_km']} กม." if p.get("red_km") else ""
        lines.append(f"จังหวัด{prov} ({p.get('region')}): {flow_th(p.get('flow'))}{jam} จากถนนที่มีข้อมูล {p.get('total_km')} กม.")
        ams = [x for x in p.get("amphoes") or [] if x.get("flow") is not None]
        picked = [x for x in ams if x.get("name") in asked]
        worst = sorted((x for x in ams if x not in picked), key=lambda x: x["flow"])[:4]
        for x in picked + worst:
            lines.append(f"  - {_amphoe_th(prov, x['name'])}: {flow_th(x['flow'])}" + (f" ติดขัด {x['red_km']} กม." if x.get("red_km") else "")
                         + f" จากถนนที่มีข้อมูลในอำเภอ {x.get('total_km')} กม.")
    top = sorted((p for p in provs.values() if p.get("flow") is not None and (p.get("total_km") or 0) >= 30),
                 key=lambda p: p["flow"])[:5]
    if top:
        lines.append("จังหวัดที่รถติดที่สุดตอนนี้: " + ", ".join(f"{p['province']} ({flow_th(p['flow'])} ติดขัด {p.get('red_km')} กม.)" for p in top))
    return lines


def _province_flood_row(p):
    k = p.get("counts") or {}
    r = p.get("rain") or {}
    bits = [f"ล้นตลิ่ง {k.get('overflow', 0)} จุด", f"น้ำสูง {k.get('high', 0)} จุด"]
    if k.get("highways"):
        bits.append(f"ทางหลวงน้ำท่วม {k['highways']} สาย")
    if r.get("max_mm"):
        bits.append(f"ฝนสูงสุด {r['max_mm']:.0f} มม. ที่{r.get('place') or '-'}")
    if k.get("reports"):
        bits.append(f"คนแจ้งน้ำท่วม {k['reports']} เรื่อง")
    return f"- {p['province']} ({p.get('region')}): {p.get('label')} — " + ", ".join(bits)


def province_flood_context(pf, named):
    """Flood level of every province (province_flood.status()): the country, the provinces asked with the AI's
    reading and their highest gauges, and the provinces flooded worst."""
    d = pf or {}
    provs = d.get("provinces") or []
    if not provs:
        return []
    c = d.get("counts") or {}
    ai = d.get("ai") or {}
    lines = [f"น้ำท่วมรายจังหวัดทั่วประเทศ (ระดับน้ำ ThaiWater ทางหลวง ฝน {_hhmm(d.get('updated_at'))}): วิกฤต {c.get('critical', 0)} "
             f"น้ำท่วม {c.get('flood', 0)} เฝ้าระวัง {c.get('watch', 0)} ปกติ {c.get('normal', 0)} จังหวัด"]
    if ai.get("overview"):
        lines.append(f"AI สรุปน้ำท่วมทั่วประเทศ: {ai['overview'][:400]}")
    by = {p["province"]: p for p in provs}
    reading = ai.get("provinces") or {}
    asked = [prov for prov, _ in named]
    for prov in asked:
        p = by.get(prov)
        if not p:
            continue
        lines.append(_province_flood_row(p))
        for key, label in (("summary", "สรุป"), ("analysis", "วิเคราะห์"), ("advice", "คำแนะนำ")):
            if (reading.get(prov) or {}).get(key):
                lines.append(f"  {label}: {reading[prov][key][:300]}")
        for g in sorted((g for g in p.get("gauges") or [] if g.get("pct") is not None), key=lambda g: -g["pct"])[:3]:
            lines.append(f"  - จุดวัดน้ำ{g.get('name')} อ.{g.get('amphoe')}: น้ำสูง {g['pct']:.0f}% ของความสูงตลิ่ง "
                         f"(เกิน 100% = ล้นตลิ่ง ไม่ใช่ความสูงเป็นเมตร)")
    worst = [p for p in provs if p.get("level") in ("critical", "flood") and p["province"] not in asked]
    if worst:
        lines.append("จังหวัดที่น้ำท่วมหนัก (เรียงหนักไปเบา):")
        lines += [_province_flood_row(p) for p in worst[:8]]
    return lines


def province_weather_context(ex, named):
    """3-day forecast of each province asked (not Bangkok, which the weather block already has), at its first
    river gauge; `ex["weather_at"]` is weather_now.outlook."""
    fn = ex.get("weather_at")
    gauges = {p["province"]: p.get("gauges") or [] for p in (ex.get("provinces") or {}).get("provinces") or []}
    lines = []
    for prov, _ in named:
        g = next((g for g in gauges.get(prov, []) if g.get("lat") is not None), None)
        if not fn or prov == thai_regions.BANGKOK or not g:
            continue
        try:
            lines += weather_context(fn(g["lat"], g["lng"]), None, None, place=f"จังหวัด{prov}")
        except Exception as e:  # noqa: BLE001 - MET Norway down: the Bangkok forecast still goes in
            print(f"[Chat] weather for {prov} unavailable: {str(e)[:120]}")
    return lines


def site_context(question, ex):
    """Every other data set shown on the website, so the bot never says 'no data' for something on screen."""
    return (air_context(ex.get("air"), question) + guidance_context(ex.get("guidance"), question)
            + road_flood_context(ex.get("road_risk"), ex.get("flood_report"), question)
            + patrol_context(ex.get("helmet"), ex.get("wrongway"), ex.get("violations"))
            + analytics_context(ex.get("analytics")))


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


def context_sections(traffic, question, camera_stats=None, water=None, extra=None):
    """Live data as {topic: [lines]}; "base" is the one-line picture of the city that always goes in."""
    ex = extra or {}
    s = traffic.get_summary(top=8)
    sec = {"base": [f"ตอนนี้ {time.strftime('%Y-%m-%d %H:%M')} (เวลาไทย)"], "route": [], **{k: [] for k in ALL_TOPICS}}
    if not s.get("ready"):
        sec["base"].append("ยังไม่มีข้อมูลจราจร (ระบบกำลังโหลด)")
    else:
        sec["base"] += [
            f"เวลาข้อมูล: {time.strftime('%H:%M', time.localtime(s['updated_at']))} "
            f"({'ออนไลน์' if s.get('online') else 'ออฟไลน์ ใช้ข้อมูลล่าสุดที่บันทึกไว้'})",
            f"ภาพรวมกรุงเทพฯ: {flow_th(s['flow_index'])} (ระยะถนนที่คล่องตัว {s['green_pct']}% ชะลอตัว {s['yellow_pct']}% "
            f"ติดขัด {s['red_pct']}% จาก {s['road_count']} สาย)",
        ]
        t = sec["traffic"]
        mentioned = traffic.find_roads_in_text(question)
        if mentioned:
            t.append("ถนนที่ผู้ใช้ถามถึง:")
            t += [_fmt_road(r) for r in mentioned]
        trend = _trend_th(s.get("history", []))
        if trend:
            t.append(f"แนวโน้มจราจร 1 ชม.ล่าสุด: {trend}")
            sec["predict"].append(f"แนวโน้มจราจร 1 ชม.ล่าสุด: {trend}")
        t.append("ถนนที่ติดขัดมากที่สุดตอนนี้:")
        t += [_fmt_road(r) for r in s["congested"][:8]]
        t.append("ถนนสายหลักที่รถคล่อง:")
        t += [_fmt_road(r) for r in s["free_flow"][:5]]
    if camera_stats and camera_stats.get("active"):
        sec["traffic"].append(
            f"กล้อง AI ที่เปิดอยู่: {camera_stats.get('title')} ({camera_stats.get('province')}) "
            f"รถยนต์ {camera_stats.get('cars', 0)} มอเตอร์ไซค์ {camera_stats.get('motorcycles', 0)} "
            f"รถบรรทุก {camera_stats.get('trucks', 0)} รวม {camera_stats.get('total', 0)} คัน — {camera_stats.get('traffic_level', '')}")
    sec["traffic"] += (guidance_context(ex.get("guidance"), question) + bma_count_context(ex.get("bma_analytics"))
                       + analytics_traffic(ex.get("analytics")))
    sec["flood"] += (water_context(water) + north_flow_context(ex.get("north_flow")) + tide_context(water)
                     + road_flood_context(ex.get("road_risk"), ex.get("flood_report"), question)
                     + analytics_flood(ex.get("analytics")))
    sec["weather"] += weather_context(ex.get("weather_outlook"), water, ex.get("tmd"))
    sec["predict"] += predict_context(ex) + weather_context(ex.get("weather_outlook"), None, None)
    sec["accident"] += (incident_context(ex.get("incidents"), ex.get("bma_events"))
                        + accident_stats_context(ex.get("rsc"), ex.get("camera_risk"))
                        + patrol_context(ex.get("helmet"), ex.get("wrongway"), ex.get("violations"))
                        + analytics_accidents(ex.get("analytics")))
    sec["air"] += air_context(ex.get("air"), question)

    # The whole country: first when the question names a province outside Bangkok or asks about the country,
    # after the Bangkok detail otherwise
    named = named_places(question, ex.get("areas"))
    sec["named"] = [prov for prov, _ in named]
    away = any(prov != thai_regions.BANGKOK for prov in sec["named"]) or any(w in (question or "") for w in NATION_WORDS)
    nation = {"traffic": province_traffic_context(ex.get("areas"), named),
              "flood": province_flood_context(ex.get("provinces"), named),
              "weather": province_weather_context(ex, named) if away else []}
    for k, lines in nation.items():
        sec[k] = lines + sec[k] if away else sec[k] + lines
    if away:
        sec["predict"] = nation["flood"] + sec["predict"]
    if ex.get("route"):
        sec["route"] = route_context(ex["route"])
    elif ex.get("route_error"):
        sec["route"] = [f"เส้นทาง: {ex['route_error']}"]
    return sec


def pick_topics(question, sections):
    """Topics for the prompt; a named road puts traffic in, a route adds the water and the jams beside it,
    an overview question takes every topic."""
    chosen = question_topics(question)
    if "traffic" not in chosen and any(x.startswith("ถนนที่ผู้ใช้ถามถึง") for x in sections.get("traffic", [])):
        chosen.append("traffic")
    if sections.get("route"):
        chosen = ["route"] + chosen
        for k in ("flood", "traffic"):
            if k not in chosen:
                chosen.append(k)
    if not chosen and any(w in (question or "") for w in OVERVIEW_WORDS):
        chosen = ["traffic", "flood", "weather", "accident", "air"]
    if not chosen and sections.get("named"):        # "เชียงใหม่เป็นยังไงบ้าง"
        chosen = ["traffic", "flood", "weather"]
    return chosen


def build_context(traffic, question, camera_stats=None, water=None, extra=None, max_chars=None, topics=None):
    """The live-data block for the prompt. With max_chars, only the asked topics go in, cut to fit."""
    sec = context_sections(traffic, question, camera_stats, water, extra)
    if max_chars is None and topics is None:
        order = ["route"] + ALL_TOPICS
    else:
        order = pick_topics(question, sec) if topics is None else topics
    lines = list(sec["base"])
    seen = set(lines)
    budget = (max_chars or 10 ** 9) - sum(len(x) + 1 for x in lines)
    for k in order:
        if not sec.get(k) or budget <= 0:
            continue
        lines.append("")
        for x in sec[k]:          # rows are ranked inside each builder, so cutting keeps the important ones
            if x in seen:         # a line can belong to two topics
                continue
            if len(x) + 1 > budget:
                break
            lines.append(x)
            seen.add(x)
            budget -= len(x) + 1
    return "\n".join(lines)



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


# ---------------------------------------------------------------- route questions
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


# Common words written without their tone mark ("ไม" for ไม่, "ผาน" for ผ่าน, "ได" for ได้ ...): the gateway's Qwen
# sometimes drops tone marks for a whole reply. A few in one reply means it happened; one can be a real word.
_NO_TONE = re.compile(r"ไม[ ก-ฮ](?![ัิ-ฺ็-์])|ผาน|ทวม|ได[ ,.)\n]|แต[ \n]|นี[ ,\n]|เพยี|ตึด|ตืด|เทาน")
GARBLED_MIN = 3


def garbled(text):
    """How many tone-mark-less common words the reply has."""
    return len(_NO_TONE.findall(text or ""))


def chat(traffic, messages, camera_stats=None, water=None, extra=None, router=None, location=None):
    """messages: list of {role: user|assistant, content: str}. Returns {reply, mode[, model, route]}.
    `water` is water_service.get_summary() or None when it is unavailable.
    `extra` holds optional sources: incidents, bma_events, bma_analytics, rsc, camera_risk, air, guidance, ...
    `router` (flood_route.FloodRouter) plans route questions; `location` is the user's {lat, lng} if shared."""
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    history = [{"role": m["role"], "content": m["content"][:HISTORY_CHARS]}
               for m in messages[-HISTORY_KEEP:] if m.get("content")]
    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": question or "สรุปสภาพจราจรตอนนี้"})
    asked = history[-1]["content"]

    extra = dict(extra or {})
    route = None
    if router and wants_route(asked):
        plan = plan_route(router, history, location)
        if plan and plan.get("ask"):
            return {"reply": plan["ask"], "mode": "local" if llm.enabled() else "offline",
                    "need_location": bool(plan.get("need_location"))}
        if plan and plan.get("route"):
            route = extra["route"] = plan["route"]
        elif plan:
            extra["route_error"] = plan["error"]

    def offline():
        out = {"reply": rule_based_reply(traffic, question, water, extra), "mode": "offline"}
        return dict(out, route=route) if route else out

    if not llm.enabled():
        return offline()
    style = answer_style(asked, question_topics(asked), route=bool(route))
    note = f"\n\nวิธีตอบคำถามนี้: {style}" if style else ""
    room = llm.token_budget(SYSTEM_PROMPT, note, *(m["content"] for m in history), reply_tokens=REPLY_TOKENS + 300)
    max_chars = max(0, int(room * local_llm.CHARS_PER_TOKEN))
    for share in (1.0, 0.5, 0.0):        # the character estimate can be off; shrink the data and retry
        context = build_context(traffic, asked, camera_stats, water, extra, max_chars=int(max_chars * share))
        turn = {"role": "user", "content": f"ข้อมูลสดที่เกี่ยวข้อง:\n{context}\n\nคำถาม: {asked}{note}"}
        try:
            prompt = [{"role": "system", "content": SYSTEM_PROMPT}] + history[:-1] + [turn]
            text = llm.chat(prompt, max_tokens=REPLY_TOKENS)
            if garbled(text) >= GARBLED_MIN:     # once the model drops a tone mark it keeps doing so: ask again
                again = llm.chat(prompt, max_tokens=REPLY_TOKENS, temperature=0.7)
                text = min((text, again), key=garbled)
            out = {"reply": text, "mode": "local", "model": llm.model}
            return dict(out, route=route) if route else out
        except local_llm.ContextTooLong:
            continue
        except Exception as e:  # noqa: BLE001 - local server off / model unloaded: answer from the data
            print(f"[Chat] local model error: {str(e)[:200]}")
            break
    return offline()
