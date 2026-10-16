# API Micro-Cache (Load Capacity Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise production capacity from ~200 req/s to the 600 req/s target. The busy GET endpoints answer from JSON and gzip bytes encoded at most once every 10 seconds, instead of encoding on every request.

**Architecture:** A new `backend/core/response_cache.py` keeps, per key, the encoded JSON body and its gzip copy. One thread rebuilds a stale key. Other callers get the old bytes at once, or wait only when nothing is cached yet. Each busy route handler wraps its data call in `cached_json(request, key, build)`. Phase 2 (process split) is outlined at the end and gets its own plan only if Phase 1 misses the target.

**Tech Stack:** Python 3.14, FastAPI/Starlette, `gzip`, `json`, pytest, aiohttp (load test only).

**Spec:** This document plus the decisions of 2026-10-13. There is no separate spec file. The facts below were measured that day on production (`instances/production`, single uvicorn process, 12-core Windows host):
- Ramp load test (visit mix in `local/loadtest/loadtest.py`): 200 req/s holds (p95 0.1-0.6 s), 250 req/s breaks (10-29 % errors). Server CPU sits at ~1.1 core, which is the GIL limit of one process.
- Per-request JSON encoding cost (FastAPI `jsonable_encoder` + `JSONResponse`): `/api/cameras/all` 84 ms (1.7 MB), `/api/traffic/areas` 18 ms plus gzip, `/api/traffic/summary` 7.7 ms, `/api/air/stations` 3.5 ms, `/api/flood/reports` 2.3 ms, `/api/traffic/guidance` 2.0 ms. Weighted by the visit mix, that is ~4 ms of CPU per request, ~0.85 core at 200 req/s. Plain `json.dumps` of the same data is 6-8x faster.

## Global Constraints

- Cache age: `TTL = 10` seconds. The user picked this. Data on a page may be at most 10 s older than the source.
- Load target: 600 req/s with error rate ≤ 1 % and p95 ≤ 1 s, measured direct to the origin (`127.0.0.2:8000`).
- Response bodies must stay byte-for-byte equal to what FastAPI produces today, apart from key order and whitespace: same JSON value, `ensure_ascii=False`, `allow_nan=False` (FastAPI raises on NaN; keep that).
- No new runtime dependency. Tests must not import the real `backend.services`: it loads YOLO and starts camera threads beside production. Tests stub it (see Task 2).
- Run tests with `.venv/Scripts/python.exe -m pytest -q tests` (Windows, Git Bash). The suite was 246 passed before this plan.
- Production deploy = `launch\production\restart.bat` in a new window. The server is down ~15 s. Never build or test against `instances/production/dist`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Per-viewer query parameters must never cross.** `/api/traffic/summary?top=25` and `?top=8` are different keys, and so are `/api/alerts/recent?limit=`, `/api/news?kind=` and `/api/flood/status?min_cm=`. A reviewer should check that every wired handler puts every query parameter into its key. Task 2 has a test for `top`.
2. **Error answers are not cached.** `water_summary` returns a `JSONResponse(503)` when the water service fails. A `Response` from `build` must pass through uncached, so the next request retries. Task 1 has a test.
3. **A build that raises after a good value was cached serves the old bytes.** A brief upstream error must not become a 500 for every viewer. Task 1 has a test.
4. **Each request gets its own `Response` object.** `access_guard.guard` adds the `bkk_s` session cookie and security headers to the response afterwards. A shared `Response` would leak one viewer's `Set-Cookie` to another. Task 1 has a test.
5. **Memory stays bounded.** Keys include query values that viewers choose, so the store keeps at most `MAX_KEYS = 256` entries and evicts the least recently used. Task 1 has a test.

---

## File Structure

- Create `backend/core/response_cache.py`: the encoded-response store (`ResponseCache`) and the module-level helper `cached_json(request, key, build)` that route handlers call. It has one job: turn a Python value into cached JSON/gzip bytes and a fresh `Response`.
- Modify route handlers (wiring only, no data logic changes):
  - `backend/api/traffic.py`: `/api/traffic/summary`, `/api/traffic/areas`, `/api/traffic/guidance`, `/api/analytics/summary`
  - `backend/api/flood.py`: `/api/flood/status`, `/api/flood/reports`
  - `backend/api/weather.py`: `/api/air/stations`
  - `backend/api/water.py`: `/api/water/summary`
  - `backend/api/insights.py`: `/api/news`
  - `backend/api/site.py`: `/api/alerts/recent`
  - `backend/api/bma.py`: `/api/bma/analytics`
  - `backend/api/cameras.py`: `/api/cameras`, `/api/cameras/all`
