"""
Live event feed from the BMA traffic control centre (cpudapp.bangkok.go.th/bmatraffic).

The event page is a classic ASP.NET page: a cookie-bound session, an HTML grid
of the latest reports (mostly flooded roads during the rainy season) and a
detail page per event with coordinates. This module polls the list every
minute, fetches details for unseen events once and keeps them on disk.
"""
import html
import http.cookiejar
import json
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
CACHE_FILE = os.path.join(DATA_DIR, "cache", "bma_events.json")
BMA_BASE = "https://cpudapp.bangkok.go.th/bmatraffic/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BKK-Traffic-CCTV/2.0"
BKK_TZ = timezone(timedelta(hours=7))

POLL_SECONDS = 60
PAGES = 2            # 10 events per page
MAX_KEEP = 200
DETAIL_TIMEOUT = 20

KINDS = (
    ("flood", ("น้ำท่วม", "น้ำขัง", "น้ำรอระบาย")),
    ("accident", ("อุบัติเหตุ", "รถชน", "รถเสีย", "รถคว่ำ")),
    ("fire", ("ไฟไหม้", "เพลิงไหม้", "ไฟฟ้าลัดวงจร")),
    ("roadwork", ("ปิดการจราจร", "ปิดเบี่ยง", "เบี่ยงการจราจร", "ก่อสร้าง", "ซ่อม")),
    ("tree", ("ต้นไม้ล้ม", "ต้นไม้หัก", "ป้ายล้ม")),
)

_CARD_RE = re.compile(
    r'<td class="link-news">.*?<img src="([^"]*)".*?<div class="title">(.*?)</div>\s*<div class="desc">(.*?)</div>'
    r'.*?event-detail\.aspx\?id=(\d+)', re.S)
_THAI_DT_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2})[.:](\d{2})")
_LAT_RE = re.compile(r'DetailContent_lbllatitude">[^<]*?(-?\d+\.\d+)')
_LNG_RE = re.compile(r'DetailContent_lbllongitude">[^<]*?(-?\d+\.\d+)')
_ITEM_RE = re.compile(r'DetailContent_lblItem">(.*?)</span>', re.S)
_REF_RE = re.compile(r'DetailContent_lblRef">(.*?)</span>', re.S)
_BULLETIN_RE = re.compile(
    r'headline:\s*"(.*?)",\s*detail:\s*"(.*?)",\s*runimg:\s*"(.*?)",\s*id:\s*"(\d+)",.*?refer:\s*"(.*?)"', re.S)


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def _kind(title):
    for kind, words in KINDS:
        if any(w in title for w in words):
            return kind
    return "other"


def _parse_thai_dt(text):
    """'15/09/2569 19.54 น.' -> epoch (Buddhist year)."""
    m = _THAI_DT_RE.search(text or "")
    if not m:
        return None
    d, mo, y, h, mi = (int(x) for x in m.groups())
    if y > 2400:
        y -= 543
    try:
        return int(datetime(y, mo, d, h, mi, tzinfo=BKK_TZ).timestamp())
    except ValueError:
        return None


