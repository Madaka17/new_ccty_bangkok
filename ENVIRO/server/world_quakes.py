"""Real, live earthquake locations from public feeds -- no API key needed.

Merged from several independent real sources, per the earthquake-severity
reference doc's recommendation to cross-check the Edge AI against USGS
Earthquake Hazards Program, EMSC Seismic Portal, and GEOFON as the primary
worldwide catalogs, plus TMD for events inside Thailand specifically:
  - "global": significant quakes worldwide (M4.5+), from USGS and GEOFON
  - "regional": a bounding-box query covering Thailand + its seismically
    active neighbors (Myanmar, Laos, Andaman Sea, southern China), from
    USGS, EMSC, AND GEOFON independently, so real (if modest) nearby
    seismicity shows up even when nothing worldwide is currently M4.5+.
    Thailand itself is genuinely a low-seismicity country in these catalogs
    -- most real activity near it originates in Myanmar/Indonesia, not
    inside Thailand's own borders. That's a fact about the real world, not
    a gap in this app.
  - "TMD": Thailand's own Meteorological Department network
    (earthquake.tmd.go.th), which -- being a dense in-country network --
    genuinely detects small local Thai quakes (down to ~M1.5) that never
    reach international catalogs like USGS/EMSC/GEOFON at all. This is the
    undocumented but public JSON the department's own live map page fetches
    (found by reading that page's own <script> source), not a private API.
  - "GEOFON": GFZ Potsdam's global network (geofon.gfz-potsdam.de), a third
    independent worldwide catalog -- its FDSN Event webservice only supports
    `format=text` (pipe-delimited), not GeoJSON, hence the custom parser below.

The background cache (_poll_once, refreshed every POLL_SECONDS) always holds
the widest window each source supports (90 days) -- the "90 วัน / 7 วัน /
วันนี้" filter on /api/world/earthquakes (server/routes/world.py) just slices
this cache by `time_ms` at request time, so switching the filter is instant
and doesn't re-query any external API.

Every event this cache ever sees is also permanently written to the
`world_quake_history` SQLite table (see schema.sql) -- the in-memory cache
above is lost on restart and never exceeds each source's own retention
window, but the DB table accumulates real history for as long as this
system keeps running, which is what a future Edge AI trend/forecast feature
would actually need to train or reason against.
"""
import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import db as dbmod

USGS_REGIONAL_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EMSC_REGIONAL_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
GEOFON_URL = "https://geofon.gfz-potsdam.de/fdsnws/event/1/query"
TMD_URL = "https://earthquake.tmd.go.th/map-events.json"
TMD_TZ = timezone(timedelta(hours=7))  # TMD publishes event times in Thailand local time (ICT, UTC+7)

# A TMD event is treated as "active / just happened" (and blinks on the map)
# for this long after its origin time -- long enough to stay visible for a
# user who opens the page shortly after a real local quake, short enough
# that it stops demanding attention once it's just historical record.
RECENT_QUAKE_MINUTES = 60

# Thailand + Myanmar/Laos/Andaman Sea/southern China -- where real regional
# seismicity that could be felt in Thailand actually originates.
REGION_BBOX = {"minlat": 0.0, "maxlat": 28.0, "minlon": 90.0, "maxlon": 110.0}
REGIONAL_MINMAG = 2.0
REGIONAL_DAYS = 90

# The background cache always fetches this widest window for worldwide
# significant quakes too (not just the old fixed 7-day feed), so the
# "90 วัน / 7 วัน / วันนี้" UI filter (server/routes/world.py) can just slice
# the cache by time instead of re-querying external APIs on every change.
GLOBAL_MINMAG = 4.5
GLOBAL_DAYS = 90

POLL_SECONDS = 300
TIMEOUT_SECONDS = 10

_lock = threading.Lock()
_state = {"connected": False, "checked_at": None, "quakes": [], "error": None, "history_error": None}


def get_state():
    with _lock:
        return dict(_state)


