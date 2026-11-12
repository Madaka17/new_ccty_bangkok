"""The helmet check's hourly cap is a shared HourlyBudget, so it is safe across worker threads."""
from types import SimpleNamespace

from backend.core.hourly_budget import HourlyBudget
from backend.vision.violation_service import HELMET_MAX_PER_HOUR, ViolationMonitor


def _monitor_with_api_only():
    # Only the attributes _helmet_budget_ok reads: no threads, no models, no database.
    m = object.__new__(ViolationMonitor)
    m.helmet_cls = None
    m.vision = SimpleNamespace(client=object())   # an API client makes helmet checks "enabled"
    m._helmet_last = {}
    m._helmet_budget = HourlyBudget(HELMET_MAX_PER_HOUR)
    return m


def test_helmet_budget_stops_after_max_per_hour():
    m = _monitor_with_api_only()
    now = 1_000_000.0
    assert m._helmet_budget_ok("cam", now)
    for i in range(HELMET_MAX_PER_HOUR):
        m._helmet_budget.spend(now + i)   # spread out, so the per-camera cooldown is not the limit
    assert m._helmet_budget_ok("other-cam", now + HELMET_MAX_PER_HOUR) is False


def test_helmet_budget_frees_up_after_an_hour():
    m = _monitor_with_api_only()
    now = 1_000_000.0
    for i in range(HELMET_MAX_PER_HOUR):
        m._helmet_budget.spend(now + i)
    assert m._helmet_budget_ok("cam", now + 3600 + HELMET_MAX_PER_HOUR) is True


def test_constructor_creates_helmet_budget(tmp_path):
    m = ViolationMonitor(str(tmp_path / "v.db"), load_models=False)
    assert isinstance(m._helmet_budget, HourlyBudget)
    assert m._helmet_budget.limit == HELMET_MAX_PER_HOUR
