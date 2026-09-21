"""Access guard for public exposure (Tailscale Funnel / LAN).

- Control endpoints (POST/PUT/DELETE that change AI or scanner state) are only
  allowed from trusted networks (localhost, LAN, tailnet) or with a valid
  ``X-Admin-Token`` header matching ``ADMIN_TOKEN`` in .env.
- ``/api/chat`` (uses paid Gemini/Claude keys) is rate limited per client IP and
  the request body is size-capped, so a stranger with the link cannot drain the
  key. Set ``CHAT_RATE_PER_MIN`` / ``CHAT_RATE_PER_DAY`` in .env to tune.
- Any other request is soft rate limited to stop scripted floods.

Tailscale serve/funnel forwards the real client address in ``X-Forwarded-For``,
so the limiter keys on that header when the direct peer is a local proxy.
"""
import os
import time
import ipaddress
import threading
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
CHAT_RATE_PER_MIN = int(os.getenv("CHAT_RATE_PER_MIN", "6"))
CHAT_RATE_PER_DAY = int(os.getenv("CHAT_RATE_PER_DAY", "60"))
CHAT_MAX_BODY = int(os.getenv("CHAT_MAX_BODY", "8000"))       # bytes
GENERAL_RATE_PER_MIN = int(os.getenv("GENERAL_RATE_PER_MIN", "600"))

# Networks that may call control endpoints without a token
TRUSTED_NETS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "::1/128",
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",   # LAN
    "100.64.0.0/10",                                    # Tailscale CGNAT range
    "fd7a:115c:a1e0::/48",                              # Tailscale IPv6
)]

# Mutating endpoints that are public by design (anonymous usage telemetry)
PUBLIC_WRITE_PREFIXES = ("/api/telemetry/", "/api/chat")


class _Window:
    """Sliding window counter per key."""
    def __init__(self, limit, seconds):
        self.limit = limit
        self.seconds = seconds
        self.hits = {}
        self.lock = threading.Lock()

    def allow(self, key):
        if self.limit <= 0:
            return True
        now = time.time()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and q[0] < now - self.seconds:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            # keep the map from growing forever
            if len(self.hits) > 5000:
                for k in [k for k, v in self.hits.items() if not v or v[-1] < now - self.seconds]:
                    self.hits.pop(k, None)
            return True


chat_min = _Window(CHAT_RATE_PER_MIN, 60)
chat_day = _Window(CHAT_RATE_PER_DAY, 86400)
general_min = _Window(GENERAL_RATE_PER_MIN, 60)


def _is_trusted_ip(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in TRUSTED_NETS)


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    # Only trust X-Forwarded-For when the direct peer is our own proxy (tailscale serve)
    if peer in ("127.0.0.1", "::1"):
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return peer


def is_trusted(request: Request) -> bool:
    if ADMIN_TOKEN and request.headers.get("x-admin-token", "") == ADMIN_TOKEN:
        return True
    # Tailscale serve (tailnet-only) tags authenticated users; funnel never sets it
    if request.headers.get("tailscale-user-login"):
        return True
    return _is_trusted_ip(client_ip(request))


def _deny(status, msg):
    return JSONResponse(status_code=status, content={"error": msg})


async def guard(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    ip = client_ip(request)
    trusted = is_trusted(request)

    if request.method in ("POST", "PUT", "DELETE") and not path.startswith(PUBLIC_WRITE_PREFIXES):
        if not trusted:
            return _deny(403, "control endpoints are limited to the operator")

    if path == "/api/chat" and request.method == "POST" and not trusted:
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        if length > CHAT_MAX_BODY:
            return _deny(413, "message too long")
        if not chat_min.allow(ip) or not chat_day.allow(ip):
            return _deny(429, "too many chat requests, try again later")

    if not trusted and not general_min.allow(ip):
        return _deny(429, "too many requests")

    return await call_next(request)
