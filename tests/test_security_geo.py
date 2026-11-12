import gzip
import json
import math

import pytest

from launch.security_check import geo


@pytest.fixture
def geodir(tmp_path, monkeypatch):
    csv = "\n".join([
        "1.0.0.0,1.0.0.255,AU",
        "8.8.8.0,8.8.8.255,US",
        "9.9.9.0,9.9.9.255,ZZ",
        "10.0.0.0,10.255.255.255,XX",
        "2a00:1450::,2a00:1450::ffff,DE",
    ])
    with gzip.open(tmp_path / "dbip-country-lite-2026-11.csv.gz", "wt") as fh:
        fh.write(csv)
    (tmp_path / "countries.json").write_text(json.dumps(
        [{"cca2": "US", "latlng": [38, -97], "name": {"common": "United States"}}]), encoding="utf-8")
    topo = {"type": "Topology", "transform": {"scale": [1, 1], "translate": [-180, -90]},
            "arcs": [[[100, 100], [10, 0], [0, 10], [-10, 0], [0, -10]]],
            "objects": {"land": {"type": "GeometryCollection",
                                 "geometries": [{"type": "Polygon", "arcs": [[0]]}]}}}
    (tmp_path / "land-110m.json").write_text(json.dumps(topo), encoding="utf-8")
    monkeypatch.setenv("BKK_GEO_DIR", str(tmp_path))
    geo._db = None
    geo._countries = None
    return tmp_path


def test_lookup_v4_v6(geodir):
    assert geo.lookup("8.8.8.8") == "US"
    assert geo.lookup("1.0.0.7") == "AU"
    assert geo.lookup("2a00:1450::5") == "DE"
    assert geo.lookup("8.8.9.1") is None


def test_lookup_zz_private_invalid(geodir):
    assert geo.lookup("9.9.9.9") is None
    assert geo.lookup("10.1.2.3") is None
    assert geo.lookup("127.0.0.1") is None
    assert geo.lookup("not-an-ip") is None


def test_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BKK_GEO_DIR", str(tmp_path))
    geo._db = None
    geo._countries = None
    assert geo.lookup("8.8.8.8") is None
    assert geo.available() is False
    assert geo.land_path() == ""
    assert geo.centroid("US") is None
    assert geo.country_name("US") == "US"


def test_country_info(geodir):
    assert geo.country_name("US") == "United States"
    assert geo.centroid("us") == (38.0, -97.0)
    assert geo.centroid("FR") is None


def test_land_path(geodir):
    d = geo.land_path()
    assert d.startswith("M") and "nan" not in d.lower()
    assert d.count("M") == 1 and d.count("L") == 4
    for tok in d.replace("M", " ").replace("L", " ").split():
        assert not math.isnan(float(tok))


def test_project_corners():
    assert geo.project(90, -180) == (0, 0)
    assert geo.project(-90, 180) == (1000, 500)
    assert geo.project(0, 0, 200, 100) == (100, 50)
