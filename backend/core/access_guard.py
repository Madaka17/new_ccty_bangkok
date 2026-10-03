"""Access guard for public exposure (Cloudflare Tunnel at bkksmartstreet.com / LAN).

- Control endpoints (POST/PUT/DELETE that change AI or scanner state) are only
  allowed from trusted networks (localhost, LAN, tailnet) or with a valid
  ``X-Admin-Token`` header matching ``ADMIN_TOKEN`` in .env.
- ``/api/chat`` (uses paid Gemini/Claude keys) is rate limited per client IP and
  the request body is size-capped, so a stranger with the link cannot drain the
  key. Set ``CHAT_RATE_PER_MIN`` / ``CHAT_RATE_PER_DAY`` in .env to tune.
- ``POST /api/flood/user-reports`` (a flood report with a photo from the public) is the one other public
  write: that exact path and method only (deleting a report stays operator-only), body capped at
  ``USER_REPORT_MAX_BODY`` and ``USER_REPORT_RATE_PER_HOUR`` / ``USER_REPORT_RATE_PER_DAY`` per IP.
- Any other request is soft rate limited to stop scripted floods (per minute and per day).
- Paths with a backslash, ``..`` or ``:`` are refused before routing: ids in the URL end up in file
  paths (``/api/helmet/{hid}/crop``), and on Windows those let a request read any .jpg on the disk.
- Anti-scraping: from outside the trusted networks, /api/ answers only requests a browser makes from
  this site's own pages (``Sec-Fetch-Site: same-origin``, or a same-host Referer on browsers without
  fetch metadata). A script, another website or a pasted API URL gets 403. ``API_BROWSER_ONLY=0``
  turns it off. This raises the bar; it cannot stop someone copying what the page itself shows.
- Page session: that header is easy to fake, so from outside the trusted networks /api/ also wants the
  ``bkk_s`` cookie. The server signs it (HMAC of the time with a secret kept in the instance's cache) and
  sets it with the page (HttpOnly, SameSite=Strict, 12 h, renewed while the page keeps calling the API).
  A script must now load the page and keep its cookies first. ``API_SESSION=0`` turns it off.
- /docs, /redoc and /openapi.json (the full endpoint map) are trusted-only.
- Every response carries security headers (CSP, no framing, nosniff, referrer / permissions policy,
  HSTS, noindex).

Tailscale serve/funnel forwards the real client address in ``X-Forwarded-For``,
so the limiter keys on that header when the direct peer is a local proxy.
Cloudflare Tunnel (cloudflared) connects to ``CLOUDFLARE_TUNNEL_ADDR`` (127.0.0.2) instead of 127.0.0.1,
and only those requests are keyed on ``CF-Connecting-IP``: both proxies come from 127.0.0.1, and a
Funnel visitor could send that header themselves.
"""
import hashlib
import hmac
import os
import time
import ipaddress
import re
import threading
from collections import deque

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.core.instance import DATA_DIR

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
CHAT_RATE_PER_MIN = int(os.getenv("CHAT_RATE_PER_MIN", "6"))
CHAT_RATE_PER_DAY = int(os.getenv("CHAT_RATE_PER_DAY", "60"))
CHAT_MAX_BODY = int(os.getenv("CHAT_MAX_BODY", "8000"))       # bytes
GENERAL_RATE_PER_MIN = int(os.getenv("GENERAL_RATE_PER_MIN", "600"))
GENERAL_RATE_PER_DAY = int(os.getenv("GENERAL_RATE_PER_DAY", "40000"))
USER_REPORT_PATH = "/api/flood/user-reports"
USER_REPORT_MAX_BODY = int(os.getenv("USER_REPORT_MAX_BODY", str(6 * 2**20)))   # bytes: one photo as a data: URL
USER_REPORT_RATE_PER_HOUR = int(os.getenv("USER_REPORT_RATE_PER_HOUR", "5"))
USER_REPORT_RATE_PER_DAY = int(os.getenv("USER_REPORT_RATE_PER_DAY", "20"))
API_BROWSER_ONLY = os.getenv("API_BROWSER_ONLY", "1").strip() != "0"
API_SESSION = os.getenv("API_SESSION", "1").strip() != "0"
SESSION_COOKIE = "bkk_s"
SESSION_MAX_AGE = 12 * 3600
SESSION_RENEW = 3600          # a cookie older than this is replaced on the next page or API answer
SESSION_SECRET_FILE = os.path.join(DATA_DIR, "cache", "session_secret")
TUNNEL_ADDR = os.getenv("CLOUDFLARE_TUNNEL_ADDR", "127.0.0.2")   # cloudflared's origin: http://127.0.0.2:8000
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
        # 'self': the Earthquake page frames ENVIRO at /enviro/; nstcctv: Nakhon Si Thammarat's camera player
        "frame-src 'self' https://embed.windy.com https://nstcctv.nakhoncity.org",
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
report_hour = _Window(USER_REPORT_RATE_PER_HOUR, 3600)
report_day = _Window(USER_REPORT_RATE_PER_DAY, 86400)


