import os
import shutil
import sqlite3
import time
from datetime import datetime

from flask import Blueprint, jsonify, request, current_app

from .. import db as dbmod
from .. import auth
from .. import telegram_notify
from ..ws import broadcast

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

PROCESS_STARTED_AT = time.time()

UPTIME_BASELINE = {
    "API Gateway": 99.98, "Ingestion Service (MQTT)": 99.91, "Edge AI Model Service": 99.87,
    "Alert Dispatch Engine": 99.52, "Calibration Service": 99.99, "Database / Storage Cluster": 99.95,
}


def _fmt_uptime_duration():
    secs = int(time.time() - PROCESS_STARTED_AT)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ชม. {m} นาที"
    if m:
        return f"{m} นาที {s} วินาที"
    return f"{s} วินาที"


@bp.get("/services")
@auth.require_auth
def services():
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT * FROM services").fetchall()
    conn.close()
    out = []
    for r in rows:
        status = r["forced_status"] or "good"
        out.append({
            "name": r["name"], "status": status,
            "uptime_pct": UPTIME_BASELINE.get(r["name"], 99.9),
            "process_uptime": _fmt_uptime_duration(),
            "checked_at": datetime.now().strftime("%H:%M:%S"),
            "note": r["note"],
        })
    return jsonify(out)


@bp.get("/roles")
@auth.require_auth
def roles():
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT * FROM roles").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@bp.get("/audit-log")
@auth.require_auth
def audit_log():
    limit = min(int(request.args.get("limit", 25)), 200)
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@bp.get("/backup")
@auth.require_auth
def backup_status():
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM backups ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return jsonify(dict(row) if row else None)


@bp.post("/backup/run")
@auth.require_role("admin")
def run_backup():
    """Performs a *real* SQLite backup to disk via the sqlite3 backup API."""
    backups_dir = os.path.join(dbmod.BASE_DIR, "backups")
    os.makedirs(backups_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_path = os.path.join(backups_dir, f"enviro-{stamp}.db")

    src = sqlite3.connect(dbmod.DB_PATH)
    dst = sqlite3.connect(dest_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    size_bytes = os.path.getsize(dest_path)

    conn = dbmod.get_conn()
    ts = dbmod.now_iso()
    conn.execute("INSERT INTO backups(ts, size_bytes, path) VALUES (?,?,?)", (ts, size_bytes, dest_path))
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?, ?, ?)",
        (ts, request.user["username"], f"สั่งสำรองข้อมูลด้วยตนเอง ({size_bytes:,} bytes)"),
    )
    conn.commit()
    conn.close()
    return jsonify({"ts": ts, "size_bytes": size_bytes, "path": dest_path})


@bp.post("/test-alert")
@auth.require_role("admin", "operator")
def test_alert():
    body = request.get_json(silent=True) or {}
    level = int(body.get("level", 1))
    region = body.get("region", "ทั่วประเทศ (สาธิต)")
    ts = dbmod.now_iso()

    conn = dbmod.get_conn()
    level_row = conn.execute("SELECT name FROM levels WHERE lv=?", (level,)).fetchone()
    level_name = level_row["name"] if level_row else "?"
    action = f"ทดสอบส่งการแจ้งเตือนระดับ {level} ({level_name}) ในพื้นที่ {region} (แซนด์บ็อกซ์ — ไม่ส่งจริง)"
    conn.execute("INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)", (ts, request.user["username"], action))
    conn.commit()
    conn.close()

    broadcast({"type": "test-alert", "level": level, "region": region, "ts": ts, "by": request.user["username"]})
    return jsonify({"ok": True, "message": action})


MAGNITUDE_OPTIONS = [3.8, 4.5, 4.8, 5.5, 6.0, 6.5, 7.0, 7.7]


