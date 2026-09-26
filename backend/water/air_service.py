"""PM2.5 / AQI for Bangkok and the surrounding provinces.

Sources, both official and keyless:
- AirBKK (BMA Air Quality & Noise Management Division): the ~86 BMA stations, hourly.
- Air4Thai (Pollution Control Department): the PCD stations. Its main feed carries 24 h means,
  so the latest hourly value comes from getHistoryData; the 24 h mean is kept as `pm25_24h`.
  Air4Thai also relays the BMA stations (ids "bkp*"); those are skipped while AirBKK has data,
  and used as the fallback when it has none.

All values are hourly PM2.5, so the map shows what the air is now rather than a day's average.
Refreshed every 10 minutes. Each source keeps its last good snapshot, so one feed failing never
blanks the other.
"""
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

AIRBKK_URL = "https://stations.airbkk.com/api/web/data"
AIR4THAI_URL = "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
AIR4THAI_HOURLY = "https://air4thai.pcd.go.th/forweb/getHistoryData.php"
REFRESH_SECONDS = 600
MAX_AGE_H = 6  # a station whose last reading is older than this is offline; drop it
BBOX = (13.3, 100.1, 14.3, 101.1)  # min lat, min lon, max lat, max lon
BKK_TZ = timezone(timedelta(hours=7))

SOURCES = {"bma": "AirBKK (กทม.)", "pcd": "Air4Thai (คพ.)"}

# Thai AQI bands (PCD): colour id from the feed -> level used by the UI
LEVELS = {
    "1": {"level": "very_good", "label": "ดีมาก", "color": "#3BA0FF"},
    "2": {"level": "good", "label": "ดี", "color": "#4CC74A"},
    "3": {"level": "moderate", "label": "ปานกลาง", "color": "#FFD400"},
    "4": {"level": "unhealthy", "label": "เริ่มมีผลต่อสุขภาพ", "color": "#FF8C00"},
    "5": {"level": "very_unhealthy", "label": "มีผลต่อสุขภาพ", "color": "#E3272C"},
}
# PCD 2023 PM2.5 breakpoints: (conc lo, conc hi, index lo, index hi)
_TH_BP = [(0.0, 15.0, 0, 25), (15.1, 25.0, 26, 50), (25.1, 37.5, 51, 100), (37.6, 75.0, 101, 200), (75.1, 500.0, 201, 500)]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else f


def _pm25_band(v):
    """Thai PM2.5 AQI bands (µg/m³, 24 h): 0-15 / 15.1-25 / 25.1-37.5 / 37.6-75 / >75."""
    if v is None:
        return None
    if v <= 15:
        return "1"
    if v <= 25:
        return "2"
    if v <= 37.5:
        return "3"
    if v <= 75:
        return "4"
    return "5"


def _pm25_aqi(v):
    c = round(v, 1)
    for lo, hi, ilo, ihi in _TH_BP:
        if c <= hi:
            return round((ihi - ilo) / (hi - lo) * (max(c, lo) - lo) + ilo)
    return 500


