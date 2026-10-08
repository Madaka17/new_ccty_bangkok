"""
The assistant's live data as prompt lines, one builder per data set (traffic, water, weather, incidents, air,
patrols, the per-province figures, the planned route). Each returns a list of short Thai lines, most important
first, so chat_service can cut them to the model's context window. Moved out of chat_service.py (Oct 2026).
"""
import time

from backend.core import thai_regions


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
    """What the site's analysts expect next: the flood agent, Bangkok's districts, the northern water and the
    national 7-day outlook."""
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
    bd = ex.get("bkk_districts") or {}
    if bd.get("districts"):
        ai = bd.get("ai") or {}
        if ai.get("overview"):
            lines.append(f"AI สรุปน้ำท่วมรายเขต กทม. ({_hhmm(ai.get('generated_at'))}): {ai['overview'][:400]}")
        risky = [d for d in bd["districts"] if d.get("level") != "normal"][:8]
        if risky:
            lines.append("  เขตที่ต้องระวัง: " + "; ".join(
                f"{d['district']} ({d['label']} {d['score']}) {((ai.get('districts') or {}).get(d['district']) or {}).get('summary') or ', '.join(d['why'][:2])}"[:200]
                for d in risky))
    nr = ex.get("north_route") or {}
    if nr.get("provinces"):
        ai = nr.get("ai") or {}
        if ai.get("headline"):
            lines.append(f"AI วิเคราะห์น้ำเหนือ ({_hhmm(ai.get('generated_at'))}): {ai['headline']} {(ai.get('next7') or '')[:300]}")
        watch = [p for p in nr["provinces"] if p.get("level") != "normal"]
        if watch:
            lines.append("  จังหวัดตามทางน้ำเหนือที่ต้องระวังใน 7 วัน: " + ", ".join(
                f"{p['province']} ({p['label']}, หนักสุด{' +' + str(p['peak_day']) + ' วัน' if p['peak_day'] else 'วันนี้'})" for p in watch))
    nf = ex.get("national_forecast") or {}
    s = (nf.get("ai") or {}).get("summary") or {}
    if s.get("headline"):
        lines.append(f"AI สรุปน้ำท่วมทั่วประเทศ 7 วัน: {s['headline']} {(s.get('summary') or '')[:300]}")
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
