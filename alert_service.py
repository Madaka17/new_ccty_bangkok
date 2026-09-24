"""
Web Push alerts for the operator team.

Every CHECK_SECONDS the service reads the live sources the server already keeps and turns them into
alert candidates, each with a stable key and a severity:

    flood      water on a road sensor above FLOOD_CM (ปภ.: over 20 cm drivers should avoid the road,
               over 60 cm do not drive through) - flood_service; and a burst of Traffy Fondue flood
               complaints in one district (TRAFFY_MIN within TRAFFY_WINDOW) - flood_feeds
    zone       an area forecast at the red watch level, or a river / canal gauge over its bank - water_service;
               and a TMD heavy-rain / storm warning that names Bangkok - flood_feeds
    incident   an accident / breakdown confirmed by the camera AI, a Longdo accident report, and BMA
               traffic-centre reports of accidents, fires, fallen trees and road closures
    air        a PM2.5 station at the "มีผลต่อสุขภาพ" band (> 75 µg/m³) - air_service
    system     BMA scan stalled, vision agent failing, data disk nearly full, and "server started"

A candidate is pushed when its key is new or its severity went up. It is forgotten after it has been
absent for CLEAR_SECONDS, so a condition that clears and comes back alerts again, while one that stays
(a canal over its bank for days) alerts once. The sent state is kept on disk so a restart does not
repeat every open alert. New alerts of one topic in one pass go out as a single notification.

Subscriptions come from the Alerts page (browser Push API). Subscribing is a POST, so access_guard
limits it to the team (LAN / tailnet / X-Admin-Token). The VAPID key pair is generated on first run.
"""
import json
import os
import threading
import time
from collections import deque

try:
    from pywebpush import WebPushException, webpush
    from py_vapid import Vapid01
    from cryptography.hazmat.primitives import serialization
    import base64
except ImportError:  # keeps the server bootable without the push libraries
    webpush = None

TOPICS = {
    "flood": "น้ำท่วมถนน",
    "zone": "เขตเตือนภัย/คลองล้นตลิ่ง",
    "incident": "อุบัติเหตุ/ปิดถนน",
    "air": "PM2.5",
    "system": "ระบบ",
}
TOPIC_URL = {"flood": "/#water", "zone": "/#water", "incident": "/#dashboard", "air": "/#map", "system": "/#dashboard"}
CHECK_SECONDS = 60
CLEAR_SECONDS = 30 * 60
FLOOD_CM = 20.0
CLOSED_CM = 60.0
# Residents file a few flood complaints a day in normal weather; several in one district within an hour is rain now
TRAFFY_WINDOW = 3600
TRAFFY_MIN = 3
TRAFFY_SEVERE = 8
BMA_EVENT_KINDS = ("accident", "fire", "tree")
BMA_EVENT_HOURS = 2
DISK_MIN_GB = 5.0
HISTORY_KEEP = 200
# A system condition must hold this long before it alerts (the vision API hits short rate limits all day)
DEBOUNCE_SECONDS = {"system": 10 * 60}
PUSH_TTL = 3600
VAPID_SUB = os.getenv("ALERT_VAPID_SUB", "mailto:admin@example.com")


def _event_key(title):
    """Longdo and the BMA centre relay the same report, and follow-ups say "คืบหน้า...": key on the place."""
    return "inc:" + "".join((title or "").replace("คืบหน้า", "").split())


