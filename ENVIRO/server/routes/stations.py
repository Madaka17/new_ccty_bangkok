from flask import Blueprint, jsonify, current_app

from .. import db as dbmod

bp = Blueprint("stations", __name__, url_prefix="/api/stations")


def _sim():
    return current_app.config["SIMULATOR"]


@bp.get("")
def list_stations():
    return jsonify(_sim().station_status())


@bp.get("/regions")
def regions_summary():
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT region, total, online FROM station_regions").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@bp.get("/<station_id>/waveform")
def station_waveform(station_id):
    wf = _sim().waveform(station_id)
    if wf is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"station_id": station_id, "sample_rate_hz": 20.0, "axes": wf})


@bp.get("/classification")
def classification():
    return jsonify(_sim().class_probs())


@bp.get("/device-spec")
def device_spec():
    return jsonify({
        "name": "ENVIRO Node One",
        "version": "v3",
        "sensor": "MEMS Triaxial Accelerometer ±2g",
        "compute": "NPU ในตัว รองรับโมเดลจำแนกสัญญาณ",
        "connectivity": "Wi-Fi หลัก + 4G สำรองอัตโนมัติ",
        "install": "เสียบปลั๊กผนัง ตั้งค่าอัตโนมัติผ่านแอป",
        "calibration": "อัตโนมัติทุก 24 ชม.",
        "pricing": "เข้าถึงได้ระดับครัวเรือน",
    })