- Create `tests/test_response_cache.py` (Task 1) and `tests/test_api_micro_cache.py` (Tasks 2-3).
- Create `local/loadtest/loadtest.py` (Task 4): the load test used for the measurements above, kept in the repo so Phase 1 and later changes are measured the same way.

Left out on purpose: `/api/weather/now` (per-viewer coordinates, small body, already cached per cell), `/api/telemetry/online`, `/api/incidents`, `/api/ai/stats`, `/api/survey/ranking` and `/api/cameras/down` (bodies under 1 KB, encoding < 0.1 ms).

---

### Task 1: The response cache

**Files:**
- Create: `backend/core/response_cache.py`
- Test: `tests/test_response_cache.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `class ResponseCache(ttl: float = TTL, max_keys: int = MAX_KEYS, clock: Callable[[], float] = time.monotonic)`
    - `.response(accept_encoding: str, key: Hashable, build: Callable[[], Any]) -> starlette.responses.Response`
  - `cached_json(request: fastapi.Request, key: Hashable, build: Callable[[], Any]) -> Response`: uses a module-level `ResponseCache()`.
  - Constants `TTL = 10`, `MAX_KEYS = 256`, `GZIP_MIN_BYTES = 1024`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_response_cache.py`:

```python
"""Encoded-response cache: JSON and gzip bytes built once per TTL, served to every viewer."""
import gzip
import json
import threading
import time
from datetime import datetime

import pytest
from starlette.responses import JSONResponse

from backend.core.response_cache import ResponseCache


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _counting(value):
    calls = []

    def build():
        calls.append(1)
        return value

    return build, calls


def test_builds_once_within_ttl_and_again_after():
    clock = Clock()
    cache = ResponseCache(ttl=10, clock=clock)
    build, calls = _counting({"a": 1})
    assert json.loads(cache.response("", "k", build).body) == {"a": 1}
    cache.response("", "k", build)
    assert len(calls) == 1
    clock.now += 11
    cache.response("", "k", build)
    assert len(calls) == 2


def test_gzip_only_when_accepted_and_worth_it():
    cache = ResponseCache()
    big = {"text": "กรุงเทพ" * 500}
    r = cache.response("gzip, deflate, br", "big", lambda: big)
    assert r.headers["content-encoding"] == "gzip"
    assert r.headers["vary"] == "Accept-Encoding"
    assert json.loads(gzip.decompress(r.body)) == big
    plain = cache.response("", "big", lambda: big)
    assert "content-encoding" not in plain.headers
    assert json.loads(plain.body) == big
    small = cache.response("gzip", "small", lambda: {"a": 1})
    assert "content-encoding" not in small.headers   # under GZIP_MIN_BYTES: gzip would only add bytes


def test_body_matches_fastapi_encoding():
    value = {"t": datetime(2026, 10, 13, 21, 0), "s": {3}, "thai": "น้ำท่วม", "n": None}
    cache = ResponseCache()
    ours = cache.response("", "k", lambda: value)
    from fastapi.encoders import jsonable_encoder
    theirs = JSONResponse(jsonable_encoder(value))
    assert json.loads(ours.body) == json.loads(theirs.body)
    assert "น้ำท่วม".encode() in ours.body   # ensure_ascii=False, like FastAPI
    assert ours.headers["content-type"] == "application/json"


def test_nan_is_refused_like_fastapi():
    cache = ResponseCache()
    with pytest.raises(ValueError):
        cache.response("", "k", lambda: {"x": float("nan")})


def test_concurrent_callers_share_one_build():
    cache = ResponseCache()
    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.2)
        return {"v": 1}

    barrier = threading.Barrier(8)
    bodies = []

    def run():
        barrier.wait()
        bodies.append(cache.response("", "k", slow).body)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(calls) == 1
    assert len(set(bodies)) == 1 and len(bodies) == 8


def test_old_bytes_served_while_one_thread_rebuilds():
    clock = Clock()
    cache = ResponseCache(ttl=10, clock=clock)
    cache.response("", "k", lambda: {"v": "old"})
    clock.now += 11

    def slow():
        time.sleep(0.3)
        return {"v": "new"}

    t = threading.Thread(target=lambda: cache.response("", "k", slow))
    t.start()
    time.sleep(0.05)
    t0 = time.perf_counter()
    assert json.loads(cache.response("", "k", slow).body) == {"v": "old"}
    assert time.perf_counter() - t0 < 0.1
    t.join()
    assert json.loads(cache.response("", "k", slow).body) == {"v": "new"}


def test_build_error_serves_last_good_bytes():
    clock = Clock()
    cache = ResponseCache(ttl=10, clock=clock)
    cache.response("", "k", lambda: {"v": "good"})
    clock.now += 11

    def broken():
        raise RuntimeError("source down")

    assert json.loads(cache.response("", "k", broken).body) == {"v": "good"}


def test_build_error_without_cache_raises():
    cache = ResponseCache()

    def broken():
        raise RuntimeError("source down")

    with pytest.raises(RuntimeError):
        cache.response("", "k", broken)


def test_response_from_build_passes_through_uncached():
    cache = ResponseCache()
    calls = []

    def failing_answer():
        calls.append(1)
        return JSONResponse(status_code=503, content={"error": "down"})

    assert cache.response("", "k", failing_answer).status_code == 503
    assert cache.response("", "k", failing_answer).status_code == 503
    assert len(calls) == 2   # not cached: the next request tries again


def test_each_request_gets_its_own_response_object():
    cache = ResponseCache()
    a = cache.response("", "k", lambda: {"v": 1})
    a.set_cookie("bkk_s", "viewer-a")
    b = cache.response("", "k", lambda: {"v": 1})
    assert a is not b
    assert "set-cookie" not in b.headers


def test_keys_are_bounded_least_recently_used_out():
    cache = ResponseCache(max_keys=3)
    for k in ("a", "b", "c"):
        cache.response("", k, lambda: {"k": 1})
    cache.response("", "a", lambda: {"k": 1})     # touch a: b is now the oldest
    cache.response("", "d", lambda: {"k": 1})
    assert set(cache.keys()) == {"a", "c", "d"}
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_response_cache.py`
Expected: collection error `ModuleNotFoundError: No module named 'backend.core.response_cache'`.

