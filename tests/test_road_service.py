"""Road flood classes must follow the published thresholds exactly (road_service.py docstring)."""
import pytest

from road_service import GAUGE_BANDS, RAIN_BANDS, ROAD_WATER_BANDS, _classify, _norm


@pytest.mark.parametrize("cm, cls", [
    (0, 0), (5.0, 0),          # สนน. กทม.: <= 5 cm normal
    (5.1, 1), (10.0, 1),       # 5-10 cm slight
    (10.1, 2), (20.0, 2),      # > 10 cm flooded, ปภ. < 20 passable
    (20.1, 3), (60.0, 3),      # avoid
    (60.1, 4), (150, 4),       # do not drive through
])
def test_road_water_bands(cm, cls):
    assert _classify(cm, ROAD_WATER_BANDS)[0] == cls


@pytest.mark.parametrize("mm, cls", [
    (0, 0), (0.1, 0),
    (0.2, 1), (10.0, 1),
    (10.1, 2), (35.0, 2),
    (35.1, 3), (90.0, 3),
    (90.1, 4), (300, 4),
])
def test_rain_bands(mm, cls):
    assert _classify(mm, RAIN_BANDS)[0] == cls


@pytest.mark.parametrize("pct, cls", [(0, 0), (80.0, 0), (80.1, 2), (100.0, 2), (100.1, 4), (255, 4)])
def test_gauge_bands(pct, cls):
    assert _classify(pct, GAUGE_BANDS)[0] == cls


def test_unknown_reading_has_no_class():
    assert _classify(None, RAIN_BANDS) == (None, None, None)


def test_classify_returns_label_and_source():
    cls, label, source = _classify(70, ROAD_WATER_BANDS)
    assert (cls, label) == (4, "ห้ามขับผ่าน")
    assert source.startswith("ปภ.")


@pytest.mark.parametrize("a, b", [("ถนนสุขุมวิท", "สุขุมวิท"), ("ถ.พระราม 4", "พระราม4"), ("ซ.อ่อนนุช 46", "อ่อนนุช46")])
def test_norm_strips_prefixes_and_spaces(a, b):
    assert _norm(a) == _norm(b)
