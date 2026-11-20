"""
Copies the Raspberry Pi's saved camera snapshots into instances\\test\\cache\\bma_snapshots, every 300 s.

The production server on the Pi saves the latest annotated frame of each BMA camera to its bma_snapshots
folder. The test server on this PC runs with BMA_FETCH=0 (it never fetches from BMA: the public IP is shared
with production, and double traffic gets it blocked), so the flood watch takes its frames from this copy.
Only the *.jpg files changed since the last successful sync cross the network (ssh + tar); each file is
written to a temp file and renamed into place, and its mtime is set to the Pi's, because the flood watch
reads the mtime as the frame time.

    PI_SYNC_HOST     ssh target            test@192.168.1.109
    PI_SYNC_KEY      ssh private key       C:\\Users\\user\\.ssh\\bkkpi_ed25519
    PI_SYNC_DIR      snapshot folder on the Pi   /mnt/ssd/new_ccty_bangkok/instances/production/cache/bma_snapshots
    PI_SYNC_SECONDS  seconds between syncs  300

Runs only while the test server is up: it exits by itself after 3 failed checks of 127.0.0.1:8001 in a row
(checked from 5 minutes after start). One copy at a time (a lock file). Log: launch\\logs\\pi_frames_sync.log.

    python launch\\test\\pi_frames_sync.py           run until the test server stops
    python launch\\test\\pi_frames_sync.py --once    one sync, then exit (testing)
"""
import argparse
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
from datetime import datetime

import msvcrt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGET = os.path.join(ROOT, "instances", "test", "cache", "bma_snapshots")
CACHE = os.path.join(ROOT, "instances", "test", "cache")
LOCK_FILE = os.path.join(CACHE, "pi_frames_sync.lock")
STATE_FILE = os.path.join(CACHE, "pi_frames_sync.state")
LOG_FILE = os.path.join(ROOT, "launch", "logs", "pi_frames_sync.log")

HOST = os.getenv("PI_SYNC_HOST", "test@192.168.1.109")
KEY = os.getenv("PI_SYNC_KEY", r"C:\Users\user\.ssh\bkkpi_ed25519")
REMOTE_DIR = os.getenv("PI_SYNC_DIR", "/mnt/ssd/new_ccty_bangkok/instances/production/cache/bma_snapshots")
SECONDS = int(os.getenv("PI_SYNC_SECONDS", "300"))

TEST_PORT = 8001
GRACE = 300              # no exit check during the first 5 minutes (the server is still starting)
CHECK_EVERY = 60         # seconds between checks of the test server
GONE_AFTER = 3           # checks in a row with nothing listening: exit
SSH_TIMEOUT = 120        # seconds for one sync; the ssh process is killed after this
FIRST_LOOKBACK_MIN = 15  # first run: files saved in the last 15 minutes
OVERLAP = 300            # seconds before the newest Pi mtime seen last time: covers PC/Pi clock skew and late saves
REPLACE_TRIES = 3        # os.replace attempts per file (the server may have the old file open)
REPLACE_WAIT = 0.2       # seconds between those attempts
LOG_KEEP = 2000          # log trimmed to its last LOG_KEEP lines when it grows past 2 x LOG_KEEP


def safe_name(name):
    """A plain <camid>.jpg name: no folder part, no '..', nothing but the file name."""
    base = name[:-4] if name.endswith(".jpg") else ""
    return bool(base) and ".." not in name and "/" not in name and "\\" not in name and base.strip() == base


def remote_command(remote_dir, since):
    """The command run on the Pi: the .jpg files changed since `since` (unix time; None = first run), as a tar stream."""
    when = f"-newermt '@{int(since)}'" if since is not None else f"-mmin -{FIRST_LOOKBACK_MIN}"
    return (f"cd {shlex.quote(remote_dir)} && find . -maxdepth 1 -name '*.jpg' {when} -print0 "
            f"| tar --null -cf - -T -")


def new_stats():
    return {"written": 0, "skipped": 0, "skipped_names": [], "members": 0, "newest": None}


