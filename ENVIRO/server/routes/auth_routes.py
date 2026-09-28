from flask import Blueprint, request, jsonify

from .. import auth

bp = Blueprint("auth_routes", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    result = auth.login(username, password)
    if not result:
        return jsonify({"error": "invalid_credentials", "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"}), 401
    return jsonify(result)


@bp.post("/logout")
@auth.require_auth
def logout():
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else None
    if token:
        auth.logout(token)
    return jsonify({"ok": True})


@bp.get("/me")
@auth.require_auth
def me():
    return jsonify(request.user)