class AlertService:
    def __init__(self, data_dir, sources):
        """sources: {name: callable} for flood, traffy, tmd, water, incidents, bma_events, air, health (any may fail)."""
        self.sources = sources
        cache = os.path.join(data_dir, "cache")
        os.makedirs(cache, exist_ok=True)
        self.subs_path = os.path.join(cache, "push_subs.json")
        self.state_path = os.path.join(cache, "alert_state.json")
        self.key_path = os.path.join(cache, "vapid_private.pem")
        self.lock = threading.Lock()
        self.subs = self._load(self.subs_path, [])
        st = self._load(self.state_path, {})
        self.sent = st.get("sent", {})             # key -> {"level", "first", "seen"}
        self.history = deque(st.get("history", []), maxlen=HISTORY_KEEP)
        self.pending = {}                          # key -> first seen, for debounced topics
        self.last_check = None
        self.error = None
        self.public_key = self._vapid() if webpush else None

    # ------------------------------------------------------------ storage
    @staticmethod
    def _load(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _save(self):
        with open(self.subs_path, "w", encoding="utf-8") as f:
            json.dump(self.subs, f, ensure_ascii=False)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump({"sent": self.sent, "history": list(self.history)}, f, ensure_ascii=False)

    def _vapid(self):
        if os.path.exists(self.key_path):
            v = Vapid01.from_file(self.key_path)
        else:
            v = Vapid01()
            v.generate_keys()
            v.save_key(self.key_path)
            print(f"[Alerts] generated VAPID key {self.key_path}")
        raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    # ------------------------------------------------------------ candidates
    def _call(self, name, *args):
        fn = self.sources.get(name)
        if not fn:
            return None
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001 - one broken source must not stop the others
            print(f"[Alerts] source {name} failed: {str(e)[:120]}")
            return None

    def candidates(self, now=None):
        """Every alert condition true right now: [{topic, key, level, title, body}]."""
        now = now or time.time()
        out = []
        flood = self._call("flood") or {}
        for s in flood.get("wet") or []:
            cm = s.get("level_cm") or 0
            if cm > FLOOD_CM:
                closed = cm > CLOSED_CM
                out.append({"topic": "flood", "key": f"flood:{s.get('id') or s.get('name')}", "level": 2 if closed else 1,
                            "title": f"{'ห้ามขับผ่าน' if closed else 'ควรเลี่ยง'}: {s.get('name')}",
                            "body": f"น้ำบนถนน {cm:.0f} ซม. · {s.get('road') or '-'} เขต{s.get('district') or '-'}"})

        by_district = {}
        for r in (self._call("traffy") or {}).get("items") or []:
            if r.get("district") and now - (r.get("ts") or 0) <= TRAFFY_WINDOW:
                by_district.setdefault(r["district"], []).append(r)
        for district, reps in by_district.items():
            if len(reps) >= TRAFFY_MIN:
                depths = sorted({r["depth"] for r in reps if r.get("depth")})
                depth = f" · ระดับ{'/'.join(depths)}" if depths else ""
                out.append({"topic": "flood", "key": f"traffy:{district}", "level": 2 if len(reps) >= TRAFFY_SEVERE else 1,
                            "title": f"ประชาชนแจ้งน้ำท่วม {len(reps)} เรื่อง: เขต{district}",
                            "body": f"Traffy Fondue ในชั่วโมงที่ผ่านมา{depth} · {reps[0].get('text', '')[:100]}"})

        water = self._call("water") or {}
        for z in water.get("weather") or []:
            if z.get("watch") == "red":
                storm = f" · พายุเริ่ม {z['storm_at']} น." if z.get("storm_at") else ""
                out.append({"topic": "zone", "key": f"zone:{z.get('id')}", "level": 1,
                            "title": f"เตือนภัยสีแดง: {z.get('name')}",
                            "body": f"{z.get('areas')} · ฝน 24 ชม. {z.get('rain_24h')} มม. ลมกระโชก {z.get('gust_max', 0):.0f} กม./ชม.{storm}"})
        series = set()
        for w in (self._call("tmd") or {}).get("active") or []:    # newest issue first
            if w.get("bkk") and w.get("series") not in series:
                series.add(w.get("series"))
                out.append({"topic": "zone", "key": f"tmd:{w.get('series')}", "level": 1,
                            "title": f"กรมอุตุฯ เตือน: {w.get('title')}", "body": (w.get("summary") or "")[:160]})
        for r in (water.get("river") or []) + (water.get("canals") or []):
            if r.get("level") == "overflow":
                pct = f" {r['storage_pct']:.0f}% ของตลิ่ง" if r.get("storage_pct") is not None else ""
                out.append({"topic": "zone", "key": f"bank:{r.get('id') or r.get('name')}", "level": 1,
                            "title": f"ล้นตลิ่ง: {r.get('name')}",
                            "body": f"{r.get('district') or '-'} {r.get('province') or ''}{pct}".strip()})

        inc = self._call("incidents") or {}
        for i in inc.get("camera") or []:
            if i.get("kind") in ("accident", "breakdown"):
                out.append({"topic": "incident", "key": f"cam:{i.get('id')}", "level": 1,
                            "title": f"{'อุบัติเหตุ' if i['kind'] == 'accident' else 'รถเสียขวางทาง'} (กล้อง AI): {i.get('title')}",
                            "body": (i.get("description") or "")[:140]})
        for i in inc.get("longdo") or []:
            if i.get("kind") == "accident":
                out.append({"topic": "incident", "key": _event_key(i.get("title")), "level": 1,
                            "title": f"อุบัติเหตุ (Longdo): {i.get('title')}", "body": (i.get("description") or "")[:140]})
        ev = self._call("bma_events") or {}
        for e in ev.get("items") or []:
            title = e.get("title") or ""
            if title.startswith("รถเสีย"):    # a broken-down car is filed as "accident" but is not one
                continue
            if e.get("kind") in BMA_EVENT_KINDS or (e.get("kind") == "roadwork" and "ปิด" in title):
                out.append({"topic": "incident", "key": _event_key(title), "level": 1,
                            "title": f"ศูนย์จราจร กทม.: {e.get('title')}", "body": (e.get("desc") or "")[:140]})

        air = self._call("air") or {}
        for a in air.get("items") or []:
            if a.get("level") == "very_unhealthy":
                out.append({"topic": "air", "key": f"air:{a.get('id')}", "level": 1,
                            "title": f"PM2.5 {a.get('pm25')} µg/m³: {a.get('name')}",
                            "body": f"{a.get('label')} · {a.get('area') or ''} {a.get('province') or ''}".strip()})

        h = self._call("health") or {}
        scan = h.get("scan") or {}
        if h and not scan.get("ok", True):
            out.append({"topic": "system", "key": "sys:scan", "level": 1, "title": "สแกนกล้อง กทม. หยุดทำงาน",
                        "body": f"สแกนล่าสุด {scan.get('age_s')} วินาทีก่อน (รอบที่ {scan.get('cycle')}) watchdog จะ restart ถ้ายังไม่ฟื้น"})
        err = (h.get("helmet") or {}).get("agent_error")
        if err:
            out.append({"topic": "system", "key": "sys:agent", "level": 1, "title": "AI ตรวจภาพใช้งานไม่ได้", "body": str(err)[:140]})
        disk = h.get("data_disk") or {}
        if disk.get("free_gb") is not None and disk["free_gb"] < DISK_MIN_GB:
            out.append({"topic": "system", "key": "sys:disk", "level": 1, "title": "พื้นที่ดิสก์ข้อมูลใกล้เต็ม",
                        "body": f"{disk.get('path')} เหลือ {disk['free_gb']} GB จาก {disk.get('total_gb')} GB"})
        return out

    # ------------------------------------------------------------ check loop
    def check(self, now=None):
        """One pass: diff the candidates against what was sent, push the new ones. Returns the new alerts."""
        now = now or time.time()
        fresh = []
        with self.lock:
            found = {}
            for c in self.candidates(now):
                found.setdefault(c["key"], c)    # the same event from two feeds counts once
            self.pending = {k: t for k, t in self.pending.items() if k in found}
            for c in found.values():
                wait = DEBOUNCE_SECONDS.get(c["topic"], 0)
                if wait and c["key"] not in self.sent and now - self.pending.setdefault(c["key"], now) < wait:
                    continue
                prev = self.sent.get(c["key"])
                if prev is None or c["level"] > prev["level"]:
                    fresh.append({**c, "ts": int(now)})
                    self.sent[c["key"]] = {"level": c["level"], "first": int(now), "seen": int(now)}
                else:
                    prev["seen"] = int(now)
            for k in [k for k, v in self.sent.items() if now - v["seen"] > CLEAR_SECONDS]:
                del self.sent[k]
            self.history.extendleft(reversed(fresh))
            self.last_check = int(now)
            self._save()
        for topic in TOPICS:
            items = [a for a in fresh if a["topic"] == topic]
            if items:
                self.push(topic, *self._group(topic, items))
        return fresh

    @staticmethod
    def _group(topic, items):
        if len(items) == 1:
            return items[0]["title"], items[0]["body"]
        lines = [a["title"] for a in items[:4]] + ([f"และอีก {len(items) - 4} รายการ"] if len(items) > 4 else [])
        return f"{TOPICS[topic]} {len(items)} รายการ", "\n".join(lines)

    def announce_start(self):
        a = {"topic": "system", "key": f"sys:start:{int(time.time())}", "level": 1, "ts": int(time.time()),
             "title": "เซิร์ฟเวอร์เริ่มทำงาน", "body": "BKK StreetSmart เปิดใหม่ (restart หรือ watchdog สั่งเปิด)"}
        with self.lock:
            self.history.appendleft(a)
            self._save()
        self.push("system", a["title"], a["body"])

    def _loop(self):
        time.sleep(90)   # let the sources finish their first refresh
        self.announce_start()
        while True:
            try:
                self.check()
                self.error = None
            except Exception as e:  # noqa: BLE001
                self.error = str(e)[:200]
                print(f"[Alerts] check failed: {e}")
            time.sleep(CHECK_SECONDS)

    def start(self):
        if webpush is None:
            print("[Alerts] pywebpush not installed - alerts disabled")
            return
        threading.Thread(target=self._loop, daemon=True, name="alerts").start()

    # ------------------------------------------------------------ push
    def push(self, topic, title, body, only=None):
        """Send to every subscription that wants this topic (or just the `only` endpoint). Returns sent count."""
        if webpush is None:
            return 0
        payload = json.dumps({"title": title, "body": body, "topic": topic, "tag": topic,
                              "url": TOPIC_URL.get(topic, "/")}, ensure_ascii=False)
        with self.lock:
            targets = [s for s in self.subs if (s["endpoint"] == only if only else topic in s.get("topics", TOPICS))]
        sent, gone = 0, []
        for s in targets:
            try:
                webpush({"endpoint": s["endpoint"], "keys": s["keys"]}, payload, vapid_private_key=self.key_path,
                        vapid_claims={"sub": VAPID_SUB}, ttl=PUSH_TTL, timeout=10)
                sent += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code in (404, 410):          # the browser dropped the subscription
                    gone.append(s["endpoint"])
                else:
                    print(f"[Alerts] push failed ({code}): {str(e)[:120]}")
            except Exception as e:  # noqa: BLE001
                print(f"[Alerts] push failed: {str(e)[:120]}")
        if gone:
            with self.lock:
                self.subs = [s for s in self.subs if s["endpoint"] not in gone]
                self._save()
        return sent

    # ------------------------------------------------------------ api
    def subscribe(self, sub, topics=None, label=""):
        if not isinstance(sub, dict) or not sub.get("endpoint") or not (sub.get("keys") or {}).get("p256dh"):
            return {"ok": False, "error": "subscription ไม่ถูกต้อง"}
        topics = [t for t in (topics or TOPICS) if t in TOPICS]
        with self.lock:
            self.subs = [s for s in self.subs if s["endpoint"] != sub["endpoint"]]
            self.subs.append({"endpoint": sub["endpoint"], "keys": sub["keys"], "topics": topics,
                              "label": str(label)[:120], "created": int(time.time())})
            self._save()
        return {"ok": True, "topics": topics}

    def unsubscribe(self, endpoint):
        with self.lock:
            n = len(self.subs)
            self.subs = [s for s in self.subs if s["endpoint"] != endpoint]
            self._save()
            return {"ok": True, "removed": n - len(self.subs)}

    def test(self, endpoint=None):
        n = self.push("system", "ทดสอบการแจ้งเตือน", "ถ้าเห็นข้อความนี้ แปลว่าเครื่องนี้รับแจ้งเตือนได้แล้ว", only=endpoint)
        return {"ok": n > 0, "sent": n}

    def status(self, endpoint=None):
        with self.lock:
            mine = next((s for s in self.subs if s["endpoint"] == endpoint), None) if endpoint else None
            return {"enabled": webpush is not None, "public_key": self.public_key, "topics": TOPICS,
                    "subscribers": len(self.subs), "subscribed": bool(mine), "my_topics": mine["topics"] if mine else None,
                    "open": len(self.sent), "last_check": self.last_check, "error": self.error,
                    "check_seconds": CHECK_SECONDS}

    def recent(self, limit=50):
        with self.lock:
            return {"items": list(self.history)[:limit]}