def _is_trusted_ip(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in TRUSTED_NETS)


def _via_tunnel(request: Request) -> bool:
    """True when the connection came in on the loopback address only cloudflared is pointed at."""
    server = (getattr(request, "scope", None) or {}).get("server") or ("",)
    return server[0] == TUNNEL_ADDR


def client_ip(request: Request) -> str:
    if _via_tunnel(request):
        # Cloudflare sets CF-Connecting-IP to the visitor's address, replacing any the visitor sent. A tunnel
        # request without it still comes from outside: never fall back to the loopback peer, which is trusted.
        return request.headers.get("cf-connecting-ip", "").strip() or "cloudflare"
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


def _load_secret():
    """The key that signs page-session cookies, made once per instance and kept so a restart keeps them valid."""
    try:
        with open(SESSION_SECRET_FILE, encoding="ascii") as f:
            key = bytes.fromhex(f.read().strip())
        if len(key) >= 32:
            return key
    except (OSError, ValueError):
        pass
    key = os.urandom(32)
    try:
        os.makedirs(os.path.dirname(SESSION_SECRET_FILE), exist_ok=True)
        with open(SESSION_SECRET_FILE, "w", encoding="ascii") as f:
            f.write(key.hex())
    except OSError:
        pass   # cookies then last until the next restart
    return key


_secret = None


def _sign(ts):
    global _secret
    if _secret is None:
        _secret = _load_secret()
    return hmac.new(_secret, str(ts).encode(), hashlib.sha256).hexdigest()[:32]


def session_age(value, now=None):
    """Seconds since a page-session cookie was signed, or None when it is missing, forged or expired."""
    try:
        ts, sig = (value or "").split(".", 1)
        ts = int(ts)
    except ValueError:
        return None
    age = (now or time.time()) - ts
    if not -300 <= age <= SESSION_MAX_AGE or not hmac.compare_digest(sig, _sign(ts)):
        return None
    return age


def _set_session(response, request):
    ts = int(time.time())
    https = _via_tunnel(request) or request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    response.set_cookie(SESSION_COOKIE, f"{ts}.{_sign(ts)}", max_age=SESSION_MAX_AGE, path="/",
                        httponly=True, samesite="strict", secure=https)


def _is_page(path):
    """The page itself: "/", an .html file or an app route. Its request reaches the server on every load
    (no-cache), even when the answer is a 304, so the session cookie rides on it."""
    last = path.rsplit("/", 1)[-1]
    return path == "/" or last.endswith(".html") or "." not in last


def _secure(response):
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    # The page (index.html) names the hashed JS/CSS of the current build. Without this the browser keeps an
    # old copy by heuristic caching (it has Last-Modified only) and a new deploy shows up only after Ctrl+F5.
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Cache-Control", "no-cache")
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
        response = await call_next(request)
        if API_SESSION and request.method == "GET" and _is_page(path) and response.status_code < 400:
            age = session_age(request.cookies.get(SESSION_COOKIE))
            if age is None or age > SESSION_RENEW:
                _set_session(response, request)
        return _secure(response)

    ip = client_ip(request)

    user_report = path == USER_REPORT_PATH and request.method == "POST"
    if request.method in ("POST", "PUT", "DELETE") and not path.startswith(PUBLIC_WRITE_PREFIXES) and not user_report:
        if not trusted:
            return _deny(403, "control endpoints are limited to the operator")

    if user_report and not trusted:
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        if length > USER_REPORT_MAX_BODY:
            return _deny(413, "photo too large")
        if not report_hour.allow(ip) or not report_day.allow(ip):
            return _deny(429, "too many reports, try again later")

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

    session = None
    if not trusted and API_SESSION:
        session = session_age(request.cookies.get(SESSION_COOKIE))
        if session is None:
            return _deny(403, "the API answers this site's own pages only (reload the page)")

    if not trusted and (not general_min.allow(ip) or not general_day.allow(ip)):
        return _deny(429, "too many requests")

    response = await call_next(request)
    if session is not None and session > SESSION_RENEW:
        _set_session(response, request)   # a page left open for days keeps working
    return _secure(response)