# How close a detected/simulated event has to be to a real published quake in
# this cache to count as independently corroborated by it -- loose enough to
# tolerate this simulator's own synthetic magnitude-estimation error and each
# external network's own location/origin-time uncertainty, tight enough that
# an unrelated quake elsewhere in the 90-day window can't false-match.
EXTERNAL_MATCH_MAX_DIST_KM = 300
EXTERNAL_MATCH_MAX_TIME_MIN = 15
EXTERNAL_MATCH_MAG_TOL = 1.5


def find_corroborating_quake(lat, lng, time_ms, magnitude=None):
    """Cross-check a detected event against this same live USGS/EMSC/GEOFON/
    TMD cache already used for the world map/ticker -- per this module's own
    docstring, these are exactly the independent real networks the
    earthquake-severity reference doc recommends cross-checking the Edge AI
    against. A real published event close enough in location, time, and
    (when known) magnitude counts as strong independent corroboration
    alongside this simulator's own station count, the same way a real EEW
    operator treats agreement with an external network. Returns the closest
    matching quake dict (as stored in this cache) plus its distance, or None.
    """
    from .geo import haversine_km  # local import: geo.py has no reason to depend on this module

    if lat is None or lng is None or time_ms is None:
        return None
    best, best_dist = None, None
    for q in get_state().get("quakes", []):
        if q.get("lat") is None or q.get("lng") is None or q.get("time_ms") is None:
            continue
        if abs(q["time_ms"] - time_ms) > EXTERNAL_MATCH_MAX_TIME_MIN * 60 * 1000:
            continue
        if magnitude is not None and q.get("magnitude") is not None and abs(q["magnitude"] - magnitude) > EXTERNAL_MATCH_MAG_TOL:
            continue
        dist_km = haversine_km(lat, lng, q["lat"], q["lng"])
        if dist_km > EXTERNAL_MATCH_MAX_DIST_KM:
            continue
        if best is None or dist_km < best_dist:
            best, best_dist = q, dist_km
    if best is None:
        return None
    return {
        "source": best["source"], "place": best.get("place"), "magnitude": best.get("magnitude"),
        "dist_km": round(best_dist, 1), "url": best.get("url"),
    }


def _fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "enviro-seismic-command/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_text(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "enviro-seismic-command/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


def _parse_geofon_text(raw):
    # #EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|
    # ContributorID|MagType|Magnitude|MagAuthor|EventLocationName|EventType
    out = []
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("|")
        if len(cols) < 14:
            continue
        event_id, time_str, lat, lng, depth = cols[0], cols[1], cols[2], cols[3], cols[4]
        magnitude, place = cols[10], cols[12]
        time_ms = None
        try:
            # GEOFON times are UTC (FDSN convention) with sub-second precision
            # that isn't always 6 digits, which Python's fromisoformat (on
            # older runtimes) rejects -- truncate to whole seconds instead.
            clean_time = time_str.split(".")[0]
            time_ms = int(datetime.fromisoformat(clean_time).replace(tzinfo=timezone.utc).timestamp() * 1000)
        except Exception:
            time_ms = None
        try:
            out.append({
                "id": "geofon-" + event_id,
                "lat": float(lat), "lng": float(lng), "depth_km": float(depth) if depth else None,
                "magnitude": float(magnitude) if magnitude else None, "place": place or None,
                "time_ms": time_ms, "url": f"https://geofon.gfz-potsdam.de/eqinfo/event.php?id={event_id}",
                "source": "GEOFON",
            })
        except ValueError:
            continue
    return out


def _usgs_global():
    # The convenience "week.geojson" feed only ever covers 7 days. To let the
    # UI offer a real 90-day view too, query the general FDSN endpoint (same
    # one _usgs_regional uses) with a 90-day start time and no bounding box
    # instead -- the background cache always holds the widest window; the
    # route then filters down to whatever the user actually asked for.
    #
    # limit=10000: M4.5+ worldwide genuinely runs ~2,000-2,500 events per 90
    # days (confirmed against the real feed -- USGS's own long-term average
    # for M4.5+ is on the order of 20+/day) -- a lower cap like 1000 silently
    # truncates roughly half of the real dataset without ever surfacing an
    # error, which is worse than an honest failure.
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - GLOBAL_DAYS * 86400))
    qs = urllib.parse.urlencode({
        "format": "geojson", "starttime": start, "minmagnitude": GLOBAL_MINMAG,
        "orderby": "time", "limit": 10000,
    })
    data = _fetch_json(f"{USGS_REGIONAL_URL}?{qs}")
    out = []
    for f in data.get("features", []):
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        out.append({
            "id": "usgs-" + str(f.get("id")),
            "lat": coords[1], "lng": coords[0], "depth_km": coords[2] if len(coords) > 2 else None,
            "magnitude": props.get("mag"), "place": props.get("place"),
            "time_ms": props.get("time"), "url": props.get("url"),
            "source": "USGS", "regional": False,
        })
    return out


