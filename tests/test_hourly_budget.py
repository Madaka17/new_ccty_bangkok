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


def test_try_spend_stops_at_limit():
    b = HourlyBudget(3)
    assert b.try_spend(now=0) is True
    assert b.try_spend(now=0) is True
    assert b.try_spend(now=0) is True
    assert b.try_spend(now=0) is False
    assert b.used(now=0) == 3


def test_try_spend_allows_again_after_window_expires():
    b = HourlyBudget(1)
    assert b.try_spend(now=0) is True
    assert b.try_spend(now=10) is False
    assert b.try_spend(now=3600) is True


def test_try_spend_is_atomic_across_threads():
    b = HourlyBudget(5)
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(20)

    def attempt():
        barrier.wait()
        ok = b.try_spend(now=100.0)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == 5
    assert results.count(False) == 15
