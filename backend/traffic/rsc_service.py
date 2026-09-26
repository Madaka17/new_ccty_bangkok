"""
Road accident statistics for Bangkok from Thai RSC (thairsc.com).

Source: ศูนย์ข้อมูลอุบัติเหตุ Thai RSC, บริษัท กลางคุ้มครองผู้ประสบภัยจากรถ จำกัด.
Insurance-claim based reports (พ.ร.บ.), so cases with no injured party are not
included. Two public, read-only endpoints back the site:

- https://thairscapi.rvpeservice.com/api/...   province / district aggregates
- https://www.thairsc.com/thairsc-ws/get/accident-points   per-case points with lat/lon

What we build from them:
- summary   : Bangkok today / year-to-date, by vehicle type, by hour, by age, per district,
              joined with the BMA camera counts per district (vehicle_counts.db)
- camera risk: every accident point within RADIUS_M of each BMA camera for the current and
              previous calendar year -> cases / injured / dead / peak hours per camera

Points are cached on disk per (district, year). Victim names are dropped before caching.
"""
import json
import math
import os
import ssl
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from backend.core.instance import BASE_DIR  # project root
from backend.core.instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
CACHE_DIR = os.path.join(DATA_DIR, "cache", "rsc")
SUMMARY_CACHE_FILE = os.path.join(CACHE_DIR, "summary.json")
DB_PATH = os.path.join(DATA_DIR, "vehicle_counts.db")

RSC_API = "https://thairscapi.rvpeservice.com/api"
RSC_WS = "https://www.thairsc.com/thairsc-ws"
USER_AGENT = "BKK-Traffic-CCTV/2.0 (personal dashboard)"
BKK_TZ = timezone(timedelta(hours=7))
BKK_GEOCODE = "10"

RADIUS_M = 300          # accident points counted for a camera
# Cases that RSC could not geocode precisely land on a shared fallback point (police station /
# district office). More than this many cases on one exact coordinate = coarse; skipped for camera scoring.
COARSE_COORD_CASES = 20
SUMMARY_TTL = 3600      # province / district aggregates
POINTS_TTL_CURRENT = 6 * 3600   # current-year points refresh
FETCH_WORKERS = 4

# thairsc.com serves a certificate chain that Python cannot verify; the data is public
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------- http
def _post(url, params=None, timeout=60):
    body = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def _num(v):
    try:
        return int(str(v).replace(",", "").replace("%", "").strip() or 0)
    except ValueError:
        try:
            return float(str(v).replace(",", "").replace("%", ""))
        except ValueError:
            return 0


