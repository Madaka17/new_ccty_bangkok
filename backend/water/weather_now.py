"""
Weather right now at one spot, for the "อากาศตรงนี้" tile on the dashboard.

MET Norway Locationforecast (api.met.no, no key; its terms ask for an identifying User-Agent) gives the
current hour's temperature, humidity and a weather symbol. Open-Meteo is not used here: the water
service already spends this server's daily Open-Meteo quota. Answers are cached per ~1 km cell for
CACHE_SECONDS, so every viewer in the same area shares one upstream call.
"""
import calendar
import json
import threading
import time
import urllib.request

URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lng}"
USER_AGENT = "BKK-StreetSmart/1.0 github.com/Madaka17/new_ccty_bangkok"
CACHE_SECONDS = 600
BKK = (13.756, 100.502)
# MET symbol (without _day/_night/_polartwilight) -> Thai text, tone
SYMBOL_TH = {
    "clearsky": ("ท้องฟ้าแจ่มใส", "green"), "fair": ("มีเมฆบางส่วน", "green"),
    "partlycloudy": ("มีเมฆบางส่วน", "green"), "cloudy": ("เมฆมาก", "green"), "fog": ("หมอก", "yellow"),
    "lightrain": ("ฝนเล็กน้อย", "yellow"), "rain": ("ฝนตก", "yellow"), "heavyrain": ("ฝนตกหนัก", "red"),
    "lightrainshowers": ("ฝนเป็นช่วง ๆ", "yellow"), "rainshowers": ("ฝนเป็นช่วง ๆ", "yellow"),
    "heavyrainshowers": ("ฝนตกหนักเป็นช่วง ๆ", "red"),
}

_cache = {}
_lock = threading.Lock()


def _describe(symbol):
    base = (symbol or "").split("_")[0]
    if "thunder" in base:
        return "พายุฝนฟ้าคะนอง", "red"
    return SYMBOL_TH.get(base, ("–", "neutral"))


def _place(lat, lng):
    try:
        lat, lng = round(float(lat), 2), round(float(lng), 2)
    except (TypeError, ValueError):
        return BKK
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return BKK
    return lat, lng


def _series(lat, lng):
    """MET's hourly series for a ~1 km cell, one upstream call per CACHE_SECONDS."""
    key = (lat, lng)
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    req = urllib.request.Request(URL.format(lat=lat, lng=lng), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as r:
        series = json.loads(r.read().decode("utf-8"))["properties"]["timeseries"]
    with _lock:
        _cache[key] = (now, series)
        if len(_cache) > 500:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:250]:
                _cache.pop(k, None)
    return series


def _ts(t):
    return calendar.timegm(time.strptime(t["time"], "%Y-%m-%dT%H:%M:%SZ"))


def get(lat=None, lng=None):
    """{temp, humidity, rain_1h, symbol, text, tone, lat, lng, updated_at} for the hour now."""
    lat, lng = _place(lat, lng)
    now = time.time()
    series = _series(lat, lng)
    # the first entry at or after the start of this hour
    cur = next((t for t in series if _ts(t) >= now - 3600), series[0])
    inst = cur["data"]["instant"]["details"]
    nxt = cur["data"].get("next_1_hours") or cur["data"].get("next_6_hours") or {}
    symbol = (nxt.get("summary") or {}).get("symbol_code")
    text, tone = _describe(symbol)
    return {"temp": inst.get("air_temperature"), "humidity": inst.get("relative_humidity"),
            "rain_1h": (nxt.get("details") or {}).get("precipitation_amount"), "symbol": symbol,
            "text": text, "tone": tone, "lat": lat, "lng": lng, "updated_at": int(now)}


DAY_TH = ("วันนี้", "พรุ่งนี้", "มะรืนนี้")
TONE_RANK = {"red": 3, "yellow": 2, "green": 1, "neutral": 0}
WET_MM = 0.5      # an hour with at least this much rain counts as rainy


def outlook(lat=None, lng=None, days=3):
    """Day by day for `days` days from today (Thai time): low / high temperature, rain total, the hours it
    rains and the worst weather of the day. MET's series is hourly for about 2.5 days, then 6-hourly."""
    lat, lng = _place(lat, lng)
    series = _series(lat, lng)
    tz = 7 * 3600
    today = int((time.time() + tz) // 86400)
    out = {}
    covered = 0
    for t in series:
        ts = _ts(t)
        day = int((ts + tz) // 86400) - today
        if not 0 <= day < days:
            continue
        d = out.setdefault(day, {"day": DAY_TH[day] if day < len(DAY_TH) else f"อีก {day} วัน",
                                 "date": time.strftime("%Y-%m-%d", time.gmtime(ts + tz)), "temps": [], "rain_mm": 0.0,
                                 "wet_hours": [], "text": "–", "tone": "neutral"})
        temp = t["data"]["instant"]["details"].get("air_temperature")
        if temp is not None:
            d["temps"].append(temp)
        nxt, span = t["data"].get("next_1_hours"), 1
        if not nxt and ts >= covered:
            nxt, span = t["data"].get("next_6_hours"), 6
        if not nxt:
            continue
        covered = ts + span * 3600
        mm = (nxt.get("details") or {}).get("precipitation_amount") or 0
        d["rain_mm"] += mm
        if mm >= WET_MM:
            start = int(((ts + tz) % 86400) // 3600)
            d["wet_hours"].append((start, min(24, start + span)))
        text, tone = _describe((nxt.get("summary") or {}).get("symbol_code"))
        if TONE_RANK[tone] > TONE_RANK[d["tone"]]:
            d["text"], d["tone"] = text, tone
    days_out = []
    for day in sorted(out):
        d = out[day]
        hours = d.pop("wet_hours")
        temps = d.pop("temps")
        d["tmin"] = round(min(temps)) if temps else None
        d["tmax"] = round(max(temps)) if temps else None
        d["rain_mm"] = round(d["rain_mm"], 1)
        d["rain_hours"] = f"{min(h[0] for h in hours):02d}:00-{max(h[1] for h in hours):02d}:00" if hours else ""
        days_out.append(d)
    return {"lat": lat, "lng": lng, "source": "MET Norway", "days": days_out}
