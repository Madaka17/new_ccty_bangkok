"""
Water level / flood outlook for Bangkok and the surrounding provinces.

Sources (all public, read-only):
- ThaiWater / HII (twa.thaiwater.net): river + canal telemetry, official 7-day
  water level forecast for key Chao Phraya stations, sea tide forecast, BMA
  flood-road sensors, heavy rain warnings.
- BMA Drainage Department (weather.bangkok.go.th/water): the canal gauges themselves, ~45 min fresher
  than the ThaiWater relay, with banks and control levels; ThaiWater canal rows fill any gap.
- A small local tidal-harmonic model gives a 48 h outlook for stations that have
  no official forecast (most Bangkok stations sit in the tidal reach of the
  Chao Phraya, so trend + tide explains most of the short-term movement).
"""
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from backend.water.thaiwater_api import USER_AGENT, _get, key_status

# National Thai Water portal (nationalthaiwater.onwr.go.th) backend: no key needed, one big
# snapshot of every station in the country refreshed by HII every hour
NTW_API = "https://api-v3.thaiwater.net/api/v1/thaiwater30"
NTW_TTL = 600
# Upstream reservoirs that decide how much water reaches the lower Chao Phraya
NTW_DAMS = ["ภูมิพล", "สิริกิติ์", "แควน้อยบำรุงแดน", "ป่าสักชลสิทธิ์", "ขุนด่านปราการชล"]
BKK_TZ = timezone(timedelta(hours=7))

# Bangkok + the five surrounding provinces (ThaiWater province codes)
METRO_PROVINCES = {"10": "กรุงเทพมหานคร", "11": "สมุทรปราการ", "12": "นนทบุรี", "13": "ปทุมธานี", "73": "นครปฐม", "74": "สมุทรสาคร"}
# Stations with an official HII forecast that drive Bangkok's river level (upstream -> downstream)
OFFICIAL_FORECAST_STATIONS = {
    1648: {"name": "สะพานเดชาติวงศ์", "province": "นครสวรรค์"},
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
# Open-Meteo without a key allows 10,000 location-calls a day per IP (shared with the test server).
# Refetched with every 60 s summary, the 8 zones alone used ~11,500 a day and the quota ran out (HTTP 429).
WEATHER_TTL = 1800

SUMMARY_TTL = 60
# BMA Drainage Department canal gauges (the same sensors ThaiWater relays ~45 min later, plus ~40 more).
# The summary page embeds every station as JSON: level, both banks, bed and the department's own
# warning / critical control levels, which are pump-operation levels, not the bank.
BMA_WATER_URL = "https://weather.bangkok.go.th/water/summary"
BMA_STATION_URL = "https://weather.bangkok.go.th/water/StationDetail?id={}"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
BMA_WATER_TTL = 120          # the gauges report every 5 minutes
BMA_STALE_MINUTES = 60       # a gauge whose last reading is older than this counts as offline
CANAL_HIGH_GAP_M = 0.2       # water within this many metres of the lower bank = near overflow
CANAL_MATCH_KM = 0.15        # a ThaiWater canal station this close to a BMA gauge is the same gauge


# ---------------------------------------------------------------- cache
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


def _bma_json(html, name):
    m = re.search(r"const " + name + r" = (\[.*?\]);\n", html)
    if not m:
        raise RuntimeError(f"{name} not found on {BMA_WATER_URL}")
    return json.loads(m.group(1))


def _bma_area(name):
    """BMA district names: a Bangkok district ("บางเขน") or "อำเภอ<amphoe><province>" outside Bangkok."""
    name = (name or "").strip()
    if not name.startswith("อำเภอ"):
        return name, "กรุงเทพมหานคร"
    rest = name[len("อำเภอ"):]
    for prov in ("ปทุมธานี", "นนทบุรี", "สมุทรปราการ", "สมุทรสาคร", "นครปฐม", "ฉะเชิงเทรา"):
        if prov in rest:
            return rest.replace(prov, "").strip(), prov
    return rest, ""


def _load_bma_canals():
    """Every BMA canal gauge. Offline gauges (status 0 or an old reading) are marked, not dropped."""
    # The site's firewall answers 403 now and then; a browser-like request and one retry get through
    headers = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "th,en;q=0.8"}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(BMA_WATER_URL, headers=headers), timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code != 403 or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    districts = {d.get("district_id"): d.get("name") for d in _bma_json(html, "districtList")}
    now = time.time()
    rows = []
    for b in _bma_json(html, "waterSummaryList"):
        if not b.get("active", 1):
            continue
        wl = _num(b.get("wl_in"))
        banks = [x for x in (_num(b.get("left_bank")), _num(b.get("right_bank"))) if x is not None]
        bank, bed = (min(banks) if banks else None), _num(b.get("bed_bank"))
        warn, crit = _num(b.get("warning")), _num(b.get("critical"))
        ts = _ts(b.get("site_timestamp"))
        offline = wl is None or b.get("water_status") == 0 or not ts or now - ts > BMA_STALE_MINUTES * 60
        diff = None if wl is None or bank is None else round(bank - wl, 2)
        fill = None
        if wl is not None and bank is not None and bed is not None and bank > bed:
            fill = round((wl - bed) / (bank - bed) * 100, 1)
        if offline:
            level = "offline"
        elif diff is None:
            level = "normal"
        else:
            level = "overflow" if diff <= 0 else "high" if diff <= CANAL_HIGH_GAP_M else "normal"
        control = None
        if not offline and wl is not None:
            control = "critical" if crit is not None and wl >= crit else "warning" if warn is not None and wl >= warn else None
        district, province = _bma_area(districts.get(b.get("district_id")))
        rows.append({
            "id": f"bma-{b.get('water_id')}",
            "code": b.get("water_code"),
            "name": b.get("water_shortname") or b.get("water_name") or "",
            "canal": b.get("river_name") or "",
            "district": district,
            "province": province,
            "lat": _num(b.get("latitude")),
            "lng": _num(b.get("longitude")),
            "msl": wl,
            "bank": bank,
            "bed": bed,
            "diff_bank": diff,
            "storage_pct": fill,
            "level": level,
            "control_warning": warn,
            "control_critical": crit,
            "control": control,
            "max_today": _num(b.get("max_in_day")),
            "max_yesterday": _num(b.get("max_in_yesterday")),
            "ts": ts,
            "source": "bma",
            "url": BMA_STATION_URL.format(b.get("water_id")),
        })
    return rows


