"""HourlyBudget: a rolling-hour cap on AI calls that stays correct when several threads spend at once."""
import threading

from backend.core.hourly_budget import HourlyBudget


def test_allows_until_limit():
    b = HourlyBudget(2)
    assert b.allows(now=0)
    b.spend(now=0)
    assert b.allows(now=0)
    b.spend(now=0)
    assert not b.allows(now=0)


def test_old_calls_expire():
    b = HourlyBudget(1)
    b.spend(now=0)
    assert b.used(3601) == 0
    assert b.allows(3601)


def test_parallel_spend_counts_every_call():
    b = HourlyBudget(10_000)

    def spend_many():
        for _ in range(500):
            b.spend(now=100.0)

    threads = [threading.Thread(target=spend_many) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert b.used(now=100.0) == 4000