- [ ] **Step 3: Write the implementation**

Create `backend/core/response_cache.py`:

```python
"""
Encoded API answers kept for TTL seconds (load test, 2026-10-13).

FastAPI encodes a returned dict on every request (jsonable_encoder + JSONResponse): 84 ms for the 1.7 MB
camera list, 8-18 ms for the traffic summaries, about 4 ms a request across a dashboard visit. In one
process that was most of the CPU at 200 req/s. Here each key's JSON and gzip bytes are built at most once
per TTL and every viewer gets a new Response around the same bytes (the access guard then adds that
viewer's cookie and headers to it).

One thread rebuilds a stale key; the others get the old bytes at once, or wait when there are none yet.
A build that raises keeps the old bytes; a build that returns a Response (an error answer) is passed
through and not kept, so the next request tries again.
"""
import gzip
import json
import threading
import time
from collections import OrderedDict

from fastapi.encoders import jsonable_encoder
from starlette.responses import Response

TTL = 10               # seconds: how much older than its source an answer may be
MAX_KEYS = 256         # keys carry query values, so the store is bounded (least recently used out)
GZIP_MIN_BYTES = 1024  # smaller bodies grow under gzip


def _encode(value):
    # Same output as FastAPI (ensure_ascii=False, NaN refused); jsonable_encoder only for what json cannot do
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
                      default=jsonable_encoder).encode("utf-8")


class ResponseCache:
    def __init__(self, ttl=TTL, max_keys=MAX_KEYS, clock=time.monotonic):
        self.ttl = ttl
        self.max_keys = max_keys
        self.clock = clock
        self.lock = threading.Lock()      # guards the dicts only, never held while building
        self.entries = OrderedDict()      # key -> (body, gzip body or None, built_at)
        self.key_locks = {}               # key -> Lock held by the one caller building that key

    def keys(self):
        with self.lock:
            return list(self.entries)

    def _get(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry is not None:
                self.entries.move_to_end(key)
            return entry, self.key_locks.setdefault(key, threading.Lock())

    def _put(self, key, entry):
        with self.lock:
            self.entries[key] = entry
            self.entries.move_to_end(key)
            while len(self.entries) > self.max_keys:
                old, _ = self.entries.popitem(last=False)
                self.key_locks.pop(old, None)

    def _entry(self, key, build):
        """(body, gz) for the key, or a Response from build to pass through."""
        entry, key_lock = self._get(key)
        if entry and self.clock() - entry[2] < self.ttl:
            return entry
        if not key_lock.acquire(blocking=entry is None):
            return entry                  # being rebuilt right now: the old bytes are seconds older at most
        try:
            again, _ = self._get(key)
            if again and self.clock() - again[2] < self.ttl:
                return again
            try:
                value = build()
            except Exception:
                if entry:
                    return entry          # keep serving the last good answer
                raise
            if isinstance(value, Response):
                return value
            body = _encode(value)
            gz = gzip.compress(body, 6) if len(body) >= GZIP_MIN_BYTES else None
            entry = (body, gz, self.clock())
            self._put(key, entry)
            return entry
        finally:
            key_lock.release()

    def response(self, accept_encoding, key, build):
        entry = self._entry(key, build)
        if isinstance(entry, Response):
            return entry
        body, gz, _ = entry
        if gz is not None and "gzip" in (accept_encoding or ""):
            return Response(gz, media_type="application/json",
                            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
        headers = {"Vary": "Accept-Encoding"} if gz is not None else None
        return Response(body, media_type="application/json", headers=headers)


_cache = ResponseCache()


def cached_json(request, key, build):
    """The route's answer from the shared cache: `build()` gives the value FastAPI would have encoded."""
    return _cache.response(request.headers.get("accept-encoding", ""), key, build)
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_response_cache.py`
Expected: `11 passed`.
Then run: `.venv/Scripts/python.exe -m pytest -q tests`
Expected: `257 passed` (246 + 11).

