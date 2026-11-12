"""Read-only live feed of security events, printed as JSON lines on stdout (one flushed line per event).

Run on the Pi by the PC's live viewer over ssh (INSTANCE_DIR set by the caller):

    python -u -m backend.core.security_stream

Lines: hello (once), web (new rows of the security_log `recent` table, polled every 2 s),
ssh (sshd journal, followed with journalctl), ping (every 15 s). Starts from "now", replays nothing.
Never writes anything: the DB is opened read-only. Exits when stdout closes and kills journalctl.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from urllib.parse import quote

from backend.core.instance import DATA_DIR

POLL_SECONDS = 2.0
PING_SECONDS = 15.0
JOURNAL_CMD = ["journalctl", "-u", "ssh", "-u", "sshd", "-f", "-n", "0", "-o", "short-iso"]


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def format_line(obj: dict) -> str:
    """One output line, newline included. Thai text stays readable (utf-8)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def web_event(row: dict) -> dict:
    return {"type": "web", "ts": iso(row["ts"]), "kind": row["kind"], "ip": row["ip"],
            "path": row["path"], "method": row["method"]}


def _ro_uri(db_path: str) -> str:
    p = os.path.abspath(db_path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p  # windows drive path -> file:///C:/...
    return "file:" + quote(p, safe="/:") + "?mode=ro"


def new_rows(db_path: str, last_ts: float):
    """(rows newer than last_ts oldest first, new last_ts). DB missing or unreadable -> ([], last_ts)."""
    if not os.path.exists(db_path):
        return [], last_ts
    try:
        con = sqlite3.connect(_ro_uri(db_path), uri=True, timeout=5)
        try:
            cur = con.execute("SELECT ts, kind, ip, path, method FROM recent WHERE ts > ? "
                              "ORDER BY ts, rowid", (last_ts,))
            rows = [dict(zip(("ts", "kind", "ip", "path", "method"), r)) for r in cur]
        finally:
            con.close()
    except Exception:
        return [], last_ts
    return rows, (rows[-1]["ts"] if rows else last_ts)


class Emitter:
    """Thread-safe line writer. On a closed stdout it sets `stop` instead of raising."""

    def __init__(self, out, stop: threading.Event):
        self.out = out
        self.stop = stop
        self._lock = threading.Lock()

    def emit(self, obj: dict) -> bool:
        if self.stop.is_set():
            return False
        try:
            with self._lock:
                self.out.write(format_line(obj))
                self.out.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            self.stop.set()
            return False


def _web_loop(em: Emitter, db_path: str, start_ts: float):
    last = start_ts
    while not em.stop.wait(POLL_SECONDS):
        rows, last = new_rows(db_path, last)
        for r in rows:
            if not em.emit(web_event(r)):
                return


def _ping_loop(em: Emitter):
    while not em.stop.wait(PING_SECONDS):
        if not em.emit({"type": "ping", "ts": iso(time.time())}):
            return


PRECHECK_CMD = ["journalctl", "-u", "ssh", "-u", "sshd", "-n", "1", "--no-pager", "-o", "short-iso"]


def _precheck(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL)
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def pick_journal_cmd(runner=_precheck):
    """Follow command whose pre-check printed output: plain journalctl first, then sudo -n. None if neither."""
    for prefix in ([], ["sudo", "-n"]):
        if runner(prefix + PRECHECK_CMD):
            return prefix + JOURNAL_CMD
    return None


def _stop_proc(p):
    try:
        if os.name == "posix":
            import signal
            os.killpg(p.pid, signal.SIGTERM)   # whole group: a sudo child must not keep journalctl alive
        else:
            p.kill()
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _ssh_loop(em: Emitter, procs: list):
    from launch.security_check.collect import parse_ssh_line
    if shutil.which("journalctl") is None:
        return  # not a systemd host (e.g. the Windows test run): no ssh events
    while not em.stop.is_set():
        cmd = pick_journal_cmd()
        if cmd is None:
            if em.stop.wait(30):
                return
            continue
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                 start_new_session=(os.name == "posix"))
        except OSError:
            return
        procs[:] = [q for q in procs if q.poll() is None] + [p]
        for line in p.stdout:
            ev = parse_ssh_line(line)
            if ev and not em.emit({"type": "ssh", **ev}):
                break
        _stop_proc(p)
        p.wait()
        if em.stop.is_set():
            return
        em.stop.wait(5)


def run(out=None, db_path=None, ssh_events=True):
    out = out or sys.stdout
    stop = threading.Event()
    em = Emitter(out, stop)
    db_path = db_path or os.path.join(DATA_DIR, "security_events.db")
    start = time.time()
    em.emit({"type": "hello", "ts": iso(start)})
    procs: list = []
    threads = [threading.Thread(target=_web_loop, args=(em, db_path, start), daemon=True),
               threading.Thread(target=_ping_loop, args=(em,), daemon=True)]
    if ssh_events:
        threads.append(threading.Thread(target=_ssh_loop, args=(em, procs), daemon=True))
    for t in threads:
        t.start()
    try:
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        stop.set()
    for p in list(procs):
        _stop_proc(p)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(run())
