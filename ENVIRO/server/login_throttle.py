"""Throttle failed logins per client IP and per username.

Sliding window of failed attempts (WINDOW_SECONDS). Once an IP has MAX_FAILURES_PER_IP failures, or a
username has MAX_FAILURES_PER_USER, further attempts are refused with 429 before the password is checked.
Behind Cloudflare Tunnel the peer is loopback, so the real client IP is read from CF-Connecting-IP.
"""
import ipaddress
import threading
import time
from collections import deque

from flask import request

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_IP = 5
MAX_FAILURES_PER_USER = 10
BLOCKED_MESSAGE = "ลองเข้าสู่ระบบผิดหลายครั้ง กรุณารอ 15 นาทีแล้วลองใหม่"

_lock = threading.Lock()
_ip_failures = {}  # ip -> deque of failure timestamps
_user_failures = {}  # username -> deque of failure timestamps
SWEEP_INTERVAL_SECONDS = 60
MAX_KEY_LENGTH = 64
_clock = time.monotonic
_last_sweep = None  # clock value of the last stale-key sweep, None before the first one


def reset():
    global _last_sweep
    with _lock:
        _ip_failures.clear()
        _user_failures.clear()
        _last_sweep = None


def _user_key(username):
    return (username or "").strip().lower()[:MAX_KEY_LENGTH]


def _ip_key(ip):
    return (ip or "").strip()[:MAX_KEY_LENGTH]


def _sweep_stale(now):
    """Drop keys whose newest failure has left the window, in both tables."""
    cutoff = now - WINDOW_SECONDS
    for table in (_ip_failures, _user_failures):
        stale = [key for key, dq in table.items() if not dq or dq[-1] <= cutoff]
        for key in stale:
            del table[key]


def _is_loopback(addr):
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return False


def client_ip():
    remote = request.remote_addr or ""
    forwarded = request.headers.get("CF-Connecting-IP", "").strip()
    if forwarded and _is_loopback(remote):
        return forwarded
    return remote


def _count(table, key, now):
    dq = table.get(key)
    if dq is None:
        return 0
    cutoff = now - WINDOW_SECONDS
    while dq and dq[0] <= cutoff:
        dq.popleft()
    if not dq:
        del table[key]
        return 0
    return len(dq)


def is_blocked(ip, username):
    now = _clock()
    with _lock:
        return (
            _count(_ip_failures, _ip_key(ip), now) >= MAX_FAILURES_PER_IP
            or _count(_user_failures, _user_key(username), now) >= MAX_FAILURES_PER_USER
        )


def record_failure(ip, username):
    global _last_sweep
    now = _clock()
    with _lock:
        if _last_sweep is None or now - _last_sweep >= SWEEP_INTERVAL_SECONDS:
            _sweep_stale(now)
            _last_sweep = now
        _ip_failures.setdefault(_ip_key(ip), deque()).append(now)
        _user_failures.setdefault(_user_key(username), deque()).append(now)


def clear(ip, username):
    with _lock:
        _ip_failures.pop(_ip_key(ip), None)
        _user_failures.pop(_user_key(username), None)
