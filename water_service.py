"""
Water level / flood outlook for Bangkok and the surrounding provinces.

Sources (all public, read-only):
- ThaiWater / HII (twa.thaiwater.net): river + canal telemetry, official 7-day
  water level forecast for key Chao Phraya stations, sea tide forecast, BMA
  flood-road sensors, heavy rain warnings.
- A small local tidal-harmonic model gives a 48 h outlook for stations that have
  no official forecast (most Bangkok stations sit in the tidal reach of the
  Chao Phraya, so trend + tide explains most of the short-term movement).
"""
import json
import math
import os
from instance import DATA_DIR
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np

TWA_API = "https://twa-api-public.thaiwater.net"
# National Thai Water portal (nationalthaiwater.onwr.go.th) backend: no key needed, one big
# snapshot of every station in the country refreshed by HII every hour
NTW_API = "https://api-v3.thaiwater.net/api/v1/thaiwater30"
NTW_TTL = 600
# Upstream reservoirs that decide how much water reaches the lower Chao Phraya
NTW_DAMS = ["ภูมิพล", "สิริกิติ์", "แควน้อยบำรุงแดน", "ป่าสักชลสิทธิ์", "ขุนด่านปราการชล"]
# Anonymous key that twa.thaiwater.net ships to every browser; override with TWA_API_KEY if it rotates
TWA_API_KEY = os.getenv("TWA_API_KEY", "TPSXrHRvTHeVT2Lygq6YeTqqAm4xZ72x")
USER_AGENT = "BKK-Traffic-CCTV/2.0 (personal dashboard)"
BKK_TZ = timezone(timedelta(hours=7))

# Bangkok + the five surrounding provinces (ThaiWater province codes)
METRO_PROVINCES = {"10": "กรุงเทพมหานคร", "11": "สมุทรปราการ", "12": "นนทบุรี", "13": "ปทุมธานี", "73": "นครปฐม", "74": "สมุทรสาคร"}
# Stations with an official HII forecast that drive Bangkok's river level (upstream -> downstream)
OFFICIAL_FORECAST_STATIONS = {
    1143: {"name": "ท่าเรือ (ป่าสัก)", "province": "พระนครศรีอยุธยา"},
    1142: {"name": "พระนครศรีอยุธยา", "province": "พระนครศรีอยุธยา"},
    1132: {"name": "สะพานนวลฉวี", "province": "นนทบุรี"},
}
# Sea tide forecast points that matter for the Chao Phraya reach
TIDE_STATIONS = ["N01", "N02", "N03", "N04", "N05"]
# Watch zones for the rain / storm outlook (Open-Meteo, no key needed)
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
WEATHER_ZONES = [
    {"id": "bkk_inner", "name": "กทม. ชั้นใน", "areas": "ปทุมวัน ดินแดง ห้วยขวาง ราชเทวี", "lat": 13.745, "lng": 100.535},
    {"id": "bkk_north", "name": "กทม. เหนือ", "areas": "ดอนเมือง หลักสี่ สายไหม บางเขน", "lat": 13.905, "lng": 100.605},
    {"id": "bkk_east", "name": "กทม. ตะวันออก", "areas": "ลาดกระบัง มีนบุรี หนองจอก คลองสามวา", "lat": 13.780, "lng": 100.800},
    {"id": "bkk_south", "name": "กทม. ใต้", "areas": "บางนา พระโขนง สวนหลวง ประเวศ", "lat": 13.670, "lng": 100.620},
    {"id": "bkk_thon", "name": "ฝั่งธนบุรี", "areas": "บางแค ภาษีเจริญ บางขุนเทียน ตลิ่งชัน", "lat": 13.720, "lng": 100.400},
    {"id": "nonthaburi", "name": "นนทบุรี", "areas": "เมืองนนท์ ปากเกร็ด บางบัวทอง", "lat": 13.860, "lng": 100.510},
    {"id": "pathum", "name": "ปทุมธานี", "areas": "รังสิต คลองหลวง ลำลูกกา", "lat": 14.020, "lng": 100.600},
    {"id": "samut_prakan", "name": "สมุทรปราการ", "areas": "เมืองสมุทรปราการ บางพลี พระประแดง", "lat": 13.600, "lng": 100.600},
]
STORM_CODES = {95, 96, 99}   # WMO thunderstorm codes

SUMMARY_TTL = 60
FORECAST_TTL = 600
OBS_DAYS = 3        # history used for the local model
EST_HOURS = 48      # local outlook horizon
# Tidal constituents (period in hours): M2, S2, N2, K1, O1
TIDE_PERIODS_H = (12.4206, 12.0, 12.6583, 23.9345, 25.8193)


