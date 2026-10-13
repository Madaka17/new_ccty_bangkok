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
