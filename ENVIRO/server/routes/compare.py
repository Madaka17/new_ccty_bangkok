import hashlib
import math
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

from .. import db as dbmod
from .. import sources_usgs
from .. import sources_emsc
from .. import sources_geofon
from .. import world_quakes
from .. import auth

bp = Blueprint("compare", __name__, url_prefix="/api/compare")

HISTORY_SOURCES = {"USGS", "EMSC", "GEOFON", "TMD"}
HISTORY_LIMIT_MAX = 500
ACCURACY_SERIES_LIMIT_MAX = 200
ACCURACY_SERIES_DEFAULT = 30

FORECAST_REGIONS = [
    {"key": "north", "region": "ภาคเหนือ (กลุ่มรอยเลื่อนแม่จัน–พะเยา)", "color": "var(--series-enviro)", "risk_regions": ["เชียงราย", "พะเยา", "เชียงใหม่"]},
    {"key": "west", "region": "ภาคตะวันตก (สามองค์เจดีย์–ศรีสวัสดิ์)", "color": "var(--series-usgs)", "risk_regions": ["กาญจนบุรี", "ตาก"]},
    {"key": "south", "region": "ภาคใต้ (ระนอง–คลองมะรุ่ย)", "color": "var(--series-gistda)", "risk_regions": ["ระนอง", "สุราษฎร์ธานี"]},
]


@bp.get("")
def compare_sources():
    conn = dbmod.get_conn()
    event = conn.execute("SELECT * FROM events WHERE is_test=0 ORDER BY ts DESC LIMIT 1").fetchone()
    static_rows = conn.execute("SELECT * FROM sources_static").fetchall()
    conn.close()

    sources = []
    if event:
        sources.append({
            "name": "ENVIRO", "color_var": "var(--series-enviro)", "simulated": True,
            "magnitude": event["magnitude"], "depth": event["depth"], "latency_sec": 9,
            "confidence": 94, "loc_err_km": 3, "note": "เครือข่าย Edge AI ภายใน — เรียลไทม์",
        })
    for r in static_rows:
        mag = round(event["magnitude"] + r["mag_offset"], 1) if event else None
        sources.append({
            "name": r["name"], "color_var": r["color_var"], "simulated": True,
            "magnitude": mag, "depth": r["depth"], "latency_sec": r["latency_sec"],
            "confidence": r["confidence"], "loc_err_km": r["loc_err_km"], "note": r["note"],
        })

    usgs_state = sources_usgs.get_state()
    usgs_row = {
        "name": "USGS", "color_var": "var(--series-usgs)", "simulated": False,
        "connected": usgs_state["connected"], "checked_at": usgs_state["checked_at"],
        "error": usgs_state["error"],
    }
    if usgs_state["connected"] and usgs_state["latest"]:
        latest = usgs_state["latest"]
        usgs_row.update({
            "magnitude": latest["magnitude"], "depth": latest["depth_km"],
            "note": f"เหตุการณ์จริงล่าสุดจากฟีดสาธารณะ USGS: {latest['place']} "
                    f"(คนละเหตุการณ์กับที่จำลองไว้ด้านบน ใช้ยืนยันว่าเชื่อมต่อ API จริงได้)",
            "url": latest["url"],
        })
    else:
        usgs_row.update({
            "magnitude": None, "depth": None,
            "note": "เชื่อมต่อฟีดสาธารณะของ USGS ไม่สำเร็จในขณะนี้ (เครือข่ายของสภาพแวดล้อมนี้อาจปิดกั้นการเชื่อมต่อขาออก)",
        })
    sources.append(usgs_row)

    emsc_state = sources_emsc.get_state()
    emsc_row = {
        "name": "EMSC", "color_var": "var(--series-emsc)", "simulated": False,
        "connected": emsc_state["connected"], "checked_at": emsc_state["checked_at"],
        "error": emsc_state["error"],
    }
    if emsc_state["connected"] and emsc_state["latest"]:
        latest = emsc_state["latest"]
        emsc_row.update({
            "magnitude": latest["magnitude"], "depth": latest["depth_km"],
            "note": f"เหตุการณ์จริงล่าสุดจากฟีดสาธารณะ EMSC: {latest['place']} (เครือข่ายยุโรป-เมดิเตอร์เรเนียน "
                    f"รวมข้อมูลจาก ~65 หน่วยงานทั่วโลก · คนละเหตุการณ์กับที่จำลองไว้ด้านบน)",
        })
    else:
        emsc_row.update({
            "magnitude": None, "depth": None,
            "note": "เชื่อมต่อฟีดสาธารณะของ EMSC ไม่สำเร็จในขณะนี้",
        })
    sources.append(emsc_row)

    geofon_state = sources_geofon.get_state()
    geofon_row = {
        "name": "GEOFON", "color_var": "var(--series-geofon)", "simulated": False,
        "connected": geofon_state["connected"], "checked_at": geofon_state["checked_at"],
        "error": geofon_state["error"],
    }
    if geofon_state["connected"] and geofon_state["latest"]:
        latest = geofon_state["latest"]
        geofon_row.update({
            "magnitude": latest["magnitude"], "depth": latest["depth_km"],
            "note": f"เหตุการณ์จริงล่าสุดจากฟีดสาธารณะ GEOFON (GFZ Potsdam): {latest['place']} "
                    f"(เครือข่ายทั่วโลกอิสระที่สาม · คนละเหตุการณ์กับที่จำลองไว้ด้านบน)",
            "url": latest["url"],
        })
    else:
        geofon_row.update({
            "magnitude": None, "depth": None,
            "note": "เชื่อมต่อฟีดสาธารณะของ GEOFON ไม่สำเร็จในขณะนี้",
        })
    sources.append(geofon_row)

    return jsonify({"event_id": event["id"] if event else None, "sources": sources})


