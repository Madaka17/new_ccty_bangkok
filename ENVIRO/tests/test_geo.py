"""Characterization tests for server/geo.py haversine_km()."""
import pytest

from server.geo import haversine_km


def test_zero_distance_for_same_point():
    assert haversine_km(1.0, 1.0, 1.0, 1.0) == 0.0


def test_one_degree_of_longitude_on_equator():
    # 2*pi*R/360 with R = 6371.0088 km
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, abs=0.001)


def test_quarter_meridian_pole_to_equator():
    assert haversine_km(0.0, 0.0, 90.0, 0.0) == pytest.approx(10007.56, abs=0.01)


def test_bangkok_to_chiang_mai():
    # BKK-201 reference (13.756, 100.502) to Chiang Mai (18.788, 98.985): about 582 km great-circle
    assert haversine_km(13.756, 100.502, 18.788, 98.985) == pytest.approx(582.47, abs=0.01)


def test_symmetric():
    a = haversine_km(13.756, 100.502, 7.189, 100.595)
    assert a == pytest.approx(haversine_km(7.189, 100.595, 13.756, 100.502))