def _usgs_regional():
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - REGIONAL_DAYS * 86400))
    qs = urllib.parse.urlencode({
        "format": "geojson", "starttime": start,
        "minlatitude": REGION_BBOX["minlat"], "maxlatitude": REGION_BBOX["maxlat"],
        "minlongitude": REGION_BBOX["minlon"], "maxlongitude": REGION_BBOX["maxlon"],
        "minmagnitude": REGIONAL_MINMAG, "orderby": "time",
    })
    data = _fetch_json(f"{USGS_REGIONAL_URL}?{qs}")
    out = []
    for f in data.get("features", []):
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        out.append({
            "id": "usgs-" + str(f.get("id")),
            "lat": coords[1], "lng": coords[0], "depth_km": coords[2] if len(coords) > 2 else None,
            "magnitude": props.get("mag"), "place": props.get("place"),
            "time_ms": props.get("time"), "url": props.get("url"),
            "source": "USGS", "regional": True,
        })
    return out


def _emsc_regional():
    qs = urllib.parse.urlencode({
        "format": "json", "limit": 100, "orderby": "time",
        "minlat": REGION_BBOX["minlat"], "maxlat": REGION_BBOX["maxlat"],
        "minlon": REGION_BBOX["minlon"], "maxlon": REGION_BBOX["maxlon"],
        "minmag": REGIONAL_MINMAG,
    })
    data = _fetch_json(f"{EMSC_REGIONAL_URL}?{qs}")
    out = []
    for f in data.get("features", []):
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        time_ms = None
        raw_time = props.get("time")
        if raw_time:
            try:
                clean = raw_time.replace("Z", "+00:00")
                time_ms = int(datetime.fromisoformat(clean).timestamp() * 1000)
            except Exception:
                time_ms = None
        out.append({
            "id": "emsc-" + str(f.get("id") or props.get("unid")),
            "lat": coords[1], "lng": coords[0], "depth_km": coords[2] if len(coords) > 2 else None,
            "magnitude": props.get("mag"), "place": props.get("flynn_region"),
            "time_ms": time_ms,
            "url": f"https://www.seismicportal.eu/eventdetails.html?unid={props.get('unid')}" if props.get("unid") else None,
            "source": "EMSC", "regional": True,
        })
    return out


def _geofon_global():
    # See the limit comment on _usgs_global -- same real-world event volume
    # applies here (~1,500-2,000 M4.5+ events/90 days seen on this feed).
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - GLOBAL_DAYS * 86400))
    qs = urllib.parse.urlencode({"format": "text", "starttime": start, "minmagnitude": GLOBAL_MINMAG, "orderby": "time", "limit": 10000})
    raw = _fetch_text(f"{GEOFON_URL}?{qs}")
    out = _parse_geofon_text(raw)
    for q in out:
        q["regional"] = False
    return out


def _geofon_regional():
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - REGIONAL_DAYS * 86400))
    qs = urllib.parse.urlencode({
        "format": "text", "starttime": start, "orderby": "time",
        "minlatitude": REGION_BBOX["minlat"], "maxlatitude": REGION_BBOX["maxlat"],
        "minlongitude": REGION_BBOX["minlon"], "maxlongitude": REGION_BBOX["maxlon"],
        "minmagnitude": REGIONAL_MINMAG,
    })
    raw = _fetch_text(f"{GEOFON_URL}?{qs}")
    out = _parse_geofon_text(raw)
    for q in out:
        q["regional"] = True
    return out