- [ ] **Step 5: Commit**

```bash
git add backend/core/response_cache.py tests/test_response_cache.py
git commit -m "feat(core): response cache for encoded API answers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Wire the traffic, water, weather, flood, news, alerts and BMA endpoints

**Files:**
- Modify: `backend/api/traffic.py` (`traffic_summary`, `traffic_areas`, `traffic_guidance`, `analytics_summary`)
- Modify: `backend/api/water.py` (`water_summary`)
- Modify: `backend/api/weather.py` (`air_stations`)
- Modify: `backend/api/flood.py` (`flood_status`, `flood_reports`)
- Modify: `backend/api/insights.py` (`news`)
- Modify: `backend/api/site.py` (`alerts_recent`)
- Modify: `backend/api/bma.py` (`get_bma_analytics`)
- Test: `tests/test_api_micro_cache.py`

**Interfaces:**
- Consumes: `cached_json(request, key, build)` from Task 1 (`backend.core.response_cache`).
- Produces: the module-level test helper `_router_client(module_name)` in `tests/test_api_micro_cache.py`, which Task 3 extends.

Keys: a tuple of the path without `/api/` plus every query parameter, e.g. `("traffic/summary", top)`. Every handler gets a `request: Request` parameter. Add `Request` to the `from fastapi import ...` line where it is missing (weather, insights, site, bma, water). Drop the now-unused `gzip` import in `traffic.py` only if nothing else in the file uses it (check with grep first).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_micro_cache.py`:

