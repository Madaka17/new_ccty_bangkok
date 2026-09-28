from flask import Blueprint, jsonify, request, current_app

from .. import db as dbmod
from .. import auth

bp = Blueprint("warning", __name__, url_prefix="/api/levels")


@bp.get("")
def list_levels():
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT * FROM levels ORDER BY lv").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@bp.patch("/<int:lv>")
@auth.require_role("admin")
def update_level(lv):
    body = request.get_json(silent=True) or {}
    fields, values = [], []
    for key in ("mmi_min", "mmi_max", "mmi_roman", "severity_desc", "mag_ref", "pga_min", "pga_max",
                "ai_conf", "nodes_min", "message", "channels", "siren"):
        if key in body:
            fields.append(f"{key} = ?")
            values.append(body[key])
    if not fields:
        return jsonify({"error": "no_fields"}), 400
    values.append(lv)
    conn = dbmod.get_conn()
    conn.execute(f"UPDATE levels SET {', '.join(fields)} WHERE lv = ?", values)
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?, ?, ?)",
        (dbmod.now_iso(), request.user["username"], f"ปรับเกณฑ์ระดับเตือนภัย Lv.{lv}: {', '.join(fields)}"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM levels WHERE lv=?", (lv,)).fetchone()
    conn.close()
    return jsonify(dict(row))
