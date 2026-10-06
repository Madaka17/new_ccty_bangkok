import pytest

from backend.water import wind_field


def test_uv_points_where_the_wind_blows():
    # a north wind (from 0 degrees) blows south: v negative
    assert wind_field._uv(10, 0) == (pytest.approx(0, abs=0.01), -10.0)
    # an east wind (from 90 degrees) blows west: u negative
    assert wind_field._uv(5, 90) == (-5.0, pytest.approx(0, abs=0.01))
    assert wind_field._uv(None, 90) == (0.0, 0.0)


def test_build_keeps_grid_order_per_hour():
    blocks = [
        {"hourly": {"time": [100, 3700], "wind_speed_10m": [2, 4], "wind_direction_10m": [180, 270]}},
        {"hourly": {"time": [100, 3700], "wind_speed_10m": [None, 1], "wind_direction_10m": [None, 0]}},
    ]
    frames = wind_field._build(blocks)
    assert [f["t"] for f in frames] == [100, 3700]
    assert frames[0]["v"] == [2.0, 0.0]     # south wind blows north
    assert frames[1]["u"] == [4.0, pytest.approx(0, abs=0.01)]
    assert frames[1]["v"] == [pytest.approx(0, abs=0.01), -1.0]


def test_build_without_hours_fails():
    with pytest.raises(ValueError):
        wind_field._build([{"hourly": {}}])


def test_grid_starts_south_west_row_by_row():
    pts = wind_field._grid()
    assert len(pts) == wind_field.GRID_POINTS
    assert pts[0] == (wind_field.LAT0, wind_field.LNG0)
    assert pts[1] == (wind_field.LAT0, wind_field.LNG0 + wind_field.STEP)
    assert pts[wind_field.NX] == (wind_field.LAT0 + wind_field.STEP, wind_field.LNG0)