def _pct(v):
    try:
        return float(str(v).replace("%", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


def _now():
    return datetime.now(BKK_TZ)


# ---------------------------------------------------------------- province / district aggregates
_summary_cache = {"ts": 0, "data": None}
_summary_lock = threading.Lock()


def _fetch_aggregates():
    g = {"geocode": BKK_GEOCODE}
    tasks = {
        "prov": (f"{RSC_API}/province/GetAccidentProvince", g),
        "by_car": (f"{RSC_API}/secondary/GetDeadAccidentByCarType", g),
        "by_age": (f"{RSC_API}/secondary/GetDeadAccidentByAgeRange", g),
        "by_sex": (f"{RSC_API}/secondary/GetDeadAccidentBySex", g),
        "by_hour": (f"{RSC_API}/secondary/GetDeadAccidentByTime", g),
        "compare": (f"{RSC_API}/secondary/GetDeadAccidentByYearCompare", g),
        "per_district": (f"{RSC_API}/province/GetAccidentperDistrict", g),
        "district_codes": (f"{RSC_API}/secondary/get_district_stats", g),
        "national": (f"{RSC_API}/main/section1_1", None),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=9) as ex:
        futures = {k: ex.submit(_post, url, p) for k, (url, p) in tasks.items()}
        for k, f in futures.items():
            results[k] = f.result()

    prov = results["prov"]["Data"]
    by_car = results["by_car"]["Data"]["DeadAccidents"]
    by_age = results["by_age"]["Data"]["DeadAccidents"]
    by_sex = results["by_sex"]["Data"]
    by_hour = results["by_hour"]["Data"]["Accidents"]
    compare = results["compare"]["Data"]
    per_district = results["per_district"]["Data"]["Accident"]
    district_codes = results["district_codes"]["Data"]
    national = results["national"]["Data"]

    code_by_name = {d["district_name"].strip(): d["geocode"] for d in district_codes}
    districts = []
    for d in per_district:
        name = d["Name"].strip()
        districts.append({
            "name": name,
            "geocode": code_by_name.get(name),
            "accidents": _num(d["Accident"]),
            "dead": _num(d["Dead"]),
            "injured": _num(d["Injured"]),
        })

    return {
        "updated": prov.get("DataUpdate"),
        "source": prov.get("DataRef"),
        "year_be": _num(prov.get("CurrentYear")),
        "today": {"dead": _num(prov["Today_Death"]), "injured": _num(prov["Today_Injuries"])},
        "yesterday": {"dead": _num(prov["Yesterday_Death"]), "injured": _num(prov["Yesterday_Injuries"])},
        "ytd": {"dead": _num(prov["Year_Death"]), "injured": _num(prov["Year_Injuries"])},
        "national": {
            "today": {"dead": _num(national["Today_Death"]), "injured": _num(national["Today_Injuries"])},
            "ytd": {"dead": _num(national["Year_Death"]), "injured": _num(national["Year_Injuries"])},
        },
        # cumulative per month, current vs last year
        "cumulative": {
            "dead": [_num(m["Amt"]) for m in prov.get("GraphCurrentYearDeath", [])],
            "dead_last": [_num(m["Amt"]) for m in prov.get("GraphLastYearDeath", [])],
            "injured": [_num(m["Amt"]) for m in prov.get("GraphCurrentYearInjuries", [])],
            "injured_last": [_num(m["Amt"]) for m in prov.get("GraphLastYearInjuries", [])],
        },
        "monthly_dead": {
            "current": [_num(m["Amt"]) for m in compare.get("CurrentYearDead", [])],
            "last": [_num(m["Amt"]) for m in compare.get("LastYearDead", [])],
        },
        "dead_by_vehicle": [{"label": c["CarTypeText"], "en": c["CarTypeEN"], "count": _num(c["Amt"]), "pct": _pct(c["Percent"])} for c in by_car],
        "dead_by_age": [{"label": a["AgeRangeTextDesc"], "count": _num(a["Amt"]), "pct": _pct(a["Percent"])} for a in by_age],
        "dead_by_sex": {"male": _num(by_sex["summale"]), "female": _num(by_sex["sumfemale"]), "male_pct": _pct(by_sex["percentmale"])},
        "dead_by_hour": [_num(h["DeadAmt"]) for h in sorted(by_hour, key=lambda h: int(h["TimeRangeText"]))],
        "districts": districts,
    }


def _camera_load_by_district():
    """Average vehicles per scan and congestion split for each district, from bma_latest."""
    out = defaultdict(lambda: {"cameras": 0, "online": 0, "vehicles": 0.0, "motorcycles": 0.0, "heavy": 0, "moderate": 0})
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT district, status, level, total, motorcycles, acc_total, acc_motorcycles, acc_scans FROM bma_latest").fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    for r in rows:
        d = (r["district"] or "").strip()
        if not d:
            continue
        o = out[d]
        o["cameras"] += 1
        if r["status"] == "online":
            o["online"] += 1
        scans = r["acc_scans"] or 0
        if scans > 0:
            o["vehicles"] += (r["acc_total"] or 0) / scans
            o["motorcycles"] += (r["acc_motorcycles"] or 0) / scans
        else:
            o["vehicles"] += r["total"] or 0
            o["motorcycles"] += r["motorcycles"] or 0
        if r["level"] == "heavy":
            o["heavy"] += 1
        elif r["level"] == "moderate":
            o["moderate"] += 1
    return out


def get_summary():
    with _summary_lock:
        if _summary_cache["data"] and time.time() - _summary_cache["ts"] < SUMMARY_TTL:
            return _summary_cache["data"]
        # Check disk cache if in-memory cache is empty or expired
        if os.path.exists(SUMMARY_CACHE_FILE):
            age = time.time() - os.path.getmtime(SUMMARY_CACHE_FILE)
            if age < SUMMARY_TTL:
                try:
                    with open(SUMMARY_CACHE_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    cached["risk"] = risk_status()
                    _summary_cache.update(ts=os.path.getmtime(SUMMARY_CACHE_FILE), data=cached)
                    return cached
                except Exception:
                    pass

    # Try fetching fresh data from Thai RSC
    try:
        data = _fetch_aggregates()
        load = _camera_load_by_district()
        for d in data["districts"]:
            l = load.get(d["name"])
            d["cameras"] = l["cameras"] if l else 0
            d["online"] = l["online"] if l else 0
            d["avg_vehicles"] = round(l["vehicles"], 1) if l else 0
            d["moto_share"] = round(100 * l["motorcycles"] / l["vehicles"]) if l and l["vehicles"] else None
            d["heavy"] = l["heavy"] if l else 0
            d["moderate"] = l["moderate"] if l else 0
        data["districts"].sort(key=lambda d: (-d["dead"], -d["injured"]))
        data["risk"] = risk_status()

        # Save to disk cache
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(SUMMARY_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[RSC] Failed to cache summary: {e}")

        with _summary_lock:
            _summary_cache.update(ts=time.time(), data=data)
        return data
    except Exception as e:
        # If network fetch fails, attempt to return disk cache
        if os.path.exists(SUMMARY_CACHE_FILE):
            try:
                with open(SUMMARY_CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                cached["risk"] = risk_status()
                with _summary_lock:
                    _summary_cache.update(ts=time.time(), data=cached)
                print(f"[RSC] Fresh fetch failed ({e}), using disk cache")
                return cached
            except Exception:
                pass
        raise


# ---------------------------------------------------------------- accident points (per case)
def _points_path(year, district):
    return os.path.join(CACHE_DIR, f"points_{year}_{district}.json")


def _strip(case):
    """Keep location/time/severity, drop victim identity."""
    victims = case.get("victims") or []
    ages = [v.get("age") for v in victims if isinstance(v.get("age"), int)]
    return {
        "accno": (case.get("accno") or "").strip(),
        "date": case.get("accdate"),
        "lat": float(case["lat"]) if case.get("lat") else None,
        "lon": float(case["lon"]) if case.get("lon") else None,
        "place": (case.get("accplace") or "").strip(),
        "district": (case.get("amphurname") or "").strip(),
        "subdistrict": (case.get("tumbolname") or "").strip(),
        "injured": int(case.get("injured") or 0),
        "dead": int(case.get("dead") or 0),
        "victims": len(victims),
        "ages": ages,
        "male": sum(1 for v in victims if v.get("sex") == "M"),
        "female": sum(1 for v in victims if v.get("sex") == "F"),
    }


def fetch_district_points(year, district, force=False):
    """Points for one Bangkok district (geocode 1001..1050) in one CE year, cached on disk."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _points_path(year, district)
    current = year >= _now().year
    if not force and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if not current or age < POINTS_TTL_CURRENT:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    try:
        res = _post(f"{RSC_WS}/get/accident-points", {"province_code": BKK_GEOCODE, "district": district, "year": year}, timeout=120)
        if not res.get("data"):
            raise RuntimeError(res.get("status", {}).get("text") or "empty response")
        pts = [_strip(c) for c in res["data"]["accidents"]]
        pts = [p for p in pts if p["lat"] and p["lon"]]
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"year": year, "district": district, "fetched": int(time.time()), "points": pts}, f, ensure_ascii=False)
        return {"year": year, "district": district, "fetched": int(time.time()), "points": pts}
    except Exception as e:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise


def fetch_radius_points(lat, lon, radius_m, year):
    res = _post(f"{RSC_WS}/get/accident-points", {"lat": lat, "lon": lon, "radius": int(radius_m), "year": year}, timeout=120)
    if not res.get("data"):
        return []
    return [_strip(c) for c in res["data"]["accidents"]]


def _district_codes():
    data = _post(f"{RSC_API}/secondary/get_district_stats", {"geocode": BKK_GEOCODE})["Data"]
    return sorted(d["geocode"] for d in data)


# ---------------------------------------------------------------- camera risk
_risk_lock = threading.RLock()
_risk = {
    "status": "idle",         # idle | running | ready | error
    "progress": 0,
    "total": 0,
    "error": None,
    "built": 0,
    "years": [],
    "radius_m": RADIUS_M,
    "points": [],             # all Bangkok points (both years), stripped
    "cameras": [],            # per-camera risk rows
}


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _camera_rows(cameras, points, years, radius_m):
    """Count points within radius of each camera. Grid-bucket the points so 574 x 60k stays cheap."""
    cell = 0.005  # ~550 m
    grid = defaultdict(list)
    for p in points:
        if p.get("coarse"):
            continue
        grid[(int(p["lat"] / cell), int(p["lon"] / cell))].append(p)
    latest = {}
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        for r in conn.execute("SELECT camid, total, motorcycles, acc_total, acc_motorcycles, acc_scans, level, status FROM bma_latest"):
            latest[str(r["camid"])] = dict(r)
        conn.close()
    except sqlite3.Error:
        pass
    year_span = max(1, len(years))
    this_year = _now().year
    # fraction of the current year elapsed, so cases/yr is not deflated mid-year
    elapsed = (_now() - datetime(this_year, 1, 1, tzinfo=BKK_TZ)).days / 365.0
    exposure_years = sum(min(1.0, max(elapsed, 0.05)) if y == this_year else 1.0 for y in years)

    rows = []
    for cam in cameras:
        lat, lon = cam.get("latitude"), cam.get("longitude")
        if not lat or not lon:
            continue
        gi, gj = int(lat / cell), int(lon / cell)
        near = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for p in grid.get((gi + di, gj + dj), ()):
                    if _haversine_m(lat, lon, p["lat"], p["lon"]) <= radius_m:
                        near.append(p)
        cases = len(near)
        injured = sum(p["injured"] for p in near)
        dead = sum(p["dead"] for p in near)
        by_year = Counter(int(p["date"][:4]) for p in near if p.get("date"))
        by_month = Counter((p.get("date") or "")[:7] for p in near if p.get("date"))
        l = latest.get(str(cam.get("camid")), {})
        scans = l.get("acc_scans") or 0
        avg_vehicles = (l.get("acc_total") or 0) / scans if scans else (l.get("total") or 0)
        avg_moto = (l.get("acc_motorcycles") or 0) / scans if scans else (l.get("motorcycles") or 0)
        cases_per_year = cases / exposure_years
        rows.append({
            "camid": cam.get("camid"),
            "camera_code": cam.get("camera_code"),
            "title": cam.get("title"),
            "road": cam.get("road"),
            "district": cam.get("district"),
            "latitude": lat,
            "longitude": lon,
            "cases": cases,
            "cases_per_year": round(cases_per_year, 1),
            "injured": injured,
            "dead": dead,
            "by_year": {str(k): v for k, v in sorted(by_year.items())},
            "by_month": {k: v for k, v in sorted(by_month.items())[-12:]},
            "places": [pl for pl, _ in Counter(p["place"] for p in near if p["place"]).most_common(3)],
            "avg_vehicles": round(avg_vehicles, 1),
            "moto_share": round(100 * avg_moto / avg_vehicles) if avg_vehicles else None,
            # cases per year per vehicle seen in frame: separates "busy" from "dangerous"
            "exposure_rate": round(cases_per_year / avg_vehicles, 2) if avg_vehicles >= 1 else None,
            "level": l.get("level"),
            "status": l.get("status"),
        })
    # risk score: 0-100 percentile of cases_per_year, dead weighted x10
    scored = sorted(rows, key=lambda r: r["cases_per_year"] + 10 * r["dead"])
    n = len(scored)
    for i, r in enumerate(scored):
        r["risk_score"] = round(100 * i / max(1, n - 1)) if r["cases"] else 0
    rows.sort(key=lambda r: (-r["cases_per_year"] - 10 * r["dead"], -r["injured"]))
    return rows


def _build(cameras, years, radius_m, force):
    from concurrent.futures import ThreadPoolExecutor
    try:
        codes = _district_codes()
        jobs = [(y, c) for y in years for c in codes]
        with _risk_lock:
            _risk.update(status="running", progress=0, total=len(jobs), error=None, years=years, radius_m=radius_m)
        points = []
        seen = set()

        def one(job):
            y, c = job
            last = None
            for attempt in range(3):
                try:
                    return fetch_district_points(y, c, force=force)
                except Exception as e:  # noqa: BLE001 - retry on any transport error
                    last = e
                    time.sleep(2 * (attempt + 1))
            raise last

        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
            for res in ex.map(one, jobs):
                for p in res["points"]:
                    key = p["accno"] or (p["date"], p["lat"], p["lon"], p["place"])
                    if key in seen:
                        continue
                    seen.add(key)
                    points.append(p)
                with _risk_lock:
                    _risk["progress"] += 1
        coords = Counter((p["lat"], p["lon"]) for p in points)
        for p in points:
            p["coarse"] = coords[(p["lat"], p["lon"])] > COARSE_COORD_CASES
        rows = _camera_rows(cameras, points, years, radius_m)
        with _risk_lock:
            _risk.update(status="ready", points=points, cameras=rows, built=int(time.time()))
        with _summary_lock:
            _summary_cache["ts"] = 0  # so the district table picks up risk status
    except Exception as e:  # noqa: BLE001
        with _risk_lock:
            _risk.update(status="error", error=str(e))


def build_camera_risk(cameras, years=None, radius_m=RADIUS_M, force=False, background=True):
    """Fetch every Bangkok accident point for `years` and score each camera. Runs once in a thread."""
    years = years or [_now().year - 1, _now().year]
    with _risk_lock:
        if _risk["status"] == "running":
            return risk_status()
    if background:
        threading.Thread(target=_build, args=(cameras, years, radius_m, force), daemon=True, name="rsc-build").start()
    else:
        _build(cameras, years, radius_m, force)
    return risk_status()


def risk_status():
    with _risk_lock:
        return {k: _risk[k] for k in ("status", "progress", "total", "error", "built", "years", "radius_m")} | {
            "points": len(_risk["points"]),
            "coarse_points": sum(1 for p in _risk["points"] if p.get("coarse")),
            "cameras": len(_risk["cameras"]),
        }


def get_camera_risk(limit=None, district=None):
    with _risk_lock:
        rows = list(_risk["cameras"])
        status = risk_status()
    if district:
        rows = [r for r in rows if r.get("district") == district]
    if limit:
        rows = rows[:limit]
    return {"status": status, "items": rows}


def get_points(camid=None, cameras=None, radius_m=None, lat=None, lon=None, limit=2000):
    """Stripped points near a camera (or an explicit lat/lon), newest first. For map popups."""
    radius_m = radius_m or RADIUS_M
    if camid is not None and cameras:
        cam = next((c for c in cameras if str(c.get("camid")) == str(camid)), None)
        if cam:
            lat, lon = cam.get("latitude"), cam.get("longitude")
    with _risk_lock:
        pts = _risk["points"]
    if lat is None or lon is None:
        out = pts
    else:
        out = [p for p in pts if not p.get("coarse") and _haversine_m(lat, lon, p["lat"], p["lon"]) <= radius_m]
    out = sorted(out, key=lambda p: p.get("date") or "", reverse=True)[:limit]
    return {"total": len(out), "radius_m": radius_m, "items": out}


def get_points_geojson():
    """Every cached Bangkok point as GeoJSON for a map layer (no PII)."""
    with _risk_lock:
        pts = _risk["points"]
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
        "properties": {"d": p["date"], "i": p["injured"], "k": p["dead"], "p": p["place"][:80]},
    } for p in pts if not p.get("coarse")]
    return {"type": "FeatureCollection", "features": feats}


def warm(cameras):
    """Load cached points and summary at startup without blocking; refresh in the background."""
    if os.path.exists(SUMMARY_CACHE_FILE):
        try:
            with open(SUMMARY_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with _summary_lock:
                _summary_cache.update(ts=time.time(), data=data)
        except Exception:
            pass

    def _warm_summary():
        try:
            get_summary()
        except Exception as e:
            print(f"[RSC] Summary warm note: {e}")

    threading.Thread(target=_warm_summary, daemon=True, name="rsc-summary-warm").start()
    build_camera_risk(cameras, background=True)