```python
"""The busy GET routes answer from the response cache: data source called once per TTL, gzip when asked.

The routers are imported with a stub backend.services: the real one loads YOLO and starts camera threads."""
import gzip
import importlib
import json
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import response_cache


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(response_cache, "_cache", response_cache.ResponseCache())


def _router_module(name):
    if "backend.services" not in sys.modules:
        stub = types.ModuleType("backend.services")
        stub.__getattr__ = lambda attr: MagicMock(name=attr)
        sys.modules["backend.services"] = stub
    return importlib.import_module(f"backend.api.{name}")


def _router_client(name):
    module = _router_module(name)
    app = FastAPI()
    app.include_router(module.router)
    return module, TestClient(app)


class Source:
    """Stands in for a service object: every method returns `value` and counts the calls."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.calls += 1
            return self.value
        return method


ROUTES = [  # (router module, attribute the handler reads, path)
    ("traffic", "traffic", "/api/traffic/summary?top=25"),
    ("traffic", "area_traffic", "/api/traffic/areas"),
    ("traffic", "guidance", "/api/traffic/guidance"),
    ("traffic", "analytics_service", "/api/analytics/summary"),
    ("water", "water_service", "/api/water/summary"),
    ("weather", "air", "/api/air/stations"),
    ("flood", "flood_roads", "/api/flood/status"),
    ("flood", "traffy_reports", "/api/flood/reports"),
    ("insights", "news_feed", "/api/news?kind=flood"),
    ("site", "alerts", "/api/alerts/recent?limit=20"),
    ("bma", "bma_scanner", "/api/bma/analytics"),
]


@pytest.mark.parametrize("module_name,attr,path", ROUTES)
def test_route_builds_once_per_ttl(monkeypatch, module_name, attr, path):
    module, client = _router_client(module_name)
    source = Source({"text": "น้ำท่วม" * 400})
    monkeypatch.setattr(module, attr, source)
    first = client.get(path, headers={"Accept-Encoding": "gzip"})
    second = client.get(path, headers={"Accept-Encoding": "gzip"})
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"text": "น้ำท่วม" * 400}
    assert first.headers["content-encoding"] == "gzip"
    assert source.calls == 1


def test_query_parameters_are_separate_keys(monkeypatch):
    module, client = _router_client("traffic")
    seen = []

    class Traffic:
        def get_summary(self, top):
            seen.append(top)
            return {"top": top}

    monkeypatch.setattr(module, "traffic", Traffic())
    assert client.get("/api/traffic/summary?top=25").json() == {"top": 25}
    assert client.get("/api/traffic/summary?top=8").json() == {"top": 8}
    assert seen == [25, 8]


def test_analytics_refresh_skips_the_cache(monkeypatch):
    module, client = _router_client("traffic")
    source = Source({"v": 1})
    monkeypatch.setattr(module, "analytics_service", source)
    client.get("/api/analytics/summary")
    client.get("/api/analytics/summary?refresh=true")
    assert source.calls == 2


def test_water_error_answer_is_not_cached(monkeypatch):
    module, client = _router_client("water")

    class Broken:
        calls = 0

        def get_summary(self):
            Broken.calls += 1
            raise RuntimeError("thaiwater down")

        def key_status(self):
            return "ok"

    monkeypatch.setattr(module, "water_service", Broken())
    assert client.get("/api/water/summary").status_code == 503
    assert client.get("/api/water/summary").status_code == 503
    assert Broken.calls == 2
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_api_micro_cache.py`
Expected: the 11 parametrized cases fail with `assert 2 == 1` (source called on every request), or on `content-encoding` missing; `test_analytics_refresh_skips_the_cache` passes already (2 calls either way); `test_query_parameters_are_separate_keys` and `test_water_error_answer_is_not_cached` pass already. Confirm the failures are those, not import errors. If importing a router pulls in `torch` or starts threads, stop and report.

- [ ] **Step 3: Wire the handlers**

`backend/api/traffic.py` (keep the docstrings that are there):

```python
@router.get("/api/traffic/summary")
def traffic_summary(request: Request, top: int = Query(8, ge=1, le=30)):
    return cached_json(request, ("traffic/summary", top), lambda: traffic.get_summary(top=top))

@router.get("/api/traffic/areas")
def traffic_areas(request: Request):
    """Traffic score per province and district from Longdo's lines over the whole country (area_traffic.py)."""
    return cached_json(request, ("traffic/areas",), area_traffic.status)
```

```python
@router.get("/api/traffic/guidance")
def traffic_guidance(request: Request):
    """Live dispersal guidance per main corridor: hotspots, bypass roads with live flow, advice text."""
    return cached_json(request, ("traffic/guidance",), guidance.status)
```