@bp.get("/epicenter-options")
@auth.require_auth
def epicenter_options():
    conn = dbmod.get_conn()
    faults = conn.execute("SELECT id, name, region, lat1, lng1, lat2, lng2 FROM fault_lines").fetchall()
    conn.close()
    options = [{
        "key": str(f["id"]), "label": f"{f['name']} ({f['region']})",
        "lat": round((f["lat1"] + f["lat2"]) / 2, 4), "lng": round((f["lng1"] + f["lng2"]) / 2, 4),
        "fault": f["name"], "region": f["region"],
    } for f in faults]
    return jsonify({"epicenters": options, "magnitudes": MAGNITUDE_OPTIONS})


# A small offset from the reference "you are here" station, used ONLY by the
# "trigger a specific alert level" demo control. Thailand's real named faults
# (fault_lines table, used everywhere else) all sit 150-700km+ from Bangkok --
# honestly, even a M9 there predicts only a low MMI at the reference station
# (large distant earthquakes genuinely are only mildly felt far away). So
# there is no real fault close enough to demonstrate levels 3-6 at the
# reference location without an absurd magnitude. This point exists purely so
# the demo can pick a target level and solve a realistic (magnitude, this
# short distance) pair for it -- it is explicitly labeled as a demo point in
# the resulting event, never presented as a real named fault.
DEMO_EPICENTER_NEAR_REFERENCE = {"lat": 13.95, "lng": 100.60, "place": "จุดสาธิตใกล้ตำแหน่งอ้างอิง (ไม่ใช่รอยเลื่อนจริง)",
                                   "fault": "จุดทดสอบสาธิต", "region": "ปริมณฑล", "depth": 10.0}

# The topbar "จำลองแผ่นดินไหว" quick-demo button always reproduces this one
# real historical event, per the user's explicit request: the 28 March 2025
# Myanmar earthquake (Sagaing Fault, near Sagaing/Mandalay). Epicenter and
# depth are the real, publicly reported values (~22.0N 95.9E, ~10km deep).
# Magnitude is set to 8.2 per the user's explicit instruction; the widely
# reported figure from USGS/international agencies was Mw 7.7 -- noted here,
# and in the frontend tooltip, for honesty, but 8.2 is what's simulated since
# that's what was asked for. Defined once, server-side, so the frontend can't
# drift from these exact numbers on repeated clicks.
HISTORICAL_MYANMAR_2025 = {
    "lat": 22.00, "lng": 95.92, "depth": 10.0, "magnitude": 8.2,
    "place": "อ.สะกาย เขตสะกาย ประเทศเมียนมา (ใกล้รอยเลื่อนสะกาย) — จำลองเหตุการณ์จริง 28 มี.ค. 2568",
    "fault": "รอยเลื่อนสะกาย (Sagaing Fault)", "region": "เมียนมา",
}

# Second topbar scenario: a fixed point on the Sunda Megathrust in the
# Andaman Sea (the same subduction zone that ruptured in the real Dec 2004
# Sumatra-Andaman M9.1 earthquake), given by the user as a specific lat/lng.
# Depth 20km is a realistic megathrust nucleation depth.
#
# At this point's real ~1,000km distance from the reference location, even
# magnitude 9.5 -- the largest earthquake ever instrumentally recorded (1960
# Valdivia, Chile) -- only predicts ~MMI VIII there (Level 5), matching real
# precedent: the actual 2004 M9.1 quake near this exact spot caused only mild
# shaking in Bangkok (it was a tsunami event for Thailand, not a
# shaking-damage event). The user explicitly asked for this scenario to reach
# Level 6 regardless, specifically to exercise the Level 6
# continuous-siren-until-acknowledged UI path -- so ANDAMAN_L6_MAGNITUDE_CAP
# is set past the real-world ceiling on purpose (~M10.15 is what the physics
# needs here, beyond anything the real Earth can produce) and the resulting
# event's place name says so plainly, rather than silently passing off a
# functionally-impossible magnitude as a real scenario.
ANDAMAN_L6_MAGNITUDE_CAP = 11.0
HISTORICAL_ANDAMAN_MEGATHRUST = {
    "lat": 6.255467, "lng": 95.412450, "depth": 20.0,
    "place": "ทะเลอันดามัน ใกล้แนวมุดตัวสุมาตรา-อันดามัน — ขนาดถูกปรับให้ถึงระดับ 6 ที่ตำแหน่งอ้างอิง "
             "(เกินขนาดแผ่นดินไหวจริงที่เคยบันทึกได้ ใช้เพื่อทดสอบระบบเท่านั้น)",
    "fault": "แนวมุดตัวสุมาตรา-อันดามัน (Sunda Megathrust)", "region": "มหาสมุทรอินเดีย",
}

