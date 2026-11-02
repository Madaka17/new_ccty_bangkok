"""BMA_FETCH=0: a second machine on the same public IP (the Raspberry Pi test) must not double our BMA traffic."""
from backend.bma.bma_service import bma_fetch_enabled


def test_fetch_on_by_default():
    assert bma_fetch_enabled({}) is True


def test_fetch_off_with_zero():
    assert bma_fetch_enabled({"BMA_FETCH": "0"}) is False


def test_fetch_on_with_other_values():
    assert bma_fetch_enabled({"BMA_FETCH": "1"}) is True
