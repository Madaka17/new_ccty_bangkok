"""LINE alerts for the live security view (Messaging API push; LINE Notify is discontinued).

Values come from the repo .env or the process env: LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID.
They are never logged or printed. Missing -> LINE is off, alerts still reach the page.

    python -m launch.security_check.alerts --test     sends one test message, prints OK or failed
"""
import json
import logging
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, deque
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINE_URL = "https://api.line.me/v2/bot/message/push"
STATE_PATH = os.path.join(ROOT, "local", "logs", "security_live_alerts.json")

COOLDOWN = 30 * 60
DAILY_CAP = 20
WEB_BURST = (100, 60)      # events, seconds
SSH_BURST = (20, 300)
UNKNOWN = "ไม่ทราบประเทศ"
CAP_TEXT = f"แจ้งเตือน LINE วันนี้ครบ {DAILY_CAP} ข้อความแล้ว จะไม่ส่งเพิ่มจนถึงพรุ่งนี้ (บนหน้าจอยังแจ้งตามปกติ)"
TEST_TEXT = "ทดสอบแจ้งเตือนจาก BKK Security Live"

_log = logging.getLogger("security_live.alerts")


def load_config(env_path=None, environ=None):
    """(token, user_id); either may be '' when not set. Repo .env wins over the process env."""
    from dotenv import dotenv_values
    path = env_path or os.path.join(ROOT, ".env")
    vals = dotenv_values(path) if os.path.exists(path) else {}
    env = os.environ if environ is None else environ

    def pick(k):
        return str(vals.get(k) or env.get(k) or "").strip()
    return pick("LINE_CHANNEL_ACCESS_TOKEN"), pick("LINE_USER_ID")


def line_sender(token, user_id, timeout=10):
    """sender(text) -> HTTP status int, or 0 when the request itself failed. Logs the status only."""
    def send(text):
        body = json.dumps({"to": user_id, "messages": [{"type": "text", "text": text}]},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(LINE_URL, data=body, method="POST", headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            _log.warning("LINE push failed (%s)", type(e).__name__)
            return 0
        _log.info("LINE push status %s", code)
        return code
    return send


def _where(country, cc):
    return country or cc or UNKNOWN


class Alerter:
    """observe(event) -> list of alert dicts {"type":"alert","level","text"} raised by this event.

    Only non-owner events count. LINE sending is on a background thread (or inline with sync=True)."""

    def __init__(self, sender=None, clock=time.time, state_path=STATE_PATH, sync=False):
        self.sender = sender
        self.clock = clock
        self.state_path = state_path
        self.sync = sync
        self._lock = threading.Lock()
        self._web = deque()      # (ts, ip, where)
        self._ssh = deque()
        self._fired = {}         # rule -> last time
        self._failed = False
        self._q = None
        self._worker = None

    @property
    def enabled(self):
        return self.sender is not None

    def line_status(self):
        if not self.enabled:
            return "off"
        return "failed" if self._failed else "on"

    # ---- rules -------------------------------------------------------
    def observe(self, ev):
        if ev.get("owner") or ev.get("kind") == "self_check":
            return []
        now = self.clock()
        out = []
        with self._lock:
            t = ev.get("type")
            if t == "ssh":
                if ev.get("event") == "accepted":
                    self._maybe(out, now, "ssh_accepted", "critical",
                                f"🚨 มีคนเข้า SSH เครื่อง Pi สำเร็จจากนอกบ้าน: {ev.get('ip')} "
                                f"({_where(ev.get('country'), ev.get('cc'))}) ผู้ใช้ {ev.get('user')}")
                elif ev.get("event") in ("failed", "invalid"):
                    self._ssh.append((now, ev.get("ip"), _where(ev.get("country"), ev.get("cc"))))
                    self._trim(self._ssh, now, SSH_BURST[1])
                    n = len(self._ssh)
                    if n >= SSH_BURST[0]:
                        ip = Counter(x[1] for x in self._ssh).most_common(1)[0][0]
                        self._maybe(out, now, "ssh_burst", "warn",
                                    f"⚠️ มีคนพยายามเดารหัส SSH {n} ครั้งใน 5 นาที จาก {ip}")
            elif t == "web":
                self._web.append((now, ev.get("ip"), _where(ev.get("country"), ev.get("cc"))))
                self._trim(self._web, now, WEB_BURST[1])
                n = len(self._web)
                if n >= WEB_BURST[0]:
                    ip = Counter(x[1] for x in self._web).most_common(1)[0][0]
                    where = next(x[2] for x in reversed(self._web) if x[1] == ip)
                    self._maybe(out, now, "web_burst", "warn",
                                f"⚠️ เว็บโดนยิงถี่ {n} ครั้งใน 1 นาที ตัวหลัก {ip} ({where})")
        for a in out:
            self._send(a["text"])
        return out

    @staticmethod
    def _trim(dq, now, window):
        while dq and now - dq[0][0] > window:
            dq.popleft()

    def _maybe(self, out, now, rule, level, text):
        last = self._fired.get(rule)
        if last is not None and now - last < COOLDOWN:
            return
        self._fired[rule] = now
        out.append({"type": "alert", "level": level, "text": text, "rule": rule})

    # ---- LINE --------------------------------------------------------
    def _load_state(self):
        today = date.fromtimestamp(self.clock()).isoformat()
        try:
            with open(self.state_path, encoding="utf-8") as fh:
                st = json.load(fh)
            if st.get("date") == today:
                return {"date": today, "count": int(st.get("count", 0)), "capped": bool(st.get("capped"))}
        except Exception:
            pass
        return {"date": today, "count": 0, "capped": False}

    def _save_state(self, st):
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(st, fh)
            os.replace(tmp, self.state_path)
        except Exception:
            pass

    def _send(self, text):
        if not self.enabled:
            return
        if self.sync:
            self._do_send(text)
            return
        if self._q is None:
            self._q = queue.Queue(maxsize=100)
            self._worker = threading.Thread(target=self._run, name="line-sender", daemon=True)
            self._worker.start()
        try:
            self._q.put_nowait(text)
        except queue.Full:
            pass

    def _run(self):
        while True:
            self._do_send(self._q.get())

    def _do_send(self, text):
        with self._lock:
            st = self._load_state()
            if st["count"] >= DAILY_CAP:
                if st["capped"]:
                    return
                st["capped"] = True
                self._save_state(st)
                text = CAP_TEXT
            else:
                st["count"] += 1
                self._save_state(st)
        try:
            code = self.sender(text)
        except Exception as e:
            _log.warning("LINE send error (%s)", type(e).__name__)
            code = 0
        self._failed = not (200 <= int(code or 0) < 300)

    def send_now(self, text):
        """Direct send for --test. Returns True on a 2xx. Does not touch the daily counter."""
        if not self.enabled:
            return False
        try:
            code = self.sender(text)
        except Exception:
            return False
        return 200 <= int(code or 0) < 300


def make_alerter(env_path=None, environ=None, **kw):
    token, user = load_config(env_path, environ)
    sender = line_sender(token, user) if token and user else None
    return Alerter(sender=sender, **kw)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--test" not in argv:
        print("usage: python -m launch.security_check.alerts --test")
        return 2
    a = make_alerter(sync=True)
    if not a.enabled:
        print("failed: LINE_CHANNEL_ACCESS_TOKEN / LINE_USER_ID not set in .env")
        return 1
    ok = a.send_now(TEST_TEXT)
    print("OK" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
