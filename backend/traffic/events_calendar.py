"""
Road closures and big events for the public calendar ("ปิดถนน งานใหญ่").

Feeds the server already holds (Longdo closures, BMA road-work reports, BMA traffic-centre bulletins) are
merged with events the team adds (stored in one JSON file). Each item is sorted into one bucket by its
start time in Bangkok time: ongoing, today, tomorrow or the next 7 days.
"""
import json
import logging
import math
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from backend.core import thai_regions
from backend.core.instance import BASE_DIR

log = logging.getLogger(__name__)

BKK = timezone(timedelta(hours=7))
BANGKOK = thai_regions.BANGKOK
SCOPE_PROVINCES = {"กรุงเทพมหานคร", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ", "สมุทรสาคร", "นครปฐม"}
TEAM_KINDS = ("closure", "diversion", "event", "run", "concert", "ceremony")
TEAM_MAX_EVENTS = 300
TEAM_KEEP_AFTER_END = 30 * 86400      # finished team events are pruned on write
TEAM_MAX_AHEAD = 120 * 86400          # an end time may be at most this far ahead
DISTRICTS_FILE = os.path.join(BASE_DIR, "config", "thailand_districts.geojson")
DEDUP_METERS = 300
ROAD_WORDS = re.compile("ปิด|เบี่ยง")
STOP_WORDS = {"ถนน", "ปิด", "เบี่ยง", "เบี่ยงการจราจร", "ซอย", "ช่วง", "จราจร", "การจราจร", "ซ่อม", "ก่อสร้าง",
              "แยก", "ขาเข้า", "ขาออก", "บริเวณ"}
BMA_REPORT_HOURS = 12        # a road-work report is news: taken to expire 12 h after it
BULLETIN_KEEP = 5            # long construction bulletins: only the latest few
SOURCE_KEYS = ("closures", "bma", "bulletins")

_districts = None
_districts_lock = threading.Lock()


def bangkok_districts():
    """The 50 Bangkok district names (amp_th of province code 10), read once from the district outlines."""
    global _districts
    with _districts_lock:
        if _districts is None:
            with open(DISTRICTS_FILE, encoding="utf-8") as f:
                feats = json.load(f)["features"]
            _districts = {p["amp_th"] for p in (ft["properties"] for ft in feats) if str(p["pro_code"]) == "10"}
        return _districts


def _float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _bkk_epoch(text):
    """'YYYY-MM-DD HH:MM:SS' in Bangkok time (the Longdo feed) to epoch seconds, None when missing or odd."""
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BKK).timestamp()
    except (TypeError, ValueError):
        return None


def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{name} must be a number (epoch seconds)")
    return float(v)


def _text(event, key, limit, required=False):
    v = event.get(key)
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise ValueError(f"{key} must be text")
    v = v.strip()
    if required and not v:
        raise ValueError(f"{key} is required")
    if len(v) > limit:
        raise ValueError(f"{key} is longer than {limit} characters")
    return v