def _region_of(place):
    """Coarse "location" grouping key derived from a free-text `place` string
    (e.g. USGS's "80km ENE of Ndoi Island, Fiji" -> "Fiji", TMD's
    "อ.แม่ลาว จ.เชียงราย" has no comma -> the whole string). Real place text
    varies too much per source to have a clean location column, so this is
    the practical stand-in used for the สถานที่ dropdown/filter below -- the
    text after the last comma when there is one, else the whole string."""
    if not place:
        return None
    place = place.strip()
    if not place:
        return None
    return place.rsplit(",", 1)[-1].strip() if "," in place else place


@bp.get("/history/filters")
def quake_history_filters():
    """Distinct ปี/เดือน/สถานที่ values actually present in
    world_quake_history, so the history browser's 3 dropdowns only ever
    offer options that have real data behind them."""
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT time_ms, place FROM world_quake_history WHERE time_ms IS NOT NULL").fetchall()
    conn.close()

    months_by_year = {}
    for r in rows:
        dt = datetime.utcfromtimestamp(r["time_ms"] / 1000)
        months_by_year.setdefault(dt.year, set()).add(dt.month)
    years = sorted(months_by_year.keys(), reverse=True)
    months_by_year = {str(y): sorted(m) for y, m in months_by_year.items()}

    region_counts = {}
    for r in rows:
        region = _region_of(r["place"])
        if region:
            region_counts[region] = region_counts.get(region, 0) + 1
    # Most-frequent first (the locations actually worth browsing), capped so
    # the dropdown stays usable even once the archive has accumulated a lot
    # of distinct free-text places.
    regions = sorted(region_counts.keys(), key=lambda r: (-region_counts[r], r))[:300]

    return jsonify({"years": years, "months_by_year": months_by_year, "regions": regions})


@bp.post("/history/backfill")
@auth.require_auth
def quake_history_backfill():
    """On-demand real backfill for the ปี/เดือน/สถานที่ history browser --
    per explicit request, fetches real data from USGS/EMSC/GEOFON's live
    APIs for a given calendar year (optionally narrowed to one month),
    covering up to world_quakes.BACKFILL_MAX_YEARS_BACK years back, and
    persists whatever comes back into world_quake_history. TMD has no
    historical range API, so it's never part of a backfill (only ever
    populated by the live poller). Real outbound network calls -- can take
    a few seconds; the frontend shows this as an explicit loading state."""
    body = request.get_json(silent=True) or {}
    try:
        year = int(body.get("year"))
    except (TypeError, ValueError):
        return jsonify({"error": "year_required"}), 400
    month = body.get("month")
    if month is not None:
        try:
            month = int(month)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_month"}), 400

    try:
        result = world_quakes.run_historical_backfill(year, month)
    except ValueError as exc:
        return jsonify({"error": "invalid_range", "message": str(exc)}), 400

    conn = dbmod.get_conn()
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)",
        (dbmod.now_iso(), request.user["username"],
         f"ดึงข้อมูลย้อนหลังจาก API จริง (USGS/EMSC/GEOFON) สำหรับปี {year}"
         + (f" เดือน {month}" if month else "") + f" — พบ {result['total_fetched']} เหตุการณ์"),
    )
    conn.commit()
    conn.close()

    return jsonify(result)


