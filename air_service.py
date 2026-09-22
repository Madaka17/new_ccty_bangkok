"""PM2.5 / AQI for Bangkok and the surrounding provinces.

Source: Air4Thai (Pollution Control Department) public JSON feed, which carries the PCD and BMA
monitoring stations with the Thai AQI already computed. Refreshed every 10 minutes; a failed
refresh keeps serving the last good snapshot.
"""
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

AIR4THAI_URL = "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
REFRESH_SECONDS = 600
BBOX = (13.3, 100.1, 14.3, 101.1)  # min lat, min lon, max lat, max lon
BKK_TZ = timezone(timedelta(hours=7))

# Thai AQI bands (PCD): colour id from the feed -> level used by the UI
LEVELS = {
    "1": {"level": "very_good", "label": "ดีมาก", "color": "#3BA0FF"},
    "2": {"level": "good", "label": "ดี", "color": "#4CC74A"},
    "3": {"level": "moderate", "label": "ปานกลาง", "color": "#FFD400"},
    "4": {"level": "unhealthy", "label": "เริ่มมีผลต่อสุขภาพ", "color": "#FF8C00"},
    "5": {"level": "very_unhealthy", "label": "มีผลต่อสุขภาพ", "color": "#E3272C"},
}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else f


def _pm25_band(v):
    """Thai PM2.5 AQI bands (µg/m³, 24 h): 0-15 / 15.1-25 / 25.1-37.5 / 37.6-75 / >75."""
    if v is None:
        return None
    if v <= 15:
        return "1"
    if v <= 25:
        return "2"
    if v <= 37.5:
        return "3"
    if v <= 75:
        return "4"
    return "5"


class AirService:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = []
        self.updated_at = None
        self.source_ts = None
        self.error = None
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.thread.start()

    def refresh(self):
        req = urllib.request.Request(AIR4THAI_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = []
        latest = None
        for s in data.get("stations") or []:
            try:
                lat, lon = float(s["lat"]), float(s["long"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
                continue
            last = s.get("AQILast") or {}
            pm = last.get("PM25") or {}
            pm25 = _num(pm.get("value"))
            if pm25 is None:
                continue
            aqi_all = last.get("AQI") or {}
            band = pm.get("color_id") if pm.get("color_id") not in (None, "0") else _pm25_band(pm25)
            lv = LEVELS.get(str(band)) or LEVELS["1"]
            area = (s.get("areaTH") or "").split(",")
            ts = None
            try:
                ts = int(datetime.strptime(f"{last.get('date')} {last.get('time')}", "%Y-%m-%d %H:%M")
                         .replace(tzinfo=BKK_TZ).timestamp())
            except (TypeError, ValueError):
                pass
            if ts and (latest is None or ts > latest):
                latest = ts
            items.append({
                "id": s.get("stationID"),
                "name": (s.get("nameTH") or "").strip(),
                "area": (area[0] if area else "").strip(),
                "province": (area[-1] if area else "").strip().replace("กรุงเทพฯ", "กรุงเทพมหานคร"),
                "lat": lat, "lng": lon,
                "pm25": pm25,
                "pm25_aqi": _num(pm.get("aqi")),
                "aqi": _num(aqi_all.get("aqi")),
                "aqi_param": aqi_all.get("param"),
                "pm10": _num((last.get("PM10") or {}).get("value")),
                "level": lv["level"], "label": lv["label"], "color": lv["color"],
                "ts": ts,
            })
        items.sort(key=lambda i: -i["pm25"])
        with self.lock:
            self.items = items
            self.updated_at = int(time.time())
            self.source_ts = latest
            self.error = None
        print(f"[Air] {len(items)} stations, max PM2.5 {items[0]['pm25'] if items else '-'} µg/m³")

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as e:
                with self.lock:
                    self.error = str(e)
                print(f"[Air] refresh error: {e}")
            time.sleep(REFRESH_SECONDS)

    def status(self):
        with self.lock:
            items = list(self.items)
            counts = {}
            for it in items:
                counts[it["level"]] = counts.get(it["level"], 0) + 1
            avg = round(sum(i["pm25"] for i in items) / len(items), 1) if items else None
            return {"updated_at": self.updated_at, "source_ts": self.source_ts, "error": self.error,
                    "total": len(items), "avg_pm25": avg, "counts": counts, "items": items}


air = AirService()
