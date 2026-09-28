"""Genuine integration with GEOFON's public earthquake feed (no API key required).

Docs: https://geofon.gfz-potsdam.de/waveform/webservices.php (FDSN Event)
GEOFON (GFZ Potsdam) is one of the three primary worldwide catalogs this
project cross-checks the Edge AI against, alongside USGS and EMSC (see the
earthquake-severity reference doc). Its FDSN Event webservice only supports
`format=text` (pipe-delimited), not GeoJSON.
"""
import threading
import time
import urllib.request

FEED_URL = "https://geofon.gfz-potsdam.de/fdsnws/event/1/query?format=text&minmagnitude=2.5&limit=1&orderby=time"
POLL_SECONDS = 300
TIMEOUT_SECONDS = 6

_lock = threading.Lock()
_state = {"connected": False, "checked_at": None, "latest": None, "error": None}


def get_state():
    with _lock:
        return dict(_state)


def _poll_once():
    req = urllib.request.Request(FEED_URL, headers={"User-Agent": "enviro-seismic-command/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8")
    latest = None
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("|")
        if len(cols) < 14:
            continue
        try:
            latest = {
                "place": cols[12] or None,
                "magnitude": float(cols[10]) if cols[10] else None,
                "depth_km": float(cols[4]) if cols[4] else None,
                "time_ms": None,
                "url": f"https://geofon.gfz-potsdam.de/eqinfo/event.php?id={cols[0]}",
            }
        except ValueError:
            continue
        break
    with _lock:
        _state["connected"] = True
        _state["checked_at"] = time.time()
        _state["latest"] = latest
        _state["error"] = None


def run_forever(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            _poll_once()
        except Exception as exc:  # network errors, DNS blocked in sandbox, etc.
            with _lock:
                _state["connected"] = False
                _state["checked_at"] = time.time()
                _state["error"] = str(exc)
        stop_event.wait(POLL_SECONDS)
