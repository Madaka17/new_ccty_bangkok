"""backend/core/geo.py must give the same distances as each old per-module formula.

The reference functions below are verbatim copies of the bodies that were removed from the modules.
"""
import math

import pytest

from backend.core.geo import flat_km, haversine_km
from backend.water import river_roads, north_route, water_service as ws

# (lat, lng) pairs around Bangkok and Chiang Mai
PAIRS = [
    ((13.7563, 100.5018), (18.7883, 98.9853)),
    ((13.7563, 100.5018), (13.7466, 100.5393)),
    ((13.9126, 100.5346), (13.6900, 100.7501)),
    ((18.7883, 98.9853), (18.7061, 98.9817)),
    ((14.9799, 102.0977), (13.7563, 100.5018)),
]


def _close(new, old):
    assert new == pytest.approx(old, rel=1e-12, abs=1e-9)


# ---- old reference bodies (copied verbatim)

def _ref_area_roads(lat1, lng1, lat2, lng2):
    dy = (lat2 - lat1) * 110.57
    dx = (lng2 - lng1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _ref_guidance(lat1, lon1, lat2, lon2):
    x = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    y = (lat2 - lat1) * 110.57
    return math.hypot(x, y)


def _ref_road_service(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111.0
    dlon = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def _ref_river_roads(a, b):
    cos = math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[1] - b[1]) * 111.32 * cos, (a[0] - b[0]) * 110.57)


def _ref_north_route(a, b):
    kx = 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[1] - b[1]) * kx, (a[0] - b[0]) * 110.54)


def _ref_events_calendar(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _ref_nasa_feeds(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def _ref_rsc_haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _ref_water_service(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return 999.0
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


# ---- new calls, with the same constants each module used

@pytest.mark.parametrize("p1, p2", PAIRS)
def test_area_roads_matches_flat_defaults(p1, p2):
    _close(flat_km(*p1, *p2), _ref_area_roads(*p1, *p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_guidance_matches_flat_defaults(p1, p2):
    _close(flat_km(*p1, *p2), _ref_guidance(*p1, *p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_road_service_matches_flat_111(p1, p2):
    _close(flat_km(*p1, *p2, km_per_deg_lat=111.0, km_per_deg_lng=111.0), _ref_road_service(*p1, *p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_river_roads_wrapper_matches_old(p1, p2):
    _close(river_roads._km(p1, p2), _ref_river_roads(p1, p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_north_route_wrapper_matches_old(p1, p2):
    _close(north_route._km(p1, p2), _ref_north_route(p1, p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_events_calendar_matches_haversine(p1, p2):
    _close(haversine_km(*p1, *p2), _ref_events_calendar(*p1, *p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_nasa_feeds_matches_haversine(p1, p2):
    _close(haversine_km(*p1, *p2), _ref_nasa_feeds(*p1, *p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_rsc_matches_haversine_metres(p1, p2):
    _close(haversine_km(*p1, *p2, radius_km=6371.0) * 1000, _ref_rsc_haversine_m(*p1, *p2))


@pytest.mark.parametrize("p1, p2", PAIRS)
def test_water_service_wrapper_matches_old(p1, p2):
    _close(ws._km(*p1, *p2), _ref_water_service(*p1, *p2))


def test_water_service_wrapper_none_guard():
    assert ws._km(None, 100.5, 13.7, 100.5) == 999.0
    assert ws._km(13.7, 100.5, 13.7, None) == 999.0