```python
@router.get("/api/analytics/summary")
def analytics_summary(request: Request, refresh: bool = Query(False)):
    """Traffic overview, flood watch + 1-6 h outlook, density tiers, black spots, dashboard visitors."""
    if refresh:
        return analytics_service.get_summary(force=True)
    return cached_json(request, ("analytics/summary",), analytics_service.get_summary)
```

Add near the other imports in `traffic.py`: `from backend.core.response_cache import cached_json`.

`backend/api/water.py`:

```python
@router.get("/api/water/summary")
def water_summary(request: Request):
    def build():
        try:
            return water_service.get_summary()
        except Exception as e:
            return JSONResponse(status_code=503, content={"error": str(e), "api_key": water_service.key_status()})
    return cached_json(request, ("water/summary",), build)
```

`backend/api/weather.py`:

```python
@router.get("/api/air/stations")
def air_stations(request: Request):
    """PM2.5 / AQI per monitoring station in Bangkok + surrounding provinces (Air4Thai)."""
    return cached_json(request, ("air/stations",), air.status)
```

`backend/api/flood.py`:

```python
@router.get("/api/flood/status")
def flood_status(request: Request, min_cm: float = Query(None, ge=0, le=200)):
    """Counts, every wet station and the per-district roll-up, for the flood layer on the map."""
    return cached_json(request, ("flood/status", min_cm), lambda: flood_roads.status(min_cm=min_cm))
```

```python
@router.get("/api/flood/reports")
def flood_reports(request: Request):
    """Flood complaints from Traffy Fondue in the last few hours, newest first."""
    return cached_json(request, ("flood/reports",), traffy_reports.status)
```

`backend/api/insights.py`:

```python
@router.get("/api/news")
def news(request: Request, kind: str = Query(None, pattern="^(flood|accident)$")):
    """Flood and road-accident headlines from Thai news outlets' own RSS feeds, newest first (news_feed.py)."""
    return cached_json(request, ("news", kind), lambda: news_feed.status(kind))
```

`backend/api/site.py`:

```python
@router.get("/api/alerts/recent")
def alerts_recent(request: Request, limit: int = Query(50, ge=1, le=200)):
    return cached_json(request, ("alerts/recent", limit), lambda: alerts.recent(limit))
```

`backend/api/bma.py`:

```python
@router.get("/api/bma/analytics")
def get_bma_analytics(request: Request):
    """Returns comprehensive data analysis for BMA cameras vehicle counts."""
    return cached_json(request, ("bma/analytics",), bma_scanner.get_analytics)
```

Note on `Source.__getattr__` in the test: `area_traffic.status`, `guidance.status`, `air.status` and the others are looked up on the module attribute at call time. That is why the handlers pass bound methods, never names captured at import time.

In each of these 7 files add `from backend.core.response_cache import cached_json`, and add `Request` to the `from fastapi import ...` line if it is missing.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_api_micro_cache.py`
Expected: `14 passed`.
Run: `.venv/Scripts/python.exe -m pytest -q tests`
Expected: `271 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/api/traffic.py backend/api/water.py backend/api/weather.py backend/api/flood.py backend/api/insights.py backend/api/site.py backend/api/bma.py tests/test_api_micro_cache.py
git commit -m "perf(api): serve busy dashboard routes from the response cache

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Wire the camera lists

**Files:**
- Modify: `backend/api/cameras.py` (`get_cameras`, `get_all_cameras`)
- Test: `tests/test_api_micro_cache.py` (append)