def _load_canals():
    """BMA gauges first (fresh, with banks), then ThaiWater canal stations the BMA page does not list."""
    parts, errors = {}, {}

    def run(key, fn):
        try:
            parts[key] = fn()
        except Exception as e:  # noqa: BLE001 - either source alone is enough
            errors[key] = e
            print(f"[Water] canals {key}: {e}")

    threads = [threading.Thread(target=run, args=a, daemon=True) for a in (
        ("bma", lambda: _cache.get("bma_canals", BMA_WATER_TTL, _load_bma_canals)[0]), ("twa", _load_twa_canals))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=45)
    if not parts:
        raise RuntimeError(str(errors.get("bma") or errors.get("twa") or "canal sources unreachable"))
    rows = list(parts.get("bma", []))
    placed = [r for r in rows if r["lat"] and r["lng"]]
    for t in parts.get("twa", []):
        if t["lat"] and t["lng"] and any(_km(t["lat"], t["lng"], r["lat"], r["lng"]) <= CANAL_MATCH_KM for r in placed):
            continue
        rows.append(t)
    order = {"overflow": 0, "high": 1, "normal": 2, "offline": 3}
    rows.sort(key=lambda r: (order.get(r["level"], 9), r["diff_bank"] if r.get("diff_bank") is not None else 99,
                             -(r["storage_pct"] or -1)))
    return rows