# ---------------------------------------------------------------- api key discovery
TWA_SITE = "https://twa.thaiwater.net/th"
KEY_FILE = os.path.join(DATA_DIR, "cache", "twa_key.json")
KEY_RETRY_SECONDS = 300      # how long to wait between discovery attempts while no key works
_KEY_RE = re.compile(r'"x-api-key"\s*[:=]\s*"([A-Za-z0-9_\-]{16,128})"')
_CHUNK_RE = re.compile(r"/_next/static/chunks/[^\"']+\.js")


class _KeyStore:
    """Holds the anonymous key twa.thaiwater.net ships in its JS bundle.

    Order: env TWA_API_KEY > last key that worked (cache/twa_key.json) > built-in default.
    When the API answers 401 the key has rotated: scan the site's JS chunks for a new one.
    If none is found the scan is retried in the background every KEY_RETRY_SECONDS until it is."""

    def __init__(self):
        self.lock = threading.Lock()
        self.key = os.getenv("TWA_API_KEY") or self._load() or TWA_API_KEY
        self.last_scan = 0.0
        self.scanning = False
        self.broken = False   # True while the current key is known to be rejected

    def _load(self):
        try:
            with open(KEY_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("key") or None
        except Exception:
            return None

    def _save(self, key):
        try:
            os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
            with open(KEY_FILE, "w", encoding="utf-8") as f:
                json.dump({"key": key, "found_at": int(time.time())}, f)
        except Exception as e:
            print(f"[Water] key save failed: {e}")

    @staticmethod
    def _fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=40) as resp:
            return resp.read().decode("utf-8", "ignore")

    def scan(self):
        """Download the site's JS chunks and return every candidate key (most frequent first)."""
        html = self._fetch(TWA_SITE)
        found = {}
        for m in _KEY_RE.finditer(html):
            found[m.group(1)] = found.get(m.group(1), 0) + 1
        chunks = sorted(set(_CHUNK_RE.findall(html)))
        for path in chunks:
            try:
                js = self._fetch("https://twa.thaiwater.net" + path)
            except Exception:
                continue
            for m in _KEY_RE.finditer(js):
                found[m.group(1)] = found.get(m.group(1), 0) + 1
        return [k for k, _ in sorted(found.items(), key=lambda kv: -kv[1])]

    @staticmethod
    def _works(key):
        req = urllib.request.Request(TWA_API + "/v2/waterload-tide/list",
                                     headers={"User-Agent": USER_AGENT, "x-api-key": key, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            return e.code not in (401, 403)
        except Exception:
            return False

    def rediscover(self, reason=""):
        """Scan the site once (rate limited) and switch to the first key the API accepts."""
        with self.lock:
            if self.scanning or time.time() - self.last_scan < 60:
                return False
            self.scanning = True
            self.last_scan = time.time()
        try:
            print(f"[Water] api key rejected{f' ({reason})' if reason else ''}; scanning twa.thaiwater.net for a new one")
            candidates = [k for k in self.scan() if k != self.key]
            for k in candidates:
                if self._works(k):
                    with self.lock:
                        self.key = k
                        self.broken = False
                    self._save(k)
                    print(f"[Water] new api key found ({k[:6]}...)")
                    return True
            print(f"[Water] no working key among {len(candidates)} candidate(s); retry in {KEY_RETRY_SECONDS // 60} min")
            return False
        except Exception as e:
            print(f"[Water] key scan failed: {e}")
            return False
        finally:
            with self.lock:
                self.scanning = False

    def mark_broken(self):
        with self.lock:
            first = not self.broken
            self.broken = True
        if first:
            threading.Thread(target=self._retry_loop, daemon=True, name="twa-key").start()

    def _retry_loop(self):
        """Keep looking until a key works again; the site may deploy the new bundle hours later."""
        while True:
            if self.rediscover():
                return
            with self.lock:
                if not self.broken:
                    return
            time.sleep(KEY_RETRY_SECONDS)


_keys = _KeyStore()


# ---------------------------------------------------------------- http + cache
def _get(path, **params):
    url = TWA_API + path + ("?" + urllib.parse.urlencode(params) if params else "")

    def call():
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "x-api-key": _keys.key, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = call()
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            raise
        # Key rotated: try to pick up the new one right away, else keep retrying in the background
        if _keys.rediscover(f"HTTP {e.code}"):
            data = call()
        else:
            _keys.mark_broken()
            raise
    _keys.broken = False
    return data


def key_status():
    return {"key_prefix": _keys.key[:6], "rejected": _keys.broken, "last_scan": int(_keys.last_scan) or None}


class _Cache:
    """Tiny TTL cache; a failed refresh keeps serving the last good value (stale flag set)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.items = {}  # key -> (value, fetched_at)

    def get(self, key, ttl, loader):
        with self.lock:
            hit = self.items.get(key)
        if hit and time.time() - hit[1] < ttl:
            return hit[0], False
        try:
            value = loader()
        except Exception as e:
            print(f"[Water] {key} refresh failed: {e}")
            if hit:
                return hit[0], True
            raise
        with self.lock:
            self.items[key] = (value, time.time())
        return value, False


_cache = _Cache()


# ---------------------------------------------------------------- helpers
def _ts(s):
    """ThaiWater datetime string -> epoch seconds. Naive strings are Bangkok local time."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace(" ", "T"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=BKK_TZ)
    return int(d.timestamp())


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _river_level(diff_text, storage_pct, diff_bank):
    """Map ThaiWater bank text / distance to bank onto the dashboard's 4-step scale."""
    t = diff_text or ""
    if "ล้น" in t or "เท่า" in t or (storage_pct is not None and storage_pct >= 100):
        return "overflow"
    if diff_bank is not None and diff_bank <= 0.5:
        return "high"
    if storage_pct is not None and storage_pct >= 90:
        return "high"
    if storage_pct is not None and storage_pct < 10:
        return "low"
    return "normal"


def _canal_level(storage_pct):
    if storage_pct is None:
        return "normal"
    if storage_pct >= 100:
        return "overflow"
    if storage_pct >= 80:
        return "high"
    return "normal"


def _flood_level(cm):
    if cm is None or cm <= 0:
        return "normal"
    return "flooding" if cm >= 10 else "slight"


def _features(payload, provinces):
    """Flatten the province-keyed GeoJSON maps ThaiWater serves."""
    data = payload.get("data") or {}
    out = []
    for code in provinces:
        fc = data.get(code)
        for f in (fc or {}).get("features", []):
            out.append(f.get("properties") or {})
    return out


# ---------------------------------------------------------------- summary
def _load_river():
    rows = []
    for p in _features(_get("/v2/waterlevel"), METRO_PROVINCES):
        st = p.get("station") or {}
        geo = p.get("geoCode") or {}
        storage = _num(p.get("storagePercent"))
        msl = _num(p.get("waterlevelMsl"))
        prev = _num(p.get("waterlevelMslPrevious"))
        rows.append({
            "id": str(st.get("id") or p.get("id")),
            "name": st.get("station") or "",
            "river": p.get("riverName") or "",
            "district": geo.get("district") or "",
            "province": geo.get("province") or "",
            "lat": _num(st.get("latitude")),
            "lng": _num(st.get("longitude")),
            "msl": msl,
            "prev": prev,
            "trend": None if msl is None or prev is None else round(msl - prev, 2),
            "bank": _num(p.get("minBank")),
            "diff_bank": _num(p.get("diffWlBank")),
            "diff_text": p.get("diffWlBankText") or "",
            "storage_pct": storage,
            "level": _river_level(p.get("diffWlBankText"), storage, _num(p.get("diffWlBank"))),
            "ts": _ts(p.get("waterlevelDatetime")),
            "official_forecast": int(st.get("id") or 0) in OFFICIAL_FORECAST_STATIONS,
        })
    order = {"overflow": 0, "high": 1, "normal": 2, "low": 3}
    rows.sort(key=lambda r: (order.get(r["level"], 9), -(r["storage_pct"] or 0)))
    return rows


def _load_canals():
    rows = []
    for p in _features(_get("/v2/waterlevel/canal"), METRO_PROVINCES):
        st = p.get("station") or {}
        geo = p.get("geoCode") or {}
        storage = _num(p.get("storagePercent"))
        rows.append({
            "id": str(st.get("id") or p.get("id")),
            "name": st.get("station") or "",
            "district": geo.get("district") or "",
            "province": geo.get("province") or "",
            "lat": _num(st.get("latitude")),
            "lng": _num(st.get("longitude")),
            "msl": _num(p.get("measureValue")),
            "change_pct": _num(p.get("percentageDiff")),
            "storage_pct": storage,
            "level": _canal_level(storage),
            "ts": _ts(p.get("measureAt")),
        })
    rows.sort(key=lambda r: -(r["storage_pct"] or -1))
    return rows


def _load_flood_roads():
    # The map endpoint is very slow on ThaiWater's side and the list cannot be sorted;
    # page 1 carries the totals plus the worst sensor, which is what the page needs
    d = _get("/v2/flood/floodroad-bangkok/list")
    summary = (d.get("meta") or {}).get("summary") or {}

    def row(p):
        st = p.get("station") or {}
        geo = p.get("geoCode") or {}
        cm = _num(p.get("measureValue"))
        return {
            "id": str(st.get("id") or p.get("id")),
            "name": st.get("station") or "",
            "district": geo.get("district") or "",
            "lat": _num(st.get("latitude")),
            "lng": _num(st.get("longitude")),
            "depth_cm": cm,
            "level": _flood_level(cm),
            "ts": _ts(p.get("measureAt")),
        }

    items = [row(p) for p in (d.get("data") or [])]
    if isinstance(summary.get("max"), dict):
        worst = row(summary["max"])
        items = [worst] + [i for i in items if i["id"] != worst["id"]]
    return {
        "flooding": summary.get("flooding") or 0,
        "slight": summary.get("slight_flooding") or 0,
        "normal": summary.get("normal") or 0,
        "worst": items[0] if items else None,
        "items": [i for i in items if i["level"] != "normal"],
    }


def _load_tide():
    d = _get("/v2/waterload-tide/list", limit=-1)
    rows = []
    for p in d.get("data") or []:
        if p.get("code") not in TIDE_STATIONS:
            continue
        rows.append({
            "code": p.get("code"),
            "name": p.get("stationName") or "",
            "lat": _num(p.get("latitude")),
            "lng": _num(p.get("longitude")),
            "date": (p.get("measureAt") or "")[:10],
            "max": _num(p.get("maxValue")),
            "max_time": p.get("maxTime"),
            "min": _num(p.get("minValue")),
            "min_time": p.get("minTime"),
            "hours": [{"h": h, "v": _num(p.get(f"time{h:02d}00"))} for h in (0, 4, 8, 12, 16, 20)],
        })
    rows.sort(key=lambda r: TIDE_STATIONS.index(r["code"]))
    return rows


def _load_rain_warnings():
    out = []
    try:
        d = _get("/v2/summary/rainfall-24hr-forecast", limit=-1)
        for p in d.get("data") or []:
            geo = p.get("geoCode") or {}
            if geo.get("provinceCode") in METRO_PROVINCES:
                out.append({
                    "kind": "forecast",
                    "province": geo.get("province"),
                    "district": geo.get("district") if not str(geo.get("district") or "").endswith("undefined") else "",
                    "mm": _num(p.get("measureValue")),
                    "text": p.get("measureLevelText") or "",
                    "ts": _ts(p.get("measureAt")),
                })
    except Exception as e:
        print(f"[Water] rain forecast: {e}")
    try:
        d = _get("/v2/summary/warning-rainfall-24h")
        for p in ((d.get("data") or {}).get("area") or []):
            if p.get("province") in METRO_PROVINCES.values():
                out.append({
                    "kind": "observed",
                    "province": p.get("province"),
                    "district": p.get("amphoe") or "",
                    "mm": _num(p.get("sumRainfall")),
                    "text": p.get("name") or "",
                    "ts": _ts(p.get("latestRainfallDatetime")),
                })
    except Exception as e:
        print(f"[Water] rain warning: {e}")
    return out


# ---------------------------------------------------------------- National Thai Water (ONWR) portal
def _ntw_get(path):
    req = urllib.request.Request(NTW_API + path, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                                                          "Referer": "https://nationalthaiwater.onwr.go.th/"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ntw_prov(x):
    return ((x.get("geocode") or {}).get("province_name") or {}).get("th") or ""


def _ntw_amphoe(x):
    return ((x.get("geocode") or {}).get("amphoe_name") or {}).get("th") or ""


def _rain_level(mm):
    if mm is None:
        return "none"
    if mm > 90:
        return "extreme"
    if mm > 50:
        return "heavy"
    if mm > 20:
        return "moderate"
    if mm > 0:
        return "light"
    return "none"


def _load_ntw():
    """Dams, observed rain, rain outlook, storms and flood warnings for Bangkok + 5 provinces."""
    t = _ntw_get("/public/thailand")
    metro = set(METRO_PROVINCES.values())

    def rows(block):
        return ((t.get(block) or {}).get("data") or {}).get("data") or []

    dams = []
    for x in rows("dam"):
        dam = x.get("dam") or {}
        name = (dam.get("dam_name") or {}).get("th") or ""
        if name not in NTW_DAMS:
            continue
        pct = _num(x.get("dam_storage_percent"))
        dams.append({
            "name": name, "date": x.get("dam_date"), "storage": _num(x.get("dam_storage")),
            "max_storage": _num(dam.get("max_storage")), "storage_pct": pct,
            "inflow": _num(x.get("dam_inflow")), "released": _num(x.get("dam_released")),
            "uses_pct": _num(x.get("dam_uses_water_percent")),
            "level": "high" if (pct or 0) >= 90 else ("normal" if (pct or 0) >= 50 else "low"),
        })
    dams.sort(key=lambda d: NTW_DAMS.index(d["name"]))

    rain = []
    for x in rows("rain"):
        if _ntw_prov(x) not in metro:
            continue
        mm = _num(x.get("rain_24h"))
        if mm is None:
            continue
        st = x.get("station") or {}
        rain.append({
            "name": (st.get("tele_station_name") or {}).get("th") or "",
            "district": _ntw_amphoe(x), "province": _ntw_prov(x),
            "lat": _num(st.get("tele_station_lat")), "lng": _num(st.get("tele_station_long")),
            "rain_24h": mm, "rain_1h": _num(x.get("rain_1h")), "level": _rain_level(mm),
            "ts": _ts(x.get("rainfall_datetime")),
        })
    rain.sort(key=lambda r: -(r["rain_24h"] or 0))
    rain_counts = {k: sum(1 for r in rain if r["level"] == k) for k in ("extreme", "heavy", "moderate", "light", "none")}

    level_text = ((t.get("pre_rain") or {}).get("setting") or {}).get("level-text") or {}
    outlook = []
    for x in rows("pre_rain"):
        prov = (x.get("province_name") or {}).get("th") or ""
        if prov in metro:
            lv = str(x.get("rainforecast_level") or "")
            outlook.append({"province": prov, "level": int(lv or 0),
                            "text": (level_text.get(lv) or {}).get("text") or "ฝนตกหนัก"})

    storms = []
    for x in rows("storm"):
        storms.append({"name": x.get("storm_name") or x.get("name") or "", "category": x.get("category") or "",
                       "raw": {k: v for k, v in x.items() if isinstance(v, (str, int, float))}})

    warn = t.get("warning") or {}
    warnings = []
    for kind in ("flood", "drought"):
        for x in ((warn.get(kind) or {}).get("data") or []):
            prov = _ntw_prov(x) or (x.get("province_name") or {}).get("th") or ""
            if not prov or prov in metro:
                warnings.append({"kind": kind, "province": prov, "text": x.get("title") or x.get("warning_text") or json.dumps(x, ensure_ascii=False)[:200]})

    return {
        "updated_at": int(time.time()),
        "dams": dams,
        "rain": rain[:40], "rain_total": len(rain), "rain_counts": rain_counts,
        "rain_outlook": outlook, "storms": storms, "warnings": warnings,
    }


def _weather_alert(rain_24h, gust, storm):
    """Rain/storm watch level per zone. Thresholds follow TMD daily-rain classes:
    35 mm = heavy, 90 mm = very heavy; gusts >= 60 km/h count as a storm risk."""
    if rain_24h >= 90 or (storm and gust >= 60):
        return "red"
    if rain_24h >= 35 or gust >= 50 or (storm and (gust >= 40 or rain_24h >= 20)):
        return "orange"
    if rain_24h >= 10 or storm or gust >= 40:
        return "yellow"
    return "green"


# Wind field for the map overlay: a 7x7 grid over Bangkok + suburbs, current conditions only
WIND_GRID_LAT = [13.45 + i * 0.1 for i in range(7)]
WIND_GRID_LNG = [100.25 + i * 0.1 for i in range(7)]
WIND_TTL = 900


def _load_wind_grid():
    pts = [(lat, lng) for lat in WIND_GRID_LAT for lng in WIND_GRID_LNG]
    q = urllib.parse.urlencode({
        "latitude": ",".join(f"{p[0]:.2f}" for p in pts),
        "longitude": ",".join(f"{p[1]:.2f}" for p in pts),
        "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,cloud_cover,temperature_2m",
        "timezone": "Asia/Bangkok", "wind_speed_unit": "kmh",
    })
    req = urllib.request.Request(f"{OPEN_METEO}?{q}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        blocks = json.loads(resp.read().decode("utf-8"))
    if isinstance(blocks, dict):
        blocks = [blocks]
    out = []
    for (lat, lng), b in zip(pts, blocks):
        c = b.get("current") or {}
        out.append({"lat": lat, "lng": lng, "speed": c.get("wind_speed_10m"), "dir": c.get("wind_direction_10m"),
                    "gust": c.get("wind_gusts_10m"), "rain": c.get("precipitation"), "cloud": c.get("cloud_cover"),
                    "temp": c.get("temperature_2m"), "time": c.get("time")})
    return {"updated_at": int(time.time()), "points": out}


def get_wind_grid():
    data, stale = _cache.get("wind_grid", WIND_TTL, _load_wind_grid)
    return {**data, "stale": stale}


def _load_weather():
    """24 h rain / wind outlook per watch zone from Open-Meteo."""
    q = urllib.parse.urlencode({
        "latitude": ",".join(str(z["lat"]) for z in WEATHER_ZONES),
        "longitude": ",".join(str(z["lng"]) for z in WEATHER_ZONES),
        "hourly": "precipitation,precipitation_probability,wind_speed_10m,wind_gusts_10m,weather_code",
        "forecast_days": 2, "timezone": "Asia/Bangkok", "wind_speed_unit": "kmh",
    })
    req = urllib.request.Request(f"{OPEN_METEO}?{q}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        blocks = json.loads(resp.read().decode("utf-8"))
    if isinstance(blocks, dict):
        blocks = [blocks]
    now_h = datetime.now(BKK_TZ).replace(minute=0, second=0, microsecond=0)
    today = now_h.strftime("%Y-%m-%d")
    clock = lambda t: t[11:16] if t[:10] == today else "พรุ่งนี้ " + t[11:16]
    zones = []
    for zone, b in zip(WEATHER_ZONES, blocks):
        h = b.get("hourly") or {}
        times = h.get("time") or []
        try:
            start = next(i for i, t in enumerate(times) if _ts(t) >= now_h.timestamp())
        except StopIteration:
            continue
        sl = slice(start, start + 24)
        rain = [_num(v) or 0.0 for v in (h.get("precipitation") or [])[sl]]
        prob = [_num(v) or 0.0 for v in (h.get("precipitation_probability") or [])[sl]]
        gust = [_num(v) or 0.0 for v in (h.get("wind_gusts_10m") or [])[sl]]
        wind = [_num(v) or 0.0 for v in (h.get("wind_speed_10m") or [])[sl]]
        codes = [int(v or 0) for v in (h.get("weather_code") or [])[sl]]
        hours = times[sl]
        if not rain:
            continue
        storm_idx = next((i for i, c in enumerate(codes) if c in STORM_CODES), None)
        peak_idx = max(range(len(rain)), key=lambda i: rain[i])
        rain_24h = round(sum(rain), 1)
        gust_max = round(max(gust), 0)
        zones.append({
            **zone,
            "rain_6h": round(sum(rain[:6]), 1),
            "rain_24h": rain_24h,
            "prob_6h": round(max(prob[:6]), 0),
            "prob_24h": round(max(prob), 0),
            "wind_max": round(max(wind), 0),
            "gust_max": gust_max,
            "storm_at": clock(hours[storm_idx]) if storm_idx is not None else None,
            "peak_at": clock(hours[peak_idx]) if rain[peak_idx] > 0 else None,
            "peak_mm": round(rain[peak_idx], 1),
            "hourly": [{"t": hours[i][11:16], "mm": round(rain[i], 1), "gust": round(gust[i], 0)} for i in range(len(rain))],
            "alert": _weather_alert(rain_24h, gust_max, storm_idx is not None),
        })
    return zones


def _km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return 999.0
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def _zone_watch(zones, river, canals, roads, rain_warnings, radius_km=9.0):
    """Attach the nearby water situation to each weather zone so one row says
    'rain coming + canal already full' instead of two unrelated numbers."""
    order = {"green": 0, "yellow": 1, "orange": 2, "red": 3}
    for z in zones:
        near = lambda r: _km(z["lat"], z["lng"], r.get("lat"), r.get("lng")) <= radius_km
        z["stations_overflow"] = [r["name"] for r in river + canals if r["level"] == "overflow" and near(r)][:4]
        z["stations_high"] = [r["name"] for r in river + canals if r["level"] == "high" and near(r)][:4]
        z["flood_roads"] = [{"name": r["name"], "depth_cm": r["depth_cm"]} for r in roads.get("items", []) if near(r)][:4]
        if z["id"].startswith("bkk"):
            in_zone = lambda w: w.get("province") == "กรุงเทพมหานคร" and any(a in (w.get("district") or "") for a in z["areas"].split())
        else:
            in_zone = lambda w: w.get("province") == z["name"]
        z["rain_observed_mm"] = max([w["mm"] or 0 for w in rain_warnings if w["kind"] == "observed" and in_zone(w)], default=0)
        # Escalate: water already high + rain forecast -> one step up
        level = z["alert"]
        if z["flood_roads"] or z["stations_overflow"]:
            level = "red" if level in ("orange", "red") else "orange"
        elif z["stations_high"] and level == "yellow":
            level = "orange"
        if z["rain_observed_mm"] >= 90:
            level = "red"
        elif z["rain_observed_mm"] >= 35 and level in ("green", "yellow"):
            level = "orange"
        z["watch"] = level
    zones.sort(key=lambda z: (-order[z["watch"]], -z["rain_24h"]))
    return zones


def _load_official_stations():
    m = _get("/v2/waterlevel-discharge/forecast")
    rows = []
    for fc in (m.get("data") or {}).values():
        for f in fc.get("features", []):
            p = f.get("properties") or {}
            sid = int((p.get("station") or {}).get("id") or 0)
            if sid not in OFFICIAL_FORECAST_STATIONS:
                continue
            rows.append({
                "id": str(sid),
                "name": p.get("stationName") or OFFICIAL_FORECAST_STATIONS[sid]["name"],
                "province": OFFICIAL_FORECAST_STATIONS[sid]["province"],
                "river": p.get("river") or "",
                "msl": _num(p.get("msl")),
                "warning": _num(p.get("warning")),
                "alarm": _num(p.get("alarm")),
                "critical": _num(p.get("criticalVolume")),
                "bank": _num((p.get("station") or {}).get("minBank")),
                "ts": _ts(p.get("datetime")),
            })
    order = list(OFFICIAL_FORECAST_STATIONS)
    rows.sort(key=lambda r: order.index(int(r["id"])))
    return rows


def _build_summary():
    parts = {}
    errors = {}

    def run(key, fn):
        try:
            parts[key] = fn()
        except Exception as e:
            errors[key] = str(e)
            print(f"[Water] {key}: {e}")

    threads = [threading.Thread(target=run, args=a, daemon=True) for a in (
        ("river", _load_river), ("canals", _load_canals), ("flood_roads", _load_flood_roads),
        ("tide", _load_tide), ("rain", _load_rain_warnings), ("official", _load_official_stations),
        ("weather", _load_weather), ("ntw", lambda: _cache.get("ntw", NTW_TTL, _load_ntw)[0]))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    if "river" not in parts and "canals" not in parts:
        raise RuntimeError(errors.get("river") or "thaiwater unreachable")

    river = parts.get("river", [])
    canals = parts.get("canals", [])
    roads = parts.get("flood_roads", {"flooding": 0, "slight": 0, "normal": 0, "items": []})
    weather = _zone_watch(parts.get("weather", []), river, canals, roads, parts.get("rain", []))
    return {
        "updated_at": int(time.time()),
        "river": river,
        "river_counts": {k: sum(1 for r in river if r["level"] == k) for k in ("overflow", "high", "normal", "low")},
        "canals": canals[:40],
        "canal_counts": {k: sum(1 for r in canals if r["level"] == k) for k in ("overflow", "high", "normal")},
        "canal_total": len(canals),
        "flood_roads": roads,
        "tide": parts.get("tide", []),
        "rain_warnings": parts.get("rain", []),
        "official_stations": parts.get("official", []),
        "weather": weather,
        "ntw": parts.get("ntw"),
        "errors": errors,
    }


def get_summary():
    data, stale = _cache.get("summary", SUMMARY_TTL, _build_summary)
    return {**data, "stale": stale, "api_key": key_status()}


# ---------------------------------------------------------------- forecast
def _load_observed(station_id, days=OBS_DAYS):
    end = datetime.now(BKK_TZ)
    start = end - timedelta(days=days)
    d = _get("/data/platform/v1/public/tele_waterlevel/graph", stationId=station_id,
             startDate=start.strftime("%Y-%m-%d"), endDate=(end + timedelta(days=1)).strftime("%Y-%m-%d"), limit=-1)
    series = []
    for block in d.get("data") or []:
        for p in block.get("data") or []:
            v = _num(p.get("value"))
            t = _ts(p.get("datetime"))
            if v is not None and t is not None:
                series.append({"t": t, "v": round(v, 3)})
    series.sort(key=lambda p: p["t"])
    return _despike(series)


def _despike(series, jump=0.5, half_window=6):
    """Drop short telemetry glitches: samples further than `jump` m from the median of the
    surrounding ~2 h window (a genuine tidal swing moves far less in that time)."""
    if len(series) < 2 * half_window + 1:
        return series
    vals = np.array([p["v"] for p in series])
    keep = []
    for i, p in enumerate(series):
        lo, hi = max(0, i - half_window), min(len(vals), i + half_window + 1)
        if abs(p["v"] - float(np.median(vals[lo:hi]))) <= jump:
            keep.append(p)
    return keep


def _load_official_forecast(station_id):
    d = _get("/data/platform/v1/public/latest_waterlevel/forecast/graph", stationId=station_id, limit=-1)
    now = time.time()
    fore = []
    for p in d.get("data") or []:
        v = _num(p.get("foreValue"))
        t = _ts(p.get("datetime"))
        if v is not None and t is not None and t >= now - 3600:
            fore.append({"t": t, "v": round(v, 3)})
    fore.sort(key=lambda p: p["t"])
    levels = {
        "warning": _num(d.get("warningVolume")),
        "alarm": _num(d.get("alarmVolume")),
        "critical": _num(d.get("criticalVolume")),
    }
    for inc in d.get("included") or []:
        attrs = inc.get("attributes") or {}
        if inc.get("type") == "station":
            levels["bank"] = _num(attrs.get("minBank"))
    return fore, levels


def _harmonic_outlook(observed, hours=EST_HOURS):
    """48 h outlook from the station's own history.

    Tidal stations: least-squares trend + tidal constituents, extrapolated hourly.
    Non-tidal stations (gated inner-city canals): a rain pulse relaxes back towards the
    pre-event baseline, so we use exponential recession instead of forcing a tide fit.
    Returns (points, fit_rmse, model) or (None, None, None) when there is not enough data."""
    if len(observed) < 144:  # < 1 day of 10-min samples
        return None, None, None
    t0 = observed[-1]["t"]
    th = np.array([(p["t"] - t0) / 3600.0 for p in observed])
    y = np.array([p["v"] for p in observed])
    span_h = th[-1] - th[0]
    if span_h < 24:
        return None, None, None
    tf = np.arange(0, hours + 1, dtype=float)

    def design(t, tides=True):
        cols = [np.ones_like(t), t]
        if tides:
            for period in TIDE_PERIODS_H:
                if period * 1.5 > span_h:  # can't resolve a constituent longer than the window
                    continue
                w = 2 * math.pi / period
                cols += [np.cos(w * t), np.sin(w * t)]
        return np.column_stack(cols)

    X = design(th)
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    rss_tide = float(np.sum((X @ coef - y) ** 2))
    X0 = design(th, tides=False)
    coef0, *_ = np.linalg.lstsq(X0, y, rcond=None)
    rss_trend = float(np.sum((X0 @ coef0 - y) ** 2))
    tide_share = 1 - rss_tide / rss_trend if rss_trend > 0 else 0.0

    if tide_share < 0.5:
        # Tides explain little here: rain-driven canal. Relax from the latest reading towards
        # the pre-event baseline (lower quartile of the window) with a ~30 h time constant.
        base = float(np.percentile(y, 25))
        yf = base + (y[-1] - base) * np.exp(-tf / 30.0)
        # Uncertainty: how much the level typically moves in 6 h
        step = y[36:] - y[:-36] if len(y) > 36 else np.diff(y)
        rmse = float(np.std(step)) if len(step) else None
        pts = [{"t": int(t0 + h * 3600), "v": round(float(v), 3)} for h, v in zip(tf, yf)]
        return pts, (round(rmse, 3) if rmse is not None else None), "recession"

    rmse = float(np.sqrt(rss_tide / len(y)))
    yf = design(tf) @ coef
    # Damp the linear trend so a short-term rise does not extrapolate for two days
    damp = np.exp(-tf / 36.0)
    yf = yf - coef[1] * tf * (1 - damp)
    # Start from the actual latest reading; the fit residual fades out over ~6 h
    resid = y[-1] - (X[-1] @ coef)
    yf = yf + resid * np.exp(-tf / 6.0)
    pts = [{"t": int(t0 + h * 3600), "v": round(float(v), 3)} for h, v in zip(tf, yf)]
    return pts, round(rmse, 3), "tide"


def _extremes(points, limit=4):
    """Local maxima/minima in an hourly series (next high / low water)."""
    out = []
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1]["v"], points[i]["v"], points[i + 1]["v"]
        if b >= a and b > c:
            out.append({"kind": "high", "t": points[i]["t"], "v": points[i]["v"]})
        elif b <= a and b < c:
            out.append({"kind": "low", "t": points[i]["t"], "v": points[i]["v"]})
    return out[:limit]


def _build_forecast(station_id):
    observed = _load_observed(station_id)
    official, levels = [], {}
    if station_id in OFFICIAL_FORECAST_STATIONS:
        try:
            official, levels = _load_official_forecast(station_id)
        except Exception as e:
            print(f"[Water] official forecast {station_id}: {e}")
    estimate, rmse, model = _harmonic_outlook(observed)
    if levels.get("bank") is None:
        # Bank height comes with the telemetry list; reuse the cached summary instead of a second call
        cached = _cache.items.get("summary")
        for r in (cached[0]["river"] if cached else []):
            if r["id"] == str(station_id) and r.get("bank") is not None:
                levels["bank"] = r["bank"]
    basis = official or estimate or []
    latest = observed[-1] if observed else None
    peak = max(basis, key=lambda p: p["v"]) if basis else None
    return {
        "station_id": str(station_id),
        "updated_at": int(time.time()),
        "observed": observed[-(6 * 24 * 2):],  # last 48 h at 10-min resolution for the chart
        "official": official,
        "estimate": estimate,
        "estimate_rmse": rmse,
        "estimate_model": model,
        "levels": levels,
        "latest": latest,
        "peak": peak,
        "extremes": _extremes(basis),
        "source": "hii" if official else ("local" if estimate else None),
    }


def get_forecast(station_id):
    data, stale = _cache.get(f"forecast:{station_id}", FORECAST_TTL, lambda: _build_forecast(int(station_id)))
    return {**data, "stale": stale}


def warm():
    """Fetch the summary once in the background so the first page open is quick."""
    threading.Thread(target=lambda: _cache.get("summary", SUMMARY_TTL, _build_summary), daemon=True).start()