**Interfaces:**
- Consumes: `cached_json` (Task 1); `_router_client`, `fresh_cache` fixture (Task 2's test file).
- Produces: `_all_cameras() -> dict` in `backend/api/cameras.py`: the `{"total", "items"}` value `/api/cameras/all` returns.

`get_all_cameras` builds its list, `json.dumps` and gzips it on every call (84 ms for the encoding alone). Move the list-building part into `_all_cameras()`, which returns the dict, and let the handler cache it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_micro_cache.py`:

```python
def test_all_cameras_built_once_per_ttl(monkeypatch):
    module, client = _router_client("cameras")
    calls = []

    def build():
        calls.append(1)
        return {"total": 1, "items": [{"camid": "c1", "title": "สี่แยก" * 300}]}

    monkeypatch.setattr(module, "_all_cameras", build)
    a = client.get("/api/cameras/all", headers={"Accept-Encoding": "gzip"})
    b = client.get("/api/cameras/all", headers={"Accept-Encoding": "gzip"})
    assert a.json() == b.json() and a.json()["items"][0]["camid"] == "c1"
    assert a.headers["content-encoding"] == "gzip"
    assert len(calls) == 1


def test_camera_list_cached(monkeypatch):
    module, client = _router_client("cameras")
    monkeypatch.setattr(module, "cameras_data", [{"camid": "x" * 2000}])
    assert client.get("/api/cameras").json() == {"total": 1, "items": [{"camid": "x" * 2000}]}
    monkeypatch.setattr(module, "cameras_data", [])
    assert client.get("/api/cameras").json()["total"] == 1   # still the cached answer inside the TTL
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_api_micro_cache.py -k "cameras"`
Expected: `test_all_cameras_built_once_per_ttl` fails with `AttributeError: ... has no attribute '_all_cameras'` (monkeypatch `raising=True`). `test_camera_list_cached` fails on `assert 0 == 1`.

- [ ] **Step 3: Implement**

In `backend/api/cameras.py`:
1. Rename the body of `get_all_cameras` into a new module-level function `def _all_cameras():`. Keep the docstring there. Keep every line from `doh_live = ...` through the `for c in items:` province loop unchanged. End it with `return {"total": len(items), "items": items}` in place of the `body = json.dumps(...)` / gzip / `Response` lines.
2. Replace the handler:

```python
@router.get("/api/cameras/all")
def get_all_cameras(request: Request):
    """Every camera for the live camera page (see _all_cameras), about 1.7 MB: built and gzipped once per TTL."""
    return cached_json(request, ("cameras/all",), _all_cameras)
```

```python
@router.get("/api/cameras")
def get_cameras(request: Request):
    return cached_json(request, ("cameras",), lambda: {"total": len(cameras_data), "items": cameras_data})
```

3. Add `from backend.core.response_cache import cached_json`. Remove `import gzip` if grep shows no other use in the file.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests`
Expected: `273 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/api/cameras.py tests/test_api_micro_cache.py
git commit -m "perf(api): build and gzip the camera lists once per TTL

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Keep the load test in the repo, deploy, measure

**Files:**
- Create: `local/loadtest/loadtest.py` (copy of the session's scratchpad script `loadtest/loadtest.py`, which already has `LT_STEPS`, `LT_SECONDS`, `LT_SKIP` and per-path stats)
- Create: `local/loadtest/README.md`

**Interfaces:**
- Consumes: Tasks 1-3 deployed.
- Produces: `local/loadtest/results.json` (ignored by git: add `local/loadtest/results.json` to `.gitignore`).

This task has no unit test: it is the measurement the plan exists for.

- [ ] **Step 1: Add the script and README.** README content, in plain English:

```markdown
# Load test

Step load test against a running server's origin. It never goes through Cloudflare.

    .venv\Scripts\python.exe -I local\loadtest\loadtest.py instances\production\cache\osm

- Each request carries a fake visitor IP from 198.18.0.0/15 (benchmark range) in CF-Connecting-IP, so the
  per-IP limiter sees many visitors. It also sends the page-session cookie and `Sec-Fetch-Site`, like a browser.
- Only endpoints that read background snapshots and cached map tiles are used. Nothing calls ThaiWater,
  MET Norway, Longdo, BMA or the AI gateway, and no telemetry is written.
- It stops by itself at > 5 % errors or p95 > 3 s. Real visitors feel each step: run it when the site is quiet.
- LT_STEPS=100,200 sets the steps (req/s), LT_SECONDS the seconds per step, LT_SKIP=/api/x leaves a path out.
  In Git Bash, set MSYS_NO_PATHCONV=1 when LT_SKIP starts with "/", or Git Bash rewrites it into a Windows path.
- Results go to results.json next to the script: per step, p50/p95/p99, error codes, server CPU and memory,
  and per-path latency.
```

- [ ] **Step 2: Commit**

```bash
git add local/loadtest/loadtest.py local/loadtest/README.md .gitignore
git commit -m "chore: keep the step load test in the repo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Snapshot the top-level keys BEFORE deploying** (still the old server):

```bash
cd /e/new_ccty_bangkok
H='-H Host:bkksmartstreet.com -H CF-Connecting-IP:198.18.0.9'
C=$(curl -s -D - -o /dev/null $H http://127.0.0.2:8000/ | grep -oE "bkk_s=[^;]+")
snap() { for p in "traffic/summary?top=25" traffic/areas traffic/guidance analytics/summary water/summary air/stations flood/status flood/reports "news?kind=flood" "alerts/recent?limit=20" bma/analytics cameras cameras/all; do
  printf '%s ' "$p"; curl -s --compressed $H -H "Sec-Fetch-Site: same-origin" -H "Cookie: $C" -w ' %{http_code}' "http://127.0.0.2:8000/api/$p" \
  | .venv/Scripts/python.exe -I -c "import sys,json; raw=sys.stdin.read(); body,code=raw.rsplit(' ',1); d=json.loads(body); print(code, sorted(d) if isinstance(d,dict) else type(d).__name__)"; done; }
snap > /tmp/keys_before.txt; cat /tmp/keys_before.txt
```

- [ ] **Step 4: Deploy.** In PowerShell: `Start-Process cmd.exe -ArgumentList '/c','"E:\new_ccty_bangkok\launch\production\restart.bat"' -WorkingDirectory E:\new_ccty_bangkok`. Wait until `netstat -ano | grep ":8000 .*LISTEN"` shows a new PID and `/` answers 200. Wait until `/api/traffic/summary` has `"ready":true`. Wait until the server's idle CPU (psutil `cpu_percent` over 5 s) is under 20 %.

- [ ] **Step 5: Parity check.** Run the `snap` function again (re-fetch `C` first: a restart keeps the session secret, so the old cookie still works). `snap > /tmp/keys_after.txt && diff /tmp/keys_before.txt /tmp/keys_after.txt`. Expected: no difference. Then open https://bkksmartstreet.com dashboard, map (`#/map`) and live cameras (`#/cameras`) in a browser. The console should have no errors, and the tiles and camera list should show data.

- [ ] **Step 6: Measure.** Run `LT_STEPS=200,300,400,500,600,750` with `local/loadtest/loadtest.py`. Record each step's p95, error % and server CPU in the PR description.

- [ ] **Step 7: Decide.** If 600 req/s holds (≤ 1 % errors, p95 ≤ 1 s), Phase 1 is done: open a PR from `perf/load-hotspots`. If not, take the per-path stats of the first failing step and the server CPU. Then go to Phase 2 with those numbers.

---

## Phase 2 outline (separate plan, only if Phase 1 misses 600 req/s)

Not bite-sized on purpose. It gets its own brainstorm and plan with the Phase 1 numbers in hand.

- **Engine process** (`engine.py`): today's `services.start()` with YOLO, the BMA scanner, the agents and every background job. It writes each job's `.status()` as an atomic JSON snapshot (`instances/<instance>/snapshots/<name>.json`, write to a temp file and `os.replace`). It writes after each refresh, not on a timer.
- **Web workers** (`uvicorn server:app --workers N`, with `server.py` building the app without starting jobs): the API reads snapshots. Each read is cached in memory by file mtime, and the Phase 1 response cache keeps the encoded bytes. The engine and the workers share the data stores they already have (SQLite DBs, the session secret file).
- **Moves to the engine** behind a local HTTP port (127.0.0.1 only):
  - control endpoints (POST/PUT that change AI or the scanner)
  - live video and MJPEG endpoints
  - the chat agent, if it needs the live objects
- **Rate limits** are per worker under N workers. Either accept N× limits or move the windows to SQLite.
- **Risks:**
  - every `.status()` caller has to be found and moved
  - jobs that serve data from memory only (e.g. live detector stats)
  - Windows `--workers` uses spawn, so the app must be importable without side effects
  - doubled RAM, ~2 GB per worker today, minus YOLO