# Third topbar scenario: the real 5 May 2014 Mae Lao earthquake, Chiang Rai --
# the strongest instrumentally-recorded earthquake with an epicenter inside
# Thailand. Epicenter, depth and magnitude are the real, publicly reported
# figures from the Department of Mineral Resources (DMR) and the Thai
# Meteorological Department's seismological bureau:
# https://www.dmr.go.th/รายงานสถานการณ์แผ่นดินไหว-ขนาด-6-3-ริกเตอร์-เมื่อวันจันทร์ที่-5-พฤษภาคม-2557/
# (Tambon Dong Mada, Amphoe Mae Lao, Chiang Rai; 19.748N 99.692E; 7km deep;
# M6.3; associated with the Phayao Fault Zone). Magnitude is the real reported
# value, not solved for a target level -- same treatment as HISTORICAL_MYANMAR_2025.
HISTORICAL_MAE_LAO_2014 = {
    "lat": 19.748, "lng": 99.692, "depth": 7.0, "magnitude": 6.3,
    "place": "ต.ดงมะดะ อ.แม่ลาว จ.เชียงราย ประเทศไทย — จำลองเหตุการณ์จริง 5 พ.ค. 2557 เวลา 18:08 น.",
    "fault": "กลุ่มรอยเลื่อนพะเยา (แนวแม่ลาว)", "region": "เชียงราย",
}


