"""One Bangkok district (khet) at a glance: dust, flood sensors, flood reports, traffic, cameras, accidents,
closures and calendar events, all read from data the server already holds (no new external calls).

build(name, sources) takes callables/values for each source (see SOURCE_KEYS) so it can be tested without the
live services. A section with no data is None (or [] for list sections), never a made-up 0.
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


def _last_khet(text):
    """The district after the last เขต in an area label (the same rule as the web districtRanking)."""
    found = KHET_RE.findall(text or "")
    return found[-1] if found else None


def _call(sources, key):
    """The value of one source, None when it is missing or fails."""
    src = sources.get(key)
    if src is None:
        return None
    try:
        return src() if callable(src) else src
    except Exception:  # noqa: BLE001 - one feed failing must not blank the page
        return None


def _air(status, name):
    stations = []
    for it in _items(status):
        pm25 = it.get("pm25")
        if not isinstance(pm25, (int, float)) or pm25 < 0:
            continue
        if _last_khet(it.get("area")) == name:
            stations.append(pm25)
    if not stations:
        return None
    avg = round(sum(stations) / len(stations), 1)
    lv = LEVELS[_pm25_band(avg)]
    return {"pm25": avg, "level": lv["level"], "label": lv["label"], "points": len(stations)}


def _flood(status, name):
    if isinstance(status, dict):
        wet = status.get("wet")
        if wet is None:
            wet = [i for i in status.get("items") or [] if i.get("status") in ("flood", "slight")]
    else:
        wet = list(status or [])
    points = []
    for it in wet:
        if normalise(it.get("district")) != name:
            continue
        points.append({"where": it.get("short_name") or it.get("name") or "", "road": it.get("road"),
                       "level_cm": it.get("level_cm"), "status": it.get("status")})
    if not points:
        return None
    return {"points": points, "max_cm": max((p["level_cm"] or 0) for p in points)}


def _locate_district(locate, lat, lng):
    """District at a position through area_traffic.locate, '' when unknown or no position."""
    if locate is None or lat is None or lng is None:
        return ""
    try:
        return normalise(locate(lat, lng)[1])
    except Exception:  # noqa: BLE001 - a bad position is just unplaced
        return ""


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
    for r in rows or []:
        if normalise(r.get("district")) == name:
            out.append({k: r.get(k) for k in ("camid", "title", "road", "level", "total", "status")})
    return out


def _road_items(items, name, locate):
    out = []
    for it in items or []:
        district = normalise(it.get("amphoe") or it.get("district"))
        if not district:
            district = _locate_district(locate, it.get("latitude"), it.get("longitude"))
        if district == name:
            out.append({"kind": it.get("kind"), "title": it.get("title"),
                        "lat": it.get("latitude"), "lng": it.get("longitude")})
    return out


def build(name, sources, now=None):
    """The district's page data, or None when the name is not one of the 50 Bangkok districts."""
    key = normalise(name)
    if key not in _DISTRICT_SET:
        return None
    now = time.time() if now is None else now
    locate = sources.get("locate")
    road = _call(sources, "incidents") or {}
    cal = _call(sources, "calendar") or []
    flood = _call(sources, "flood")
    traffy = _call(sources, "traffy")
    return {
        "district": key,
        "updated_at": int(now),
        "air": _air(_call(sources, "air") or [], key),
        "flood": _flood(flood, key) if flood is not None else None,
        "reports": _reports(traffy, key, locate, now) if traffy is not None else None,
        "traffic": _traffic(_call(sources, "area_traffic"), key),
        "cameras": _cameras(_call(sources, "cameras") or [], key),
        "incidents": _road_items(road.get("incidents"), key, locate),
        "closures": _road_items(road.get("closures"), key, locate),
        "events": [dict(e) for e in cal if normalise(e.get("district")) == key],
    }
