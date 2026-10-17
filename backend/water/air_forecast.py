"""PM2.5 outlook for Bangkok, three days ahead.

Open-Meteo's air-quality model gives hourly PM2.5 for the city. The model runs high or low, so each
hour is scaled by the ratio of the live station average to the model's value now (clamped to 0.5-2.0).
Refreshed hourly. On error the last good outlook is kept.
"""
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from backend.water.air_service import LEVELS, _pm25_band, air

FORECAST_URL = ("https://air-quality-api.open-meteo.com/v1/air-quality?latitude=13.75&longitude=100.52"
                "&hourly=pm2_5&timezone=Asia%2FBangkok&forecast_days=3")
REFRESH_SECONDS = 3600
BKK_TZ = timezone(timedelta(hours=7))
DAY_LABELS = ["วันนี้", "พรุ่งนี้", "มะรืนนี้"]
DAY_HOURS = range(6, 22)  # 06:00 to 21:00 local


def _local(s):
    """Open-Meteo local time string ('YYYY-MM-DDTHH:MM') as a naive datetime."""
    return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M")


def build(model, station_avg, now):
    """Turn an Open-Meteo air-quality reply into the outlook. `now` is Bangkok local time."""
    if now.tzinfo is not None:
        now = now.astimezone(BKK_TZ).replace(tzinfo=None)
    current = now.replace(minute=0, second=0, microsecond=0)

    times = model["hourly"]["time"]
    values = model["hourly"]["pm2_5"]
    pairs = [(_local(t), v) for t, v in zip(times, values)]

    # model value at the current hour, or the nearest earlier one that has data
    model_now = None
    for when, v in reversed(pairs):
        if when <= current and v is not None:
            model_now = v
            break

    if station_avg is None or not model_now:
        ratio = 1.0
    else:
        ratio = min(2.0, max(0.5, station_avg / model_now))

    hours = []
    adjusted = []  # (local time, value) for the days below
    for when, v in pairs:
        if when < current or v is None:
            continue
        adj = round(v * ratio, 1)
        hours.append({"t": int(when.replace(tzinfo=BKK_TZ).timestamp()), "pm25": adj})
        adjusted.append((when, adj))

    days = []
    today = now.date()
    for i, label in enumerate(DAY_LABELS):
        day = today + timedelta(days=i)
        vals = [adj for when, adj in adjusted
                if when.date() == day and when.hour in DAY_HOURS]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        band = LEVELS[_pm25_band(mean)]
        days.append({
            "date": day.isoformat(),
            "label": label,
            "mean": round(mean, 1),
            "max": round(max(vals), 1),
            "level": band["level"],
            "label_th": band["label"],
            "color": band["color"],
        })

    return {"updated_at": int(time.time()), "ratio": round(ratio, 3), "hours": hours, "days": days}


class AirForecast:
    def __init__(self):
        self.lock = threading.Lock()
        self.result = None
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.thread.start()

    def refresh(self):
        req = urllib.request.Request(FORECAST_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            model = json.loads(resp.read().decode("utf-8"))
        station_avg = air.status()["avg_pm25"]
        result = build(model, station_avg, datetime.now(BKK_TZ))
        with self.lock:
            self.result = result
        print(f"[AirForecast] {len(result['days'])} days, ratio {result['ratio']}")

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as e:
                print(f"[AirForecast] refresh error: {e}")
            time.sleep(REFRESH_SECONDS)

    def status(self):
        with self.lock:
            return self.result


air_forecast = AirForecast()
