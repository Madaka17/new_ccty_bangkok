"""
Traffic assistant chatbot.

Answers questions about how traffic is flowing on Bangkok roads, grounded in
the live per-road aggregation from traffic_service plus the YOLO camera counts.
Provider order:
  1. Gemini Flash-Lite  - GEMINI_API_KEY (or GOOGLE_API_KEY), model from GEMINI_MODEL
  2. Claude             - ANTHROPIC_API_KEY or an `ant auth login` profile
  3. Rule-based summary - no key needed, so the page still works offline
"""
import json
import os
import time

try:
    import anthropic
except ImportError:  # keeps the server bootable without the SDK
    anthropic = None
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None

MODEL = "claude-opus-5"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

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

แนวทางตอบ
- ตัวเลข/สถานะสดของจราจร น้ำ ฝน อุบัติเหตุ ใช้จากข้อมูลที่แนบมาเท่านั้น ห้ามเดา ถ้าไม่มีข้อมูลถนน/พื้นที่ที่ถาม ให้บอกตรง ๆ และเสนอสิ่งใกล้เคียงที่มีข้อมูล
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
FLOOD_WORDS = ("น้ำ", "ฝน", "ท่วม", "พายุ", "ลม", "คลอง", "แม่น้ำ", "ระบายน้ำ", "เตือน", "เฝ้าระวัง", "ป้องกัน", "อากาศ")


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


def build_context(traffic, question, camera_stats=None, water=None, extra=None):
    s = traffic.get_summary(top=8)
    if not s.get("ready"):
        ex = extra or {}
        return "ยังไม่มีข้อมูลจราจร (ระบบกำลังโหลด)\n" + "\n".join(
            water_context(water) + incident_context(ex.get("incidents"), ex.get("bma_events")) + accident_stats_context(ex.get("rsc"), ex.get("camera_risk")))
    lines = [
        f"เวลาข้อมูล: {time.strftime('%H:%M', time.localtime(s['updated_at']))} "
        f"({'ออนไลน์' if s.get('online') else 'ออฟไลน์ ใช้ข้อมูลล่าสุดที่บันทึกไว้'})",
        f"ภาพรวมทั้งเมือง: flow index {s['flow_index']}/100, เขียว {s['green_pct']}% เหลือง {s['yellow_pct']}% "
        f"แดง {s['red_pct']}%, ถนนที่มีข้อมูล {s['road_count']} สาย รวม {s['total_km']} กม.",
    ]
    hist = s.get("history", [])
    if len(hist) >= 2:
        lines.append(f"แนวโน้ม 1 ชม.ล่าสุด: flow index {' -> '.join(str(h['flow']) for h in hist[-20::4])}")
    mentioned = traffic.find_roads_in_text(question)
    if mentioned:
        lines.append("ถนนที่ผู้ใช้ถามถึง:")
        lines += [_fmt_road(r) for r in mentioned]
    lines.append("ถนนที่ติดขัดมากที่สุดตอนนี้:")
    lines += [_fmt_road(r) for r in s["congested"][:8]]
    lines.append("ถนนสายหลักที่ระบายดี:")
    lines += [_fmt_road(r) for r in s["free_flow"][:5]]
    if camera_stats and camera_stats.get("active"):
        lines.append(
            f"กล้อง AI ที่เปิดอยู่: {camera_stats.get('title')} ({camera_stats.get('province')}) "
            f"รถยนต์ {camera_stats.get('cars', 0)} มอเตอร์ไซค์ {camera_stats.get('motorcycles', 0)} "
            f"รถบรรทุก {camera_stats.get('trucks', 0)} รวม {camera_stats.get('total', 0)} คัน — {camera_stats.get('traffic_level', '')}"
        )
    lines.append("")
    lines += water_context(water)
    lines += tide_context(water)
    ex = extra or {}
    lines.append("")
    lines += bma_count_context(ex.get("bma_analytics"))
    lines += incident_context(ex.get("incidents"), ex.get("bma_events"))
    lines += accident_stats_context(ex.get("rsc"), ex.get("camera_risk"))
    return "\n".join(lines)


def _gemini_client():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if genai is None or not key:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception:
        return None


