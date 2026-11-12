"""Characterization tests for server/seismology.py.

Known values were captured from the current code and checked by hand where a
closed-form answer exists (e.g. the Wald et al. 1999 piecewise GMICE, the
MMI roman-numeral floor, and the 3000 km felt-radius ceiling).
"""
import pytest

from server import seismology as s


def test_magnitude_amp_multiplier_is_1_at_ref_and_10x_per_2_units():
    assert s.magnitude_amp_multiplier(4.8) == pytest.approx(1.0)
    assert s.magnitude_amp_multiplier(6.8) == pytest.approx(10.0)


def test_pga_at_distance_known_values():
    # zero distance and zero depth: MMI_PGA_SCALE * 1 * amp(4.8)
    assert s.pga_at_distance(4.8, 0.0, 0.0) == pytest.approx(40.0)
    assert s.pga_at_distance(7.0, 10.0, 10.0) == pytest.approx(400.57, abs=0.01)


def test_pga_to_mmi_both_branches_and_floor():
    assert s.pga_to_mmi(1.0) == pytest.approx(1.0)      # low branch: 2.2*0 + 1
    assert s.pga_to_mmi(10.0) == pytest.approx(3.2)     # low branch: 2.2*1 + 1
    assert s.pga_to_mmi(100.0) == pytest.approx(5.66)   # high branch: 3.66*2 - 1.66
    assert s.pga_to_mmi(0.0) == 1.0                     # non-positive PGA floors at I


def test_mmi_to_pga_known_values_and_inverse():
    assert s.mmi_to_pga(1.0) == pytest.approx(1.0)
    assert s.mmi_to_pga(7.0) == pytest.approx(232.34, abs=0.01)
    for mmi in (2.0, 4.0, 6.5, 9.0):
        assert s.pga_to_mmi(s.mmi_to_pga(mmi)) == pytest.approx(mmi, abs=1e-9)


def test_mmi_roman_floors_and_clamps():
    assert s.mmi_roman(1) == "I"
    assert s.mmi_roman(5.71) == "V"    # floor, not round: 5.71 stays level V
    assert s.mmi_roman(6.0) == "VI"
    assert s.mmi_roman(12) == "XII"
    assert s.mmi_roman(0.2) == "I"     # clamped below
    assert s.mmi_roman(13) == "XII"    # clamped above


def test_felt_radius_known_values_and_ceiling():
    assert s.felt_radius_km(4.8, 8.0) == pytest.approx(717.42, abs=0.01)
    assert s.felt_radius_km(7.0, 10.0) == 3000.0       # hits the 3000 km ceiling


def test_predict_mmi_known_values():
    assert s.predict_mmi(7.0, 10.0, 10.0) == pytest.approx(7.87)
    assert s.predict_mmi(4.8, 50.0, 8.0) == pytest.approx(3.9)


def test_solve_magnitude_round_trips_through_predict():
    for target, dist, depth in [(6.0, 10.0, 10.0), (4.0, 30.0, 5.0)]:
        mag = s.solve_magnitude_for_mmi(target, dist, depth)
        assert s.predict_mmi(mag, dist, depth) == pytest.approx(target, abs=0.05)


def test_solve_magnitude_is_capped():
    # unreachable target at 500 km: returns the 9.5 cap instead of an invented magnitude
    assert s.solve_magnitude_for_mmi(12.0, 500.0, 10.0) == 9.5


def test_estimate_magnitude_inverts_its_own_physics():
    # PGA built from the simulator's own attenuation for M5.0 at 20 km, depth-free
    pga = 5.0 * s.PEAK_SHAKE_CONST * (1.0 / (1.0 + 20.0 / 55.0)) * s.magnitude_amp_multiplier(5.0)
    assert s.estimate_magnitude(pga, 20.0, 5.0) == pytest.approx(5.0)
    assert s.estimate_magnitude(0.0, 20.0, 5.0) == 0.0
