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


def get(lat=None, lng=None):
    """{temp, humidity, rain_1h, symbol, text, tone, lat, lng, updated_at} for the hour now."""
    try:
        lat, lng = round(float(lat), 2), round(float(lng), 2)
    except (TypeError, ValueError):
        lat, lng = BKK
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        lat, lng = BKK
    key = (lat, lng)
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    req = urllib.request.Request(URL.format(lat=lat, lng=lng), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    series = data["properties"]["timeseries"]
    # the first entry at or after the start of this hour
    cur = next((t for t in series if calendar.timegm(time.strptime(t["time"], "%Y-%m-%dT%H:%M:%SZ")) >= now - 3600), series[0])
    inst = cur["data"]["instant"]["details"]
    nxt = cur["data"].get("next_1_hours") or cur["data"].get("next_6_hours") or {}
    symbol = (nxt.get("summary") or {}).get("symbol_code")
    text, tone = _describe(symbol)
    out = {"temp": inst.get("air_temperature"), "humidity": inst.get("relative_humidity"),
           "rain_1h": (nxt.get("details") or {}).get("precipitation_amount"), "symbol": symbol,
           "text": text, "tone": tone, "lat": lat, "lng": lng, "updated_at": int(now)}
    with _lock:
        _cache[key] = (now, out)
        if len(_cache) > 500:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:250]:
                _cache.pop(k, None)
    return out
