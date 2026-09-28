"""Genuine integration with EMSC's real-time seismic portal (no API key required).

Docs: https://www.seismicportal.eu/fdsnws/event/1/ (FDSN event webservice)
EMSC (European-Mediterranean Seismological Centre) republishes near-real-time
picks from ~65 national/regional seismic networks worldwide -- a second,
independently-run live source alongside USGS for the "compare sources" view.
"""
import json
import threading
import time
import urllib.request
import urllib.parse

FEED_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
POLL_SECONDS = 300
TIMEOUT_SECONDS = 6

_lock = threading.Lock()
_state = {"connected": False, "checked_at": None, "latest": None, "error": None}


def get_state():
    with _lock:
        return dict(_state)


def _poll_once():
    qs = urllib.parse.urlencode({"format": "json", "limit": 1, "orderby": "time"})
    req = urllib.request.Request(f"{FEED_URL}?{qs}", headers={"User-Agent": "enviro-seismic-command/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    features = data.get("features", [])
    latest = None
    if features:
        props = features[0]["properties"]
        latest = {
            "place": props.get("flynn_region"),
            "magnitude": props.get("mag"),
            "depth_km": props.get("depth"),
            "time": props.get("time"),
            "auth": props.get("auth"),
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
        except Exception as exc:
            with _lock:
                _state["connected"] = False
                _state["checked_at"] = time.time()
                _state["error"] = str(exc)
        stop_event.wait(POLL_SECONDS)