@bp.post("/simulate-quake")
@auth.require_role("admin", "operator")
def simulate_quake():
    from ..simulator import solve_magnitude_for_mmi

    body = request.get_json(silent=True) or {}
    speed_multiplier = min(100.0, max(1.0, float(body.get("speed_multiplier", 1.0))))
    target_level = body.get("target_level")

    if body.get("historical_event") == "myanmar_2025":
        d = HISTORICAL_MYANMAR_2025
        return _simulate_from_params(
            lat=d["lat"], lng=d["lng"], place=d["place"], fault=d["fault"], region=d["region"],
            depth=d["depth"], speed_multiplier=speed_multiplier,
            magnitude_solver=lambda dist_km: d["magnitude"],
            note="จำลองซ้ำเหตุการณ์จริง 28 มี.ค. 2568",
        )

    if body.get("historical_event") == "andaman_l6":
        from ..simulator import solve_magnitude_for_mmi as _solve
        d = HISTORICAL_ANDAMAN_MEGATHRUST
        conn0 = dbmod.get_conn()
        level6 = conn0.execute("SELECT mmi_min FROM levels WHERE lv=6").fetchone()
        conn0.close()
        # Solves for target level 6's MMI floor, capped at
        # ANDAMAN_L6_MAGNITUDE_CAP (11.0) rather than the normal real-world
        # 9.5 ceiling -- per explicit user request, so this scenario reliably
        # reaches Level 6 (and its continuous-siren-until-acknowledged UI) at
        # the reference location. See the module-level comment above: this
        # trades real-world plausibility for a guaranteed functional test,
        # and the event's place name says so.
        return _simulate_from_params(
            lat=d["lat"], lng=d["lng"], place=d["place"], fault=d["fault"], region=d["region"],
            depth=d["depth"], speed_multiplier=speed_multiplier,
            magnitude_solver=lambda dist_km: _solve(level6["mmi_min"] + 0.3, dist_km, d["depth"], cap=ANDAMAN_L6_MAGNITUDE_CAP),
            note="ทดสอบระดับ 6 ที่ตำแหน่งอันดามัน (ขนาดปรับให้ถึงระดับ 6 ตามที่ร้องขอ)",
        )

    if body.get("historical_event") == "mae_lao_2014":
        d = HISTORICAL_MAE_LAO_2014
        return _simulate_from_params(
            lat=d["lat"], lng=d["lng"], place=d["place"], fault=d["fault"], region=d["region"],
            depth=d["depth"], speed_multiplier=speed_multiplier,
            magnitude_solver=lambda dist_km: d["magnitude"],
            note="จำลองซ้ำเหตุการณ์จริง 5 พ.ค. 2557 (กรมทรัพยากรธรณี)",
        )

    conn = dbmod.get_conn()
    if target_level is not None:
        # Solve for the magnitude that realistically produces this level's
        # MMI floor at the reference location, from a fixed nearby demo point
        # -- see DEMO_EPICENTER_NEAR_REFERENCE.
        target_level = max(1, min(6, int(target_level)))
        level_row = conn.execute("SELECT lv, mmi_min FROM levels WHERE lv=?", (target_level,)).fetchone()
        if level_row is None:
            conn.close()
            return jsonify({"error": "unknown_level"}), 400
        d = DEMO_EPICENTER_NEAR_REFERENCE
        sim = current_app.config["SIMULATOR"]
        conn.close()
        return _simulate_from_params(
            lat=d["lat"], lng=d["lng"], place=d["place"], fault=d["fault"], region=d["region"],
            depth=d["depth"], speed_multiplier=speed_multiplier,
            magnitude_solver=lambda dist_km: solve_magnitude_for_mmi(level_row["mmi_min"] + 0.3, dist_km, d["depth"]),
            note=f"เพื่อสาธิตระดับ {target_level}",
        )

    custom = body.get("custom_epicenter")
    if custom:
        # A specific real-world epicenter that isn't one of the seeded Thai
        # faults (e.g. reproducing a real historical event elsewhere in the
        # region) -- lat/lng/depth/magnitude taken as given, not looked up.
        conn.close()
        magnitude = min(9.5, max(3.0, float(custom.get("magnitude", 4.8))))
        return _simulate_from_params(
            lat=float(custom["lat"]), lng=float(custom["lng"]),
            place=custom.get("place", "ตำแหน่งที่กำหนดเอง"), fault=custom.get("fault", "-"),
            region=custom.get("region", "-"), depth=float(custom.get("depth", 10.0)),
            speed_multiplier=speed_multiplier, magnitude_solver=lambda dist_km: magnitude,
            note=custom.get("note", ""),
        )

    epicenter_key = str(body.get("epicenter_key", ""))
    magnitude = float(body.get("magnitude", 4.8))
    magnitude = min(9.0, max(3.0, magnitude))

    fault = conn.execute("SELECT id, name, region, lat1, lng1, lat2, lng2 FROM fault_lines WHERE id=?", (epicenter_key,)).fetchone()
    if fault is None:
        conn.close()
        return jsonify({"error": "unknown_epicenter"}), 400
    lat, lng = round((fault["lat1"] + fault["lat2"]) / 2, 4), round((fault["lng1"] + fault["lng2"]) / 2, 4)
    place = f"บริเวณ{fault['name']} จ.{fault['region']}"
    conn.close()
    return _simulate_from_params(
        lat=lat, lng=lng, place=place, fault=fault["name"], region=fault["region"],
        depth=8.0, speed_multiplier=speed_multiplier, magnitude_solver=lambda dist_km: magnitude, note="",
    )


