"""Shared live frames and stream slots for the BMA camera endpoints.

Pure module: no import of backend.services, so it can be tested on its own.

- LiveCache: one BMA fetch + YOLO run per camera per ttl, shared by every viewer. A miss (None or an
  exception) is cached as None for the same ttl so a dead camera is not hammered.
- StreamSlots: caps how many MJPEG streams are open at once, in total and per client.
"""
import logging
import threading
import time
from collections import OrderedDict

log = logging.getLogger("bma_live")


class LiveCache:
    def __init__(self, ttl, max_keys=256, clock=time.monotonic):
        self._ttl = float(ttl)
        self._max_keys = int(max_keys)
        self._clock = clock
        self._mutex = threading.Lock()
        self._entries = OrderedDict()  # key -> (expires_at, value), least recently used first
        self._locks = {}               # key -> [per-key lock, number of callers using it]

    def get(self, key, fetch):
        with self._mutex:
            value = self._fresh(key)
            if value is not _MISS:
                return value
            slot = self._locks.get(key)
            if slot is None:
                slot = [threading.Lock(), 0]
                self._locks[key] = slot
            slot[1] += 1
        try:
            with slot[0]:
                # Another caller may have filled the entry while this one waited for the lock.
                with self._mutex:
                    value = self._fresh(key)
                if value is not _MISS:
                    return value
                value = self._run(fetch, key)
                with self._mutex:
                    self._entries[key] = (self._clock() + self._ttl, value)
                    self._entries.move_to_end(key)
                    while len(self._entries) > self._max_keys:
                        self._entries.popitem(last=False)
                return value
        finally:
            with self._mutex:
                slot[1] -= 1
                if slot[1] == 0 and self._locks.get(key) is slot:
                    del self._locks[key]

    def _fresh(self, key):
        """Caller must hold self._mutex. Returns the cached value, or _MISS."""
        hit = self._entries.get(key)
        if hit is None or self._clock() >= hit[0]:
            return _MISS
        self._entries.move_to_end(key)
        return hit[1]

    @staticmethod
    def _run(fetch, key):
        try:
            return fetch()
        except Exception as e:
            log.debug("live fetch failed for %s: %s", key, e)
            return None


_MISS = object()


class StreamSlots:
    def __init__(self, total, per_key):
        self._total = int(total)
        self._per_key = int(per_key)
        self._mutex = threading.Lock()
        self._count = 0
        self._per = {}

    def acquire(self, key):
        """Returns a release callable, or None when the total or the per-key limit is reached."""
        with self._mutex:
            if self._count >= self._total or self._per.get(key, 0) >= self._per_key:
                return None
            self._count += 1
            self._per[key] = self._per.get(key, 0) + 1
        released = [False]

        def release():
            with self._mutex:
                if released[0]:
                    return
                released[0] = True
                self._count -= 1
                left = self._per.get(key, 0) - 1
                if left > 0:
                    self._per[key] = left
                else:
                    self._per.pop(key, None)

        return release