def _gemini_chat(client, history, question):
    """history: list of {role, content}; last entry is the grounded user turn."""
    contents = [
        genai_types.Content(role="model" if m["role"] == "assistant" else "user",
                            parts=[genai_types.Part(text=m["content"])])
        for m in history
    ]
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4,
            max_output_tokens=2500,
        ),
    )
    return (resp.text or "").strip()


def _client():
    if anthropic is None:
        return None
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            or os.path.exists(os.path.join(os.path.expanduser("~"), ".config", "anthropic"))):
        return None
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


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


TRAFFIC_WORDS = ("ถนน", "จราจร", "รถ", "ติด", "ทาง", "เส้น", "ไป", "โล่ง", "แยก", "ซอย", "สะพาน", "ด่วน")


def rule_based_reply(traffic, question, water=None, extra=None):
    if not any(k in question for k in ACCIDENT_WORDS + FLOOD_WORDS + TRAFFIC_WORDS):
        return ("โหมดออฟไลน์ตอบได้เฉพาะสรุปจราจร น้ำท่วม/ฝน และอุบัติเหตุจากข้อมูลสด" + chr(10) +
                "ถ้าอยากถามเรื่องอื่น ใส่ GEMINI_API_KEY ในไฟล์ .env แล้วเปิด run_server.bat ใหม่ จะถามได้ทุกเรื่องเลย")
    if any(k in question for k in ACCIDENT_WORDS):
        return _accident_reply(extra) + "\n(โหมดออฟไลน์: ใส่ GEMINI_API_KEY ในไฟล์ .env เพื่อเปิดผู้ช่วย AI เต็มรูปแบบ)"
    if any(k in question for k in FLOOD_WORDS):
        return _flood_reply(water) + "\n(โหมดออฟไลน์: ใส่ GEMINI_API_KEY ในไฟล์ .env เพื่อเปิดผู้ช่วย AI เต็มรูปแบบ)"
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
    out.append("(โหมดออฟไลน์: ใส่ GEMINI_API_KEY ในไฟล์ .env เพื่อเปิดผู้ช่วย AI เต็มรูปแบบ)")
    return "\n".join(out)


def chat(traffic, messages, camera_stats=None, water=None, extra=None):
    """messages: list of {role: user|assistant, content: str}. Returns {reply, mode}.
    `water` is water_service.get_summary() or None when it is unavailable.
    `extra` holds optional sources: incidents, bma_events, bma_analytics, rsc, camera_risk."""
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    context = build_context(traffic, question, camera_stats, water, extra)

    history = [{"role": m["role"], "content": m["content"]} for m in messages[-12:] if m.get("content")]
    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": question or "สรุปสภาพจราจรตอนนี้"})
    history[-1] = {
        "role": "user",
        "content": f"ข้อมูลจราจรและน้ำท่วมสด:\n{context}\n\nคำถาม: {history[-1]['content']}",
    }

    gem = _gemini_client()
    if gem is not None:
        try:
            text = _gemini_chat(gem, history, question)
            return {"reply": text or rule_based_reply(traffic, question, water, extra), "mode": "gemini"}
        except Exception as e:
            print(f"[Chat] Gemini error: {e}")
            # fall through to Claude / offline

    client = _client()
    if client is None:
        return {"reply": rule_based_reply(traffic, question, water, extra), "mode": "offline"}
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=history,
        )
        if resp.stop_reason == "refusal":
            return {"reply": "ขอโทษนะ คำถามนี้ผู้ช่วยตอบให้ไม่ได้", "mode": "claude"}
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return {"reply": text or rule_based_reply(traffic, question, water, extra), "mode": "claude"}
    except anthropic.AuthenticationError:
        return {"reply": rule_based_reply(traffic, question, water, extra), "mode": "offline"}
    except anthropic.RateLimitError:
        return {"reply": "ผู้ช่วยตอบถี่เกินไป รอสักครู่แล้วลองใหม่นะ\n\n" + rule_based_reply(traffic, question, water, extra), "mode": "offline"}
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        print(f"[Chat] Claude error: {e}")
        return {"reply": rule_based_reply(traffic, question, water, extra), "mode": "offline"}
