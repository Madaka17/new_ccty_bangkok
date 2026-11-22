from flask import Blueprint, request, jsonify

from .. import auth, login_throttle

bp = Blueprint("auth_routes", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "bad_request"}), 400
    raw_username = body.get("username") or ""
    password = body.get("password") or ""
    if not isinstance(raw_username, str) or not isinstance(password, str):
        return jsonify({"error": "bad_request"}), 400
    username = raw_username.strip()
    ip = login_throttle.client_ip()
    throttle_key = username.lower()
    if login_throttle.is_blocked(ip, throttle_key):
        return jsonify({"error": "too_many_attempts", "message": login_throttle.BLOCKED_MESSAGE}), 429
    result = auth.login(username, password)
    if not result:
        login_throttle.record_failure(ip, throttle_key)
        return jsonify({"error": "invalid_credentials", "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"}), 401
    login_throttle.clear(ip, throttle_key)
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
