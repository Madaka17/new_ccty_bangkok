import time

from flask import Blueprint, jsonify, request

from .. import db as dbmod
from .. import world_quakes
from .. import world_faults

bp = Blueprint("world", __name__, url_prefix="/api/world")

# Allowed values for ?days= on /earthquakes -- matches the frontend's
# "90 วัน / 7 วัน / วันนี้" selector exactly. 1 day is a real rolling 24
# hours, not a calendar-day cutoff, for consistency with the other two.
DAYS_OPTIONS = {90, 7, 1}
DEFAULT_DAYS = 90
# A fourth, non-numeric option: "สถานการณ์ปัจจุบัน (Realtime)" -- not a fixed
# day window at all, but literally "what's actively happening right now".
REALTIME_SENTINEL = "realtime"


@bp.get("/earthquakes")
def earthquakes():
    state = world_quakes.get_state()
    raw_days = request.args.get("days", str(DEFAULT_DAYS))
    is_realtime = raw_days == REALTIME_SENTINEL
    if is_realtime:
        days = REALTIME_SENTINEL
    else:
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = DEFAULT_DAYS
        if days not in DAYS_OPTIONS:
            days = DEFAULT_DAYS

    now_ms = time.time() * 1000
    recent_cutoff_ms = world_quakes.RECENT_QUAKE_MINUTES * 60 * 1000
    # Realtime uses the exact same window that already drives the blinking
    # "active" marker style (is_recent below), so this option and that visual
    # cue always agree on what counts as "happening now" -- not a separate,
    # possibly-inconsistent definition of "current".
    window_cutoff_ms = now_ms - (recent_cutoff_ms if is_realtime else days * 86400 * 1000)
    quakes = [
        {**q, "is_recent": q.get("time_ms") is not None and (now_ms - q["time_ms"]) <= recent_cutoff_ms}
        for q in state["quakes"]
        if q.get("time_ms") is not None and q["time_ms"] >= window_cutoff_ms
    ]
    days_label = (
        f"{world_quakes.RECENT_QUAKE_MINUTES} นาทีล่าสุด (Realtime)" if is_realtime
        else {90: "90 วัน", 7: "7 วัน", 1: "24 ชั่วโมงล่าสุด"}[days]
    )
    return jsonify({
        "connected": state["connected"],
        "checked_at": state["checked_at"],
        "error": state["error"],
        "history_error": state.get("history_error"),
        "count": len(quakes),
        "quakes": quakes,
        "recent_minutes": world_quakes.RECENT_QUAKE_MINUTES,
        "days": days,
        "days_options": sorted(DAYS_OPTIONS, reverse=True) + [REALTIME_SENTINEL],
        "source": (
            f"USGS Earthquake Hazards Program + EMSC Seismic Portal + GEOFON (GFZ Potsdam) — สามแหล่งอิสระหลักที่ใช้ตรวจสอบ "
            f"ความถูกต้องของ Edge AI — M4.5+ worldwide และ M2.0+ ในภูมิภาคเอเชียตะวันออกเฉียงใต้ ย้อนหลัง{days_label} "
            f"จากทั้งสามเครือข่าย · TMD (กรมอุตุนิยมวิทยา) — เหตุการณ์ในประเทศไทยและใกล้เคียงจากเครือข่ายตรวจวัดในประเทศโดยตรง "
            f"(ตรวจจับแผ่นดินไหวขนาดเล็กในไทยที่ต่ำกว่าเกณฑ์ที่แหล่งข้อมูลทั่วโลกจะบันทึกได้)"
        ),
        "source_url": "https://earthquake.usgs.gov/earthquakes/map/",
        "source_url_emsc": "https://www.seismicportal.eu/",
        "source_url_geofon": "https://geofon.gfz-potsdam.de/",
        "source_url_tmd": "https://earthquake.tmd.go.th/",
    })


@bp.get("/earthquakes/history-stats")
def earthquakes_history_stats():
    """Stats on world_quake_history -- the permanent SQLite archive of every
    real event this system has ever seen (see world_quakes._persist_history),
    as distinct from the in-memory live cache /earthquakes reads from. This
    is the groundwork for future Edge AI trend analysis/forecasting: proof
    that real historical data is actually accumulating in the database, not
    just being displayed and discarded every 5 minutes."""
    conn = dbmod.get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM world_quake_history").fetchone()["c"]
    span = conn.execute("SELECT MIN(time_ms) lo, MAX(time_ms) hi FROM world_quake_history").fetchone()
    by_source = conn.execute(
        "SELECT source, COUNT(*) c FROM world_quake_history GROUP BY source ORDER BY c DESC"
    ).fetchall()
    first_ingested = conn.execute(
        "SELECT MIN(first_seen_at) t FROM world_quake_history"
    ).fetchone()["t"]
    conn.close()
    return jsonify({
        "total_stored": total,
        "earliest_event_ms": span["lo"], "latest_event_ms": span["hi"],
        "by_source": [{"source": r["source"], "count": r["c"]} for r in by_source],
        "collecting_since": first_ingested,
        "note": "สะสมถาวรใน SQLite ตั้งแต่ระบบเริ่มทำงาน ไม่ถูกล้างทุก 5 นาทีเหมือนแคชสด — "
                "ใช้เป็นข้อมูลตั้งต้นสำหรับการวิเคราะห์แนวโน้ม/พยากรณ์ด้วย Edge AI ในอนาคต",
    })


@bp.get("/faults")
def faults():
    world_faults.ensure_built_async()
    state = world_faults.get_state()
    if not state["ready"]:
        return jsonify({"ready": False, "building": state["building"], "error": state["error"]}), 202
    cached = world_faults.get_cached()
    return jsonify({
        "ready": True,
        "count": cached["count"],
        "faults": cached["faults"],
        "source": cached["source"],
        "source_url": cached["url"],
    })
