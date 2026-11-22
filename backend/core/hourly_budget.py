"""Rolling-hour cap on AI calls, safe to spend from several worker threads at once."""
import threading
import time
from collections import deque


class HourlyBudget:
    def __init__(self, limit, window_s=3600):
        self.limit = limit          # read on every check, so a runtime change takes effect
        self.window_s = window_s
        self._ts = deque()          # spend times, oldest first
        self._lock = threading.Lock()  # appends from worker threads must not be lost

    def used(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            while self._ts and now - self._ts[0] >= self.window_s:
                self._ts.popleft()
            return len(self._ts)

    def allows(self, now=None):
        return self.used(now) < self.limit

    def spend(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._ts.append(now)

    def try_spend(self, now=None):
        """Reserve one slot if the window has room. Check and record happen under one lock,
        so concurrent callers can never all pass a check that only one of them should."""
        now = time.time() if now is None else now
        with self._lock:
            while self._ts and now - self._ts[0] >= self.window_s:
                self._ts.popleft()
            if len(self._ts) < self.limit:
                self._ts.append(now)
                return True
            return False
