"""
จุดจอดรถหนีน้ำ: car parks that the BMA, a mall or a building owner has announced as open for cars fleeing a flood.

Only announced places are shown. A driver sent to a car park whose owner then turns them away stops trusting
the site, so the list is kept by hand in config/flood_parking.json from published announcements, and a spot
without a source and a link to the announcement is skipped. The file is read again when it changes (no restart).

    {"spots": [{
        "id": "central-rama9",               unique, letters / digits / - / _
        "name": "...",
        "lat": 13.75, "lng": 100.56,
        "capacity": 300,                     approximate free spaces for flood parking (optional)
        "fee": "ฟรี",                         optional
        "hours": "ตลอด 24 ชม.",                optional
        "status": "open|near_full|full",     what the owner last said (optional)
        "status_at": "2026-10-05T18:40",     Bangkok time of that status (optional)
        "until": "2026-10-09T23:59",         Bangkok time the offer ends; the spot hides itself after it (optional)
        "source": "สำนักงานเขตห้วยขวาง",       who announced it
        "source_url": "https://..."          the announcement
    }]}

Anyone can press "เต็มแล้ว" on a spot. The report shows for REPORT_MINUTES after the last press and then goes
away by itself, unless someone presses again. One press per address per spot counts (a repeat press only
renews it). Reports are kept in memory: a restart clears them, which is at most REPORT_MINUTES of reports.
"""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.core.instance import BASE_DIR

CONFIG_FILE = os.path.join(BASE_DIR, "config", "flood_parking.json")
REPORT_MINUTES = int(os.getenv("PARKING_FULL_MINUTES", "90"))
STATUS_TH = {"open": "ว่าง", "near_full": "ใกล้เต็ม", "full": "เต็ม"}
BKK_TZ = timezone(timedelta(hours=7))
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _epoch(value):
    try:
        return int(datetime.fromisoformat(str(value)).replace(tzinfo=BKK_TZ).timestamp())
    except (TypeError, ValueError):
        return None


def _clean(raw):
    """One spot from the file, or None when it lacks what the page needs (an announcement above all)."""
    try:
        sid, name = str(raw["id"]), str(raw["name"]).strip()
        lat, lng = float(raw["lat"]), float(raw["lng"])
        source, url = str(raw["source"]).strip(), str(raw["source_url"]).strip()
    except (KeyError, TypeError, ValueError):
        return None
    if not _ID.fullmatch(sid) or not name or not source or not url.startswith("https://"):
        return None
    until = _epoch(raw["until"]) if raw.get("until") else None
    if raw.get("until") and until is None:
        return None   # a mistyped end date must not keep a closed car park on the page for good
    status = raw.get("status") if raw.get("status") in STATUS_TH else None
    capacity = raw.get("capacity")
    return {"id": sid, "name": name, "lat": lat, "lng": lng,
            "capacity": int(capacity) if isinstance(capacity, (int, float)) and capacity > 0 else None,
            "fee": str(raw.get("fee") or "").strip(), "hours": str(raw.get("hours") or "").strip(),
            "status": status, "status_th": STATUS_TH.get(status), "status_at": _epoch(raw.get("status_at")) if status else None,
            "until": until, "source": source, "source_url": url}


class FloodParking:
    def __init__(self, path=CONFIG_FILE):
        self.path = path
        self.lock = threading.Lock()
        self._mtime = None
        self._spots = []
        self._reports = {}                      # spot id -> {reporter hash: ts of their last press}
        self._salt = secrets.token_bytes(16)    # reporter hashes mean nothing outside this process

    def spots(self):
        """The announced spots whose offer has not ended, re-read when the file changed."""
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return []
        with self.lock:
            if mtime != self._mtime:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        raw = json.load(f).get("spots") or []
                except (OSError, ValueError, AttributeError) as e:
                    print(f"[FloodParking] cannot read {self.path}: {e}")
                    raw = []
                spots = [s for s in map(_clean, raw) if s]
                if len(spots) < len(raw):
                    print(f"[FloodParking] skipped {len(raw) - len(spots)} spot(s) without id, place, source or https link")
                self._spots, self._mtime = spots, mtime
            now = time.time()
            return [s for s in self._spots if not s["until"] or s["until"] > now]

    def _live_reports(self, sid, now):
        """{reporter: ts} of presses younger than REPORT_MINUTES (older ones dropped). Call under the lock."""
        live = {k: t for k, t in self._reports.get(sid, {}).items() if now - t < REPORT_MINUTES * 60}
        if live:
            self._reports[sid] = live
        else:
            self._reports.pop(sid, None)
        return live

    def report_full(self, sid, reporter):
        """Count a "เต็มแล้ว" press. KeyError for an unknown spot."""
        if sid not in {s["id"] for s in self.spots()}:
            raise KeyError(sid)
        who = hashlib.sha256(self._salt + str(reporter).encode()).hexdigest()[:16]
        now = time.time()
        with self.lock:
            self._live_reports(sid, now)
            self._reports.setdefault(sid, {})[who] = now
        return self._full(sid, now)

    def _full(self, sid, now):
        with self.lock:
            live = self._live_reports(sid, now)
        if not live:
            return None
        last = max(live.values())
        return {"count": len(live), "last_ts": int(last), "until_ts": int(last + REPORT_MINUTES * 60)}

    def status(self):
        now = time.time()
        spots = [{**s, "user_full": self._full(s["id"], now)} for s in self.spots()]
        return {"spots": spots, "total": len(spots), "report_minutes": REPORT_MINUTES, "updated_at": int(now)}


flood_parking = FloodParking()
