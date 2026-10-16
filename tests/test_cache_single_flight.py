"""Cache stampede: when a value goes stale, one thread runs the upstream loader and the rest wait for its result."""
import json
import threading
import time
import urllib.request

from backend.traffic import analytics_service
from backend.water import water_service, weather_now

THREADS = 8


def _race(call):
    """Start THREADS threads at the same moment, each calling `call()`; return their results."""
    barrier = threading.Barrier(THREADS)
    results, errors = [None] * THREADS, []

    def run(i):
        try:
            barrier.wait()
            results[i] = call()
        except Exception as e:  # surfaced below, so a failing thread is not silently lost
            errors.append(e)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors, errors
    return results


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


# ---------------------------------------------------------------- water _Cache
def test_water_cache_runs_loader_once_under_load():
    cache = water_service._Cache()
    calls = []

    def loader():
        calls.append(1)
        time.sleep(0.2)
        return {"v": 1}

    results = _race(lambda: cache.get("summary", 60, loader))
    assert len(calls) == 1
    values = {id(v) for v, _stale in results}
    assert len(values) == 1
    assert all(stale is False for _v, stale in results)


def test_water_cache_keeps_stale_value_when_refresh_fails():
    cache = water_service._Cache()
    cache.get("gauge", 0, lambda: "old")  # ttl 0: every call is stale

    def broken():
        raise RuntimeError("upstream down")

    assert cache.get("gauge", 0, broken) == ("old", True)


def test_water_cache_reraises_when_nothing_cached():
    cache = water_service._Cache()

    def broken():
        raise RuntimeError("upstream down")

    try:
        cache.get("new", 60, broken)
    except RuntimeError:
        return
    raise AssertionError("expected the loader error to propagate")


# ---------------------------------------------------------------- analytics get_summary
def test_analytics_summary_builds_once_under_load(monkeypatch):
    monkeypatch.setattr(analytics_service, "_cache", {"ts": 0, "data": None})
    calls = []

    def build():
        calls.append(1)
        time.sleep(0.2)
        return {"generated_at": 1}

    monkeypatch.setattr(analytics_service, "_build", build)
    results = _race(analytics_service.get_summary)
    assert len(calls) == 1
    assert len({id(r) for r in results}) == 1


# ---------------------------------------------------------------- weather_now _series
def test_weather_series_one_upstream_call_under_load(monkeypatch):
    monkeypatch.setattr(weather_now, "_cache", {})
    calls = []
    body = json.dumps({"properties": {"timeseries": [{"time": "2026-10-13T05:00:00Z", "data": {}}]}}).encode()

    def fake_urlopen(req, timeout=None):
        calls.append(1)
        time.sleep(0.2)
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    results = _race(lambda: weather_now._series(13.75, 100.5))
    assert len(calls) == 1
    assert len({id(r) for r in results}) == 1


# ---------------------------------------------------------------- longdo_cameras
def _longdo_body():
    return json.dumps({"item": [{"camid": "c1", "title": "(กรุงเทพฯ) สี่แยก", "latitude": "13.7", "longitude": "100.5"}]}).encode()


def _longdo(monkeypatch, tmp_path):
    from backend.vision import longdo_cameras as mod
    monkeypatch.setattr(mod, "CACHE_FILE", str(tmp_path / "cache" / "longdo_cameras.json"))
    monkeypatch.setattr(mod, "_cache", {"data": None, "next_try": 0.0})
    return mod


def test_longdo_cameras_one_live_fetch_under_load(monkeypatch, tmp_path):
    mod = _longdo(monkeypatch, tmp_path)
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(1)
        time.sleep(0.2)
        return _FakeResponse(_longdo_body())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    results = _race(mod.longdo_cameras)
    assert len(calls) == 1
    assert len({id(r) for r in results}) == 1
    assert results[0]["items"][0]["camid"] == "c1"


