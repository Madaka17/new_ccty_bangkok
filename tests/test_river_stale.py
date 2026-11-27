"""A river reading older than RIVER_STALE_MINUTES is stale: its level is 'stale' and it is not counted."""
from backend.water import water_service as ws

NOW = 1_800_000_000


def test_river_row_five_hours_old_is_stale_and_not_counted():
    rows = [{'name': 'สามเสน', 'level': 'overflow', 'ts': NOW - 5 * 3600}]
    ws._mark_stale_rivers(rows, NOW)
    assert rows[0]['stale'] is True
    assert rows[0]['level'] == 'stale'
    assert ws._river_counts(rows)['overflow'] == 0


def test_river_row_one_hour_old_is_counted():
    rows = [{'name': 'สามเสน', 'level': 'overflow', 'ts': NOW - 3600}]
    ws._mark_stale_rivers(rows, NOW)
    assert rows[0]['stale'] is False
    assert rows[0]['level'] == 'overflow'
    assert ws._river_counts(rows)['overflow'] == 1


def test_river_row_without_a_time_is_left_as_it_is():
    rows = [{'name': 'x', 'level': 'high', 'ts': None}]
    ws._mark_stale_rivers(rows, NOW)
    assert rows[0]['level'] == 'high'
