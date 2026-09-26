"""
Flood signals that the road sensors and ThaiWater gauges do not give:

- Traffy Fondue (publicapi.traffy.in.th): complaints Bangkok residents file with a location. The newest
  complaints have no category yet, so flood reports are picked out by wording ("น้ำท่วม", "น้ำขัง" ...).
  A burst of them in one district is water in the sois, where there is no sensor.
- Thai Meteorological Department (tmd.go.th): the numbered heavy-rain / storm warnings. The data.tmd.go.th
  WeatherWarningNews API only serves a 2022 announcement with the public key, so the warning list on the
  website is read instead. Each item carries a title, a one-paragraph summary of the regions hit and a date.

- Department of Highways HDMS (hdms.doh.go.th) and JS100 radio (js100.com): flooded highways and roads
  in Bangkok and vicinity, for the flood report list. See parse_hdms / parse_js100.

All poll in a background thread and keep the last good answer when a fetch fails. Served by
/api/flood/reports, /api/flood/hdms, /api/flood/js100 and /api/weather/warnings; Traffy and TMD are
also read by alert_service.
"""
import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request
import zlib
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

# Department of Highways disaster centre (hdms.doh.go.th/dashboard): the public dashboard's JSON, open
# and closed tickets on highways. Only floods (incident_type_id 1) in Bangkok and vicinity are kept.
HDMS_URL = "https://hdms.doh.go.th/internal-api/public/dashboard?start={start}&end={end}"
# The dashboard sends every imageList empty; the photos come with the ticket's own public detail
HDMS_DETAIL_URL = "https://hdms.doh.go.th/internal-api/public/detail/{case_id}"
HDMS_PHOTO_RECHECK = 1800    # an open ticket without photos is asked again after this long
HDMS_MAX_PHOTOS = 4
HDMS_REFRESH = 600
HDMS_DAYS = 7                # a flood stays open for days; 7 days of tickets is ~1.3 MB
HDMS_FLOOD_TYPE = 1
ENDED_KEEP_HOURS = 3         # a closed ticket still shows this long, as "ended" (as the Longdo reports)
BKK_VICINITY = ("กรุงเทพมหานคร", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ", "สมุทรสาคร", "นครปฐม")

# JS100 radio traffic news (js100.com/en/site/traffic): the newest 50 items as HTML, text and time only,
# no location. The list runs a day or more behind the station's social feeds, so 48 h are kept.
JS100_URL = "https://www.js100.com/en/site/traffic"
JS100_REFRESH = 600
JS100_KEEP_HOURS = 48
# JS100 is a Bangkok station; items elsewhere name the province (or Pattaya), items here name a road.
# ตาก and เลย need the จ. prefix: "สะพานตากสิน", "ช่วงเลย..." are Bangkok text.
OTHER_PROVINCES = re.compile(
    r"(?:จ\.|จังหวัด)\s?(?:ตาก|เลย)|"
    "พัทยา|กระบี่|กาญจนบุรี|กาฬสินธุ์|กำแพงเพชร|ขอนแก่น|จันทบุรี|ฉะเชิงเทรา|ชลบุรี|ชัยนาท|ชัยภูมิ|ชุมพร|เชียงราย|"
    "เชียงใหม่|ตรัง|ตราด|นครนายก|นครพนม|นครราชสีมา|นครศรีธรรมราช|นครสวรรค์|นราธิวาส|น่าน|บึงกาฬ|บุรีรัมย์|"
    "ประจวบคีรีขันธ์|ปราจีนบุรี|ปัตตานี|อยุธยา|พะเยา|พังงา|พัทลุง|พิจิตร|พิษณุโลก|เพชรบุรี|เพชรบูรณ์|แพร่|ภูเก็ต|"
    "มหาสารคาม|มุกดาหาร|แม่ฮ่องสอน|ยโสธร|ยะลา|ร้อยเอ็ด|ระนอง|ระยอง|ราชบุรี|ลพบุรี|ลำปาง|ลำพูน|ศรีสะเกษ|"
    "สกลนคร|สงขลา|สตูล|สมุทรสงคราม|สระแก้ว|สระบุรี|สิงห์บุรี|สุโขทัย|สุพรรณบุรี|สุราษฎร์ธานี|สุรินทร์|หนองคาย|"
    "หนองบัวลำภู|อ่างทอง|อำนาจเจริญ|อุดรธานี|อุตรดิตถ์|อุทัยธานี|อุบลราชธานี")
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


def parse_hdms_photos(image_list):
    """HDMS imageList -> [{url, thumb}], images only, at most HDMS_MAX_PHOTOS."""
    out = []
    for f in image_list or []:
        url = (f.get("file_path") or "").strip()
        if f.get("file_type", "image") == "image" and url.startswith("https://"):
            thumb = (f.get("file_thumbnail") or "").strip()
            out.append({"url": url, "thumb": thumb if thumb.startswith("https://") else url})
    return out[:HDMS_MAX_PHOTOS]


def parse_hdms(tickets, now=None):
    """HDMS dashboard tickets -> floods in Bangkok and vicinity, open or closed in the last
    ENDED_KEEP_HOURS, newest first. The reporter's name and phone are not passed on."""
    now = now or time.time()
    out = []
    for t in tickets or []:
        if t.get("incident_type_id") != HDMS_FLOOD_TYPE or t.get("province") not in BKK_VICINITY:
            continue
        try:
            ts = datetime.fromisoformat(t["start_date"]).timestamp()
            end = datetime.fromisoformat(t["end_date"]).timestamp() if t.get("end_date") else None
        except (KeyError, TypeError, ValueError):
            continue
        if end and now - end > ENDED_KEEP_HOURS * 3600:
            continue
        try:
            lat, lng = float(t["latitude"]), float(t["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lng = None
        road = f"ทล.{int(t['road_code'])}" if (t.get("road_code") or "").isdigit() else ""
        km = f"กม.{t['km_start']}" if t.get("km_start") else ""
        level = (t.get("flood_level") or "").strip()
        out.append({"id": f"hdms-{t.get('gid')}", "case_id": t.get("case_id") or None,
                    "photos": parse_hdms_photos(t.get("imageList")), "ts": int(ts), "end_ts": int(end) if end else None,
                    "active": end is None, "title": (t.get("case_name") or "น้ำท่วม").strip(),
                    "place": " ".join(x for x in (road, t.get("section_name") or "", km) if x),
                    "province": t.get("province"), "amphoe": t.get("amphoe") or None,
                    "depth_cm": level or None, "lane_closure": bool(t.get("lane_closure")),
                    "closure": t.get("road_closure_text") or None,
                    "cause": (t.get("cause_of_accident") or "").strip() or None,
                    "relief": (t.get("initial_relief") or "").strip() or None,
                    "depot": t.get("depot_name") or None, "lat": lat, "lng": lng})
    out.sort(key=lambda i: -i["ts"])
    return out


def parse_js100(page, now=None):
    """JS100 traffic news page -> flood items of the last JS100_KEEP_HOURS outside other provinces, newest first."""
    now = now or time.time()
    out = []
    for when, body in re.findall(r"<li>\s*<h4>(.*?)</h4>(.*?)</li>", page, re.S):
        text = _text(body)
        if not FLOOD_WORDS.search(text) or OTHER_PROVINCES.search(text):
            continue
        day = _thai_date(when)
        hm = re.search(r"(\d{1,2}):(\d{2})", when)
        if not day or not hm:
            continue
        ts = datetime(day.year, day.month, day.day, int(hm.group(1)), int(hm.group(2)), tzinfo=BKK_TZ).timestamp()
        if now - ts > JS100_KEEP_HOURS * 3600:
            continue
        out.append({"id": f"js100-{zlib.crc32(text.encode())}", "ts": int(ts), "text": text[:400]})
    out.sort(key=lambda i: -i["ts"])
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


class HdmsFloods(_Poller):
    name = "HDMS"
    refresh_seconds = HDMS_REFRESH

    def fetch(self):
        today = datetime.now(BKK_TZ).date()
        url = HDMS_URL.format(start=today - timedelta(days=HDMS_DAYS), end=today)
        items = parse_hdms(json.loads(_get(url, timeout=60)))
        self._add_photos(items)
        return items

    def _add_photos(self, items):
        """Photos from each ticket's public detail, kept per case_id: a closed ticket is asked once,
        an open one without photos again after HDMS_PHOTO_RECHECK (photos are often added later)."""
        from concurrent.futures import ThreadPoolExecutor
        cache = self.__dict__.setdefault("_photos", {})   # case_id -> (asked_at, photos)
        now = time.time()

        def stale(i):
            got = cache.get(i["case_id"])
            return not got or (i["active"] and not got[1] and now - got[0] > HDMS_PHOTO_RECHECK)

        def ask(case_id):
            try:
                detail = json.loads(_get(HDMS_DETAIL_URL.format(case_id=urllib.parse.quote(case_id)), timeout=20))
                return case_id, parse_hdms_photos(detail.get("imageList"))
            except Exception as e:  # noqa: BLE001 - no photos this round, asked again next refresh
                print(f"[{self.name}] detail {case_id}: {e}")
                return case_id, None

        todo = [i["case_id"] for i in items if i["case_id"] and not i["photos"] and stale(i)]
        if todo:
            with ThreadPoolExecutor(4) as ex:
                for case_id, photos in ex.map(ask, todo):
                    if photos is not None:
                        cache[case_id] = (now, photos)
        for i in items:
            if not i["photos"] and i["case_id"] in cache:
                i["photos"] = cache[i["case_id"]][1]
        keep = {i["case_id"] for i in items}
        for case_id in [c for c in cache if c not in keep]:
            del cache[case_id]


class Js100Floods(_Poller):
    name = "JS100"
    refresh_seconds = JS100_REFRESH

    def fetch(self):
        return parse_js100(_get(JS100_URL))


traffy_reports = TraffyFloodReports()
tmd_warnings = TmdWarnings()
hdms_floods = HdmsFloods()
js100_floods = Js100Floods()
