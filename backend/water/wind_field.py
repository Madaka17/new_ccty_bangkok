"""
Wind field over Thailand for the moving wind lines on the camera map.

Open-Meteo (no key, CC BY 4.0) gives the hourly 10 m wind on a 1 degree grid. One request asks for every
grid point with a few hours on each side of now, so the page can blend between the two hours around the
current time and the field keeps moving with the clock between refreshes. Every viewer shares the one
cached answer; the page never calls Open-Meteo itself.

Quota: GRID_POINTS location-calls per refresh. At FIELD_TTL that is about 1,500 a day per server, on top of
the water service's own Open-Meteo use, under the free 10,000 a day even with the test server running.
"""
import json
import math
import time
import urllib.parse
import urllib.request

from backend.water import water_service as ws

LAT0, LNG0 = 5.0, 96.0     # south-west corner of the grid
STEP = 1.0                 # degrees between grid points
NY, NX = 17, 11            # 5..21 N, 96..106 E: Thailand and its borders
GRID_POINTS = NY * NX
PAST_HOURS, NEXT_HOURS = 2, 6
FIELD_TTL = 3 * 3600       # the hours fetched still cover now until the next refresh


def _grid():
    """Grid points row by row from the south-west corner: row = latitude, column = longitude."""
    return [(round(LAT0 + j * STEP, 2), round(LNG0 + i * STEP, 2)) for j in range(NY) for i in range(NX)]


def _uv(speed, direction):
    """Speed (m/s) and the direction the wind comes FROM (degrees) -> eastward u, northward v."""
    if speed is None or direction is None:
        return 0.0, 0.0
    rad = math.radians(direction)
    return round(-speed * math.sin(rad), 2), round(-speed * math.cos(rad), 2)


def _build(blocks):
    """Open-Meteo answers (one per grid point, grid order) -> {frames: [{t, u, v}]} in grid order."""
    times = None
    for b in blocks:
        times = (b.get("hourly") or {}).get("time")
        if times:
            break
    if not times:
        raise ValueError("Open-Meteo answer has no hours")
    frames = []
    for k, t in enumerate(times):
        u, v = [], []
        for b in blocks:
            h = b.get("hourly") or {}
            speeds = h.get("wind_speed_10m") or []
            dirs = h.get("wind_direction_10m") or []
            pu, pv = _uv(ws._num(speeds[k]) if k < len(speeds) else None, ws._num(dirs[k]) if k < len(dirs) else None)
            u.append(pu)
            v.append(pv)
        frames.append({"t": int(t), "u": u, "v": v})
    return frames


def _load():
    pts = _grid()
    q = urllib.parse.urlencode({
        "latitude": ",".join(f"{p[0]:.2f}" for p in pts),
        "longitude": ",".join(f"{p[1]:.2f}" for p in pts),
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms", "timeformat": "unixtime",
        "past_hours": PAST_HOURS, "forecast_hours": NEXT_HOURS,
    })
    req = urllib.request.Request(f"{ws.OPEN_METEO}?{q}", headers={"User-Agent": ws.USER_AGENT})
    with urllib.request.urlopen(req, timeout=40) as resp:
        blocks = json.loads(resp.read().decode("utf-8"))
    if isinstance(blocks, dict):
        blocks = [blocks]
    if len(blocks) != GRID_POINTS:
        raise ValueError(f"Open-Meteo gave {len(blocks)} points, asked for {GRID_POINTS}")
    return {"updated_at": int(time.time()), "lat0": LAT0, "lng0": LNG0, "step": STEP, "nx": NX, "ny": NY,
            "frames": _build(blocks), "source": "Open-Meteo"}


def get():
    """The cached field, or an empty one when nothing was ever fetched (the map then shows no wind)."""
    try:
        data, stale = ws._cache.get("wind_field", FIELD_TTL, _load)
    except Exception:
        return {"updated_at": None, "frames": [], "stale": True}
    return {**data, "stale": stale}
