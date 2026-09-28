import secrets
import threading
from functools import wraps

from flask import request, jsonify
from werkzeug.security import check_password_hash

from . import db as dbmod

_lock = threading.Lock()
_tokens = {}  # token -> {"username":..., "role":..., "display_name":...}


def login(username, password):
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    token = secrets.token_hex(20)
    with _lock:
        _tokens[token] = {"username": row["username"], "role": row["role"], "display_name": row["display_name"]}
    return {"token": token, "username": row["username"], "role": row["role"], "display_name": row["display_name"]}


def logout(token):
    with _lock:
        _tokens.pop(token, None)


def user_for_token(token):
    with _lock:
        return _tokens.get(token)


def current_user():
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token")
    if not token:
        return None
    return user_for_token(token)


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "unauthorized", "message": "ต้องเข้าสู่ระบบก่อนใช้งาน"}), 401
        request.user = user
        return f(*args, **kwargs)
    return wrapper


def require_role(*roles):
    def deco(f):
        @wraps(f)
        @require_auth
        def wrapper(*args, **kwargs):
            if request.user["role"] not in roles:
                return jsonify({"error": "forbidden", "message": "สิทธิ์ไม่เพียงพอสำหรับการทำรายการนี้"}), 403
            return f(*args, **kwargs)
        return wrapper
    return deco
