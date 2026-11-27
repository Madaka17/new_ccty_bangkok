import os
import secrets
import threading
import time
from functools import wraps

from flask import request, jsonify
from werkzeug.security import check_password_hash

from . import db as dbmod

_lock = threading.Lock()
# token -> {"user": {"username":..., "role":..., "display_name":...}, "issued_at": epoch seconds}
_tokens = {}

# A token stops working this many seconds after login (default 12 h). Tokens are only held in memory,
# so a restart already logs everyone out; the TTL keeps a long-lived browser from holding one forever.
def _ttl_from_env(default=12 * 3600):
    """ENVIRO_TOKEN_TTL in seconds; a missing, non-numeric or non-positive value gives the default."""
    try:
        ttl = int(os.environ.get("ENVIRO_TOKEN_TTL", default))
    except ValueError:
        return default
    return ttl if ttl > 0 else default


TOKEN_TTL = _ttl_from_env()

# Clock hook: tests replace this to move time forward without sleeping.
_clock = time.time

# A visitor who has not logged in browses as this read-only guest, so the dashboard opens without a
# password (it is embedded in BKK StreetSmart). require_auth lets the guest through; require_role
# still needs a real account, so only admin/operator can send alerts, simulate quakes or change settings.
GUEST = {"username": "guest", "role": "guest", "display_name": "ผู้เยี่ยมชม"}


def login(username, password):
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    token = secrets.token_hex(20)
    now = _clock()
    user = {"username": row["username"], "role": row["role"], "display_name": row["display_name"]}
    with _lock:
        # sweep expired tokens so memory stays bounded by the number of recent logins
        for old in [t for t, rec in _tokens.items() if now - rec["issued_at"] >= TOKEN_TTL]:
            del _tokens[old]
        _tokens[token] = {"user": user, "issued_at": now}
    return {"token": token, **user}


def logout(token):
    with _lock:
        _tokens.pop(token, None)


def user_for_token(token):
    with _lock:
        rec = _tokens.get(token)
        if rec is None:
            return None
        if _clock() - rec["issued_at"] >= TOKEN_TTL:
            del _tokens[token]
            return None
        return dict(rec["user"])


def current_user():
    # Only the Authorization header carries a token. A ?token= query string would end up in access
    # logs, browser history and Referer headers, so it is ignored and the caller is treated as a guest.
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else None
    if not token:
        return GUEST
    # An unknown token (e.g. from before a server restart) still answers 401, so the page drops it
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
