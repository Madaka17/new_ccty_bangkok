"""in_bangkok(lat, lng): point-in-polygon against the 50 Bangkok districts in config/thailand_districts.geojson."""
from backend.water import bkk_districts


def test_sukhumvit_is_in_bangkok():
    assert bkk_districts.in_bangkok(13.7372, 100.5608) is True


def test_nonthaburi_is_not_in_bangkok():
    assert bkk_districts.in_bangkok(13.8600, 100.5150) is False


def test_chaophraya_north_of_the_city_line_is_not_in_bangkok():
    assert bkk_districts.in_bangkok(14.2000, 100.6000) is False
