"""One Bangkok district (khet) at a glance: dust, flood sensors, flood reports, traffic, cameras, accidents,
closures and calendar events, all read from data the server already holds (no new external calls).

build(name, sources) takes callables/values for each source (see the routes in api/traffic.py) so it can be
tested without the live services. A section whose feed is down or never loaded is None; a live feed with
nothing in the district is an empty list (or, for air/flood/traffy, None because there is no reading to show).
"""
import re
import time
from urllib.parse import unquote

from backend.traffic.events_calendar import bangkok_districts
from backend.water.air_service import LEVELS, _pm25_band

BANGKOK = "กรุงเทพมหานคร"
PREFIX = "เขต"
REPORT_HOURS = 6
LATEST = 5
AREA_CODE_BANGKOK = "10"
KHET_RE = re.compile(r"เขต\s*([\u0e00-\u0e7f]+)")

DISTRICTS = sorted(bangkok_districts())
_DISTRICT_SET = frozenset(DISTRICTS)


def normalise(name):
    """'เขตดินแดง', 'ดินแดง', URL-encoded or padded -> 'ดินแดง'."""
    text = unquote(str(name or "")).strip()
    if text.startswith(PREFIX):
        text = text[len(PREFIX):].strip()
    return text


def is_district(name):
    return normalise(name) in _DISTRICT_SET


def _items(status):
    if isinstance(status, dict):
        return list(status.get("items") or [])
    return list(status or [])


def _not_bangkok(province):
    """True when an item says it is outside Bangkok (items with no province are kept)."""
    return bool(province) and province != BANGKOK


def _last_khet(text):
    """The district after the last เขต in an area label (the same rule as the web districtRanking)."""
    found = KHET_RE.findall(text or "")
    return found[-1] if found else None


def _call(sources, key):
    """The value of one source, None when it is missing or fails (= the feed is down or never loaded)."""
    src = sources.get(key)
    if src is None:
        return None
    try:
        return src() if callable(src) else src
    except Exception:  # noqa: BLE001 - one feed failing must not blank the page
        return None


def _locate_district(locate, lat, lng):
    """District at a position through area_traffic.locate, only when that spot is inside Bangkok."""
    if locate is None or lat is None or lng is None:
        return ""
    try:
        province, district = locate(lat, lng)
    except Exception:  # noqa: BLE001 - a bad position is just unplaced
        return ""
    return normalise(district) if province == BANGKOK else ""


def _air(status, name):
    stations = []
    for it in _items(status):
        pm25 = it.get("pm25")
        if not isinstance(pm25, (int, float)) or pm25 < 0 or it.get("province") != BANGKOK:
            continue
        if _last_khet(it.get("area")) == name:
            stations.append(pm25)
    if not stations:
        return None
    avg = round(sum(stations) / len(stations), 1)
    lv = LEVELS[_pm25_band(avg)]
    return {"pm25": avg, "level": lv["level"], "label": lv["label"], "points": len(stations)}


def _flood(feed, name):
    """Road water sensors in the district. feed = every station plus the feed's error and updated_at.
    None when the feed is down or never loaded, or the district has no live sensor (offline ones do not count)."""
    if not isinstance(feed, dict) or feed.get("updated_at") is None or feed.get("error"):
        return None
    live = [i for i in feed.get("items") or []
            if i.get("status") != "offline" and normalise(i.get("district")) == name]
    if not live:
        return None
    wet = [i for i in live if i.get("status") in ("flood", "slight")]
    points = [{"where": i.get("short_name") or i.get("name") or "", "road": i.get("road"),
               "level_cm": i.get("level_cm"), "status": i.get("status")} for i in wet]
    return {"sensors": len(live), "wet": len(wet), "points": points,
            "max_cm": max((i.get("level_cm") or 0) for i in live)}


def _reports(status, name, locate, now):
    if not isinstance(status, dict):
        return None
    items = _items(status)
    if status.get("updated_at") is None and not items:
        return None
    mine = []
    for it in items:
        ts = it.get("ts")
        if not isinstance(ts, (int, float)) or now - ts > REPORT_HOURS * 3600:
            continue
        district = normalise(it.get("district"))
        if not district:
            district = _locate_district(locate, it.get("lat"), it.get("lng"))
        if district == name:
            mine.append(it)
    mine.sort(key=lambda i: -i["ts"])
    latest = [{k: i.get(k) for k in ("id", "text", "ts", "address", "url")} for i in mine[:LATEST]]
    return {"count": len(mine), "latest": latest}


def _traffic(area, name):
    if not isinstance(area, dict):
        return None
    for prov in area.get("provinces") or []:
        if str(prov.get("code")) != AREA_CODE_BANGKOK:
            continue
        for amp in prov.get("amphoes") or []:
            if normalise(amp.get("name")) == name and amp.get("flow") is not None:
                flow = amp["flow"]
                level = "คล่องตัว" if flow >= 75 else ("ชะลอตัว" if flow >= 45 else "ติดขัด")
                return {"score": flow, "level": level}
    return None


def _cameras(rows, name):
    out = []
    for r in rows:
        if normalise(r.get("district")) == name:
            out.append({k: r.get(k) for k in ("camid", "title", "road", "level", "total", "status")})
    return out


def _road_items(items, name, locate):
    out = []
    for it in items or []:
        if _not_bangkok(it.get("province")):
            continue
        district = normalise(it.get("amphoe") or it.get("district"))
        if not district:
            district = _locate_district(locate, it.get("latitude"), it.get("longitude"))
        if district == name:
            out.append({"kind": it.get("kind"), "title": it.get("title"),
                        "lat": it.get("latitude"), "lng": it.get("longitude")})
    return out


def _events(cal, name):
    return [dict(e) for e in cal if normalise(e.get("district")) == name and not _not_bangkok(e.get("province"))]


def build(name, sources, now=None):
    """The district's page data, or None when the name is not one of the 50 Bangkok districts."""
    key = normalise(name)
    if key not in _DISTRICT_SET:
        return None
    now = time.time() if now is None else now
    locate = sources.get("locate")
    road = _call(sources, "incidents")
    cameras = _call(sources, "cameras")
    cal = _call(sources, "calendar")
    flood = _call(sources, "flood")
    traffy = _call(sources, "traffy")
    road_live = isinstance(road, dict) and road.get("updated_at") is not None
    return {
        "district": key,
        "updated_at": int(now),
        "air": _air(_call(sources, "air") or [], key),
        "flood": _flood(flood, key),
        "reports": _reports(traffy, key, locate, now) if traffy is not None else None,
        "traffic": _traffic(_call(sources, "area_traffic"), key),
        "cameras": None if cameras is None else _cameras(cameras, key),
        "incidents": _road_items(road.get("incidents"), key, locate) if road_live else None,
        "closures": _road_items(road.get("closures"), key, locate) if road_live else None,
        "events": None if cal is None else _events(cal, key),
    }
