"""
Traffic assistant chatbot.

Answers questions about how traffic is flowing on Bangkok roads, grounded in
the live per-road aggregation from traffic_service plus the YOLO camera counts.
Provider order:
  1. AI model           - local_llm.chat_client (CHAT_LLM_*, else LOCAL_LLM_* in .env)
  2. Rule-based summary - when the local server is off, so the page still works

The live data is split into topics (traffic, flood, accident, air) and only the topics the question is
about go into the prompt, most relevant first, cut to what fits the local model's context window.
"""
import time

import local_llm

llm = local_llm.chat_client

REPLY_TOKENS = 1200
HISTORY_KEEP = 6            # past messages sent with the question
HISTORY_CHARS = 800         # per past message

SYSTEM_PROMPT = """คุณคือ "ผู้ช่วยอัจฉริยะ" ของแอป BKK StreetSmart (กรุงเทพฯ และปริมณฑล)
ตอบได้ทุกคำถาม ทั้งเรื่องที่มีข้อมูลสดแนบมา และเรื่องทั่วไปทุกหัวข้อ (ความรู้ ภาษา คณิต เทคโนโลยี สุขภาพ อาหาร ท่องเที่ยว งาน ชีวิตประจำวัน เขียน/แปล/สรุป ฯลฯ)
เหมือน ChatGPT/Gemini ปกติ ไม่ต้องจำกัดตัวเองอยู่แค่เรื่องจราจรหรือน้ำท่วม

เรื่องที่มีข้อมูลสดให้ใช้
1) จราจร: การระบายรถของถนนจากเส้นจราจรสด (Longdo Traffic) จำนวนรถจากกล้อง AI (YOLO) ทั้งกล้องที่เลือกและกล้อง กทม. 500+ ตัว
   สรุปตามเขต/ถนน แนะนำเส้นทาง เวลาที่ควรออกเดินทาง
2) น้ำท่วม ฝน พายุ: ระดับน้ำแม่น้ำ/คลอง (ThaiWater/HII) เซ็นเซอร์น้ำท่วมถนน (กทม.) น้ำทะเลหนุน ฝนที่ตกแล้ว
   พยากรณ์ฝน-ลมกระโชก-พายุฝนฟ้าคะนอง 24 ชม.ล่วงหน้ารายพื้นที่ (Open-Meteo) และระดับเฝ้าระวังรายพื้นที่
3) อุบัติเหตุและเหตุการณ์: อุบัติเหตุที่กล้อง AI ตรวจพบตอนนี้ รายงานอุบัติเหตุจาก Longdo เหตุการณ์จากศูนย์จราจร กทม.
   (อุบัติเหตุ น้ำท่วม ปิดถนน ซ่อมถนน) และสถิติอุบัติเหตุ กทม. (ThaiRSC): วันนี้/ปีนี้ เขตเสี่ยง ประเภทรถ ช่วงเวลา จุดกล้องเสี่ยงสูง
4) คำแนะนำเกี่ยวกับเมือง: การเตรียมตัวรับมือน้ำท่วม/พายุ ขับขี่ปลอดภัย วางแผนเดินทางในกรุงเทพฯ กฎจราจร เบอร์ฉุกเฉิน
   (1669 แพทย์ฉุกเฉิน, 1197 จราจร, 191 ตำรวจ, 1555 กทม., 1784 ปภ., 1460 ชลประทาน) วิธีใช้แอปนี้ (หน้าแดชบอร์ด/แผนที่/กล้อง/น้ำ/AI)
5) ฝุ่น PM2.5/AQI รายชั่วโมงรายสถานี (AirBKK + Air4Thai) ค่าเฉลี่ยเมืองและสถานีที่ค่าสูงสุด
6) คำแนะนำระบายรถรายสายทางหลัก: จุดสะสม ทางเลี่ยงพร้อม flow สด และสิ่งที่ควรทำ
7) ระดับน้ำท่วมรายถนนตามเกณฑ์ทางการ (ห้ามขับผ่าน/ควรเลี่ยง/ผ่านได้/เฝ้าระวัง) และบทวิเคราะห์เซ็นเซอร์น้ำบนถนน
8) การฝ่าฝืนจากกล้อง AI: ไม่สวมหมวกกันน็อก และขับย้อนศร (วันนี้ สะสม และรายการล่าสุด)
9) analytics แดชบอร์ด: ดัชนีความแออัดและสาเหตุ ความหนาแน่นถนน เขตน้ำเร่งด่วน คาดการณ์น้ำท่วม 1-6 ชม. จุดเสี่ยงอุบัติเหตุ (black spot)

แนวทางตอบ
- ประโยคแรกต้องตอบสิ่งที่ถามตรง ๆ ก่อน แล้วค่อยให้รายละเอียดสนับสนุน 2-4 บรรทัด
  เช่น ถาม "ใช้เวลานานไหม" ตอบเป็นช่วงนาที, ถาม "ติดไหม" ตอบติด/ไม่ติด, ถาม "ท่วมไหม" ตอบท่วม/ไม่ท่วม
  ห้ามเล่าข้อมูลหมวดที่ไม่ได้ถาม (ถามเส้นทางอย่าเล่าน้ำท่วม/ฝุ่น ยกเว้นมีน้ำท่วมหรือเหตุบนเส้นทางนั้นจริง)
- ถามเวลาเดินทางจาก A ไป B: ประเมินระยะทางจากความรู้ทั่วไปเรื่องกรุงเทพฯ ปรับตาม flow ของถนนที่เกี่ยวข้องในข้อมูลสด
  ตอบเป็นช่วงเวลา (เช่น 35-50 นาที) บอกเส้นทางแนะนำ 1 เส้น และบอกว่าถนนช่วงไหนติดถ้ามี
- ตัวเลข/สถานะสดของจราจร น้ำ ฝน ฝุ่น อุบัติเหตุ การฝ่าฝืน ใช้จากข้อมูลที่แนบมาเท่านั้น ห้ามเดา
- ก่อนตอบว่า "ไม่มีข้อมูล" ให้หาในข้อมูลที่แนบมาทุกหมวดก่อน ชื่อถนน/เขตอาจอยู่คนละหมวด (เช่น ถนนในหมวดน้ำท่วมรายถนนหรือคำแนะนำระบายรถ เขตในสถานี PM2.5 หรือ black spot)
  ถ้าหาไม่เจอจริง ให้บอกตรง ๆ ว่าไม่มีข้อมูลของที่ถามตอนนี้ แล้วเสนอพื้นที่ใกล้เคียงหรือภาพรวมที่มีข้อมูลแทนเสมอ
- คำถามอื่นทุกเรื่อง ตอบเต็มที่จากความรู้ของคุณ ไม่ต้องอ้างข้อมูลสดและไม่ต้องดึงเรื่องกลับมาที่จราจร/น้ำท่วม
  ถ้าเป็นเรื่องที่เปลี่ยนเร็ว (ข่าว ราคา ผลกีฬา) บอกว่าเป็นความรู้ ณ ช่วงที่ฝึก อาจไม่ล่าสุด
- ใช้ข้อมูลสดที่แนบมาเฉพาะเมื่อเกี่ยวกับคำถาม ไม่ต้องไล่ทุกหมวด ถ้าถามภาพรวมเมืองให้สรุปหมวดละ 1-2 บรรทัดแล้วชี้จุดที่น่าห่วงสุด
- ตอบเป็นภาษาเดียวกับที่ผู้ใช้ถาม (ไทยเป็นหลัก) อบอุ่น เป็นกันเอง กระชับ ปกติไม่เกิน 8-12 บรรทัด ยาวกว่านี้ได้ถ้าผู้ใช้ขอรายละเอียด
  เช่น เขียนบทความ อธิบายทีละขั้น หรือโค้ด ใช้ bullet สั้น ๆ ได้ ไม่ต้องใส่หัวข้อ Markdown ใหญ่
- ถ้าผู้ใช้ให้ทำงาน เช่น แปล สรุป เขียน แก้ไข คำนวณ ให้ทำเลย ไม่ต้องถามกลับถ้าไม่จำเป็น
- อุบัติเหตุ: ระบุจุด เวลา แหล่งที่มา และแนะนำเส้นเลี่ยง ถ้าถามสถิติให้ระบุปี พ.ศ. และเทียบวันนี้/ปีนี้
- เรื่องจราจร: อธิบายด้วยค่า flow (0-100: 100 = โล่งทั้งสาย) และสัดส่วนเขียว/เหลือง/แดง
  ถ้าถามเส้นทาง A ไป B ให้เทียบถนนที่เกี่ยวข้องและแนะนำเส้นที่ระบายดีกว่า
- เรื่องน้ำท่วม/ฝน ให้ตอบตามลำดับนี้
  (1) สถานการณ์ตอนนี้: ถนนที่มีน้ำท่วมขัง (ระบุ ซม.) แม่น้ำ/คลองที่ล้นตลิ่งหรือใกล้เต็ม ฝนที่ตกแล้ว
  (2) คาดการณ์: ฝนสะสม 24 ชม., ช่วงเวลาที่ฝนหนักสุด, พายุฝนฟ้าคะนอง/ลมกระโชกแรง (กม./ชม.) รายพื้นที่
  (3) เตือนภัยรายพื้นที่: ใช้ระดับเฝ้าระวัง เขียว=ปกติ เหลือง=ติดตาม ส้ม=เฝ้าระวัง แดง=เตือนภัย ระบุชื่อพื้นที่/เขตให้ชัด
  (4) แนวทางป้องกัน/รับมือ 2-3 ข้อที่ทำได้จริง เช่น เลี่ยงถนนที่ท่วม ย้ายรถขึ้นที่สูง ยกของขึ้นชั้นบน เตรียมกระสอบทราย
      ตรวจท่อระบายน้ำหน้าบ้าน ไม่จอดรถใต้ต้นไม้/ป้ายโฆษณาช่วงพายุ ตัดไฟชั้นล่างถ้าน้ำเข้าบ้าน
  ถ้าผู้ใช้ถามพื้นที่เฉพาะ ให้เจาะพื้นที่นั้น ถ้าถามภาพรวม ให้ไล่จากพื้นที่ที่เสี่ยงสุดลงมา
- ถ้าจราจรกับน้ำท่วมเกี่ยวกัน (ถนนติดเพราะน้ำท่วม) ให้เชื่อมโยงและแนะนำเส้นเลี่ยง
- คำถามจราจร/น้ำท่วม/อุบัติเหตุ ปิดท้ายด้วยคำแนะนำสั้น ๆ 1 ข้อ คำถามทั่วไปไม่ต้องใส่คำแนะนำท้ายและไม่ต้องโยงกลับมาเรื่องเมือง
- หน้าจอแสดงข้อความล้วน: ห้ามใช้ Markdown ตัวหนา (**), หัวข้อ (#), ตาราง หรือสูตร LaTeX ($...$) เขียนสูตรเป็นข้อความธรรมดา เช่น H2O, 480 x 0.25 = 120"""

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


