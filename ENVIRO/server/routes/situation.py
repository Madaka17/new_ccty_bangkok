from datetime import datetime
from flask import Blueprint, jsonify, current_app

from .. import db as dbmod
from ..seismology import felt_radius_km, mmi_roman, predict_mmi
from ..simulator import VP_KM_S, VS_KM_S, CONFIDENCE_LABELS, Simulator
from ..geo import haversine_km

bp = Blueprint("situation", __name__, url_prefix="/api/situation")


def _sim():
    return current_app.config["SIMULATOR"]


@bp.get("")
def get_situation():
    conn = dbmod.get_conn()
    event = conn.execute(
        "SELECT * FROM events WHERE is_test=0 ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    # The query above always returns SOME row once any event has ever been
    # triggered -- with no staleness check, a demo triggered hours or days
    # ago would keep being reported as "currently happening" on every future
    # page load or server restart, forever. An event stops counting as
    # current the moment its own S-wave has swept past its felt radius (see
    # seismology.felt_radius_km) -- the same physical threshold that already
    # governs when the frontend's map ripple stops animating, so "is this
    # event still active" agrees everywhere instead of the REST response
    # resurrecting something the map has long since stopped showing.
    if event:
        try:
            event_ts = datetime.fromisoformat(event["ts"])
            event_elapsed_s = (datetime.now(event_ts.tzinfo) - event_ts).total_seconds()
        except Exception:
            event_elapsed_s = 0
        event_speed_mult = event["speed_multiplier"] or 1.0
        event_vs_eff = VS_KM_S * event_speed_mult
        if event_elapsed_s * event_vs_eff > felt_radius_km(event["magnitude"], event["depth"]):
            event = None
    stations = conn.execute("SELECT id,region,lat,lng,status FROM stations").fetchall()
    faults = conn.execute("SELECT name,region,lat1,lng1,lat2,lng2 FROM fault_lines").fetchall()
    cities = conn.execute("SELECT name,lat,lng,mmi_label FROM cities").fetchall()
    conn.close()

    quake = _sim().snapshot()["quake"]
    origin_lat, origin_lng = (event["lat"], event["lng"]) if event else (quake["lat"], quake["lng"])

    event_out = None
    elapsed = None
    speed_mult = 1.0
    if event:
        event_out = dict(event)
        # The `events` table only persists the raw facts (level number, PGA,
        # etc.); the level's display text (name/message/channels/siren) lives
        # in `levels` and has to be joined in here so the REST response
        # matches what the WebSocket 'alert' payload already carries --
        # otherwise the guidance banner reads fine off a live WS push but
        # shows "undefined" after a plain page load/refresh.
        conn2 = dbmod.get_conn()
        level_row = conn2.execute(
            "SELECT name, message, channels, siren, color FROM levels WHERE lv=?", (event["level"],)
        ).fetchone()
        conn2.close()
        if level_row:
            event_out.update({
                "level_name": level_row["name"], "message": level_row["message"],
                "channels": level_row["channels"], "siren": level_row["siren"], "color": level_row["color"],
            })
        # `magnitude_estimate`/`confidence_tier`/`confidence_label`/`fully_confirmed`
        # are runtime-only fields that live on the simulator's in-memory
        # active_event (see Simulator._declare_event) and were never given DB
        # columns -- without this merge they're simply absent from the REST
        # response (a plain page load/refresh would render "confidence:
        # undefined") even though the same fields render fine off a live WS
        # push, exactly the kind of REST/WS drift the level_name join above
        # already exists to prevent.
        active = _sim().active_event
        if active and active.get("id") == event["id"]:
            event_out.update({
                "magnitude_estimate": active["magnitude_estimate"],
                "confidence_tier": active["confidence_tier"],
                "confidence_label": active["confidence_label"],
                "fully_confirmed": active["fully_confirmed"],
                "predicted_mmi": active["predicted_mmi"],
                "predicted_mmi_roman": active["predicted_mmi_roman"],
                "tsunami_risk": active["tsunami_risk"],
                "external_match": active.get("external_match"),
            })
        else:
            # historical event (server restarted since, or a different one is
            # now active) -- no live runtime estimate exists any more, so
            # fall back to the persisted facts: the DB's own magnitude/MMI,
            # and a confidence tier recomputed from the persisted
            # corroboration count -- re-checked against the external feed the
            # same way _declare_event/_recheck_confidence do, so a page
            # load/refresh after a restart shows the same corroboration a
            # live WS push would have.
            external_match = Simulator._external_corroboration(event["lat"], event["lng"], event["ts"], event["magnitude"])
            tier = Simulator._apply_external_boost(Simulator._confidence_tier(event["stations_triggered"]), external_match)
            event_out.update({
                "magnitude_estimate": event["magnitude"],
                "confidence_tier": tier,
                "confidence_label": CONFIDENCE_LABELS[tier],
                "fully_confirmed": tier >= 5,
                "predicted_mmi": event["predicted_mmi"],
                "predicted_mmi_roman": mmi_roman(event["predicted_mmi"]),
                "tsunami_risk": bool(event["tsunami_risk"]),
                "external_match": external_match,
            })
        speed_mult = event["speed_multiplier"] or 1.0
        try:
            ts = datetime.fromisoformat(event["ts"])
            elapsed = (datetime.now(ts.tzinfo) - ts).total_seconds()
        except Exception:
            elapsed = 0

    vp_eff, vs_eff = VP_KM_S * speed_mult, VS_KM_S * speed_mult

    # Per-city predicted MMI is computed live from the current/last event's
    # magnitude and depth at each city's real distance -- not the old static
    # per-city label, which claimed the same fixed intensity for every city
    # regardless of which quake (or none) was actually active. A city's
    # "typical" MMI genuinely depends on which specific event is happening.
    conn3 = dbmod.get_conn()
    level_bands = [(r["mmi_min"], r["mmi_max"], r["name"]) for r in
                   conn3.execute("SELECT mmi_min, mmi_max, name FROM levels ORDER BY lv").fetchall()]
    conn3.close()

    def level_name_for_mmi(mmi_val):
        for mmi_min, mmi_max, name in reversed(level_bands):
            if mmi_val >= mmi_min:
                return name
        return level_bands[0][2]

    def mmi_label_for(dist_km):
        if not event:
            return "ไม่มีเหตุการณ์ปัจจุบัน"
        mag = event_out["magnitude_estimate"] or event["magnitude"]
        mmi_val = predict_mmi(mag, dist_km, event["depth"])
        return f"{mmi_roman(mmi_val)} ({level_name_for_mmi(mmi_val)})"

    city_rows = []
    for c in cities:
        dist_km = round(haversine_km(c["lat"], c["lng"], origin_lat, origin_lng), 1)
        mmi_label = mmi_label_for(dist_km)
        if event:
            p_remain = max(0.0, dist_km / vp_eff - elapsed)
            s_remain = max(0.0, dist_km / vs_eff - elapsed)
            city_rows.append({
                "name": c["name"], "dist_km": dist_km, "mmi_label": mmi_label,
                "p_remaining_sec": round(p_remain, 1), "s_remaining_sec": round(s_remain, 1),
                "p_arrived": p_remain <= 0, "s_arrived": s_remain <= 0,
            })
        else:
            city_rows.append({
                "name": c["name"], "dist_km": dist_km, "mmi_label": mmi_label,
                "p_remaining_sec": None, "s_remaining_sec": None, "p_arrived": False, "s_arrived": False,
            })

    return jsonify({
        "event": event_out,
        "stations": [dict(s) for s in stations],
        "faults": [dict(f) for f in faults],
        "cities": city_rows,
        "vp_km_s": round(vp_eff, 2), "vs_km_s": round(vs_eff, 2),
        "speed_multiplier": speed_mult,
        "you_are_here": "BKK-201",
        "pending_quake": None if event else quake,
    })
