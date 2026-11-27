"""BMA live frames and stream slots: shared fetches per camera, a limit on open streams.

Tests the pure module only; importing backend.api.bma builds all the services.
"""
import threading
import time

from backend.bma.bma_live import LiveCache, StreamSlots


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- LiveCache -----------------------------------------------------------

def test_cached_value_within_ttl_is_not_refetched():
    clock = FakeClock()
    cache = LiveCache(ttl=3, clock=clock)
    calls = []

    def fetch():
        calls.append(1)
        return ("jpeg", {"cars": 1})

    assert cache.get(("12", True), fetch) == ("jpeg", {"cars": 1})
    clock.now += 2.9
    assert cache.get(("12", True), fetch) == ("jpeg", {"cars": 1})
    assert len(calls) == 1


def test_value_is_refetched_after_ttl():
    clock = FakeClock()
    cache = LiveCache(ttl=3, clock=clock)
    values = iter(["first", "second"])
    assert cache.get("k", lambda: next(values)) == "first"
    clock.now += 3.0
    assert cache.get("k", lambda: next(values)) == "second"


def test_concurrent_callers_for_one_key_run_fetch_once():
    cache = LiveCache(ttl=10)
    calls = []
    results = []

    def fetch():
        calls.append(1)
        time.sleep(0.2)
        return "frame"

    def worker():
        results.append(cache.get("cam", fetch))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1
    assert results == ["frame"] * 10


def test_none_result_is_cached_for_ttl():
    clock = FakeClock()
    cache = LiveCache(ttl=3, clock=clock)
    calls = []

    def fetch():
        calls.append(1)
        return None

    assert cache.get("dead", fetch) is None
    assert cache.get("dead", fetch) is None
    assert len(calls) == 1
    clock.now += 3.0
    assert cache.get("dead", fetch) is None
    assert len(calls) == 2


def test_exception_is_swallowed_and_cached_as_none():
    clock = FakeClock()
    cache = LiveCache(ttl=3, clock=clock)
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("bma 429")

    assert cache.get("cam", boom) is None
    assert cache.get("cam", boom) is None
    assert len(calls) == 1


def test_least_recently_used_key_is_evicted_beyond_max_keys():
    clock = FakeClock()
    cache = LiveCache(ttl=100, max_keys=2, clock=clock)
    cache.get("a", lambda: "A")
    cache.get("b", lambda: "B")
    cache.get("a", lambda: "A2")  # touch a, so b is now the least recently used
    cache.get("c", lambda: "C")   # evicts b
    calls = []
    assert cache.get("a", lambda: calls.append("a") or "A3") == "A"  # still cached
    assert cache.get("b", lambda: calls.append("b") or "B3") == "B3"  # evicted, refetched
    assert calls == ["b"]


# --- StreamSlots ---------------------------------------------------------

def test_per_key_limit():
    slots = StreamSlots(total=10, per_key=2)
    r1 = slots.acquire("1.2.3.4")
    r2 = slots.acquire("1.2.3.4")
    assert r1 is not None and r2 is not None
    assert slots.acquire("1.2.3.4") is None
    assert slots.acquire("5.6.7.8") is not None


def test_total_limit():
    slots = StreamSlots(total=2, per_key=5)
    assert slots.acquire("a") is not None
    assert slots.acquire("b") is not None
    assert slots.acquire("c") is None


def test_release_frees_a_slot():
    slots = StreamSlots(total=1, per_key=1)
    release = slots.acquire("a")
    assert slots.acquire("a") is None
    release()
    assert slots.acquire("a") is not None


def test_double_release_frees_only_one_slot():
    slots = StreamSlots(total=2, per_key=2)
    release = slots.acquire("a")
    slots.acquire("a")
    release()
    release()  # idempotent: must not free the second holder's slot
    assert slots.acquire("a") is not None
    assert slots.acquire("a") is None
