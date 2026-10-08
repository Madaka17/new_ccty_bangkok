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

The parts: chat_context (the live data as prompt lines), chat_topics (what the question is about),
chat_route (route questions) and chat_offline (answers without the model). This module puts them together.
"""
import re
import time

from backend.agents.chat_context import (
    NATION_WORDS, _fmt_road, _trend_th, accident_stats_context, air_context, analytics_accidents, analytics_flood,
    analytics_traffic, bma_count_context, flow_th, guidance_context, incident_context, named_places,
    north_flow_context, patrol_context, predict_context, province_flood_context, province_traffic_context,
    province_weather_context, road_flood_context, route_context, tide_context, water_context, weather_context)
from backend.agents.chat_offline import rule_based_reply
from backend.agents.chat_route import plan_route
from backend.agents.chat_topics import ALL_TOPICS, OVERVIEW_WORDS, answer_style, question_topics, wants_route
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


# ---------------------------------------------------------------- route questions


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