def _tmd_thailand():
    # TMD's own live-map page fetches this exact path with no auth beyond a
    # normal browser User-Agent/Referer -- undocumented, but genuinely public.
    data = _fetch_json(TMD_URL, headers={
        "User-Agent": "enviro-seismic-command/1.0",
        "Referer": "https://earthquake.tmd.go.th/",
    })
    out = []
    for ev in data.get("events", []):
        time_ms = None
        raw = ev.get("otime")
        if raw:
            try:
                dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TMD_TZ)
                time_ms = int(dt.timestamp() * 1000)
            except Exception:
                time_ms = None
        event_id = ev.get("eventID")
        path = ev.get("path")
        out.append({
            "id": "tmd-" + str(event_id),
            "lat": ev.get("lat"), "lng": ev.get("lon"), "depth_km": ev.get("depth"),
            "magnitude": ev.get("mag"), "place": ev.get("region"),
            "time_ms": time_ms,
            "url": f"https://earthquake.tmd.go.th/{path}" if path else "https://earthquake.tmd.go.th/",
            "source": "TMD", "regional": True,
        })
    return out


# ---- On-demand historical backfill (ปี/เดือน/สถานที่ history browser) ----
# The background cache above only ever holds each source's own short live
# window (90 days). These query the SAME FDSN endpoints with an arbitrary
# starttime/endtime instead, so selecting a year/month outside that live
# window can still pull real data on demand. TMD has no historical range
# API (its feed is "what's on the live map right now" only, no date
# parameter), so backfill only ever covers USGS/EMSC/GEOFON.
HISTORICAL_MINMAG = 4.0  # keeps a worldwide month/year backfill's result size reasonable
BACKFILL_MAX_YEARS_BACK = 3  # per explicit request -- not a real API limit (USGS's own history goes back a century+)


def _usgs_range(start_iso, end_iso):
    qs = urllib.parse.urlencode({
        "format": "geojson", "starttime": start_iso, "endtime": end_iso,
        "minmagnitude": HISTORICAL_MINMAG, "orderby": "time", "limit": 20000,
    })
    data = _fetch_json(f"{USGS_REGIONAL_URL}?{qs}")
    out = []
    for f in data.get("features", []):
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        out.append({
            "id": "usgs-" + str(f.get("id")),
            "lat": coords[1], "lng": coords[0], "depth_km": coords[2] if len(coords) > 2 else None,
            "magnitude": props.get("mag"), "place": props.get("place"),
            "time_ms": props.get("time"), "url": props.get("url"),
            "source": "USGS", "regional": False,
        })
    return out