@bp.get("/history")
def quake_history():
    """Real earthquake history accumulated in `world_quake_history` since this
    system started running (see server/world_quakes.py:_persist_history) --
    the raw material a future Edge AI trend/forecast feature would train or
    reason against. Browsable/filterable (source, year, month, region) with
    real pagination -- per explicit request, a proper database view for
    analysis, not just "latest N". This endpoint itself does no analysis:
    it's a browsable record, not a prediction."""
    source = request.args.get("source")
    if source and source not in HISTORY_SOURCES:
        return jsonify({"error": "unknown_source"}), 400
    year = request.args.get("year")
    month = request.args.get("month")
    region = request.args.get("region") or None
    q = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(HISTORY_LIMIT_MAX, max(1, int(request.args.get("page_size", request.args.get("limit", 100)))))
    except (TypeError, ValueError):
        page_size = 100

    clauses, params = [], []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if year:
        try:
            clauses.append("strftime('%Y', time_ms/1000, 'unixepoch') = ?")
            params.append(f"{int(year):04d}")
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_year"}), 400
    if month:
        try:
            clauses.append("strftime('%m', time_ms/1000, 'unixepoch') = ?")
            params.append(f"{int(month):02d}")
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_month"}), 400
    if q:
        # Free-text search typed by the user, matched against the whole
        # place string -- broader than the ปี/สถานที่ dropdowns (which only
        # match a derived exact region), so a typed keyword can hit anything
        # in the place text (a city, a country, part of a description).
        clauses.append("place LIKE ?")
        params.append(f"%{q}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    conn = dbmod.get_conn()
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM world_quake_history {where} ORDER BY time_ms DESC", params,
    ).fetchall()]
    by_source = conn.execute("SELECT source, COUNT(*) c FROM world_quake_history GROUP BY source").fetchall()
    earliest = conn.execute("SELECT MIN(first_seen_at) t FROM world_quake_history").fetchone()["t"]
    conn.close()

    # region is a derived value (see _region_of), not a real column -- easier
    # and clear enough to filter in Python after the SQL-filterable columns
    # have already narrowed the row count down.
    if region:
        rows = [r for r in rows if _region_of(r.get("place")) == region]

    total = len(rows)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)
    page_rows = rows[(page - 1) * page_size: page * page_size]

    return jsonify({
        "total": total,
        "returned": len(page_rows),
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "by_source": {r["source"]: r["c"] for r in by_source},
        "tracking_since": earliest,
        "history_error": world_quakes.get_state().get("history_error"),
        "events": page_rows,
    })


def _simulated_enviro_estimate(event_id, true_magnitude):
    """A deterministic (not random-per-request) simulated magnitude estimate
    standing in for a real ENVIRO sensor network measurement of the same real
    event -- our own network only ever runs the simulated Thai demo scenarios
    (see routes/admin.py), so it has never actually measured any of these real
    USGS/EMSC/GEOFON/TMD events. Per explicit request, this endpoint fabricates
    a plausible reading so the accuracy chart below has something of ENVIRO's
    "own" to compare against real agencies' reported magnitudes -- seeded from
    the event's own id (stable hash, not `random`) so the same event always
    shows the same simulated value across refreshes, rather than jittering.
    The +/-0.35 spread mirrors the real, well-documented inter-agency
    disagreement seen between USGS/EMSC/GEOFON on the same real earthquake.
    """
    if true_magnitude is None:
        return None
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    unit = (int(digest[:8], 16) % 10000) / 10000.0  # stable pseudo-random in [0, 1)
    offset = (unit - 0.5) * 0.7  # spread to +/-0.35
    return round(true_magnitude + offset, 2)