@bp.post("/clear-event")
@auth.require_role("admin", "operator")
def clear_event():
    """Stops a currently-running/scheduled simulated quake -- the "stop" half
    of the topbar "จำลองแผ่นดินไหว" toggle button (simulate-quake is the
    "start" half)."""
    sim = current_app.config["SIMULATOR"]
    was_active = sim.clear_active_event()
    if was_active:
        conn = dbmod.get_conn()
        conn.execute(
            "INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)",
            (dbmod.now_iso(), request.user["username"], "หยุดการจำลองแผ่นดินไหว"),
        )
        conn.commit()
        conn.close()
    return jsonify({"ok": True, "was_active": was_active})


def _simulate_from_params(lat, lng, place, fault, region, depth, speed_multiplier, magnitude_solver, note):
    from ..geo import haversine_km

    sim = current_app.config["SIMULATOR"]
    ref = sim.stations["BKK-201"]
    ref_dist_km = haversine_km(ref["lat"], ref["lng"], lat, lng)
    magnitude = round(magnitude_solver(ref_dist_km), 2)

    ts = dbmod.now_iso()
    speed_note = f" (เร่งเวลา {speed_multiplier:g}x)" if speed_multiplier != 1.0 else ""
    action = f"สั่งจำลองเหตุการณ์แผ่นดินไหวขนาด M{magnitude} ที่ {fault} ({region}){speed_note}{(' ' + note) if note else ''}"
    conn = dbmod.get_conn()
    conn.execute("INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)", (ts, request.user["username"], action))
    conn.commit()
    conn.close()

    eta_s = sim.trigger_manual_quake(lat, lng, magnitude, place, fault, region, depth=depth, speed_multiplier=speed_multiplier)
    return jsonify({"ok": True, "message": action, "eta_s": eta_s, "lat": lat, "lng": lng,
                    "magnitude": magnitude, "speed_multiplier": speed_multiplier})


@bp.get("/telegram")
@auth.require_role("admin")
def telegram_get():
    cfg = telegram_notify.get_config()
    return jsonify({
        "bot_token_masked": telegram_notify.mask_token(cfg["bot_token"]),
        "has_token": bool(cfg["bot_token"]),
        "chat_id": cfg["chat_id"],
        "enabled": cfg["enabled"],
    })


@bp.post("/telegram")
@auth.require_role("admin")
def telegram_set():
    body = request.get_json(silent=True) or {}
    cfg = telegram_notify.get_config()
    submitted_token = (body.get("bot_token") or "").strip()
    # An unchanged masked value (or a blank field when a token is already saved)
    # means "keep the existing token" -- the UI never round-trips the real secret.
    bot_token = cfg["bot_token"] if (not submitted_token or submitted_token == telegram_notify.mask_token(cfg["bot_token"])) else submitted_token
    chat_id = (body.get("chat_id") or "").strip()
    enabled = bool(body.get("enabled"))
    telegram_notify.set_config(bot_token, chat_id, enabled)

    ts = dbmod.now_iso()
    conn = dbmod.get_conn()
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)",
        (ts, request.user["username"], f"อัปเดตการตั้งค่า Telegram ({'เปิดใช้งาน' if enabled else 'ปิดใช้งาน'})"),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.post("/telegram/test")
@auth.require_role("admin")
def telegram_test():
    cfg = telegram_notify.get_config()
    ok, info = telegram_notify.send_message(
        cfg["bot_token"], cfg["chat_id"],
        "🔔 <b>ทดสอบการเชื่อมต่อ ENVIRO Seismic Command</b>\nหากคุณเห็นข้อความนี้ แสดงว่าเชื่อมต่อ Telegram Bot สำเร็จแล้ว",
    )
    ts = dbmod.now_iso()
    conn = dbmod.get_conn()
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)",
        (ts, request.user["username"], f"ทดสอบส่งข้อความ Telegram: {'สำเร็จ' if ok else 'ล้มเหลว'} ({info})"),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": ok, "message": info})