def _emsc_range(start_iso, end_iso):
    qs = urllib.parse.urlencode({
        "format": "json", "limit": 10000, "orderby": "time",
        "starttime": start_iso, "endtime": end_iso, "minmag": HISTORICAL_MINMAG,
    })
    data = _fetch_json(f"{EMSC_REGIONAL_URL}?{qs}")
    out = []
    for f in data.get("features", []):
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        time_ms = None
        raw_time = props.get("time")
        if raw_time:
            try:
                time_ms = int(datetime.fromisoformat(raw_time.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                time_ms = None
        out.append({
            "id": "emsc-" + str(f.get("id") or props.get("unid")),
            "lat": coords[1], "lng": coords[0], "depth_km": coords[2] if len(coords) > 2 else None,
            "magnitude": props.get("mag"), "place": props.get("flynn_region"),
            "time_ms": time_ms,
            "url": f"https://www.seismicportal.eu/eventdetails.html?unid={props.get('unid')}" if props.get("unid") else None,
            "source": "EMSC", "regional": False,
        })
    return out


def _geofon_range(start_iso, end_iso):
    qs = urllib.parse.urlencode({
        "format": "text", "starttime": start_iso, "endtime": end_iso,
        "minmagnitude": HISTORICAL_MINMAG, "orderby": "time", "limit": 20000,
    })
    raw = _fetch_text(f"{GEOFON_URL}?{qs}")
    out = _parse_geofon_text(raw)
    for q in out:
        q["regional"] = False
    return out


def run_historical_backfill(year, month=None):
    """On-demand real backfill for the ปี/เดือน/สถานที่ history browser --
    queries USGS/EMSC/GEOFON's real FDSN endpoints for the given calendar
    year (or year+month) and persists whatever they return into
    world_quake_history (see _persist_history), exactly like the live
    poller already does. Raises ValueError if `year` is outside the
    supported lookback window."""
    now = datetime.now(timezone.utc)
    if year < now.year - BACKFILL_MAX_YEARS_BACK or year > now.year:
        raise ValueError(f"year must be within the last {BACKFILL_MAX_YEARS_BACK} years")
    if month and not (1 <= month <= 12):
        raise ValueError("month must be 1-12")

    if month:
        start_dt = datetime(year, month, 1, tzinfo=timezone.utc)
        end_dt = (datetime(year + 1, 1, 1, tzinfo=timezone.utc) if month == 12
                  else datetime(year, month + 1, 1, tzinfo=timezone.utc))
    else:
        start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    end_dt = min(end_dt, now)  # never query into the future
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    results = {}
    all_quakes = []
    for name, fn in (("USGS", _usgs_range), ("EMSC", _emsc_range), ("GEOFON", _geofon_range)):
        try:
            quakes = fn(start_iso, end_iso)
            all_quakes.extend(quakes)
            results[name] = {"fetched": len(quakes), "error": None}
        except Exception as exc:
            results[name] = {"fetched": 0, "error": str(exc)}

    _persist_history(all_quakes)
    return {"range": {"start": start_iso, "end": end_iso}, "by_source": results, "total_fetched": len(all_quakes)}


_FETCHERS = (_usgs_global, _usgs_regional, _emsc_regional, _geofon_global, _geofon_regional, _tmd_thailand)


def _poll_once():
    quakes = []
    errors = []
    for fn in _FETCHERS:
        try:
            quakes.extend(fn())
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")
    # de-dupe near-identical picks of the same real event from multiple
    # independent networks (within ~0.3 deg and 5 minutes of each other)
    deduped = []
    for q in sorted(quakes, key=lambda q: q.get("time_ms") or 0, reverse=True):
        dup = False
        for kept in deduped:
            if (abs(kept["lat"] - q["lat"]) < 0.3 and abs(kept["lng"] - q["lng"]) < 0.3
                    and abs((kept.get("time_ms") or 0) - (q.get("time_ms") or 0)) < 5 * 60 * 1000):
                dup = True
                break
        if not dup:
            deduped.append(q)
    with _lock:
        _state["connected"] = len(errors) < len(_FETCHERS)  # at least one source reachable
        _state["checked_at"] = time.time()
        _state["quakes"] = deduped
        _state["error"] = "; ".join(errors) if errors else None
    _persist_history(deduped)


def _persist_history(quakes):
    """INSERT OR IGNORE, keyed on each event's own source-prefixed id, so
    repeated polls of the same real event are silently no-ops -- only
    genuinely new events add a row. This is what makes world_quake_history
    accumulate real history over the system's running lifetime instead of
    just mirroring whatever the live cache currently holds."""
    if not quakes:
        return
    now = dbmod.now_iso()
    rows = [
        (q["id"], q["source"], q["lat"], q["lng"], q.get("depth_km"), q.get("magnitude"),
         q.get("place"), q.get("time_ms"), int(bool(q.get("regional"))), q.get("url"), now)
        for q in quakes
    ]
    try:
        conn = dbmod.get_conn()
        conn.executemany(
            "INSERT OR IGNORE INTO world_quake_history"
            "(id, source, lat, lng, depth_km, magnitude, place, time_ms, regional, url, first_seen_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()
        with _lock:
            _state["history_error"] = None
    except Exception as exc:
        # Kept separate from `_state["error"]` (external feed connectivity) --
        # a DB write failure here doesn't mean USGS/EMSC/GEOFON/TMD are
        # unreachable, so it shouldn't be reported as "ขาดการเชื่อมต่อ". It's
        # still surfaced via get_state() rather than swallowed, so a broken
        # persistence layer doesn't fail silently forever.
        with _lock:
            _state["history_error"] = str(exc)


def run_forever(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            _poll_once()
        except Exception as exc:
            with _lock:
                _state["connected"] = False
                _state["checked_at"] = time.time()
                _state["error"] = str(exc)
        stop_event.wait(POLL_SECONDS)