def _replace(tmp, dest):
    """os.replace with a few retries: Windows refuses it while the server has the old file open.
    False when the file stayed locked."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(tmp, dest)
            return True
        except PermissionError:
            if attempt + 1 < REPLACE_TRIES:
                time.sleep(REPLACE_WAIT)
    return False


def extract(stream, target, stats=None):
    """Write every safe regular file of the tar stream into target (atomically, with the Pi's mtime).
    Fills and returns stats (see new_stats): written, skipped (locked, after the retries), newest = the
    newest mtime of any regular file in the stream (the Pi's clock, kept as the next sync's start).
    Raises tarfile.TarError on a truncated stream, after the complete files before the cut are written."""
    stats = new_stats() if stats is None else stats
    with tarfile.open(fileobj=stream, mode="r|") as tf:
        for member in tf:
            stats["members"] += 1
            if member.isfile():
                stats["newest"] = max(stats["newest"] or 0, member.mtime)
            name = member.name[2:] if member.name.startswith("./") else member.name
            if not member.isfile() or not safe_name(name):
                continue
            fd, tmp = tempfile.mkstemp(dir=target, prefix=".sync-", suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as out, tf.extractfile(member) as src:
                    shutil.copyfileobj(src, out)
                os.utime(tmp, (member.mtime, member.mtime))
                if _replace(tmp, os.path.join(target, name)):
                    stats["written"] += 1
                else:
                    stats["skipped"] += 1
                    stats["skipped_names"].append(name)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
    return stats


def _stop(proc):
    """Make sure the ssh process is gone and its pipes are closed, whatever happened before."""
    if proc.poll() is None:
        proc.kill()
    for pipe in (proc.stdout, proc.stderr):
        if pipe is not None:
            pipe.close()
    proc.wait()


def _read_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return None


def _write_state(ts):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(str(ts))


def _since():
    """Start of the next sync's window on the Pi's clock: the newest mtime seen last time, less OVERLAP.
    None on the first run (then the last FIRST_LOOKBACK_MIN minutes)."""
    state = _read_state()
    return None if state is None else state - OVERLAP


def _log(line):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{stamp} {line}\n")
    if os.path.getsize(LOG_FILE) > 200_000:   # trim now and then; one line per sync keeps it small
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        if len(lines) > 2 * LOG_KEEP:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-LOG_KEEP:])
    if sys.stdout is not None:   # pythonw has no console
        print(f"{stamp} {line}")


def sync_once():
    """One round: copy the changed snapshots. Never raises; a failure is logged and the next round retries.
    The state (the newest Pi mtime) only moves on a sync that ran to the end of its stream."""
    started = time.time()
    cmd = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST,
           remote_command(REMOTE_DIR, _since())]
    os.makedirs(TARGET, exist_ok=True)
    stats = new_stats()
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        timer = threading.Timer(SSH_TIMEOUT, proc.kill)
        timer.start()
        read_error = None
        try:
            extract(proc.stdout, TARGET, stats)
        except tarfile.TarError as e:   # truncated stream, or an empty one (GNU tar refuses an empty archive)
            read_error = e
        finally:
            timer.cancel()
        err = proc.stderr.read().decode("utf-8", "replace").strip()
        rc = proc.wait()
    except Exception as e:  # noqa: BLE001 - the Pi may be off or slow; try again next round
        _log(f"failed after {time.time() - started:.1f} s: {type(e).__name__}: {str(e)[:200]}"
             f" ({stats['written']} files written)")
        return False
    finally:
        if proc is not None:
            _stop(proc)
    empty = "empty archive" in err.lower()
    if read_error is not None and not (stats["members"] == 0 and empty):
        _log(f"partial sync after {time.time() - started:.1f} s: {stats['written']} files written, then "
             f"{type(read_error).__name__}: {str(read_error)[:120]}; state not moved, retried next round")
        return False
    if rc != 0 and not empty:
        _log(f"failed after {time.time() - started:.1f} s: ssh exit {rc}: {err[-160:]}")
        return False
    if stats["newest"] is not None:
        _write_state(stats["newest"])
    skipped = ""
    if stats["skipped"]:
        skipped = f", skipped {stats['skipped']} locked: {', '.join(stats['skipped_names'][:5])}"
    _log(f"copied {stats['written']} files in {time.time() - started:.1f} s{skipped}")
    return True


def server_up():
    try:
        socket.create_connection(("127.0.0.1", TEST_PORT), timeout=2).close()
        return True
    except OSError:
        return False


def take_lock():
    """An exclusive lock on LOCK_FILE for the life of the process; None when another copy holds it."""
    os.makedirs(CACHE, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        return None
    return fd


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copy the Pi's flood-watch snapshots into the test server's cache.")
    parser.add_argument("--once", action="store_true", help="one sync, then exit")
    args = parser.parse_args(argv)

    lock = take_lock()
    if lock is None:
        if args.once:
            print("another pi_frames_sync is running")
        return 0

    if args.once:
        sync_once()
        return 0

    start = time.time()
    next_sync = start
    next_check = start + GRACE
    misses = 0
    _log(f"started (pid {os.getpid()})")
    while True:
        now = time.time()
        if now >= next_sync:
            try:
                sync_once()
            except Exception:  # noqa: BLE001 - under pythonw an uncaught error ends the copy without a trace
                _log("sync crashed: " + traceback.format_exc()[-400:].replace("\n", " | "))
            next_sync = time.time() + SECONDS
        if now >= next_check:
            next_check = now + CHECK_EVERY
            misses = 0 if server_up() else misses + 1
            if misses >= GONE_AFTER:
                _log("test server not running: exiting")
                return 0
        time.sleep(5)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - pythonw has no console: leave the reason in the log
        _log("exited on error: " + traceback.format_exc()[-400:].replace("\n", " | "))
        raise
