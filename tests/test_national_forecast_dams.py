from backend.water.national_forecast import _same_dam, parse_large


def dam_row(dam_id, name, date, storage, lat, lng, normal=1000.0):
    return {
        "dam": {"id": dam_id, "dam_name": {"th": name}, "normal_storage": normal, "max_storage": normal * 1.2,
                "dam_lat": lat, "dam_long": lng},
        "dam_date": date, "dam_storage": storage, "dam_inflow": 5, "dam_released": 4, "basin": None,
    }


def test_twin_rows_for_one_dam_keep_the_newer():
    rows = [
        dam_row(53, "แม่งัด", "2026-11-25", 300.0, 18.0000, 98.0000),
        dam_row(23, "แม่งัดสมบูรณ์ชล", "2026-11-26", 310.0, 18.0010, 98.0010),
    ]
    out = parse_large(rows)
    assert [d["id"] for d in out] == [23]


def test_row_with_zero_storage_is_dropped():
    rows = [
        dam_row(7, "ปากมูล", "2026-11-26", 0.0, 15.2, 104.8),
        dam_row(8, "ภูมิพล", "2026-11-26", 500.0, 17.2, 98.9),
    ]
    out = parse_large(rows)
    assert [d["name"] for d in out] == ["ภูมิพล"]


def test_zero_storage_twin_does_not_hide_the_real_row():
    rows = [
        dam_row(53, "แม่งัด", "2026-11-26", 0.0, 18.0010, 98.0010),
        dam_row(23, "แม่งัดสมบูรณ์ชล", "2026-11-25", 310.0, 18.0000, 98.0000),
    ]
    out = parse_large(rows)
    assert [d["id"] for d in out] == [23]


def test_far_apart_dams_with_different_names_are_both_kept():
    rows = [
        dam_row(1, "ภูมิพล", "2026-11-26", 500.0, 17.2, 98.9),
        dam_row(2, "สิริกิติ์", "2026-11-26", 600.0, 17.6, 100.8),
    ]
    out = parse_large(rows)
    assert sorted(d["name"] for d in out) == ["ภูมิพล", "สิริกิติ์"]


def test_same_date_tie_keeps_the_larger_storage():
    rows = [
        dam_row(53, "แม่งัด", "2026-11-26", 300.0, 18.0000, 98.0000),
        dam_row(23, "แม่งัดสมบูรณ์ชล", "2026-11-26", 320.0, 18.0010, 98.0010),
    ]
    out = parse_large(rows)
    assert [d["id"] for d in out] == [23]


def test_same_dam_by_position_or_name():
    a = {"name": "แม่งัด", "lat": 18.0000, "lng": 98.0000}
    assert _same_dam(a, {"name": "แม่งัดสมบูรณ์ชล", "lat": 18.0200, "lng": 98.0000}) is False
    assert _same_dam(a, {"name": "แม่งัดสมบูรณ์ชล", "lat": 18.0050, "lng": 98.0050}) is True
    assert _same_dam(a, {"name": "แม่งัด", "lat": None, "lng": None}) is True