def _parse_local(s):
    """'YYYY-MM-DD HH:MM[:SS]' in Bangkok time -> epoch seconds."""
    try:
        return int(datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M").replace(tzinfo=BKK_TZ).timestamp())
    except (TypeError, ValueError):
        return None


def _get(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _item(source, sid, name, area, province, lat, lon, pm25, pm10, ts, now, extra=None):
    """One station in the shape the UI and chat read; None if it is outside the area or offline."""
    if pm25 is None or ts is None or lat is None or lon is None:
        return None
    if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
        return None
    if not (-3600 <= now - ts <= MAX_AGE_H * 3600):
        return None
    lv = LEVELS[_pm25_band(pm25)]
    aqi = _pm25_aqi(pm25)
    it = {
        "id": f"{source}:{sid}",
        "source": source,
        "source_label": SOURCES[source],
        "name": (name or "").strip(),
        "area": (area or "").strip(),
        "province": (province or "").strip().replace("กรุงเทพฯ", "กรุงเทพมหานคร"),
        "lat": lat, "lng": lon,
        "pm25": round(pm25, 1),
        "pm25_aqi": aqi,
        "aqi": aqi,
        "aqi_param": "PM25",
        "pm10": round(pm10, 1) if pm10 is not None else None,
        "level": lv["level"], "label": lv["label"], "color": lv["color"],
        "ts": ts,
    }
    if extra:
        it.update(extra)
    return it


def _load_airbkk(now):
    raw = _get(AIRBKK_URL, {"message": "Request data"})
    rows = raw.get("message") if isinstance(raw, dict) else raw
    items = []
    for r in rows if isinstance(rows, list) else []:
        it = _item("bma", r.get("MeasIndex"), r.get("Area"), r.get("District"), "กรุงเทพมหานคร",
                   _num(r.get("Lat")), _num(r.get("Long")), _num(r.get("PM2.5")), _num(r.get("PM10")),
                   _parse_local(r.get("DateTime")), now,
                   {"station_type": "ริมถนน" if str(r.get("Type")) == "11" else "พื้นที่ทั่วไป"})
        if it:
            items.append(it)
    return items


def _load_air4thai(now, skip_bma):
    data = _get(AIR4THAI_URL)
    stations = []
    for s in data.get("stations") or []:
        if skip_bma and str(s.get("stationID") or "").startswith("bkp"):
            continue
        try:
            lat, lon = float(s["lat"]), float(s["long"])
        except (KeyError, TypeError, ValueError):
            continue
        if BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]:
            stations.append((s, lat, lon))
    if not stations:
        return []

    hourly = {}
    since = datetime.fromtimestamp(now - MAX_AGE_H * 3600, BKK_TZ)
    today = datetime.fromtimestamp(now, BKK_TZ)
    q = (f"stationID={','.join(s['stationID'] for s, _, _ in stations)}&param=PM25,PM10&type=hr"
         f"&sdate={since:%Y-%m-%d}&edate={today:%Y-%m-%d}&stime={since:%H}&etime=23")
    try:
        for st in _get(f"{AIR4THAI_HOURLY}?{q}").get("stations") or []:
            rows = [r for r in st.get("data") or [] if (r.get("PM25") or 0) > 0]  # 0 / null = sensor gap
            if rows:
                hourly[st["stationID"]] = rows[-1]
    except Exception as e:
        print(f"[Air] Air4Thai hourly failed, using 24 h means: {e}")

    items = []
    for s, lat, lon in stations:
        last = s.get("AQILast") or {}
        pm24 = _num((last.get("PM25") or {}).get("value"))
        hr = hourly.get(s["stationID"])
        if hr:
            pm25, pm10, ts = _num(hr.get("PM25")), _num(hr.get("PM10")), _parse_local(hr.get("DATETIMEDATA"))
        else:
            pm25, pm10 = pm24, _num((last.get("PM10") or {}).get("value"))
            ts = _parse_local(f"{last.get('date')} {last.get('time')}")
        area = (s.get("areaTH") or "").split(",")
        it = _item("pcd", s.get("stationID"), s.get("nameTH"), area[0], area[-1], lat, lon, pm25, pm10, ts, now,
                   {"pm25_24h": pm24})
        if it:
            items.append(it)
    return items


class AirService:
    def __init__(self):
        self.lock = threading.Lock()
        self.by_source = {}  # source -> last good list of items
        self.items = []
        self.updated_at = None
        self.source_ts = None
        self.error = None
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.thread.start()

    def refresh(self):
        now = int(time.time())
        errors = []
        with self.lock:
            by_source = dict(self.by_source)
        try:
            by_source["bma"] = _load_airbkk(now)
        except Exception as e:
            errors.append(f"AirBKK: {e}")
        try:
            by_source["pcd"] = _load_air4thai(now, skip_bma=bool(by_source.get("bma")))
        except Exception as e:
            errors.append(f"Air4Thai: {e}")

        items = [it for src in by_source.values() for it in src]
        items.sort(key=lambda i: -i["pm25"])
        latest = max((i["ts"] for i in items), default=None)
        with self.lock:
            self.by_source = by_source
            self.items = items
            self.updated_at = now
            self.source_ts = latest
            self.error = "; ".join(errors) or None
        counts = ", ".join(f"{k} {len(v)}" for k, v in by_source.items())
        print(f"[Air] {len(items)} stations ({counts}), max PM2.5 {items[0]['pm25'] if items else '-'} µg/m³")
        if len(errors) == len(SOURCES):
            raise RuntimeError(self.error)

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as e:
                with self.lock:
                    self.error = str(e)
                print(f"[Air] refresh error: {e}")
            time.sleep(REFRESH_SECONDS)

    def status(self):
        with self.lock:
            items = list(self.items)
            counts = {}
            for it in items:
                counts[it["level"]] = counts.get(it["level"], 0) + 1
            sources = {k: {"label": SOURCES[k], "count": len(v)} for k, v in self.by_source.items()}
            avg = round(sum(i["pm25"] for i in items) / len(items), 1) if items else None
            return {"updated_at": self.updated_at, "source_ts": self.source_ts, "error": self.error,
                    "total": len(items), "avg_pm25": avg, "counts": counts, "sources": sources, "items": items}


air = AirService()
