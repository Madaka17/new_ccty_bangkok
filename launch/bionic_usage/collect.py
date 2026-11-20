"""Collect Bionic (LM Studio rebrand) request usage from its server logs into SQLite.

Bionic writes one log file per day under
C:\\Users\\user\\.lmstudio\\apps\\bionic\\server-logs\\YYYY-MM\\YYYY-MM-DD.N.log.
Each chat request shows up as a "Received request" block with its JSON body,
and its answer as a "Generated prediction" block with the token usage. This
script pairs the two per model (first in, first out), writes one row per
served call into local\\bionic_usage\\usage.db, and remembers how far it has
read each log file (byte offset and line count) so that the next run continues
where this one stopped.

Only tokens and call counts are stored. No prices.

Run with:  python collect.py          (prints one summary line)
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_ROOT = Path.home() / ".lmstudio" / "apps" / "bionic" / "server-logs"
DEFAULT_DB = REPO_ROOT / "local" / "bionic_usage" / "usage.db"

# Asia/Bangkok has no daylight saving time, so a fixed +07:00 offset is exact.
BANGKOK = timezone(timedelta(hours=7))

# Log files are read in pieces of this size, so a long backlog never sits in
# memory at once. A single line longer than this is still read: the buffer grows.
CHUNK_BYTES = 32 * 1024 * 1024

# Friendly job names, keyed by the start of the first system message.
KNOWN_JOBS = {
    "You are the flood-watch agent": "flood_cam",
}

# Only these POST endpoints produce a "Generated prediction". Load, unload and
# download calls also carry a JSON body with a "model" key, so they must not
# join the pending queue or they would steal the next answer.
INFERENCE_ENDPOINTS = {
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/responses",
    "/api/v1/chat",
}

# A request with no answer older than this (compared with the newest log
# time seen) is dropped from the pending queue.
PENDING_MAX_AGE_SECONDS = 3600

STAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")
RECEIVED_RE = re.compile(r"Received request: POST to (\S+) with body \{$")
PREDICTION_RE = re.compile(r"\[([^\]]+)\] Generated prediction: \{$")
RUNNING_RE = re.compile(r"\[([^\]]+)\] Running chat completion")
ERROR_RE = re.compile(r"^\[[^\]]+\]\[ERROR\]\[([^\]]+)\]")
TOTAL_RE = re.compile(r"total time =\s*([0-9]+(?:\.[0-9]+)?)\s*ms")

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    ts INTEGER,
    model TEXT,
    job TEXT,
    endpoint TEXT,
    prompt_tokens INT,
    completion_tokens INT,
    reasoning_tokens INT,
    total_ms REAL,
    ok INT,
    log_file TEXT,
    line_no INT,
    UNIQUE(log_file, line_no)
);
CREATE INDEX IF NOT EXISTS requests_ts ON requests(ts);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    offset INT,
    lines INT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT,
    endpoint TEXT,
    job TEXT,
    ts INTEGER,
    total_ms REAL
);
"""


@dataclass
class RunResult:
    """Counts reported by one collector run."""

    files_scanned: int = 0
    new_rows: int = 0


@dataclass
class Pending:
    """A request that has been received but not yet answered."""

    model: str
    endpoint: str
    job: str
    ts: int
    total_ms: float | None = None


@dataclass
class ParseState:
    """Parser memory that is carried from one file to the next within a run."""

    pending: dict[str, deque]
    current_model: str | None
    newest_ts: int | None
    log_path: Path


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open the usage database in WAL mode, creating folder and tables if needed.

    A first start that races another process can meet "database is locked";
    the schema setup is retried with a growing pause instead of failing.
    The connection is in autocommit mode; callers start transactions explicitly.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    con.execute("PRAGMA busy_timeout=30000")
    delay = 0.5
    for attempt in range(1, 9):
        try:
            _init_schema(con)
            return con
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 8:
                con.close()
                raise
            time.sleep(delay)
            delay = min(delay * 2, 5.0)
    raise AssertionError("unreachable")  # the loop above always returns or raises


def summary_line(result: RunResult) -> str:
    """Return the one-line summary printed after each run."""
    return f"collect: {result.files_scanned} files scanned, {result.new_rows} new rows"


LOG_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.(\d+)\.log$")


def log_file_key(path: Path) -> tuple:
    """Sort key for a log file: its date, then its rotation number as a number.

    Plain string order puts "2026-11-20.10.log" before "2026-11-20.9.log", so the
    number is compared as an integer. Names that do not match sort by name.
    """
    match = LOG_NAME_RE.match(Path(path).name)
    if match:
        return (match.group(1), int(match.group(2)))
    return (Path(path).name, 0)