def _load_twa_canals():
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
            "source": "thaiwater",
        })
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
            "lat": _num(dam.get("dam_lat")), "lng": _num(dam.get("dam_long")),
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
        # the page shows the wettest 40; rain_all is for road_service and is dropped
        # from the summary payload again in _build_summary
        "rain": rain[:40], "rain_all": rain, "rain_total": len(rain), "rain_counts": rain_counts,
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
WIND_TTL = 3600     # 49 points per call: hourly keeps the grid under 1,200 Open-Meteo calls a day


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
    try:
        data, stale = _cache.get("wind_grid", WIND_TTL, _load_wind_grid)
    except Exception:   # nothing cached yet and Open-Meteo is down or over quota: the map just shows no arrows
        return {"updated_at": None, "points": [], "stale": True}
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
        ("weather", lambda: _cache.get("weather", WEATHER_TTL, _load_weather)[0]),
        ("ntw", lambda: {k: v for k, v in _cache.get("ntw", NTW_TTL, _load_ntw)[0].items() if k != "rain_all"}))]
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
        "canals": [r for r in canals if r["level"] != "offline"][:40],
        "canal_counts": {k: sum(1 for r in canals if r["level"] == k) for k in ("overflow", "high", "normal", "offline")},
        "canal_total": sum(1 for r in canals if r["level"] != "offline"),
        "canal_control": sum(1 for r in canals if r.get("control") == "critical"),
        "canal_sources": {k: sum(1 for r in canals if r.get("source") == k) for k in ("bma", "thaiwater")},
        "canals_all": canals,    # every gauge, for get_map(); dropped from the summary payload
        "flood_roads": roads,
        "tide": parts.get("tide", []),
        "rain_warnings": parts.get("rain", []),
        "official_stations": parts.get("official", []),
        "weather": weather,
        "ntw": parts.get("ntw"),
        "errors": errors,
    }


def rain_stations():
    """Every metro rain gauge with its 24 h total, from the same cache the summary uses."""
    try:
        return _cache.get("ntw", NTW_TTL, _load_ntw)[0].get("rain_all") or []
    except Exception:  # noqa: BLE001 - callers treat rain as optional context
        return []


def get_summary():
    data, stale = _cache.get("summary", SUMMARY_TTL, _build_summary)
    return {**{k: v for k, v in data.items() if k != "canals_all"}, "stale": stale, "api_key": key_status()}


RIVER_STALE_MINUTES = 180    # ThaiWater river gauges report hourly at best


def get_map():
    """Every metro gauge as one map point, for the Water Forecast station map: water level (rivers +
    canals, offline ones included), 24 h rain and the upstream dams."""
    data, stale = _cache.get("summary", SUMMARY_TTL, _build_summary)
    now = time.time()

    def pt(r, kind, **extra):
        return {"id": f"{kind}-{r.get('id') or r.get('name')}", "kind": kind, "name": r.get("name") or "",
                "district": r.get("district") or "", "province": r.get("province") or "",
                "lat": r.get("lat"), "lng": r.get("lng"), "ts": r.get("ts"), **extra}

    water = []
    for r in data.get("river") or []:
        old = not r.get("ts") or now - r["ts"] > RIVER_STALE_MINUTES * 60
        water.append(pt(r, "river", status="offline" if old else r.get("level"), msl=r.get("msl"), bank=r.get("bank"),
                        diff_bank=r.get("diff_bank"), storage_pct=r.get("storage_pct"), river=r.get("river"),
                        trend=r.get("trend"), station_id=r.get("id")))
    for r in data.get("canals_all") or data.get("canals") or []:
        water.append(pt(r, "canal", status=r.get("level"), msl=r.get("msl"), bank=r.get("bank"),
                        diff_bank=r.get("diff_bank"), storage_pct=r.get("storage_pct"), river=r.get("canal"),
                        control=r.get("control"), control_critical=r.get("control_critical"),
                        source=r.get("source"), url=r.get("url")))
    rain = [pt(r, "rain", status=r.get("level"), rain_24h=r.get("rain_24h"), rain_1h=r.get("rain_1h"))
            for r in rain_stations()]
    dams = [pt({**d, "province": ""}, "dam", status=d.get("level"), storage_pct=d.get("storage_pct"),
               storage=d.get("storage"), max_storage=d.get("max_storage"), inflow=d.get("inflow"),
               released=d.get("released"), date=d.get("date"))
            for d in (data.get("ntw") or {}).get("dams") or []]
    keep = lambda rows: [r for r in rows if r["lat"] and r["lng"]]
    return {"updated_at": data.get("updated_at"), "stale": stale,
            "water": keep(water), "rain": keep(rain), "dams": keep(dams)}


def warm():
    """Fetch the summary once in the background so the first page open is quick."""
    threading.Thread(target=lambda: _cache.get("summary", SUMMARY_TTL, _build_summary), daemon=True).start()
