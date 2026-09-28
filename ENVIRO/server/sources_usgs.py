"""Genuine integration with the USGS public earthquake feed (no API key required).

Docs: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
This is the one external source in the "compare sources" view backed by a
real, live, public API. TMD / GISTDA / NASA require agency-specific
credentials we don't have, so those stay clearly-labelled illustrative rows
(see server/db.py: sources_static) until real access is arranged.
"""
import json
import threading
import time
import urllib.request

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"
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
        data = json.loads(resp.read().decode("utf-8"))
    features = data.get("features", [])
    latest = None
    if features:
        f = features[0]
        props = f["properties"]
        coords = f["geometry"]["coordinates"]
        latest = {
            "place": props.get("place"),
            "magnitude": props.get("mag"),
            "depth_km": coords[2] if len(coords) > 2 else None,
            "time_ms": props.get("time"),
            "url": props.get("url"),
        }
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