class BMAEventFeed:
    def __init__(self):
        self.lock = threading.Lock()
        self.events = {}       # id -> event dict
        self.bulletins = []    # ticker items on the page (weather report, road closures)
        self.updated_at = None
        self.error = None
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._load_cache()

    # ------------------------------------------------------------ persistence
    def _load_cache(self):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.events = {e["id"]: e for e in data.get("events", [])}
            self.bulletins = data.get("bulletins", [])
        except Exception:
            pass

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"events": self._sorted()[:MAX_KEEP], "bulletins": self.bulletins}, f, ensure_ascii=False)
        except Exception as e:
            print(f"[BMA] cache save failed: {e}")

    # ------------------------------------------------------------ http
    def _fetch(self, path, timeout=30):
        req = urllib.request.Request(BMA_BASE + path, headers={"User-Agent": USER_AGENT, "Accept-Language": "th"})
        with self._opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "ignore")

    def _fetch_page(self, path):
        # Without a session cookie the site bounces to a 404; hitting index.aspx first issues one
        try:
            body = self._fetch(path)
            if 'id="news-list"' in body or "DetailContent" in body:
                return body
        except Exception:
            pass
        self._fetch("index.aspx")
        return self._fetch(path)

    # ------------------------------------------------------------ parsing
    def _parse_list(self, body):
        found = []
        for img, title, desc, eid in _CARD_RE.findall(body):
            title, desc = _clean(title), _clean(desc)
            found.append({
                "id": eid,
                "title": title,
                "desc": desc,
                "kind": _kind(title + " " + desc),
                "ts": _parse_thai_dt(desc),
                "image": BMA_BASE + img.lstrip("/").replace("bmatraffic/", "", 1) if img else None,
                "url": f"{BMA_BASE}event-detail.aspx?id={eid}",
            })
        return found

    def _parse_bulletins(self, body):
        out = []
        for headline, detail, img, bid, refer in _BULLETIN_RE.findall(body):
            out.append({
                "id": bid,
                "headline": _clean(headline),
                "detail": _clean(detail),
                "image": BMA_BASE + img if img else None,
                "source": _clean(refer),
            })
        return out

    def _fetch_detail(self, event):
        try:
            body = self._fetch_page(f"event-detail.aspx?id={event['id']}")
        except Exception as e:
            print(f"[BMA] detail {event['id']}: {e}")
            return event
        lat, lng = _LAT_RE.search(body), _LNG_RE.search(body)
        item, ref = _ITEM_RE.search(body), _REF_RE.search(body)
        if lat and lng:
            event["lat"], event["lng"] = float(lat.group(1)), float(lng.group(1))
        if item:
            event["desc"] = _clean(item.group(1))
            event["ts"] = _parse_thai_dt(event["desc"]) or event.get("ts")
        if ref:
            event["source"] = _clean(ref.group(1))
        event["detailed"] = True
        return event

    # ------------------------------------------------------------ polling
    def refresh(self):
        listed = []
        bulletins = None
        for page in range(1, PAGES + 1):
            body = self._fetch_page("event.aspx" if page == 1 else f"event.aspx?page={page}")
            listed += self._parse_list(body)
            if page == 1:
                bulletins = self._parse_bulletins(body)
        if not listed:
            raise RuntimeError("no events parsed")
        with self.lock:
            fresh = [e for e in listed if e["id"] not in self.events or not self.events[e["id"]].get("detailed")]
        for e in fresh:
            self._fetch_detail(e)
        with self.lock:
            for e in listed:
                known = self.events.get(e["id"], {})
                self.events[e["id"]] = {**known, **e} if e.get("detailed") else {**e, **known}
            if bulletins:
                self.bulletins = bulletins
            self.updated_at = int(time.time())
            self.error = None
            # keep memory bounded
            for stale in self._sorted()[MAX_KEEP:]:
                self.events.pop(stale["id"], None)
        self._save_cache()
        return len(fresh)

    def _loop(self):
        while True:
            try:
                n = self.refresh()
                if n:
                    print(f"[BMA] {n} new event(s)")
            except Exception as e:
                with self.lock:
                    self.error = str(e)
                print(f"[BMA] refresh failed: {e}")
            time.sleep(POLL_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="bma-events").start()

    # ------------------------------------------------------------ api
    def _sorted(self):
        return sorted(self.events.values(), key=lambda e: (e.get("ts") or 0, int(e["id"])), reverse=True)

    def get(self, kind=None, hours=24, limit=60):
        cutoff = time.time() - hours * 3600
        with self.lock:
            items = [e for e in self._sorted() if (e.get("ts") or 0) >= cutoff and (not kind or e.get("kind") == kind)]
            counts = {}
            for e in self.events.values():
                if (e.get("ts") or 0) >= cutoff:
                    counts[e.get("kind", "other")] = counts.get(e.get("kind", "other"), 0) + 1
            return {
                "updated_at": self.updated_at,
                "poll_seconds": POLL_SECONDS,
                "error": self.error,
                "counts": counts,
                "items": items[:limit],
                "bulletins": list(self.bulletins),
            }


bma_feed = BMAEventFeed()
