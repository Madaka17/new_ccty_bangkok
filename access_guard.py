"""Access guard for public exposure (Tailscale Funnel / LAN).

- Control endpoints (POST/PUT/DELETE that change AI or scanner state) are only
  allowed from trusted networks (localhost, LAN, tailnet) or with a valid
  ``X-Admin-Token`` header matching ``ADMIN_TOKEN`` in .env.
- ``/api/chat`` (uses paid Gemini/Claude keys) is rate limited per client IP and
  the request body is size-capped, so a stranger with the link cannot drain the
  key. Set ``CHAT_RATE_PER_MIN`` / ``CHAT_RATE_PER_DAY`` in .env to tune.
- Any other request is soft rate limited to stop scripted floods (per minute and per day).
- Paths with a backslash, ``..`` or ``:`` are refused before routing: ids in the URL end up in file
  paths (``/api/helmet/{hid}/crop``), and on Windows those let a request read any .jpg on the disk.
- Anti-scraping: from outside the trusted networks, /api/ answers only requests a browser makes from
  this site's own pages (``Sec-Fetch-Site: same-origin``, or a same-host Referer on browsers without
  fetch metadata). A script, another website or a pasted API URL gets 403. ``API_BROWSER_ONLY=0``
  turns it off. This raises the bar; it cannot stop someone copying what the page itself shows.
- /docs, /redoc and /openapi.json (the full endpoint map) are trusted-only.
- Every response carries security headers (CSP, no framing, nosniff, referrer / permissions policy,
  HSTS, noindex).

Tailscale serve/funnel forwards the real client address in ``X-Forwarded-For``,
so the limiter keys on that header when the direct peer is a local proxy.
"""
import hmac
import os
import time
import ipaddress
import re
import threading
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
CHAT_RATE_PER_MIN = int(os.getenv("CHAT_RATE_PER_MIN", "6"))
CHAT_RATE_PER_DAY = int(os.getenv("CHAT_RATE_PER_DAY", "60"))
CHAT_MAX_BODY = int(os.getenv("CHAT_MAX_BODY", "8000"))       # bytes
GENERAL_RATE_PER_MIN = int(os.getenv("GENERAL_RATE_PER_MIN", "600"))
GENERAL_RATE_PER_DAY = int(os.getenv("GENERAL_RATE_PER_DAY", "40000"))
API_BROWSER_ONLY = os.getenv("API_BROWSER_ONLY", "1").strip() != "0"
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
BAD_PATH = re.compile(r"\\|\.\.|:")

# Sent with every response. script-src 'self' is the XSS guard; images / video / HLS come from many
# camera and map hosts, so those stay open to any https (and http for old camera feeds).
SECURITY_HEADERS = {
    "Content-Security-Policy": "; ".join((
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' https: http: data: blob:",
        "media-src 'self' https: http: blob:",
        "connect-src 'self' https: http: blob: data:",
        "worker-src 'self' blob:",
        "frame-src https://embed.windy.com",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    )),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=(), payment=(), usb=()",
    "Strict-Transport-Security": "max-age=31536000",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Robots-Tag": "noindex, nofollow",
}

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
general_day = _Window(GENERAL_RATE_PER_DAY, 86400)


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
            # The proxy appends the real peer; earlier entries come from the client and can be forged
            return fwd.split(",")[-1].strip()
    return peer


def is_trusted(request: Request) -> bool:
    if ADMIN_TOKEN and hmac.compare_digest(request.headers.get("x-admin-token", ""), ADMIN_TOKEN):
        return True
    # Tailnet users come through tailscale serve from 127.0.0.1 with their 100.x address in
    # X-Forwarded-For, so the address check covers them. Identity headers (Tailscale-User-Login)
    # are not trusted: a client could send one itself.
    return _is_trusted_ip(client_ip(request))


def _from_own_page(request: Request) -> bool:
    """True when a browser fetched this from one of this site's pages."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        return site == "same-origin"
    # browsers without fetch metadata: fall back to the Referer host
    ref = request.headers.get("referer", "")
    host = request.headers.get("host", "")
    return bool(host) and re.match(rf"^https?://{re.escape(host)}(/|$)", ref) is not None


def _secure(response):
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


def _deny(status, msg):
    return _secure(JSONResponse(status_code=status, content={"error": msg}))


async def guard(request: Request, call_next):
    path = request.url.path
    if BAD_PATH.search(path):
        return _deny(400, "bad path")
    trusted = is_trusted(request)
    if path.startswith(DOC_PATHS) and not trusted:
        return _deny(404, "not found")
    if not path.startswith("/api/"):
        return _secure(await call_next(request))

    ip = client_ip(request)

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

    if not trusted and API_BROWSER_ONLY and not _from_own_page(request):
        return _deny(403, "the API answers this site's own pages only")

    if not trusted and (not general_min.allow(ip) or not general_day.allow(ip)):
        return _deny(429, "too many requests")

    return _secure(await call_next(request))