def _km(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _words(title):
    return [w for w in re.split(r"[\s()\[\]\-/,.:;]+", title.lower()) if w]


def _share_word(a, b):
    """Two titles share a word: the same word of 2+ characters (not a stop word), or a 4+ character part of one
    inside the other."""
    for x in _words(a):
        for y in _words(b):
            if x in STOP_WORDS or y in STOP_WORDS:
                continue
            if x == y and len(x) >= 2:
                return True
            if min(len(x), len(y)) >= 4 and (x in y or y in x):
                return True
    return False


def _validate(event, now):
    """The team event's fields, checked. Raises ValueError with the reason."""
    if not isinstance(event, dict):
        raise ValueError("body must be a JSON object")
    title = _text(event, "title", 120, required=True)
    detail = _text(event, "detail", 600)
    place = _text(event, "place", 120)
    kind = event.get("kind")
    if kind not in TEAM_KINDS:
        raise ValueError("kind must be one of " + ", ".join(TEAM_KINDS))
    lat, lng = event.get("lat"), event.get("lng")
    if (lat is None) != (lng is None):
        raise ValueError("lat and lng must be given together")
    if lat is not None:
        lat, lng = _num(lat, "lat"), _num(lng, "lng")
        if not 5 <= lat <= 21:
            raise ValueError("lat is outside Thailand")
        if not 97 <= lng <= 106:
            raise ValueError("lng is outside Thailand")
    district = _text(event, "district", 60)
    if district and district not in bangkok_districts():
        raise ValueError("district must be one of the 50 Bangkok districts")
    start = _num(event.get("start"), "start")
    end = _num(event.get("end"), "end")
    if start >= end:
        raise ValueError("start must be before end")
    if end > now + TEAM_MAX_AHEAD:
        raise ValueError("end must be within 120 days from now")
    url = _text(event, "url", 300) or None
    if url is not None and not re.match(r"^https?://\S+$", url):
        raise ValueError("url must be an http or https link")
    return {"kind": kind, "title": title, "detail": detail, "place": place, "district": district,
            "lat": lat, "lng": lng, "start": start, "end": end, "url": url}


class EventsCalendar:
    def __init__(self, store_path, sources, now=time.time, locate=None, health=None):
        """sources: name -> callable. "closures" (Longdo), "bma" (road-work), "bulletins" (BMA bulletins).
        locate(lat, lng) -> (province, district) fills the place of items that have coordinates.
        health() -> {"closures": bool, "bma": bool, "bulletins": bool}: whether each feed has loaded and has no
        error (the feed objects' own state). A source whose call fails is never ok, whatever health says."""
        self.store_path = store_path
        self.sources = sources
        self.now = now
        self.locate = locate
        self.health = health
        self.lock = threading.Lock()
        self._warned = False

    # ---- team events file
    def _warn_once(self, msg):
        if not self._warned:
            log.warning(msg)
            self._warned = True

    def _read_store(self):
        try:
            with open(self.store_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            self._warn_once(f"team events file unreadable, treated as empty: {e}")
            return []
        if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
            self._warn_once("team events file has the wrong shape, treated as empty")
            return []
        rows = []
        for e in data:
            start, end = _float(e.get("start")), _float(e.get("end"))
            if start is None or end is None:
                self._warn_once("team events file has a row without usable start/end, row skipped")
                continue
            rows.append({"id": str(e.get("id") or ""), "source": "team", "kind": str(e.get("kind") or "event"),
                         "title": str(e.get("title") or ""), "detail": str(e.get("detail") or ""),
                         "place": str(e.get("place") or ""), "district": str(e.get("district") or ""),
                         "province": str(e.get("province") or ""), "lat": _float(e.get("lat")),
                         "lng": _float(e.get("lng")), "start": start, "end": end,
                         "url": e.get("url") or None})
        return rows

    def _write_store(self, events):
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        tmp = self.store_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.store_path)

    @staticmethod
    def _prune(events, now):
        return [e for e in events if e["end"] >= now - TEAM_KEEP_AFTER_END]

    def add(self, event):
        """Validate and store one team event; returns the stored item with its new id."""
        now = self.now()
        clean = _validate(event, now)
        province, district = "", clean["district"]
        if district:
            province = BANGKOK
        elif clean["lat"] is not None and self.locate:
            province, district = self._located(clean["lat"], clean["lng"])
        with self.lock:
            events = self._prune(self._read_store(), now)
            if len(events) >= TEAM_MAX_EVENTS:
                raise ValueError(f"too many team events (max {TEAM_MAX_EVENTS})")
            item = {"id": "team-" + secrets.token_hex(6), "source": "team", **clean,
                    "district": district, "province": province}
            events.append(item)
            self._write_store(events)
        return item

    def remove(self, event_id):
        """Delete one team event; False when no such id is stored."""
        now = self.now()
        with self.lock:
            events = self._read_store()
            kept = [e for e in events if e.get("id") != event_id]
            if len(kept) == len(events):
                return False
            self._write_store(self._prune(kept, now))
        return True

    # ---- reading
    def _located(self, lat, lng):
        try:
            prov, dist = self.locate(lat, lng)
        except Exception:
            return "", ""
        return prov or "", dist or ""

    def _source(self, key, failed):
        fn = self.sources.get(key)
        if fn is None:
            return []
        try:
            return list(fn() or [])
        except Exception as e:
            log.warning("calendar source %s failed: %s", key, e)
            failed.add(key)
            return []

    def _sources_ok(self, failed):
        """Per source: its feed is loaded with no error (health) and its call did not fail this time."""
        if self.health is None:
            health = {}
        else:
            try:
                health = dict(self.health() or {})
            except Exception as e:
                log.warning("calendar health check failed: %s", e)
                health = {k: False for k in SOURCE_KEYS}
        return {k: bool(health.get(k, True)) and k not in failed for k in SOURCE_KEYS}

    def _norm_longdo(self, e):
        lat, lng = _float(e.get("latitude")), _float(e.get("longitude"))
        return {"id": str(e.get("id") or ""), "source": "longdo", "kind": e.get("kind") or "closed",
                "title": e.get("title") or "", "detail": e.get("description") or e.get("reason") or "",
                "place": "", "district": e.get("amphoe") or "", "province": e.get("province") or "",
                "lat": lat, "lng": lng, "start": _bkk_epoch(e.get("start")), "end": _bkk_epoch(e.get("stop")),
                "url": None}

    def _norm_bma(self, e):
        start = _float(e.get("ts"))
        return {"id": f"bma-{e.get('id')}", "source": "bma", "kind": "roadwork", "title": e.get("title") or "",
                "detail": e.get("desc") or "", "place": "", "district": "", "province": BANGKOK,
                "lat": _float(e.get("lat")), "lng": _float(e.get("lng")),
                "start": start, "end": None if start is None else start + BMA_REPORT_HOURS * 3600,
                "url": e.get("url") or None}

    def _norm_bulletin(self, b):
        headline, detail = b.get("headline") or "", b.get("detail") or ""
        return {"id": f"bma_bulletin-{b.get('id')}", "source": "bma_bulletin",
                "kind": "closed" if "ปิด" in headline + detail else "diversion",
                "title": headline, "detail": detail, "place": "", "district": "", "province": BANGKOK,
                "lat": None, "lng": None, "start": None, "end": None, "url": None}

    def _gather(self, failed):
        items = [self._norm_longdo(e) for e in self._source("closures", failed) if isinstance(e, dict)]
        items += [self._norm_bma(e) for e in self._source("bma", failed) if isinstance(e, dict)]
        bulletins = [b for b in self._source("bulletins", failed)
                     if isinstance(b, dict) and ROAD_WORDS.search(f"{b.get('headline') or ''} {b.get('detail') or ''}")]
        items += [self._norm_bulletin(b) for b in bulletins[:BULLETIN_KEEP]]
        for item in items:
            if self.locate and item["lat"] is not None and (not item["province"] or not item["district"]):
                prov, dist = self._located(item["lat"], item["lng"])
                item["province"] = item["province"] or prov
                item["district"] = item["district"] or dist
        with self.lock:
            items += [dict(e) for e in self._read_store() if e.get("source") == "team"]
        return items

    @staticmethod
    def _dedup(items):
        """A BMA road-work report within 300 m of a Longdo closure, sharing a title word, is the same closure:
        the BMA one is dropped."""
        longdo = [i for i in items if i["source"] == "longdo" and i["lat"] is not None]
        drop = set()
        for b in items:
            if b["source"] != "bma" or b["lat"] is None:
                continue
            for lg in longdo:
                if _km(b["lat"], b["lng"], lg["lat"], lg["lng"]) * 1000 <= DEDUP_METERS and _share_word(b["title"], lg["title"]):
                    drop.add(id(b))
                    break
        return [i for i in items if id(i) not in drop]

    def calendar(self, scope="bkk"):
        if scope not in ("bkk", "all"):
            raise ValueError("scope must be bkk or all")
        now = self.now()
        failed = set()
        items = [i for i in self._gather(failed) if i["end"] is None or i["end"] > now]
        sources_ok = self._sources_ok(failed)
        items = self._dedup(items)
        if scope == "bkk":
            # a feed item with neither a province nor coordinates cannot be placed in Bangkok: dropped
            items = [i for i in items if i["province"] in SCOPE_PROVINCES
                     or (not i["province"] and (i["source"] == "team" or i["lat"] is not None))]

        day = datetime.fromtimestamp(now, BKK).replace(hour=0, minute=0, second=0, microsecond=0)
        at = lambda days: (day + timedelta(days=days)).timestamp()
        t0, t1, t2, t7 = at(0), at(1), at(2), at(7)
        out = {"ongoing": [], "today": [], "tomorrow": [], "week": []}
        for i in items:
            s = i["start"]
            if s is None or s < t0:
                bucket = "ongoing"
            elif s < t1:
                bucket = "today"
            elif s < t2:
                bucket = "tomorrow"
            elif s < t7:
                bucket = "week"
            else:
                continue
            out[bucket].append({k: i[k] for k in ("id", "source", "kind", "title", "detail", "place", "district",
                                                    "province", "lat", "lng", "start", "end", "url")})
        for bucket in out.values():
            bucket.sort(key=lambda i: (i["start"] is not None, i["start"] or 0, i["title"]))
        return {"updated_at": int(now), "sources_ok": sources_ok, **out}