def list_log_files(log_root: Path) -> list[Path]:
    """Every log file under log_root/YYYY-MM/, oldest first. [] when the folder is missing."""
    root = Path(log_root)
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*.log"), key=log_file_key)


def job_label(messages: list) -> str:
    """Return a short job name taken from the first system message."""
    system = next((m for m in messages
                   if isinstance(m, dict) and m.get("role") == "system"), None)
    if system is None:
        return "(no system prompt)"
    content = _content_text(system.get("content"))
    head = content.split(" ... <Truncated", 1)[0]
    for prefix, name in KNOWN_JOBS.items():
        if head.startswith(prefix):
            return name
    return head[:60] or "(empty system prompt)"


def run(log_root: Path, db_path: Path) -> RunResult:
    """Read every new complete record in the log folder and store it.

    All work for one run happens in a single transaction, so a crash leaves
    the database exactly as it was before the run started.
    """
    db_path = Path(db_path)
    con = open_db(db_path)
    result = RunResult()
    try:
        con.execute("BEGIN IMMEDIATE")
        state = ParseState(pending=_load_pending(con), current_model=None,
                           newest_ts=None, log_path=db_path.parent / "collect.log")
        stored = {path: (offset, lines) for path, offset, lines in
                  con.execute("SELECT path, offset, lines FROM files").fetchall()}

        for path in list_log_files(log_root):
            result.files_scanned += 1
            key = str(path)
            offset, lines = stored.get(key, (0, 0))
            size = path.stat().st_size
            if size < offset:
                _log(state, f"WARNING: {key} is smaller ({size} bytes) than its stored offset "
                            f"({offset}); it is read again from the start. Rows whose "
                            "(file, line) already exist are skipped.")
                offset, lines = 0, 0
            if size == offset:
                continue
            offset, lines = _read_file(path, offset, lines, key, state, con, result)
            con.execute("INSERT INTO files(path, offset, lines) VALUES(?, ?, ?) "
                        "ON CONFLICT(path) DO UPDATE SET offset = excluded.offset, "
                        "lines = excluded.lines",
                        (key, offset, lines))

        if state.newest_ts is not None:
            cutoff = state.newest_ts - PENDING_MAX_AGE_SECONDS
            for model, queue in state.pending.items():
                state.pending[model] = deque(p for p in queue if p.ts >= cutoff)
        _save_pending(con, state.pending)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the collector on the default log folder and database."""
    try:
        result = run(DEFAULT_LOG_ROOT, DEFAULT_DB)
    except Exception:
        _say("collect: failed, see collect.log next to usage.db")
        _append_log(DEFAULT_DB.parent / "collect.log", traceback.format_exc())
        return 1
    _say(summary_line(result))
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _init_schema(con: sqlite3.Connection) -> None:
    """Set WAL mode, create the tables and add any column missing from an older DB."""
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    _migrate_files_table(con)


def _migrate_files_table(con: sqlite3.Connection) -> None:
    """Add the `lines` column to an older files table and fill it with one count per file."""
    columns = {row[1] for row in con.execute("PRAGMA table_info(files)").fetchall()}
    if "lines" in columns:
        return
    con.execute("ALTER TABLE files ADD COLUMN lines INT NOT NULL DEFAULT 0")
    for path, offset in con.execute("SELECT path, offset FROM files").fetchall():
        log_file = Path(path)
        if log_file.exists() and (offset or 0) <= log_file.stat().st_size:
            lines = _count_newlines_before(log_file, offset or 0)
        else:
            # The file is gone or changed size: start it over; unique keys guard duplicates.
            offset, lines = 0, 0
        con.execute("UPDATE files SET offset = ?, lines = ? WHERE path = ?", (offset, lines, path))


def _read_file(path: Path, offset: int, lines: int, key: str, state: ParseState,
               con: sqlite3.Connection, result: RunResult) -> tuple[int, int]:
    """Read one log file from `offset` in bounded chunks and return the new (offset, lines).

    Bytes that do not yet form a complete record are carried into the next
    chunk. The returned position only moves past complete records.
    """
    carry = b""
    with path.open("rb") as f:
        f.seek(offset)
        while True:
            chunk = f.read(CHUNK_BYTES)
            if not chunk:
                break
            buf = carry + chunk
            used_bytes, used_lines = _parse_buffer(buf, lines, key, state, con, result)
            offset += used_bytes
            lines += used_lines
            carry = buf[used_bytes:]
    return offset, lines


def _parse_buffer(buf: bytes, base_line: int, key: str, state: ParseState,
                  con: sqlite3.Connection, result: RunResult) -> tuple[int, int]:
    """Parse the complete records at the start of `buf`.

    `base_line` is the number of lines already consumed from the file. Returns
    (bytes used, lines used). Anything after the last consumed record is left for
    the caller to carry into the next chunk.
    """
    if b"\n" not in buf:
        return 0, 0  # not even one complete line yet
    raw_lines = buf.split(b"\n")
    raw_lines.pop()  # the text after the last newline is incomplete, never parsed
    pos = 0
    i = 0
    while i < len(raw_lines):
        line_no = base_line + i + 1
        text = _text(raw_lines[i])
        stamp = _stamp_to_unix(text)
        if stamp is not None:
            state.newest_ts = stamp if state.newest_ts is None else max(state.newest_ts, stamp)

        if text.startswith("[") and RECEIVED_RE.search(text):
            close, kind = _find_close(raw_lines, i + 1)
            if close is None:
                break  # the block is still being written; wait for more bytes
            if kind == "header":
                _log(state, f"request block at {key} line {line_no} has no closing brace "
                            "before the next record; block skipped")
                pos += len(raw_lines[i]) + 1
                i += 1
                continue
            block = raw_lines[i:close + 1]
            _handle_request(text, block, stamp, state, key, con, result)
            pos += _span(block)
            i = close + 1
            continue

        if PREDICTION_RE.search(text):
            close, kind = _find_close(raw_lines, i + 1)
            if close is None:
                break  # the answer is still being written; wait for more bytes
            if kind == "header":
                _log(state, f"prediction block at {key} line {line_no} has no closing brace "
                            "before the next record; block skipped")
                pos += len(raw_lines[i]) + 1
                i += 1
                continue
            block = raw_lines[i:close + 1]
            _handle_prediction(text, block, line_no, state, key, con, result)
            pos += _span(block)
            i = close + 1
            continue

        _handle_line(text, state, key, con, result, line_no)
        pos += len(raw_lines[i]) + 1
        i += 1
    return pos, i


def _handle_line(text: str, state: ParseState, key: str, con: sqlite3.Connection,
                 result: RunResult, line_no: int) -> None:
    """Handle a single-line record: the running marker, token timing or an error."""
    running = RUNNING_RE.search(text)
    if running:
        state.current_model = running.group(1)
        return

    total = TOTAL_RE.search(text)
    if total and state.current_model:
        queue = state.pending.get(state.current_model)
        if queue:
            # Timing lines carry no model tag. The one for the running model
            # belongs to the request now at the head of its queue.
            queue[0].total_ms = float(total.group(1))
        return

    error = ERROR_RE.search(text)
    if error:
        model = error.group(1)
        queue = state.pending.get(model)
        if not queue:
            _log(state, f"error line without a pending request for {model} at line {line_no}")
            return
        req = queue.popleft()
        _insert_row(con, result, req, key, line_no, ok=0, prompt=0, completion=0,
                    reasoning=0, total_ms=req.total_ms)


def _handle_request(header: str, block: list[bytes], stamp: int | None,
                    state: ParseState, key: str, con: sqlite3.Connection,
                    result: RunResult) -> None:
    """Queue a chat request until its answer shows up."""
    endpoint = RECEIVED_RE.search(header).group(1)
    if endpoint not in INFERENCE_ENDPOINTS:
        return
    if stamp is None:
        _log(state, f"request without a time stamp in {key}, skipped")
        return
    body = _body_from_block(header, block, "with body ")
    try:
        obj = json.loads(body)
    except ValueError:
        _log(state, f"request body in {key} does not parse, skipped")
        return
    if not isinstance(obj, dict) or not isinstance(obj.get("model"), str):
        _log(state, f"request body in {key} has no model, skipped")
        return
    messages = obj.get("messages") if isinstance(obj.get("messages"), list) else []
    queue = state.pending.setdefault(obj["model"], deque())
    queue.append(Pending(model=obj["model"], endpoint=endpoint,
                         job=job_label(messages), ts=stamp))


def _handle_prediction(header: str, block: list[bytes], line_no: int,
                       state: ParseState, key: str, con: sqlite3.Connection,
                       result: RunResult) -> None:
    """Pair an answer with the oldest queued request for the same model."""
    model = PREDICTION_RE.search(header).group(1)
    queue = state.pending.get(model)
    body = _body_from_block(header, block, "Generated prediction: ")
    try:
        obj = json.loads(body)
    except ValueError:
        _log(state, f"prediction in {key} line {line_no} does not parse, request dropped")
        if queue:
            queue.popleft()
        return
    if not queue:
        _log(state, f"prediction for {model} without a pending request, line {line_no}")
        return
    req = queue.popleft()
    usage = obj.get("usage") if isinstance(obj, dict) and isinstance(obj.get("usage"), dict) else {}
    details = usage.get("completion_tokens_details")
    reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
    _insert_row(con, result, req, key, line_no, ok=1,
                prompt=_int(usage.get("prompt_tokens")),
                completion=_int(usage.get("completion_tokens")),
                reasoning=_int(reasoning), total_ms=req.total_ms)


def _insert_row(con: sqlite3.Connection, result: RunResult, req: Pending, key: str,
                line_no: int, *, ok: int, prompt: int, completion: int, reasoning: int,
                total_ms: float | None) -> None:
    """Insert one call row. A repeated (file, line) pair is ignored."""
    cur = con.execute(
        "INSERT OR IGNORE INTO requests(ts, model, job, endpoint, prompt_tokens, "
        "completion_tokens, reasoning_tokens, total_ms, ok, log_file, line_no) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (req.ts, req.model, req.job, req.endpoint, prompt, completion, reasoning,
         total_ms, ok, key, line_no))
    result.new_rows += cur.rowcount


def _load_pending(con: sqlite3.Connection) -> dict[str, deque]:
    """Read the unanswered requests left by the previous run, in order."""
    pending: dict[str, deque] = {}
    for model, endpoint, job, ts, total_ms in con.execute(
            "SELECT model, endpoint, job, ts, total_ms FROM pending ORDER BY seq").fetchall():
        pending.setdefault(model, deque()).append(
            Pending(model=model, endpoint=endpoint, job=job, ts=ts, total_ms=total_ms))
    return pending


def _save_pending(con: sqlite3.Connection, pending: dict[str, deque]) -> None:
    """Replace the stored queue with the in-memory one."""
    con.execute("DELETE FROM pending")
    for queue in pending.values():
        for p in queue:
            con.execute("INSERT INTO pending(model, endpoint, job, ts, total_ms) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (p.model, p.endpoint, p.job, p.ts, p.total_ms))


def _find_close(raw_lines: list[bytes], start: int) -> tuple[int | None, str | None]:
    """Find where a JSON block ends.

    Returns (index, "close") for the lone closing brace, or (index, "header")
    when a new timestamped record starts first (the block is corrupt). Returns
    (None, None) when neither has been written yet.
    """
    for j in range(start, len(raw_lines)):
        line = raw_lines[j]
        if line.rstrip(b"\r") == b"}":
            return j, "close"
        if STAMP_RE.match(_text(line)):
            return j, "header"
    return None, None


def _body_from_block(header: str, block: list[bytes], marker: str) -> str:
    """Join the JSON text that follows the header marker into one string."""
    first = header[header.index(marker) + len(marker):]
    return "\n".join([first] + [_text(x) for x in block[1:]])


def _span(block: list[bytes]) -> int:
    """Return the number of bytes a block occupies, including newlines."""
    return sum(len(line) + 1 for line in block)


def _text(raw: bytes) -> str:
    """Decode one log line as UTF-8, replacing bad bytes instead of failing."""
    return raw.decode("utf-8", errors="replace").rstrip("\r")


def _stamp_to_unix(text: str) -> int | None:
    """Turn a leading [YYYY-MM-DD HH:MM:SS] stamp into Unix seconds."""
    match = STAMP_RE.match(text)
    if not match:
        return None
    moment = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=BANGKOK)
    return int(moment.timestamp())


def _content_text(content: object) -> str:
    """Return a message's text whether it is a plain string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and isinstance(part.get("text"), str))
    return ""


def _int(value: object) -> int:
    """Return an integer token count, or 0 when the value is missing or odd."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _count_newlines_before(path: Path, end: int) -> int:
    """Count the newline bytes in the first `end` bytes of a file (used once, by the migration)."""
    count = 0
    remaining = end
    with path.open("rb") as f:
        while remaining > 0:
            chunk = f.read(min(1 << 20, remaining))
            if not chunk:
                break
            count += chunk.count(b"\n")
            remaining -= len(chunk)
    return count


def _log(state: ParseState, message: str) -> None:
    """Record a skipped record or warning in collect.log next to the database."""
    stamp = datetime.now(BANGKOK).strftime("%Y-%m-%d %H:%M:%S")
    _append_log(state.log_path, f"[{stamp}] {message}")


def _append_log(path: Path, message: str) -> None:
    """Append a line to a log file. Never raises, because pythonw has no console."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except OSError:
        pass


def _say(message: str) -> None:
    """Print to the console when there is one (pythonw has no stdout)."""
    if sys.stdout is not None:
        print(message)


if __name__ == "__main__":
    sys.exit(main())
