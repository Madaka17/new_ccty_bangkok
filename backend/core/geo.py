"""Distance helpers in km, shared by the traffic and water modules.

flat_km is the equirectangular approximation used for short distances inside Bangkok. The constants are
per-degree km; modules pass their own when they used different ones, so results do not change.
haversine_km is the great-circle distance.
"""
import math


def flat_km(lat1, lng1, lat2, lng2, km_per_deg_lat=110.57, km_per_deg_lng=111.32):
    return math.hypot((lng2 - lng1) * km_per_deg_lng * math.cos(math.radians((lat1 + lat2) / 2)),
                      (lat2 - lat1) * km_per_deg_lat)


def haversine_km(lat1, lng1, lat2, lng2, radius_km=6371.0):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))
