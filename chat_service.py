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

SYSTEM_PROMPT = """คุณคือ "ผู้ช่วยการจราจร" ของแอป BKK Traffic: Your Street Smart Guide
บทบาท: วิเคราะห์ "การระบายรถ" ของถนนในกรุงเทพฯ และปริมณฑลจากข้อมูลเส้นจราจรสด (Longdo Traffic)
และจำนวนรถจากกล้อง AI (YOLO) ที่แนบมาให้ในแต่ละคำถาม

แนวทางตอบ
- ใช้ตัวเลขจากข้อมูลที่ให้เท่านั้น ห้ามเดา ถ้าไม่มีข้อมูลถนนที่ถาม ให้บอกตรง ๆ และเสนอถนนใกล้เคียงที่มีข้อมูล
- ตอบเป็นภาษาไทยที่อบอุ่น เป็นกันเอง เหมือนเพื่อนบ้านที่รู้เรื่องถนนดี กระชับ ไม่เกิน 6-8 บรรทัด
- อธิบายการระบายรถด้วยค่า flow (0-100: 100 = โล่งทั้งสาย) และสัดส่วนเขียว/เหลือง/แดง
- ถ้าผู้ใช้ถามเส้นทาง A ไป B ให้เทียบถนนที่เกี่ยวข้องและแนะนำเส้นที่ระบายดีกว่า
- ปิดท้ายด้วยคำแนะนำสั้น ๆ 1 ข้อ (เช่น เลี่ยงช่วงไหน หรือไปได้เลย)
- ไม่ต้องใส่หัวข้อ Markdown ใหญ่ ใช้ bullet สั้น ๆ ได้"""


def _fmt_road(r):
    return (f"- {r['name']}: flow {r['flow']}/100 ({r['level']}), เขียว {r['green_pct']}% "
            f"เหลือง {r['yellow_pct']}% แดง {r['red_pct']}%, ระยะที่มีข้อมูล {r['length_km']} กม., ติดขัด {r['red_km']} กม.")


def build_context(traffic, question, camera_stats=None):
    s = traffic.get_summary(top=8)
    if not s.get("ready"):
        return "ยังไม่มีข้อมูลจราจร (ระบบกำลังโหลด)"
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
            max_output_tokens=1200,
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


def rule_based_reply(traffic, question):
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


def chat(traffic, messages, camera_stats=None):
    """messages: list of {role: user|assistant, content: str}. Returns {reply, mode}."""
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    context = build_context(traffic, question, camera_stats)

    history = [{"role": m["role"], "content": m["content"]} for m in messages[-12:] if m.get("content")]
    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": question or "สรุปสภาพจราจรตอนนี้"})
    history[-1] = {
        "role": "user",
        "content": f"ข้อมูลจราจรสด:\n{context}\n\nคำถาม: {history[-1]['content']}",
    }

    gem = _gemini_client()
    if gem is not None:
        try:
            text = _gemini_chat(gem, history, question)
            return {"reply": text or rule_based_reply(traffic, question), "mode": "gemini"}
        except Exception as e:
            print(f"[Chat] Gemini error: {e}")
            # fall through to Claude / offline

    client = _client()
    if client is None:
        return {"reply": rule_based_reply(traffic, question), "mode": "offline"}
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=history,
        )
        if resp.stop_reason == "refusal":
            return {"reply": "ขอโทษนะ คำถามนี้ผู้ช่วยตอบให้ไม่ได้", "mode": "claude"}
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return {"reply": text or rule_based_reply(traffic, question), "mode": "claude"}
    except anthropic.AuthenticationError:
        return {"reply": rule_based_reply(traffic, question), "mode": "offline"}
    except anthropic.RateLimitError:
        return {"reply": "ผู้ช่วยตอบถี่เกินไป รอสักครู่แล้วลองใหม่นะ\n\n" + rule_based_reply(traffic, question), "mode": "offline"}
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        print(f"[Chat] Claude error: {e}")
        return {"reply": rule_based_reply(traffic, question), "mode": "offline"}
