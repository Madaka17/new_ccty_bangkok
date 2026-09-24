"""
Two early flood signals that the road sensors and ThaiWater gauges do not give:

- Traffy Fondue (publicapi.traffy.in.th): complaints Bangkok residents file with a location. The newest
  complaints have no category yet, so flood reports are picked out by wording ("น้ำท่วม", "น้ำขัง" ...).
  A burst of them in one district is water in the sois, where there is no sensor.
- Thai Meteorological Department (tmd.go.th): the numbered heavy-rain / storm warnings. The data.tmd.go.th
  WeatherWarningNews API only serves a 2022 announcement with the public key, so the warning list on the
  website is read instead. Each item carries a title, a one-paragraph summary of the regions hit and a date.

Both poll in a background thread and keep the last good answer when a fetch fails. Served by
/api/flood/reports and /api/weather/warnings, and read by alert_service.
"""
import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BKK_TZ = timezone(timedelta(hours=7))
USER_AGENT = "Mozilla/5.0 (BKK StreetSmart dashboard)"

TRAFFY_URL = "https://publicapi.traffy.in.th/share/teamchadchart/search"
TRAFFY_LIMIT = 500           # newest first; about half a day of Bangkok complaints
TRAFFY_REFRESH = 300
TRAFFY_KEEP_HOURS = 6
FLOOD_WORDS = re.compile(r"น้ำท่วม|ท่วมขัง|น้ำขัง|น้ำรอการระบาย|น้ำไม่ระบาย|ระบายน้ำไม่ทัน")
# The Traffy form appends "ความสูงระดับ<ข้อเท้า|หน้าแข้ง|เข่า|...>" to flood reports
DEPTH = re.compile(r"ความสูงระดับ\s*([^\s,]+)")

TMD_BASE = "https://www.tmd.go.th"
TMD_LIST = TMD_BASE + "/warning-and-events/warning-storm"
TMD_REFRESH = 900
TMD_KEEP_DAYS = 2
THAI_MONTHS = {m: i + 1 for i, m in enumerate(
    ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
     "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"])}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _thai_date(s):
    """'24 กันยายน 2569' -> date, or None."""
    m = re.search(r"(\d{1,2})\s+(\S+)\s+(\d{4})", s or "")
    if not m or m.group(2) not in THAI_MONTHS:
        return None
    try:
        return datetime(int(m.group(3)) - 543, THAI_MONTHS[m.group(2)], int(m.group(1))).date()
    except ValueError:
        return None


def parse_traffy(results, now=None):
    """Traffy search results -> flood reports from the last TRAFFY_KEEP_HOURS, newest first."""
    now = now or time.time()
    out = []
    for r in results or []:
        text = (r.get("description") or "").strip()
        kinds = [k for k in r.get("problem_type_abdul") or [] if k]
        if not (FLOOD_WORDS.search(text) or "น้ำท่วม" in kinds):
            continue
        try:
            ts = datetime.fromisoformat((r.get("timestamp") or "").replace("+00", "+00:00")).timestamp()
        except ValueError:
            continue
        if now - ts > TRAFFY_KEEP_HOURS * 3600:
            continue
        addr = r.get("address") or ""
        district = re.search(r"เขต\s*(\S+)", addr)
        depth = DEPTH.search(text)
        try:
            lng, lat = (float(c) for c in r.get("coords") or [])
        except (TypeError, ValueError):
            lng = lat = None
        out.append({"id": r.get("ticket_id"), "ts": int(ts), "district": district.group(1) if district else None,
                    "address": addr, "state": r.get("state"), "depth": depth.group(1) if depth else None,
                    "text": text[:300], "lat": lat, "lng": lng, "photo": r.get("photo_url") or None,
                    "url": f"https://share.traffy.in.th/teamchadchart/{r.get('ticket_id')}"})
    out.sort(key=lambda i: -i["ts"])
    return out


def parse_tmd(page):
    """TMD warning list page -> [{title, series, summary, date, url, bkk}], newest first."""
    out = []
    for block in re.findall(r'<div class="link-list-content">(.*?)</div>\s*</div>', page, re.S):
        link = re.search(r'href="(/warning-and-events/warning-storm/[^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        title = _text(link.group(2))
        rest = _text(block[link.end():])
        date_s = rest.split("วันที่ข้อมูล:")[-1] if "วันที่ข้อมูล:" in rest else ""
        summary = rest.split("วันที่ข้อมูล:")[0].strip(" |")
        day = _thai_date(date_s)
        out.append({"title": title,
                    # one storm / rain event keeps its name across issues; the "(มีผลกระทบ...)" dates
                    # and "ฉบับที่ N (x/yyyy)" change with every issue
                    "series": re.sub(r"\s*(\(|ฉบับที่).*$", "", title),
                    "summary": summary, "date": day.isoformat() if day else None,
                    "url": TMD_BASE + urllib.parse.quote(html.unescape(link.group(1))),
                    "bkk": "กรุงเทพ" in title + summary})
    return out


class _Poller:
    name = "?"
    refresh_seconds = 600

    def __init__(self):
        self.lock = threading.Lock()
        self.items = []
        self.updated_at = None
        self.error = None

    def fetch(self):
        raise NotImplementedError

    def refresh(self):
        items = self.fetch()
        with self.lock:
            self.items, self.updated_at, self.error = items, int(time.time()), None
        print(f"[{self.name}] {len(items)} items")

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001 - keep the last good answer
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[{self.name}] refresh error: {e}")
            time.sleep(self.refresh_seconds)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name=self.name).start()

    def status(self):
        with self.lock:
            return {"updated_at": self.updated_at, "error": self.error, "total": len(self.items),
                    "items": list(self.items)}


class TraffyFloodReports(_Poller):
    name = "Traffy"
    refresh_seconds = TRAFFY_REFRESH

    def fetch(self):
        data = json.loads(_get(f"{TRAFFY_URL}?limit={TRAFFY_LIMIT}", timeout=60))
        return parse_traffy(data.get("results"))


class TmdWarnings(_Poller):
    name = "TMD"
    refresh_seconds = TMD_REFRESH

    def fetch(self):
        return parse_tmd(_get(TMD_LIST))

    def status(self):
        st = super().status()
        since = (datetime.now(BKK_TZ) - timedelta(days=TMD_KEEP_DAYS)).date().isoformat()
        st["active"] = [w for w in st["items"] if w["date"] and w["date"] >= since]
        return st


traffy_reports = TraffyFloodReports()
tmd_warnings = TmdWarnings()