def test_longdo_failure_waits_a_minute_before_retrying(monkeypatch, tmp_path):
    mod = _longdo(monkeypatch, tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "longdo_cameras.json").write_text(json.dumps({"total": 1, "items": [{"camid": "disk"}]}), encoding="utf-8")
    calls = []

    def down(req, timeout=None):
        calls.append(1)
        raise OSError("longdo down")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    first = mod.longdo_cameras()
    second = mod.longdo_cameras()
    assert first["items"][0]["camid"] == "disk"
    assert second["items"][0]["camid"] == "disk"
    assert len(calls) == 1  # the second call is inside the 60 s retry wait: no live try


def test_longdo_failure_without_a_copy_also_waits(monkeypatch, tmp_path):
    mod = _longdo(monkeypatch, tmp_path)
    calls = []

    def down(req, timeout=None):
        calls.append(1)
        raise OSError("longdo down")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    ours = [{"camid": "ours"}]
    first = mod.longdo_cameras(fallback=ours)
    second = mod.longdo_cameras(fallback=ours)
    assert first == second == {"total": 1, "items": ours}
    assert len(calls) == 1


# ---------------------------------------------------------------- outages: no queue of failing calls, no waiting for a refresh
def _slow_in_background(call, seconds=0.3):
    """Run `call` in a thread that is still inside the loader for `seconds`; return the thread."""
    t = threading.Thread(target=call)
    t.start()
    time.sleep(0.05)   # let it take the lock
    return t


def test_water_cache_remembers_a_failure_for_a_while():
    cache = water_service._Cache()
    cache.get("gauge", 0, lambda: "old")
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError("upstream down")

    assert cache.get("gauge", 0, broken) == ("old", True)
    assert cache.get("gauge", 0, broken) == ("old", True)
    assert len(calls) == 1


def test_water_cache_without_value_reraises_without_retrying():
    cache = water_service._Cache()
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError("upstream down")

    for _ in range(2):
        try:
            cache.get("new", 60, broken)
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected the loader error")
    assert len(calls) == 1


def test_water_cache_serves_old_value_while_one_thread_refreshes():
    cache = water_service._Cache()
    cache.get("summary", 0, lambda: "old")

    def slow():
        time.sleep(0.3)
        return "new"

    t = _slow_in_background(lambda: cache.get("summary", 0, slow))
    t0 = time.perf_counter()
    value, _stale = cache.get("summary", 0, slow)
    assert value == "old" and time.perf_counter() - t0 < 0.1
    t.join()


def test_weather_series_remembers_a_failure_for_a_while(monkeypatch):
    monkeypatch.setattr(weather_now, "_cache", {})
    monkeypatch.setattr(weather_now, "_failed", {})
    calls = []

    def down(req, timeout=None):
        calls.append(1)
        raise OSError("met.no down")

    monkeypatch.setattr(urllib.request, "urlopen", down)
    for _ in range(2):
        try:
            weather_now._series(13.75, 100.5)
        except OSError:
            pass
        else:
            raise AssertionError("expected the upstream error")
    assert len(calls) == 1


def test_weather_series_serves_old_series_while_one_thread_refreshes(monkeypatch):
    monkeypatch.setattr(weather_now, "_cache", {(13.75, 100.5): (0, ["old"])})   # fetched long ago: stale
    monkeypatch.setattr(weather_now, "_failed", {})
    body = json.dumps({"properties": {"timeseries": ["new"]}}).encode()

    def slow(req, timeout=None):
        time.sleep(0.3)
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", slow)
    t = _slow_in_background(lambda: weather_now._series(13.75, 100.5))
    t0 = time.perf_counter()
    assert weather_now._series(13.75, 100.5) == ["old"]
    assert time.perf_counter() - t0 < 0.1
    t.join()


def test_longdo_serves_old_list_while_one_thread_refreshes(monkeypatch, tmp_path):
    mod = _longdo(monkeypatch, tmp_path)
    old = {"total": 1, "items": [{"camid": "old"}]}
    monkeypatch.setattr(mod, "_cache", {"data": old, "next_try": 0.0})   # due for a live try

    def slow(req, timeout=None):
        time.sleep(0.3)
        return _FakeResponse(_longdo_body())

    monkeypatch.setattr(urllib.request, "urlopen", slow)
    t = _slow_in_background(mod.longdo_cameras)
    t0 = time.perf_counter()
    assert mod.longdo_cameras() is old
    assert time.perf_counter() - t0 < 0.1
    t.join()
