"""Track the Bionic requests that are still running, from the newest server log.

The collector (collect.py) only counts a call once its answer is written. This
module answers a different question for the live page: which requests have
started but not finished yet, and how far along each one is.

It reads the newest log file from the end of the tail window and then only the
bytes appended since the last poll. Each poll reads at most `max_read` bytes, so
a large backlog never blocks the page. The state lives in memory and is rebuilt
after a restart from the last `tail_bytes` of the newest log.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import collect

# Read this much from the end of the newest log when the tracker starts.
TAIL_BYTES = 256 * 1024
# Upper bound on the bytes read in one poll (catch-up happens over several polls).
MAX_READ_BYTES = 4 * 1024 * 1024
# A request with no answer after this many seconds (wall clock) is forgotten.
STALE_SECONDS = 3600
# A request body larger than this is skipped instead of being held in memory.
MAX_BLOCK_BYTES = 16 * 1024 * 1024
# A line still missing its newline after this many bytes is dropped, not kept.
MAX_CARRY_BYTES = 8 * 1024 * 1024

PROGRESS_RE = re.compile(r"\[([^\]]+)\] Prompt processing progress:\s*([0-9]+(?:\.[0-9]+)?)%")


@dataclass
class _Flight:
    """One request that was received and has not been answered yet."""

    model: str
    job: str
    started_ts: int
    percent: float | None = None


class LiveTracker:
    """Reads the newest Bionic log and keeps the list of unfinished requests.

    `poll()` is called from one background thread. `snapshot()` may be called
    from any thread; a lock keeps the two apart.
    """

    def __init__(self, log_root: Path, clock=time.time, tail_bytes: int = TAIL_BYTES,
                 max_read: int = MAX_READ_BYTES, max_carry: int = MAX_CARRY_BYTES,
                 log=None) -> None:
        self._root = Path(log_root)
        self._clock = clock
        self._tail_bytes = tail_bytes
        self._max_read = max_read
        self._max_carry = max_carry
        self._log = log or (lambda message: None)
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._offset = 0
        self._carry = b""
        self._skip_first_line = False
        self._discarding = False   # inside a line that was too long: drop bytes to its newline
        self._carry_warned = False
        self._queues: dict[str, deque] = {}
        self._reset_parse_state()
        self._newest_ts: int | None = None

    # -- reading ------------------------------------------------------------

    def poll(self) -> None:
        """Read the bytes appended to the newest log since the last poll."""
        files = collect.list_log_files(self._root)
        if not files:
            return
        newest = files[-1]
        try:
            size = newest.stat().st_size
        except OSError:
            return
        with self._lock:
            if newest != self._path:
                # A new file: unanswered requests from the old one may still be answered here.
                self._start_file(newest, size, keep_queues=True)
            elif size < self._offset:
                # The file was truncated or replaced: read it again from the top.
                self._start_file(newest, 0, keep_queues=False)
            if size <= self._offset:
                return
            try:
                with newest.open("rb") as f:
                    f.seek(self._offset)
                    data = f.read(min(self._max_read, size - self._offset))
            except OSError:
                return
            self._offset += len(data)
            if self._discarding:
                cut = data.find(b"\n")
                if cut < 0:
                    return  # still inside the dropped line
                self._discarding = False
                data = data[cut + 1:]
            buf = self._carry + data
            if b"\n" not in buf:
                self._carry = buf
                self._check_carry()
                return
            parts = buf.split(b"\n")
            self._carry = parts.pop()
            for raw in parts:
                if self._skip_first_line:
                    self._skip_first_line = False
                    continue
                self._handle(_text(raw))
            self._check_carry()

    def _check_carry(self) -> None:
        """Drop a partial line that has grown past the cap, and log it once."""
        if len(self._carry) <= self._max_carry:
            return
        self._carry = b""
        self._discarding = True
        if not self._carry_warned:
            self._carry_warned = True
            self._log(f"a log line longer than {self._max_carry} bytes was dropped; "
                      "later lines are read normally")

    def snapshot(self) -> dict:
        """Return the unfinished requests (oldest first) and the newest log time."""
        now = self._clock()
        with self._lock:
            flights = []
            for model, queue in self._queues.items():
                # Forget requests that have waited too long; they will never be answered.
                kept = deque(f for f in queue if now - f.started_ts <= STALE_SECONDS)
                self._queues[model] = kept
                for f in kept:
                    flights.append({
                        "model": f.model,
                        "job": f.job,
                        "started_ts": f.started_ts,
                        "elapsed_s": int(max(0, now - f.started_ts)),
                        "phase": _phase(f.percent),
                        "percent": f.percent,
                    })
            newest = self._newest_ts
        flights.sort(key=lambda f: f["started_ts"])
        return {"in_flight": flights, "newest_log_ts": newest}

    # -- internal -----------------------------------------------------------

    def _start_file(self, path: Path, start_offset_from_end: int, keep_queues: bool) -> None:
        """Begin reading `path`. A big file is entered near its end, at a line start.

        `start_offset_from_end` is the file size for a new file (so the tail window
        is used) or 0 for a truncated file (read from the top).
        """
        self._path = path
        self._offset = max(0, start_offset_from_end - self._tail_bytes)
        self._skip_first_line = self._offset > 0
        self._carry = b""
        self._discarding = False
        if not keep_queues:
            self._queues = {}
        self._reset_parse_state()

    def _reset_parse_state(self) -> None:
        self._block_lines: list[str] | None = None
        self._block_ts: int | None = None
        self._block_bytes = 0
        self._skip_body = False

    def _handle(self, text: str) -> None:
        """Process one complete log line."""
        stamp = _stamp(text)
        if stamp is not None:
            self._newest_ts = stamp if self._newest_ts is None else max(self._newest_ts, stamp)

        if self._block_lines is not None:
            if text.rstrip() == "}":
                self._finish_request_block()
                return
            if collect.STAMP_RE.match(text):
                # A new record starts before the body closed: the block is corrupt.
                self._reset_parse_state()
            else:
                self._block_bytes += len(text)
                if self._block_bytes > MAX_BLOCK_BYTES:
                    self._reset_parse_state()
                    self._skip_body = True
                else:
                    self._block_lines.append(text)
                return

        if self._skip_body:
            if text.rstrip() == "}":
                self._skip_body = False
                return
            if not collect.STAMP_RE.match(text):
                return
            self._skip_body = False

        if text.startswith("[") and collect.RECEIVED_RE.search(text):
            # Every request with a JSON body is read to its closing brace. Only
            # inference endpoints are queued; load and unload calls are ignored.
            endpoint = collect.RECEIVED_RE.search(text).group(1)
            if endpoint in collect.INFERENCE_ENDPOINTS and stamp is not None:
                self._block_lines = []
                self._block_ts = stamp
                self._block_bytes = 0
            else:
                self._skip_body = True
            return

        if text.startswith("[") and collect.PREDICTION_RE.search(text):
            model = collect.PREDICTION_RE.search(text).group(1)
            queue = self._queues.get(model)
            if queue:
                queue.popleft()
            self._skip_body = True
            return

        error = collect.ERROR_RE.search(text)
        if error:
            queue = self._queues.get(error.group(1))
            if queue:
                queue.popleft()
            return

        progress = PROGRESS_RE.search(text)
        if progress:
            queue = self._queues.get(progress.group(1))
            if queue:
                queue[0].percent = float(progress.group(2))

    def _finish_request_block(self) -> None:
        """Close a request body: parse it and queue the request."""
        lines = self._block_lines or []
        ts = self._block_ts
        self._reset_parse_state()
        if ts is None:
            return
        body = "\n".join(["{"] + lines + ["}"])
        try:
            obj = json.loads(body)
        except ValueError:
            return
        if not isinstance(obj, dict) or not isinstance(obj.get("model"), str):
            return
        messages = obj.get("messages") if isinstance(obj.get("messages"), list) else []
        queue = self._queues.setdefault(obj["model"], deque())
        queue.append(_Flight(model=obj["model"], job=collect.job_label(messages), started_ts=ts))


def _phase(percent: float | None) -> str:
    """Name the stage of a request from its prompt progress."""
    if percent is None:
        return "waiting"
    if percent >= 100:
        return "answering"
    return "prompt"


def _stamp(text: str) -> int | None:
    """Unix seconds of a leading [YYYY-MM-DD HH:MM:SS] stamp, or None."""
    try:
        return collect._stamp_to_unix(text)
    except ValueError:
        return None


def _text(raw: bytes) -> str:
    """Decode one log line, replacing bad bytes instead of failing."""
    return raw.decode("utf-8", errors="replace").rstrip("\r")
