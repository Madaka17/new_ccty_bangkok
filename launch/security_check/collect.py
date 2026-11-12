"""Collectors: gather facts. Read-only. Never returns secret values (only lengths and booleans)."""
import base64
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PI = {"host": "192.168.1.109", "user": "test", "key": r"C:\Users\user\.ssh\bkkpi_ed25519",
      "repo": "/mnt/ssd/new_ccty_bangkok"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")
STATUS_PATHS = ("/docs", "/openapi.json", "/.env", "/.git/HEAD", "/api/traffic/summary")

_FLAGS_SCRIPT = r'''
import json, sys
from dotenv import dotenv_values
v = dotenv_values(sys.argv[1])
def i(k, d):
    try: return int(str(v.get(k, d)).strip())
    except Exception: return d
print(json.dumps({
    "admin_token_len": len((v.get("ADMIN_TOKEN") or "").strip()),
    "api_session": str(v.get("API_SESSION", "1")).strip() != "0",
    "api_browser_only": str(v.get("API_BROWSER_ONLY", "1")).strip() != "0",
    "general_rate_per_min": i("GENERAL_RATE_PER_MIN", 600),
    "chat_rate_per_day": i("CHAT_RATE_PER_DAY", 60),
}))
'''

_HOST_SCRIPT = r'''
echo @@listen; ss -Htln | awk '{print $4}'
echo @@sshd; o=$(sudo -n sshd -T 2>/dev/null); if [ -n "$o" ]; then echo "$o" | grep -Ei '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication) '; else echo DENIED; fi
echo @@ufw; if command -v ufw >/dev/null 2>&1 || [ -x /usr/sbin/ufw ]; then o=$(sudo -n ufw status 2>/dev/null | head -1); if [ -n "$o" ]; then echo "$o"; else echo denied; fi; else echo none; fi
echo @@upgradable; apt list --upgradable 2>/dev/null | grep -c upgradable
echo @@unattended; dpkg -s unattended-upgrades >/dev/null 2>&1 && echo yes
echo @@reboot; test -f /var/run/reboot-required && echo yes
echo @@fail2ban; systemctl is-active fail2ban
true
'''


def _b64(s):
    return base64.b64encode(s.encode()).decode()


def ssh(cmd, timeout=20):
    args = ["ssh", "-i", PI["key"], "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            f"{PI['user']}@{PI['host']}", cmd]
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def _parse_json(text):
    try:
        d = json.loads((text or "").strip().splitlines()[-1])
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def pi_attack_summary(days=30):
    """dict = summary; None = ssh failed; {"_error": "not_deployed"} = ssh ok but CLI failed."""
    if ssh("echo ok", timeout=15) is None:
        return None
    repo = PI["repo"]
    out = ssh(f"cd {repo} && INSTANCE_DIR={repo}/instances/production "
              f".venv/bin/python -m backend.core.security_log --summary-json --days {int(days)}", timeout=40)
    d = _parse_json(out)
    return d if d is not None else {"_error": "not_deployed"}


def local_attack_summary(instance_dir, days=30):
    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        py = sys.executable
    env = dict(os.environ, INSTANCE_DIR=instance_dir)
    try:
        r = subprocess.run([py, "-m", "backend.core.security_log", "--summary-json", "--days", str(int(days))],
                           cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    return _parse_json(r.stdout) if r.returncode == 0 else None


def _token_or_none(text):
    t = (text or "").strip()
    return t if re.fullmatch(r"[0-9a-f]{32}", t) else None


def pi_self_check_token():
    """The code that marks this program's own test requests; None when it cannot be read."""
    repo = PI["repo"]
    return _token_or_none(ssh(f"cd {repo} && INSTANCE_DIR={repo}/instances/production "
                              f".venv/bin/python -m backend.core.security_log --self-check-token", timeout=40))


def local_self_check_token(instance_dir):
    py = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.exists(py):
        py = sys.executable
    env = dict(os.environ, INSTANCE_DIR=instance_dir)
    try:
        r = subprocess.run([py, "-m", "backend.core.security_log", "--self-check-token"],
                           cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    return _token_or_none(r.stdout) if r.returncode == 0 else None


def pi_config_flags():
    repo = PI["repo"]
    cmd = f"cd {repo} && echo {_b64(_FLAGS_SCRIPT)} | base64 -d | .venv/bin/python - {repo}/.env"
    return _parse_json(ssh(cmd))


def local_config_flags(env_path):
    from dotenv import dotenv_values
    v = dotenv_values(env_path) if os.path.exists(env_path) else {}

    def i(k, d):
        try:
            return int(str(v.get(k, d)).strip())
        except Exception:
            return d
    return {
        "admin_token_len": len((v.get("ADMIN_TOKEN") or "").strip()),
        "api_session": str(v.get("API_SESSION", "1")).strip() != "0",
        "api_browser_only": str(v.get("API_BROWSER_ONLY", "1")).strip() != "0",
        "general_rate_per_min": i("GENERAL_RATE_PER_MIN", 600),
        "chat_rate_per_day": i("CHAT_RATE_PER_DAY", 60),
    }


def parse_host_output(text):
    sections, cur = {}, None
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("@@"):
            cur = line[2:]
            sections[cur] = []
        elif cur and line:
            sections[cur].append(line)
    sshd = {}
    if "DENIED" in sections.get("sshd", []):
        sshd = {"_denied": True}
    for line in sections.get("sshd", []):
        k, _, v = line.partition(" ")
        if v:
            sshd[k.lower()] = v.strip().lower()
    ufw = " ".join(sections.get("ufw", [])).lower()
    if "denied" in ufw:
        fw = "denied"
    elif "inactive" in ufw:
        fw = "inactive"
    elif "active" in ufw:
        fw = "active"
    else:
        fw = "none"
    try:
        up = int((sections.get("upgradable") or ["0"])[0])
    except ValueError:
        up = 0
    return {
        "listen": [(l.split()[3] if len(l.split()) >= 4 else l) for l in sections.get("listen", [])],
        "sshd": sshd,
        "firewall": fw,
        "upgradable": up,
        "unattended": "yes" in sections.get("unattended", []),
        "reboot_required": "yes" in sections.get("reboot", []),
        "fail2ban": "active" in sections.get("fail2ban", []),
    }


def pi_host_raw():
    out = ssh(f"echo {_b64(_HOST_SCRIPT)} | base64 -d | sh", timeout=60)
    return None if out is None else parse_host_output(out)


_SSH_JOURNAL_SCRIPT = r'''
days="$1"
o=$(journalctl -u ssh -u sshd --since "$days days ago" --no-pager -o short-iso 2>/dev/null)
if [ -z "$o" ]; then o=$(sudo -n journalctl -u ssh -u sshd --since "$days days ago" --no-pager -o short-iso 2>/dev/null); fi
echo "$o" | grep -E 'sshd(-session)?\[[0-9]+\]: (Failed |Invalid user|Accepted |Connection closed by|Disconnected from)'
true
'''

# short-iso line = "TS host sshd[pid]: message". Every pattern is anchored on the message start and the
# user part is greedy so the LAST " from IP port N" wins: a hostile user name cannot fake the IP.
_RE_LINE = re.compile(r"^\S+ \S+ sshd(?:-session)?\[(\d+)\]: (.*)$")
_RE_ACCEPT = re.compile(r"^Accepted (publickey|password|keyboard-interactive/pam) for (.*) from (\S+) port \d+")
_RE_FAILED = re.compile(r"^Failed (?:password|publickey|keyboard-interactive/pam) for (invalid user )?(.*) from (\S+) port \d+")
_RE_INVALID = re.compile(r"^Invalid user (.*) from (\S+)(?: port \d+)?")
_RE_AUTHFAIL = re.compile(r"^(?:Connection closed by|Disconnected from) authenticating user (.*) (\S+) port \d+")
_RE_CLOSED_INVALID = re.compile(r"^Connection closed by invalid user (.*) (\S+) port \d+")


def _top(counter, key, limit=10):
    return [{key: k, "n": n} for k, n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def parse_ssh_line(line):
    """One short-iso sshd journal line -> event dict, or None when it is not a login event.

    {"ts", "pid", "event": accepted|failed|invalid, "method": publickey|password|None, "user", "ip"}"""
    lm = _RE_LINE.match((line or "").rstrip("\r\n"))
    if not lm:
        return None
    ts = line.split(" ", 1)[0]
    pid, msg = lm.group(1), lm.group(2)
    m = _RE_ACCEPT.match(msg)
    if m:
        meth = "publickey" if m.group(1) == "publickey" else "password"
        return {"ts": ts, "pid": pid, "event": "accepted", "method": meth, "user": m.group(2), "ip": m.group(3)}
    m = _RE_FAILED.match(msg)
    if m:
        meth = "publickey" if msg.startswith("Failed publickey") else "password"
        return {"ts": ts, "pid": pid, "event": "invalid" if m.group(1) else "failed", "method": meth,
                "user": m.group(2), "ip": m.group(3)}
    m = _RE_INVALID.match(msg)
    if m:
        return {"ts": ts, "pid": pid, "event": "invalid", "method": None, "user": m.group(1), "ip": m.group(2)}
    m = _RE_CLOSED_INVALID.match(msg)
    if m:
        return {"ts": ts, "pid": pid, "event": "invalid", "method": None, "user": m.group(1), "ip": m.group(2)}
    m = _RE_AUTHFAIL.match(msg)
    if m:
        return {"ts": ts, "pid": pid, "event": "failed", "method": None, "user": m.group(1), "ip": m.group(2)}
    return None


def parse_ssh_journal(text):
    """Pure parser for `journalctl -u ssh -o short-iso` text. One attempt per (pid, user, ip)."""
    accepted, attempts = {}, {}
    for line in (text or "").splitlines():
        ev = parse_ssh_line(line)
        if not ev:
            continue
        if ev["event"] == "accepted":
            k = (ev["ip"], ev["user"], ev["method"])
            accepted[k] = accepted.get(k, 0) + 1
            continue
        key = (ev["pid"], ev["user"], ev["ip"])
        attempts[key] = attempts.get(key, False) or ev["event"] == "invalid"
    failed = invalid = 0
    ips, users = {}, {}
    for (_pid, user, ip), inv in attempts.items():
        if inv:
            invalid += 1
        else:
            failed += 1
        users[user] = users.get(user, 0) + 1
        ips[ip] = ips.get(ip, 0) + 1
    acc = [{"ip": ip, "user": u, "method": meth, "n": n} for (ip, u, meth), n in sorted(accepted.items())]
    return {"failed": failed, "invalid_user": invalid, "accepted": acc,
            "failed_ips": _top(ips, "ip"), "users_tried": _top(users, "user")}


def pi_ssh_log(days=30):
    """Read-only: the Pi's SSH journal, parsed. None when ssh to the Pi fails."""
    out = ssh(f"echo {_b64(_SSH_JOURNAL_SCRIPT)} | base64 -d | sh -s {int(days)}", timeout=60)
    return None if out is None else parse_ssh_journal(out)


def public_ip():
    """The owner's home public IP, from our own domain's Cloudflare trace. None on failure."""
    try:
        _code, _h, body = _get("https://bkksmartstreet.com/cdn-cgi/trace", timeout=10)
    except Exception:
        return None
    m = re.search(r"^ip=(\S+)$", body.decode("utf-8", "replace"), re.M)
    return m.group(1) if m else None


def public_ip_v4():
    """Owner's home public IPv4 (public_ip() returns whichever family this PC used). None on any failure."""
    host = "bkksmartstreet.com"
    try:
        af, st, pr, _cn, sa = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0]
        with socket.create_connection(sa[:2], timeout=10) as raw:
            raw.settimeout(10)
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as s:
                s.sendall((f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {UA}\r\n"
                           "Accept: */*\r\nConnection: close\r\n\r\n").encode("ascii"))
                buf = b""
                while len(buf) < 4096:
                    chunk = s.recv(1024)
                    if not chunk:
                        break
                    buf += chunk
        m = re.search(r"^ip=(\S+)$", buf.decode("utf-8", "replace"), re.M)
        if not m:
            return None
        import ipaddress
        return m.group(1) if ipaddress.ip_address(m.group(1)).version == 4 else None
    except Exception:
        return None


def _get(url, timeout=15, extra_headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", **(extra_headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(200)
    except urllib.error.HTTPError as e:
        try:
            body = e.read(200)
        except Exception:
            body = b""
        return e.code, {k.lower(): v for k, v in e.headers.items()}, body


def _cert_days_left(host, port=443):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as s:
        with ctx.wrap_socket(s, server_hostname=host) as t:
            cert = t.getpeercert()
    exp = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), tz=timezone.utc)
    return (exp - datetime.now(timezone.utc)).days


def web_checks(base_url, self_check_token=None):
    base = base_url.rstrip("/")
    extra = {"X-BKK-Self-Check": self_check_token} if self_check_token else None
    out = {}
    try:
        _code, headers, _ = _get(base + "/", extra_headers=extra)
        out["headers"] = headers
    except Exception:
        pass
    status = {}
    for p in STATUS_PATHS:
        try:
            code, h, body = _get(base + p, extra_headers=extra)
            status[p] = (code, h.get("content-type", ""), body.decode("utf-8", "replace"))
        except Exception:
            continue
    out["status"] = status
    u = urlparse(base)
    if u.scheme == "https" and u.hostname:
        try:
            out["cert_days_left"] = _cert_days_left(u.hostname, u.port or 443)
        except Exception:
            pass
    return out