@bp.get("/accuracy-series")
def accuracy_series():
    """Chronological magnitude comparison across real data sources, plus a
    simulated ENVIRO sensor-network reading per event (see
    _simulated_enviro_estimate) -- for the "เปรียบเทียบแหล่งข้อมูล" accuracy
    chart. Each real event here was reported by exactly one of USGS/EMSC/
    GEOFON/TMD (this system does not yet cross-match the same physical quake
    across sources), so those four lines are naturally sparse -- only ENVIRO's
    simulated line has a point for every event."""
    try:
        limit = min(ACCURACY_SERIES_LIMIT_MAX, max(1, int(request.args.get("limit", ACCURACY_SERIES_DEFAULT))))
    except (TypeError, ValueError):
        limit = ACCURACY_SERIES_DEFAULT

    conn = dbmod.get_conn()
    rows = conn.execute(
        "SELECT * FROM world_quake_history WHERE magnitude IS NOT NULL AND time_ms IS NOT NULL "
        "ORDER BY time_ms DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    rows = list(reversed(rows))  # oldest -> newest, left to right on the chart

    events = []
    for r in rows:
        events.append({
            "id": r["id"], "source": r["source"], "time_ms": r["time_ms"],
            "magnitude": r["magnitude"], "place": r["place"],
            "enviro_estimate": _simulated_enviro_estimate(r["id"], r["magnitude"]),
        })

    return jsonify({
        "events": events,
        "count": len(events),
        "limit": limit,
        "note": (
            "เส้น USGS/EMSC/GEOFON/TMD คือขนาดจริงที่แต่ละแหล่งรายงานเอง (มีจุดเฉพาะเหตุการณ์ที่แหล่งนั้นรายงาน "
            "เนื่องจากระบบยังไม่จับคู่เหตุการณ์เดียวกันข้ามแหล่งข้อมูล) ส่วนเส้น \"ENVIRO Sensor Network (จำลอง)\" "
            "เป็นค่าจำลอง -- เครือข่ายของเรายังไม่เคยตรวจวัดเหตุการณ์จริงเหล่านี้โดยตรง (มีแต่ทดสอบกับสถานการณ์จำลองในไทย) "
            "จึงสร้างค่าประมาณที่ใกล้เคียงขนาดจริง +/-0.35 (สะท้อนความคลาดเคลื่อนระหว่างหน่วยงานจริงที่มักพบในเหตุการณ์เดียวกัน) "
            "เพื่อใช้เปรียบเทียบความแม่นยำเชิงภาพเท่านั้น ไม่ใช่ข้อมูลการตรวจวัดจริง"
        ),
    })


@bp.get("/forecast")
def forecast():
    """Illustrative statistical projection only -- see the disclaimer this endpoint
    ships alongside. No system can deterministically predict earthquakes."""
    conn = dbmod.get_conn()
    risk = {r["region"]: r["score"] for r in conn.execute("SELECT region, score FROM risk_scores").fetchall()}
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    recent_events = conn.execute(
        "SELECT COUNT(*) c FROM events WHERE is_test=0 AND ts >= ?", (week_ago,)
    ).fetchone()["c"]
    conn.close()

    today = datetime.now()
    days = []
    for i in range(7):
        d = today + timedelta(days=i)
        days.append(["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"][d.weekday()] + f".{d.day}")

    series = []
    for region in FORECAST_REGIONS:
        base = sum(risk.get(r, 40) for r in region["risk_regions"]) / len(region["risk_regions"])
        base = base * 0.35 + recent_events * 3
        pts = []
        for i in range(7):
            wobble = 6 * math.sin((i + hash(region["key"]) % 7) * 0.9)
            pts.append(round(max(2, min(45, base + wobble))))
        series.append({"region": region["region"], "color": region["color"], "data": pts})

    return jsonify({
        "days": days,
        "series": series,
        "disclaimer": "เป็นการประมาณค่าทางสถิติจากความถี่แผ่นดินไหวย้อนหลังและกิจกรรมของรอยเลื่อนเท่านั้น "
                       "ไม่ใช่การพยากรณ์แผ่นดินไหวที่แม่นยำ ปัจจุบันยังไม่มีเทคโนโลยีใดในโลกที่พยากรณ์เวลา "
                       "ตำแหน่ง และขนาดแผ่นดินไหวล่วงหน้าได้อย่างแม่นยำ",
    })