def _fmt_road(r):
    return (f"- {r['name']}: flow {r['flow']}/100 ({r['level']}), เขียว {r['green_pct']}% "
            f"เหลือง {r['yellow_pct']}% แดง {r['red_pct']}%, ระยะที่มีข้อมูล {r['length_km']} กม., ติดขัด {r['red_km']} กม.")


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
        alts = ", ".join(f"{a['name']} {a['flow']}/100" for a in (i.get("alternatives") or [])[:3])
        lines.append(f"  - {i['name']} ({i.get('zone')}): {i.get('status_label')} flow {i.get('flow')}/100"
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
            lines.append(f"  - ติดสุด {r['name']}: แดง {r['red_km']} กม. flow {r['flow']} สาเหตุ: {r.get('cause_text')}")
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


def site_context(question, ex):
    """Every other data set shown on the website, so the bot never says 'no data' for something on screen."""
    return (air_context(ex.get("air"), question) + guidance_context(ex.get("guidance"), question)
            + road_flood_context(ex.get("road_risk"), ex.get("flood_report"), question)
            + patrol_context(ex.get("helmet"), ex.get("wrongway"), ex.get("violations"))
            + analytics_context(ex.get("analytics")))


# Tie order matters: a route question that also names a place goes to traffic first
TOPIC_WORDS = {
    "traffic": ("ถนน", "จราจร", "รถ", "ติด", "ทาง", "เส้น", "ไป", "โล่ง", "แยก", "ซอย", "สะพาน", "ด่วน", "flow", "กล้อง",
                "ใช้เวลา", "นานไหม", "กี่นาที", "เดินทาง", "จาก"),
    "flood": FLOOD_WORDS,
    "accident": ("อุบัติเหตุ", "ชน", "รถคว่ำ", "เสียชีวิต", "บาดเจ็บ", "เหตุการณ์", "ปิดถนน", "หมวก", "ย้อนศร",
                 "ฝ่าฝืน", "จุดเสี่ยง", "black spot"),
    "air": ("ฝุ่น", "PM", "pm", "AQI", "aqi", "มลพิษ", "คุณภาพอากาศ"),
}
OVERVIEW_WORDS = ("ภาพรวม", "สรุป", "เมือง", "สถานการณ์", "วันนี้", "ตอนนี้", "กรุงเทพ", "กทม")
# Place names and words that contain a topic word but are not about it (สี"ลม", ท่า"น้ำ", "น้ำ"มัน)
NOT_TOPIC = ("สีลม", "ท่าน้ำ", "น้ำมัน", "น้ำใจ", "น้ำหอม", "ลมหายใจ", "ทางด่วน")


def question_topics(question):
    """Topics the question is about, most matched first ([] for a general question)."""
    q = question or ""
    for w in NOT_TOPIC:
        q = q.replace(w, " ทาง " if w == "ทางด่วน" else " ")
    hits = {k: sum(w in q for w in words) for k, words in TOPIC_WORDS.items()}
    return [k for k in sorted(hits, key=lambda k: -hits[k]) if hits[k]]


def context_sections(traffic, question, camera_stats=None, water=None, extra=None):
    """Live data as {topic: [lines]}; "base" is the one-line picture of the city that always goes in."""
    ex = extra or {}
    s = traffic.get_summary(top=8)
    sec = {"base": [f"ตอนนี้ {time.strftime('%Y-%m-%d %H:%M')} (เวลาไทย)"], "traffic": [], "flood": [], "accident": [], "air": []}
    if not s.get("ready"):
        sec["base"].append("ยังไม่มีข้อมูลจราจร (ระบบกำลังโหลด)")
    else:
        sec["base"] += [
            f"เวลาข้อมูล: {time.strftime('%H:%M', time.localtime(s['updated_at']))} "
            f"({'ออนไลน์' if s.get('online') else 'ออฟไลน์ ใช้ข้อมูลล่าสุดที่บันทึกไว้'})",
            f"ภาพรวมทั้งเมือง: flow index {s['flow_index']}/100, เขียว {s['green_pct']}% เหลือง {s['yellow_pct']}% "
            f"แดง {s['red_pct']}%, ถนนที่มีข้อมูล {s['road_count']} สาย รวม {s['total_km']} กม.",
        ]
        t = sec["traffic"]
        mentioned = traffic.find_roads_in_text(question)
        if mentioned:
            t.append("ถนนที่ผู้ใช้ถามถึง:")
            t += [_fmt_road(r) for r in mentioned]
        hist = s.get("history", [])
        if len(hist) >= 2:
            t.append(f"แนวโน้ม 1 ชม.ล่าสุด: flow index {' -> '.join(str(h['flow']) for h in hist[-20::4])}")
        t.append("ถนนที่ติดขัดมากที่สุดตอนนี้:")
        t += [_fmt_road(r) for r in s["congested"][:8]]
        t.append("ถนนสายหลักที่ระบายดี:")
        t += [_fmt_road(r) for r in s["free_flow"][:5]]
    if camera_stats and camera_stats.get("active"):
        sec["traffic"].append(
            f"กล้อง AI ที่เปิดอยู่: {camera_stats.get('title')} ({camera_stats.get('province')}) "
            f"รถยนต์ {camera_stats.get('cars', 0)} มอเตอร์ไซค์ {camera_stats.get('motorcycles', 0)} "
            f"รถบรรทุก {camera_stats.get('trucks', 0)} รวม {camera_stats.get('total', 0)} คัน — {camera_stats.get('traffic_level', '')}")
    sec["traffic"] += (guidance_context(ex.get("guidance"), question) + bma_count_context(ex.get("bma_analytics"))
                       + analytics_traffic(ex.get("analytics")))
    sec["flood"] += (water_context(water) + tide_context(water)
                     + road_flood_context(ex.get("road_risk"), ex.get("flood_report"), question)
                     + analytics_flood(ex.get("analytics")))
    sec["accident"] += (incident_context(ex.get("incidents"), ex.get("bma_events"))
                        + accident_stats_context(ex.get("rsc"), ex.get("camera_risk"))
                        + patrol_context(ex.get("helmet"), ex.get("wrongway"), ex.get("violations"))
                        + analytics_accidents(ex.get("analytics")))
    sec["air"] += air_context(ex.get("air"), question)
    return sec


def pick_topics(question, sections):
    """Topics for the prompt; a named road puts traffic in, an overview question takes every topic."""
    chosen = question_topics(question)
    if "traffic" not in chosen and any(x.startswith("ถนนที่ผู้ใช้ถามถึง") for x in sections.get("traffic", [])):
        chosen.append("traffic")
    if not chosen and any(w in (question or "") for w in OVERVIEW_WORDS):
        chosen = ["traffic", "flood", "accident", "air"]
    return chosen


def build_context(traffic, question, camera_stats=None, water=None, extra=None, max_chars=None, topics=None):
    """The live-data block for the prompt. With max_chars, only the asked topics go in, cut to fit."""
    sec = context_sections(traffic, question, camera_stats, water, extra)
    if max_chars is None and topics is None:
        order = ["traffic", "flood", "accident", "air"]
    else:
        order = pick_topics(question, sec) if topics is None else topics
    lines = list(sec["base"])
    budget = (max_chars or 10 ** 9) - sum(len(x) + 1 for x in lines)
    for k in order:
        if not sec[k] or budget <= 0:
            continue
        lines.append("")
        for x in sec[k]:          # rows are ranked inside each builder, so cutting keeps the important ones
            if len(x) + 1 > budget:
                break
            lines.append(x)
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


def rule_based_reply(traffic, question, water=None, extra=None):
    topics = question_topics(question)
    if not topics:
        return ("โหมดออฟไลน์ตอบได้เฉพาะสรุปจราจร น้ำท่วม/ฝน อุบัติเหตุ และฝุ่นจากข้อมูลสด" + chr(10) +
                "เชื่อมต่อโมเดล AI ไม่ได้ตอนนี้ ลองถามใหม่อีกครั้งในอีกสักครู่")
    if topics[0] == "accident":
        return _accident_reply(extra) + "\n" + OFFLINE_NOTE
    if topics[0] == "flood":
        return _flood_reply(water) + "\n" + OFFLINE_NOTE
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
            out.append(f"• {r['name']}: ระบายรถ {r['flow']}/100 ({r['level']}) เขียว {r['green_pct']}% เหลือง {r['yellow_pct']}% แดง {r['red_pct']}%")
    else:
        out.append(f"ภาพรวมตอนนี้ระบายรถได้ {s['flow_index']}/100 (เขียว {s['green_pct']}% เหลือง {s['yellow_pct']}% แดง {s['red_pct']}%)")
        out.append("ถนนที่ติดขัดมากสุด:")
        out += [f"• {r['name']} ติด {r['red_km']} กม. (flow {r['flow']})" for r in s["congested"][:4]]
    worst = min(mentioned or s["congested"][:1] or [None], key=lambda r: r["flow"] if r else 0)
    if worst and worst["flow"] < 45:
        out.append(f"แนะนำ: เลี่ยง {worst['name']} ไปก่อนนะ")
    else:
        out.append("แนะนำ: ไปได้เลย ทางค่อนข้างสะดวก")
    out.append(OFFLINE_NOTE)
    return "\n".join(out)


def chat(traffic, messages, camera_stats=None, water=None, extra=None):
    """messages: list of {role: user|assistant, content: str}. Returns {reply, mode}.
    `water` is water_service.get_summary() or None when it is unavailable.
    `extra` holds optional sources: incidents, bma_events, bma_analytics, rsc, camera_risk, air, guidance, ..."""
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    offline = lambda: {"reply": rule_based_reply(traffic, question, water, extra), "mode": "offline"}
    if not llm.enabled():
        return offline()

    history = [{"role": m["role"], "content": m["content"][:HISTORY_CHARS]}
               for m in messages[-HISTORY_KEEP:] if m.get("content")]
    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": question or "สรุปสภาพจราจรตอนนี้"})
    asked = history[-1]["content"]
    room = llm.token_budget(SYSTEM_PROMPT, *(m["content"] for m in history), reply_tokens=REPLY_TOKENS + 300)
    max_chars = max(0, int(room * local_llm.CHARS_PER_TOKEN))
    for share in (1.0, 0.5, 0.0):        # the character estimate can be off; shrink the data and retry
        context = build_context(traffic, question, camera_stats, water, extra, max_chars=int(max_chars * share))
        turn = {"role": "user", "content": f"ข้อมูลสดที่เกี่ยวข้อง:\n{context}\n\nคำถาม: {asked}"}
        try:
            text = llm.chat([{"role": "system", "content": SYSTEM_PROMPT}] + history[:-1] + [turn],
                                  max_tokens=REPLY_TOKENS)
            return {"reply": text, "mode": "local", "model": llm.model}
        except local_llm.ContextTooLong:
            continue
        except Exception as e:  # noqa: BLE001 - local server off / model unloaded: answer from the data
            print(f"[Chat] local model error: {str(e)[:200]}")
            break
    return offline()
