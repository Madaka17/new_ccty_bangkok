r"""
Runs one BKK server (or the camera status watcher) with no console window and keeps its output in a log file.

    .venv\Scripts\pythonw.exe launch\run_hidden.py production|test|enviro|camera

The start.bat files call this when started without --window (Desktop icons, Startup folder, restart.bat,
the watchdog). It starts launch\<name>\start.bat --child (camera: launch\camera_status.bat --watch 300) in a
hidden console, writes every line it prints to launch\logs\<name>.log with the time in front (10 MB x 5
files), and keeps launch\logs\<name>.json with the PIDs so BKK Monitor can show whether it runs.
Stopping works as before: launch\kill_server.ps1 finds the hidden cmd.exe by its command line and kills
it with the server; this runner then sees the output end and exits.

The runner must keep draining the child's stdout until it closes. If it stops, the child blocks on a full
pipe and the live server freezes. So nothing in the log or state files may stop that loop: a locked file
(Windows raises PermissionError while another program has it open) only costs log lines or a state update.
"""
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "launch" / "logs"
MAX_BYTES = 10 * 2**20
BACKUPS = 5
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TARGETS = {name: ["cmd.exe", "/c", str(ROOT / "launch" / name / "start.bat"), "--child"]
           for name in ("production", "test", "enviro")}
TARGETS["camera"] = ["cmd.exe", "/c", str(ROOT / "launch" / "camera_status.bat"), "--watch", "300"]


class RotatingLog:
    """Appends timestamped lines. write() never raises: a failed rotation keeps appending to the current
    file and retries on the next write; a line that cannot be written is dropped."""

    def __init__(self, path, max_bytes, backups):
        self.path, self.max_bytes, self.backups = Path(path), max_bytes, backups
        self.f = None
        self._open()

    def _open(self):
        self.f = open(self.path, "ab")

    def write(self, text):
        try:
            data = f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n".encode("utf-8")
            if self.f is None:
                self._open()
            if self.f.tell() + len(data) > self.max_bytes and self.f.tell() > 0:
                self._rotate()
            self.f.write(data)
            self.f.flush()
        except Exception:
            # Broad on purpose: any failure here must not stop the caller from draining the child's pipe.
            pass

    def _rotate(self):
        self._close_quiet()
        try:
            for i in range(self.backups - 1, 0, -1):
                src = self.path.with_name(f"{self.path.name}.{i}")
                if src.exists():
                    os.replace(src, self.path.with_name(f"{self.path.name}.{i + 1}"))
            os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
        except OSError:
            pass  # locked by another program: keep the current file and retry on the next write
        self._open()

    def _close_quiet(self):
        try:
            if self.f is not None:
                self.f.close()
        except OSError:
            pass
        self.f = None

    def close(self):
        self._close_quiet()


def _save(path, state):
    tmp = path.with_suffix(".json.tmp")
    for _ in range(5):
        try:
            tmp.write_text(json.dumps(state), encoding="utf-8")
            os.replace(tmp, path)
            return
        except OSError:
            time.sleep(0.05)  # file locked by another program; retry, then give up quietly


def run(name, cmd, log_dir=LOG_DIR, max_bytes=MAX_BYTES, backups=BACKUPS):
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log = RotatingLog(log_dir / f"{name}.log", max_bytes, backups)
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
    state_path = log_dir / f"{name}.json"
    state = {"name": name, "runner_pid": os.getpid(), "child_pid": proc.pid, "started_at": time.time(),
             "command": subprocess.list2cmdline(cmd)}
    try:
        _save(state_path, state)
        log.write(f"--- {name} started (pid {proc.pid}) ---")
        for raw in proc.stdout:
            log.write(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
    finally:
        code = proc.wait()
        log.write(f"--- {name} exited with code {code} ---")
        log.close()
        _save(state_path, {**state, "exited_at": time.time(), "exit_code": code})
    return code


def _crash(text):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "run_hidden.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass  # under pythonw there is no stderr either; nothing more can be done


def main(argv):
    # pythonw has no stderr, so a crash here would vanish. Put the traceback in run_hidden.log instead.
    try:
        if not argv or argv[0] not in TARGETS:
            _crash(f"usage: run_hidden.py {'|'.join(TARGETS)} (got {argv})")
            return 2
        return run(argv[0], TARGETS[argv[0]], log_dir=LOG_DIR)
    except Exception:
        _crash("runner crashed:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
