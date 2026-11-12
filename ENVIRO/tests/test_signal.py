"""Characterization tests for server/signal.py classify_source().

Inputs are deterministic synthetic waveforms (seeded numpy RNG). The expected
values were captured by running the current code once and are pinned here, so
a change to the classifier's behaviour shows up as a failing test. Each test
targets one return path of classify_source().
"""
import numpy as np
import pytest

from server import signal as sig

RATE = int(sig.SAMPLE_RATE_HZ)  # 20 samples/s
N = 60 * RATE                    # 60 s buffer
SHAKE_START = N - 9 * RATE       # last 9 s carry the event


def _quiet(seed):
    """Background noise only: STA/LTA ~1, below the 1.3 activity gate."""
    return np.random.default_rng(seed).normal(0.0, 0.1, N)


def _quake(seed):
    """Background noise, then a broadband burst in the last 9 s."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 0.1, N)
    x[SHAKE_START:] += rng.normal(0.0, 2.0, N - SHAKE_START)
    return x


def _machine(seed):
    """Background noise, then a single sharp 5 Hz tone in the last 9 s."""
    t = np.arange(N) / sig.SAMPLE_RATE_HZ
    x = np.random.default_rng(seed).normal(0.0, 0.1, N)
    x[SHAKE_START:] += 5.0 * np.sin(2 * np.pi * 5.0 * t[SHAKE_START:])
    return x


def _assert_pct(result, expected):
    assert set(result) == {"earthquake", "vehicle", "machinery", "noise"}
    for key, value in expected.items():
        assert result[key] == pytest.approx(value, abs=0.2), key


def test_short_buffer_returns_fixed_prior():
    # Under 16 s of samples: no analysis at all, the fixed prior comes back.
    result = sig.classify_source(np.zeros(RATE * 10))
    assert result == {"earthquake": 15.0, "vehicle": 20.0, "machinery": 20.0, "noise": 45.0}


def test_quiet_buffer_is_background_noise():
    # Activity (STA/LTA) below 1.3: the gate returns the fixed noise profile.
    buf = _quiet(2)
    assert sig.sta_lta(list(buf)) < 1.3
    assert sig.classify_source(buf) == {"earthquake": 4.0, "vehicle": 9.0, "machinery": 9.0, "noise": 78.0}


def test_sharp_tone_is_classified_as_machinery():
    # Peakiness well above 15 (tonal_like): machinery dominates.
    result = sig.classify_source(_machine(1))
    _assert_pct(result, {"earthquake": 14.5, "vehicle": 14.5, "machinery": 56.5, "noise": 14.5})
    assert max(result, key=result.get) == "machinery"


def test_broadband_burst_without_neighbour_scores_earthquake_above_vehicle():
    # Active, broadband, no neighbour supplied: coherence is None, frequency alone decides.
    # Noise still wins overall for this input; the pinned values are what matter.
    result = sig.classify_source(_quake(1))
    _assert_pct(result, {"earthquake": 27.1, "vehicle": 18.9, "machinery": 12.0, "noise": 42.0})
    assert result["earthquake"] > result["vehicle"] > result["machinery"]


def test_short_neighbour_is_ignored():
    # A neighbour buffer shorter than 16 s is not used as evidence at all.
    buf = _quake(1)
    assert sig.classify_source(buf, neighbor_buffer=np.zeros(RATE * 5)) == sig.classify_source(buf)


def test_quiet_neighbour_means_not_yet_corroborated():
    # Neighbour long enough but still at background level (activity < 1.3):
    # coherence stays None and the result matches the no-neighbour case.
    neighbour = _quiet(5)
    assert sig.sta_lta(list(neighbour)) < 1.3
    assert sig.classify_source(_quake(1), neighbour) == sig.classify_source(_quake(1))


def test_correlated_active_neighbour_corroborates_earthquake():
    # Neighbour is active and coherent (|r| > 0.35): strong earthquake evidence,
    # vehicle and machinery scores are suppressed.
    buf = _quake(1)
    neighbour = buf + np.random.default_rng(9).normal(0.0, 0.2, N)
    result = sig.classify_source(buf, neighbour)
    _assert_pct(result, {"earthquake": 67.2, "vehicle": 3.6, "machinery": 2.3, "noise": 26.9})


def test_uncorrelated_active_neighbour_refutes_earthquake():
    # Neighbour is active but uncorrelated (|r| <= 0.35): a local-only source.
    # Earthquake score is cut, vehicle and machinery are raised.
    buf = _quake(1)
    neighbour = _quake(2)
    result = sig.classify_source(buf, neighbour)
    _assert_pct(result, {"earthquake": 4.2, "vehicle": 36.9, "machinery": 32.6, "noise": 26.2})
    assert max(result, key=result.get) == "vehicle"


def test_percentages_sum_to_about_100():
    cases = [
        sig.classify_source(np.zeros(RATE * 10)),
        sig.classify_source(_quiet(2)),
        sig.classify_source(_quake(1)),
        sig.classify_source(_machine(1)),
        sig.classify_source(_quake(1), _quake(2)),
    ]
    for result in cases:
        assert sum(result.values()) == pytest.approx(100.0, abs=0.5)
