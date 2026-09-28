"""Real Telegram Bot API integration for alert notifications.

Uses the standard `sendMessage` endpoint (https://core.telegram.org/bots/api)
-- genuine HTTP calls, not a mock. It needs the *user's own* bot token and
chat id (see the admin UI for the short BotFather setup instructions); with
no token configured, notify_alert() is a silent no-op.

Network calls run on a background thread so a slow/unreachable Telegram API
never blocks the detection loop that calls notify_alert().
"""
import json
import threading
import urllib.error
import urllib.request

from . import db as dbmod

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 8
LEVEL_EMOJI = {1: "🟢", 2: "🟦", 3: "🟡", 4: "🟠", 5: "🔴", 6: "🟣"}


def get_config():
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM telegram_config WHERE id=1").fetchone()
    conn.close()
    if not row:
        return {"bot_token": "", "chat_id": "", "enabled": False}
    return {"bot_token": row["bot_token"] or "", "chat_id": row["chat_id"] or "", "enabled": bool(row["enabled"])}


def mask_token(token):
    if not token:
        return ""
    if len(token) <= 6:
        return "•" * len(token)
    return "•" * (len(token) - 4) + token[-4:]


def set_config(bot_token, chat_id, enabled):
    conn = dbmod.get_conn()
    conn.execute(
        "UPDATE telegram_config SET bot_token=?, chat_id=?, enabled=? WHERE id=1",
        (bot_token, chat_id, 1 if enabled else 0),
    )
    conn.commit()
    conn.close()


def send_message(bot_token, chat_id, text):
    """Real synchronous call to the Telegram Bot API. Returns (ok, info)."""
    if not bot_token or not chat_id:
        return False, "ยังไม่ได้ตั้งค่า Bot Token หรือ Chat ID"
    url = API_URL.format(token=bot_token)
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                return True, "ส่งสำเร็จ"
            return False, f"Telegram API ปฏิเสธคำขอ: {body.get('description', 'ไม่ทราบสาเหตุ')}"
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            desc = body.get("description", str(e))
        except Exception:
            desc = str(e)
        return False, f"Telegram API ผิดพลาด ({e.code}): {desc}"
    except Exception as e:
        return False, f"เชื่อมต่อ Telegram ไม่สำเร็จ: {e}"


def _format_alert_text(event, is_new):
    emoji = LEVEL_EMOJI.get(event["level"], "⚪")
    header = "แจ้งเตือนแผ่นดินไหวใหม่" if is_new else "ยกระดับการแจ้งเตือน"
    lines = [
        f"{emoji} <b>{header}: ระดับ {event['level']} — {event['level_name']}</b>",
        f"ตำแหน่ง: {event['place']}",
        f"ขนาดเหตุการณ์ (Mw): M{event.get('magnitude_estimate', event['magnitude'])} ลึก {event['depth']} กม.",
        f"ความรุนแรงที่คาด ณ ตำแหน่งอ้างอิง: MMI {event.get('predicted_mmi_roman', '—')}",
        f"PGA ที่สถานีใกล้ที่สุด: {event['pga_gal']} Gal",
        f"ความเชื่อมั่น AI: {event.get('confidence_label', '—')} · สถานียืนยันร่วม {event['stations_triggered']} สถานี",
    ]
    if event.get("tsunami_risk"):
        lines.append("⚠️ <b>เฝ้าระวังสึนามิ (เบื้องต้น)</b> — พื้นที่ชายฝั่งควรอพยพขึ้นที่สูงทันทีหลังแรงสั่นหยุด")
    lines += [
        "",
        event["message"],
        "",
        f"รหัสเหตุการณ์: {event['id']}",
        "— ระบบ ENVIRO Seismic Command (ข้อมูลจำลองเพื่อการสาธิต)",
    ]
    return "\n".join(lines)


def notify_alert(event, is_new):
    cfg = get_config()
    if not (cfg["enabled"] and cfg["bot_token"] and cfg["chat_id"]):
        return
    text = _format_alert_text(event, is_new)

    def _send():
        ok, info = send_message(cfg["bot_token"], cfg["chat_id"], text)
        ts = dbmod.now_iso()
        conn = dbmod.get_conn()
        conn.execute(
            "INSERT INTO audit_log(ts, username, action) VALUES (?, 'system', ?)",
            (ts, f"ส่งแจ้งเตือนผ่าน Telegram สำหรับ {event['id']}: {'สำเร็จ' if ok else 'ล้มเหลว'} ({info})"),
        )
        conn.commit()
        conn.close()

    threading.Thread(target=_send, daemon=True).start()
