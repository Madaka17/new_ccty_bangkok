"""
Water level outlook for one ThaiWater gauge (/api/water/forecast/{station}): the last days of readings, HII's official
7-day forecast where there is one, and a small local model (tide harmonics + trend, or a rain recession for gated
canals) for the next 48 h. Moved out of water_service.py (Oct 2026).
"""
import math
import time
from datetime import datetime, timedelta

import numpy as np

from backend.water.thaiwater_api import _get
from backend.water.water_service import BKK_TZ, OFFICIAL_FORECAST_STATIONS, _cache, _num, _ts

FORECAST_TTL = 600
OBS_DAYS = 3        # history used for the local model
EST_HOURS = 48      # local outlook horizon
# Tidal constituents (period in hours): M2, S2, N2, K1, O1
TIDE_PERIODS_H = (12.4206, 12.0, 12.6583, 23.9345, 25.8193)


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
