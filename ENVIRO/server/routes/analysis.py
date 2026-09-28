from flask import Blueprint, jsonify, current_app

from .. import db as dbmod

bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")


def _sim():
    return current_app.config["SIMULATOR"]


@bp.get("/stalta")
def stalta():
    sim = _sim()
    return jsonify({
        "threshold": sim.stalta_threshold,
        "series": sim.stalta_series(),
        "sample_rate_hz": 20.0,
        "station_id": sim.focus_station,
    })


@bp.get("/waveform")
def waveform():
    sim = _sim()
    return jsonify({
        "station_id": sim.focus_station,
        "sample_rate_hz": 20.0,
        "axes": sim.waveform(sim.focus_station),
    })


@bp.get("/fft")
def fft():
    sim = _sim()
    spectrum, dominant = sim.fft()
    return jsonify({"bins": spectrum, "dominant_hz": round(dominant, 2), "station_id": sim.focus_station})


@bp.get("/correlation")
def correlation():
    sim = _sim()
    # The 6 stations nearest the *current* focus station, so this stays
    # relevant to wherever the active (or most recent) event actually is,
    # instead of a fixed northern cluster that goes stale after a quake
    # elsewhere in the country.
    station_ids = sim.nearest_stations_to(sim.focus_station, 6)
    names, matrix = sim.correlation(station_ids)
    return jsonify({"stations": names, "matrix": matrix})


@bp.get("/model-performance")
def model_performance():
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM model_performance WHERE id=1").fetchone()
    conn.close()
    return jsonify(dict(row))


@bp.get("/risk")
def risk():
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT region, score FROM risk_scores ORDER BY score DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
