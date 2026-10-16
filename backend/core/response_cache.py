"""
Encoded API answers kept for TTL seconds (load test, 2026-10-13).

FastAPI encodes a returned dict on every request (jsonable_encoder + JSONResponse): 84 ms for the 1.7 MB
camera list, 8-18 ms for the traffic summaries, about 4 ms a request across a dashboard visit. In one
process that was most of the CPU at 200 req/s. Here each key's JSON and gzip bytes are built at most once
per TTL and every viewer gets a new Response around the same bytes (the access guard then adds that
viewer's cookie and headers to it).

One thread rebuilds a stale key; the others get the old bytes at once, or wait when there are none yet.
A build that raises, or returns a Response (an error answer), keeps the old bytes and the next try waits one TTL.
With no old bytes a Response is passed through and not kept, so the next request tries again.
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

    def _keep_old(self, key, entry):
        # keep serving the last good answer; the next try waits one TTL
        entry = (entry[0], entry[1], self.clock())
        self._put(key, entry)
        return entry

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
                    return self._keep_old(key, entry)
                raise
            if isinstance(value, Response):
                # an error answer: viewers keep the last good bytes when there are any
                return self._keep_old(key, entry) if entry else value
            body = _encode(value)
            gz = gzip.compress(body, 6) if len(body) >= GZIP_MIN_BYTES else None
            entry = (body, gz, self.clock())
            self._put(key, entry)
            return entry
        finally:
            key_lock.release()
            with self.lock:
                if key not in self.entries:   # nothing cached: no lock to keep for this key
                    self.key_locks.pop(key, None)

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
