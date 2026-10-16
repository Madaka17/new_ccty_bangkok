# Hidden Servers + Processes Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run production, test, ENVIRO and camera status without console windows (output to rotating log files), show each one's running state and live log in the BKK Monitor app, keep a `--window` escape hatch, let the watchdog restart camera status, and silence the harmless `ConnectionResetError [WinError 10054]` asyncio noise.

**Architecture:** A small runner, `launch\run_hidden.py <name>`, runs under `pythonw` (no window). It starts the target's `.bat` with `--child` in a hidden console and pumps its stdout/stderr, line by line with a timestamp, into `launch\logs\<name>.log` (10 MB × 5 rotation). It also records the PIDs in `launch\logs\<name>.json`. Each `start.bat` gets three modes:
- **no flag:** spawn the runner and exit.
- **`--child`:** run the body with no `pause` (the runner uses this).
- **`--window`:** the old visible console.

`restart.bat`, `stop.bat`, `kill_server.ps1`, the watchdog and the Desktop/Startup shortcuts stay as they are. `kill_server.ps1` already finds the server by the `cmd.exe` command line `launch\<folder>\start.bat`, which the hidden child still has. In BKK Monitor, a new module `monitor_processes.py` (process state + log tail) backs new `Api` methods and a new "Processes" page. The collector adds a `service:camera` check.

**Tech Stack:** Python 3.14 (.venv, stdlib only: subprocess, ctypes, json), Windows batch, PowerShell 5.1, pywebview page (vanilla JS), pytest.

**Spec (agreed with the user 2026-10-15):**
- Move production :8000, test :8001, ENVIRO :5050 and camera status into hidden background processes. No cmd windows.
- The runner owns the processes, not the app window: closing BKK Monitor never stops a server. The existing watchdog keeps restarting production and ENVIRO.
- Keep an escape hatch: `start.bat --window` gives the old visible console.
- Logs per process: 10 MB × 5 files, rotating.
- The watchdog also restarts camera status when it has died while production runs.
- Silence only the `ConnectionResetError` 10054 `_call_connection_lost` asyncio noise; other errors still show.
- App "Processes" page: a card per process with running state, PID and uptime; a live log with ERROR/WARNING colours, an "Errors only" filter and an "Open log" button.
- The collector adds a camera-status check: `instances\production\camera_status.json` younger than 15 min, so it toasts like the others.
- Switch-over (controller, Task 6): test hidden on :8001 first, then restart production + ENVIRO + camera status hidden (user authorized Claude to do it), then check the public site.

## Global Constraints

- Repo `E:\new_ccty_bangkok`, branch `feat/hidden-servers`. Python: `.venv\Scripts\python.exe` only; tests `.venv/Scripts/python.exe -m pytest tests/<file> -v`.
- Production :8000 and ENVIRO :5050 are LIVE and public. Tasks 1-5 must not start, stop or restart them, and must not run any `launch\production\*.bat` or `launch\enviro\*.bat`. Only Task 6 (controller) switches them.
- Test :8001 may be started/stopped only in the task that says so.
- Batch files keep CRLF line endings, `@echo off` + `chcp 65001 >nul` header style, and `rem` comments explaining why.
- New logs live in `launch\logs\` (git-ignored). Names: `production`, `test`, `enviro`, `camera`.
- States in the monitor are exactly `ok`, `warn`, `fail`, `idle`, `stopped`. New status key: `service:camera`, target `camera`, label `Camera status`.
- Never call `os.kill(pid, 0)` on Windows: it terminates the process. Check liveness with ctypes `OpenProcess` + `GetExitCodeProcess` (`STILL_ACTIVE = 259`).
- Commits: conventional (`feat(launch): ...`, `feat(monitor): ...`). Stage only your task's files and never `launch/camera_status.py`, which has an unrelated uncommitted change. Use the Co-Authored-By trailer your harness reminder gives.
- UI text in English.

## Review Focus

- `kill_server.ps1` must still find and kill a hidden server: its regex `launch\\<folder>\\(re)?start(_local)?\.bat` must match the hidden child's command line `cmd.exe /c E:\...\launch\<folder>\start.bat --child`. Test in Task 2.
- A hidden child must never hang at `pause` or a prompt: stdin is DEVNULL and `--child` skips every `pause`. Test in Task 1 (stdin) and Task 2 (bat).
- Log rotation while the app tails the file: the tail must restart from 0 when the file shrinks and must not crash on a missing file. Test in Task 4.
- PID reuse or a stale `<name>.json` after a crash must not show "running" forever: the runner writes `exited_at`, and liveness checks both PIDs. Test in Task 4.
- The asyncio filter must drop only ConnectionResetError from `_call_connection_lost`, never other asyncio errors. Test in Task 3.

---

### Task 1: `launch\run_hidden.py` — the hidden runner

**Files:**
- Create: `launch/run_hidden.py`
- Modify: `.gitignore` (add `launch/logs/`)
- Test: `tests/test_run_hidden.py`

**Interfaces:**
- Produces:
  - `run_hidden.ROOT`, `run_hidden.LOG_DIR` (`ROOT/"launch"/"logs"`), `run_hidden.MAX_BYTES = 10 * 2**20`, `run_hidden.BACKUPS = 5`.
  - `run_hidden.TARGETS: dict[str, list[str]]`:
    - `production`: `["cmd.exe", "/c", str(ROOT/"launch"/"production"/"start.bat"), "--child"]`
    - `test`: same pattern with `test`.
    - `enviro`: same pattern with `enviro`.
    - `camera`: `["cmd.exe", "/c", str(ROOT/"launch"/"camera_status.bat"), "--watch", "300"]`.
  - `run_hidden.run(name, cmd, log_dir=LOG_DIR, max_bytes=MAX_BYTES, backups=BACKUPS) -> int`. It starts `cmd` with:
    - `cwd=ROOT`
    - `stdin=DEVNULL`
    - stdout pipe, with stderr merged into it
    - `creationflags=CREATE_NO_WINDOW`
    - env plus `PYTHONUNBUFFERED=1` and `PYTHONIOENCODING=utf-8`

    It writes `<log_dir>/<name>.json` = `{"name", "runner_pid", "child_pid", "started_at", "command"}` right after start. It writes every output line as `YYYY-MM-DD HH:MM:SS <line>` (UTF-8, `errors="replace"`), rotating `<name>.log` -> `.log.1` ... `.log.<backups>` when the next write would pass `max_bytes`. It adds a line `--- <name> started (pid N) ---` first and `--- <name> exited with code C ---` last. When the child exits it updates the json with `exited_at` and `exit_code`, and returns the exit code.
  - `run_hidden.main(argv) -> int`: `argv[0]` must be a key of TARGETS (else print usage to the log dir file `run_hidden.log` and return 2), then calls `run`.

- [ ] **Step 1: Write the failing tests**

```python
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "launch"))
import run_hidden  # noqa: E402

PY = sys.executable


def test_run_writes_log_and_state(tmp_path):
    cmd = [PY, "-c", "import sys; print('hello'); print('ERROR boom', file=sys.stderr); sys.exit(3)"]
    code = run_hidden.run("demo", cmd, log_dir=tmp_path)
    assert code == 3
    text = (tmp_path / "demo.log").read_text(encoding="utf-8")
    assert "--- demo started (pid" in text
    assert " hello" in text and " ERROR boom" in text
    assert text.rstrip().endswith("--- demo exited with code 3 ---")
    st = json.loads((tmp_path / "demo.json").read_text(encoding="utf-8"))
    assert st["name"] == "demo" and st["exit_code"] == 3 and st["exited_at"] >= st["started_at"]
    assert isinstance(st["child_pid"], int) and isinstance(st["runner_pid"], int)


def test_stdin_is_closed_so_pause_cannot_hang(tmp_path):
    cmd = [PY, "-c", "import sys; data = sys.stdin.read(); print('read', len(data))"]
    assert run_hidden.run("stdin", cmd, log_dir=tmp_path) == 0
    assert " read 0" in (tmp_path / "stdin.log").read_text(encoding="utf-8")


def test_rotation(tmp_path):
    cmd = [PY, "-c", "for i in range(400): print('x' * 50, i)"]
    run_hidden.run("rot", cmd, log_dir=tmp_path, max_bytes=4000, backups=2)
    assert (tmp_path / "rot.log").stat().st_size <= 4000
    assert (tmp_path / "rot.log.1").exists() and (tmp_path / "rot.log.2").exists()
    assert not (tmp_path / "rot.log.3").exists()


def test_utf8_thai(tmp_path):
    cmd = [PY, "-c", "print('กล้อง ok')"]
    run_hidden.run("thai", cmd, log_dir=tmp_path)
    assert "กล้อง ok" in (tmp_path / "thai.log").read_text(encoding="utf-8")


def test_targets_and_unknown_name(tmp_path, monkeypatch):
    assert run_hidden.TARGETS["production"][-2].endswith(str(Path("launch") / "production" / "start.bat"))
    assert run_hidden.TARGETS["production"][-1] == "--child"
    assert run_hidden.TARGETS["camera"][-2:] == ["--watch", "300"]
    monkeypatch.setattr(run_hidden, "LOG_DIR", tmp_path)
    assert run_hidden.main(["nope"]) == 2
    assert run_hidden.main([]) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_hidden.py -v`. Expected: `ModuleNotFoundError: No module named 'run_hidden'`.

- [ ] **Step 3: Implement `launch/run_hidden.py`**

```python
r"""
Runs one BKK server (or the camera status watcher) with no console window and keeps its output in a log file.

    .venv\Scripts\pythonw.exe launch\run_hidden.py production|test|enviro|camera

The start.bat files call this when started without --window (Desktop icons, Startup folder, restart.bat,
the watchdog). It starts launch\<name>\start.bat --child (camera: launch\camera_status.bat --watch 300) in a
hidden console, writes every line it prints to launch\logs\<name>.log with the time in front (10 MB x 5
files), and keeps launch\logs\<name>.json with the PIDs so BKK Monitor can show whether it runs.
Stopping works as before: launch\kill_server.ps1 finds the hidden cmd.exe by its command line and kills
it with the server; this runner then sees the output end and exits.
"""
import json
import os
import subprocess
import sys
import time
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
    def __init__(self, path, max_bytes, backups):
        self.path, self.max_bytes, self.backups = Path(path), max_bytes, backups
        self.f = open(self.path, "ab")

    def write(self, text):
        data = f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n".encode("utf-8")
        if self.f.tell() + len(data) > self.max_bytes and self.f.tell() > 0:
            self._rotate()
        self.f.write(data)
        self.f.flush()

    def _rotate(self):
        self.f.close()
        for i in range(self.backups - 1, 0, -1):
            src = self.path.with_name(f"{self.path.name}.{i}")
            if src.exists():
                os.replace(src, self.path.with_name(f"{self.path.name}.{i + 1}"))
        os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
        self.f = open(self.path, "ab")

    def close(self):
        self.f.close()


def _save(path, state):
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)


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
    _save(state_path, state)
    log.write(f"--- {name} started (pid {proc.pid}) ---")
    try:
        for raw in proc.stdout:
            log.write(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
    finally:
        code = proc.wait()
        log.write(f"--- {name} exited with code {code} ---")
        log.close()
        _save(state_path, {**state, "exited_at": time.time(), "exit_code": code})
    return code


def main(argv):
    if not argv or argv[0] not in TARGETS:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "run_hidden.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} usage: run_hidden.py {'|'.join(TARGETS)} (got {argv})\n")
        return 2
    return run(argv[0], TARGETS[argv[0]])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Append to `.gitignore`:
```
# launch\run_hidden.py output (server logs and PIDs)
launch/logs/
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_hidden.py -v`. Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add launch/run_hidden.py tests/test_run_hidden.py .gitignore
git commit -m "feat(launch): run_hidden runs a server with no window and a rotating log"
```

---

### Task 2: start.bat modes, camera window script, test-server live check

**Files:**
- Modify: `launch/production/start.bat`, `launch/test/start.bat`, `launch/enviro/start.bat`
- Modify: `launch/production/restart.bat`, `launch/test/restart.bat`, `launch/enviro/restart.bat` (pass `%*` through to start.bat)
- Modify: `launch/camera_status_window.ps1`

**Interfaces:**
- Consumes: `launch\run_hidden.py <name>` (Task 1).
- Produces:
  - `start.bat` with no flag: removes the `stopped_<port>` mark, checks the port (if busy: print "already running" and `exit /b 0`, no pause), starts `start "" /b "%PYW%" "%CD%\launch\run_hidden.py" <name>`, prints where the log is, waits about 2 s and `exit /b 0`. `PYW` is `.venv\Scripts\pythonw.exe` (ENVIRO too: the runner is the main repo's).
  - `start.bat --child`: the old body without any `pause`. Production starts camera status hidden with `camera_status_window.ps1`, no switch.
  - `start.bat --window`: the old body exactly as today. Production starts camera status with `camera_status_window.ps1 -Window`.
  - `camera_status_window.ps1 [-Stop] [-Window]`: detection and `-Stop` unchanged. When none is open, it opens the old visible cmd window with `-Window`, otherwise it starts `.venv\Scripts\pythonw.exe launch\run_hidden.py camera` (`Start-Process -WindowStyle Hidden`, working dir = repo root).

**Batch pattern** (apply to each start.bat, keeping its existing body). Put this right after the `cd /d` / `title` lines, and after the stopped-mark deletion for production and ENVIRO. The test server has no mark deletion today: add `if exist "launch\watchdog\state\stopped_8001" del "launch\watchdog\state\stopped_8001"` for consistency.

```bat
rem Modes: no flag = start hidden through launch\run_hidden.py (output in launch\logs\<name>.log, shown in
rem BKK Monitor > Processes); --child = the hidden run itself (no pause, nobody is there to press a key);
rem --window = the old visible console, for debugging.
set "MODE=hidden"
for %%a in (%*) do (
    if /i "%%~a"=="--child" set "MODE=child"
    if /i "%%~a"=="--window" set "MODE=window"
)
if "%MODE%"=="hidden" (
    netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul && (
        echo [!] Server is already running on port 8000. Use restart.bat to restart it.
        exit /b 0
    )
    start "" /b "%~dp0..\..\.venv\Scripts\pythonw.exe" "%~dp0..\run_hidden.py" production
    echo [OK] Started in the background. Log: launch\logs\production.log  ^(BKK Monitor ^> Processes^)
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)
```

(Use the right port and name per file: test 8001 / `test`, enviro 5050 / `enviro`. In ENVIRO's start.bat the `cd /d` goes into `ENVIRO`, so use the `%~dp0`-relative paths shown, not `%CD%`.)

Then in each body:
- Every `pause` becomes `if not "%MODE%"=="child" pause`. That covers the already-running branch, the error branches and the final `pause`.
- Production: replace the `powershell ... camera_status_window.ps1` line with:
  ```bat
  if "%MODE%"=="window" (
      powershell -NoProfile -ExecutionPolicy Bypass -File "launch\camera_status_window.ps1" -Window
  ) else (
      powershell -NoProfile -ExecutionPolicy Bypass -File "launch\camera_status_window.ps1"
  )
  ```
- `title` lines stay; they are harmless in a hidden console.

Each `restart.bat`: change `call "%~dp0start.bat"` to `call "%~dp0start.bat" %*` so `restart.bat --window` keeps the old behaviour.

`camera_status_window.ps1`: change `param([switch]$Stop)` to `param([switch]$Stop, [switch]$Window)` and the open branch to:
```powershell
} elseif ($Window) {
    Start-Process -FilePath 'cmd.exe' -ArgumentList "/c `"`"$bat`"`""
    Write-Host '[*] Camera status window opened: every camera checked every 5 minutes, log in instances\production\camera_status.log'
} else {
    $root = Split-Path $PSScriptRoot -Parent
    Start-Process -FilePath (Join-Path $root '.venv\Scripts\pythonw.exe') -ArgumentList "`"$PSScriptRoot\run_hidden.py`" camera" `
        -WorkingDirectory $root -WindowStyle Hidden
    Write-Host '[*] Camera status started in the background: log in launch\logs\camera.log (BKK Monitor > Processes)'
}
```
Update the header comment to say so.

- [ ] **Step 1: Edit the files above.** Keep CRLF line endings (check afterwards with `file launch/production/start.bat` or `grep -c $'\r' ...`).

- [ ] **Step 2: Static checks** (no server touched):
  - `powershell -NoProfile -Command "$null=[System.Management.Automation.Language.Parser]::ParseFile('E:\new_ccty_bangkok\launch\camera_status_window.ps1',[ref]$null,[ref]$e); $e"` prints nothing.
  - The kill_server regex matches the hidden child's command line:
    `powershell -NoProfile -Command "'cmd.exe /c E:\new_ccty_bangkok\launch\production\start.bat --child' -match 'launch\\production\\(re)?start(_local)?\.bat'"` prints `True`.

- [ ] **Step 3: Live check on the TEST server only** (port 8001; production and ENVIRO are not touched). From PowerShell in the repo root:
  1. `cmd /c launch\test\start.bat`. Expected: it returns within a few seconds, printing `[OK] Started in the background`.
  2. Poll `http://127.0.0.1:8001/api/health` (200 or 503 both mean up) for up to 5 minutes, because the first start may build the web UI.
  3. `launch\logs\test.log` holds the server banner lines with timestamps, and `launch\logs\test.json` has both PIDs.
  4. No visible console window was opened. Check `Get-Process | ? MainWindowTitle -like '*TEST*'` returns nothing.
  5. `cmd /c launch\test\stop.bat`. Expected: `[*] Closed server window (PID …)`; :8001 stops answering within 10 s; `test.json` gets `exited_at` within a few seconds; `launch\watchdog\state\stopped_8001` exists again.
  6. Record all outputs in the report.

- [ ] **Step 4: Commit**

```bash
git add launch/production/start.bat launch/test/start.bat launch/enviro/start.bat launch/production/restart.bat launch/test/restart.bat launch/enviro/restart.bat launch/camera_status_window.ps1
git commit -m "feat(launch): start.bat runs hidden by default (--window for the old console, --child for the runner)"
```

---

### Task 3: Watchdog restarts camera status; silence 10054 noise

**Files:**
- Modify: `launch/watchdog/watchdog.ps1`
- Create: `backend/core/log_filters.py`
- Modify: `server.py` (in `if __name__ == "__main__":`, before `uvicorn.run`)
- Test: `tests/test_log_filters.py`

**Interfaces:**
- Produces: `backend.core.log_filters.quiet_client_resets()`, which adds `DropClientResets` to `logging.getLogger("asyncio")` once (idempotent). `DropClientResets.filter(record)` returns False only when `record.exc_info` holds a `ConnectionResetError` and `"_call_connection_lost"` is in `record.getMessage()`.

- [ ] **Step 1: Failing test `tests/test_log_filters.py`**

```python
import logging
import sys

from backend.core.log_filters import DropClientResets, quiet_client_resets


def rec(msg, exc):
    try:
        raise exc
    except Exception:
        info = sys.exc_info()
    return logging.LogRecord("asyncio", logging.ERROR, __file__, 1, msg, None, info)


def test_drops_only_client_reset_in_connection_lost():
    f = DropClientResets()
    assert f.filter(rec("Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
                        ConnectionResetError(10054, "forcibly closed"))) is False
    assert f.filter(rec("Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
                        RuntimeError("other"))) is True
    assert f.filter(rec("Task exception was never retrieved", ConnectionResetError())) is True
    assert f.filter(logging.LogRecord("asyncio", logging.ERROR, __file__, 1, "plain", None, None)) is True


def test_install_is_idempotent():
    quiet_client_resets()
    quiet_client_resets()
    assert sum(isinstance(x, DropClientResets) for x in logging.getLogger("asyncio").filters) == 1
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_log_filters.py -v`. Expected: ModuleNotFoundError.

- [ ] **Step 2: Implement `backend/core/log_filters.py`**

```python
"""
Log filters for the server console / log file.

quiet_client_resets(): on Windows, asyncio's proactor logs a full traceback ("Exception in callback
_ProactorBasePipeTransport._call_connection_lost() ... ConnectionResetError: [WinError 10054]") every time a
visitor's browser drops the connection first. That is normal traffic, not a fault, and it buried real errors
in the production window. Only that exact case is dropped; every other asyncio error still shows.
"""
import logging


class DropClientResets(logging.Filter):
    def filter(self, record):
        exc = record.exc_info[1] if record.exc_info else None
        return not (isinstance(exc, ConnectionResetError) and "_call_connection_lost" in record.getMessage())


def quiet_client_resets():
    log = logging.getLogger("asyncio")
    if not any(isinstance(f, DropClientResets) for f in log.filters):
        log.addFilter(DropClientResets())
```

In `server.py`, inside `if __name__ == "__main__":` after `import uvicorn`:
```python
    from backend.core.log_filters import quiet_client_resets
    quiet_client_resets()
```

- [ ] **Step 3: Watchdog.** In `launch/watchdog/watchdog.ps1`, after the `foreach ($server ...)` loop, append:

```powershell
# Camera status (launch\camera_status.py) writes the list of dead cameras the live camera page hides; it runs
# next to production. If production is up and not stopped on purpose but no camera watcher runs, start it
# (hidden, launch\camera_status_window.ps1 decides how).
if (-not (Test-Path (Join-Path $state 'stopped_8000')) -and (Test-Up 8000)) {
    $cam = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object { $_.CommandLine -match 'launch\\camera_status\.bat' -and $_.CommandLine -notmatch '--once|--all|8001' })
    if (-not $cam) {
        Write-Log 'camera status not running: starting it (launch\camera_status_window.ps1)'
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $launch 'camera_status_window.ps1') | Out-Null
    }
}
```
Update the header comment (first lines) to mention camera status. Parse-check with the PowerShell parser command from Task 2. Do NOT run watchdog.ps1. It would act on live production.

- [ ] **Step 4: Run tests**: `.venv/Scripts/python.exe -m pytest tests/test_log_filters.py -v` (2 passed), then `pytest tests -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/core/log_filters.py server.py tests/test_log_filters.py launch/watchdog/watchdog.ps1
git commit -m "feat(launch): watchdog restarts camera status; server drops WinError 10054 client-reset noise"
```

---

### Task 4: `monitor_processes` + Api methods + camera check

**Files:**
- Create: `launch/monitor/monitor_processes.py`
- Modify: `launch/monitor/monitor_app.py` (new Api methods)
- Modify: `launch/monitor/monitor_checks.py` (LABELS `camera`, `service:camera` row in `run_round`)
- Test: `tests/test_monitor_processes.py`, additions to `tests/test_monitor_app.py`, `tests/test_monitor_checks.py`

**Interfaces:**
- Consumes: `launch\logs\<name>.json` / `.log` from Task 1. `monitor_checks.ROOT`.
- Produces:
  - `monitor_processes.NAMES = ("production", "test", "enviro", "camera")`, `LABELS = {"production": "Production", "test": "Test", "enviro": "ENVIRO", "camera": "Camera status"}`, `LOG_DIR = ROOT/"launch"/"logs"`.
  - `alive(pid) -> bool`: uses ctypes `OpenProcess(0x1000, False, pid)` then `GetExitCodeProcess == 259`, and closes the handle. Falsy or invalid pid gives False. Never `os.kill`.
  - `info(name, log_dir=LOG_DIR, alive=alive, now=time.time) -> dict` returns `{"name", "label", "running": bool, "pid": child_pid|None, "started_at": float|None, "uptime_s": int|None, "exit_code": int|None, "exited_at": float|None, "log": str(path), "log_size": int}`. `running` is true when the json exists, has no `exited_at`, and both `runner_pid` and `child_pid` are alive.
  - `tail(name, offset=None, log_dir=LOG_DIR, first_bytes=65536, max_bytes=262144) -> {"lines": list[str], "offset": int, "reset": bool}`:
    - `offset=None`: the last `first_bytes` of the file, dropping a partial first line.
    - `offset` at or below the size: the new bytes from `offset`, at most `max_bytes`, whole lines only.
    - file smaller than `offset` (rotated): start from 0 with `reset=True`.
    - missing file: `{"lines": [], "offset": 0, "reset": offset is not None and offset > 0}`.
  - `Api.processes() -> list[dict]` = `[info(n) for n in NAMES]`.
  - `Api.log_tail(name, offset=None)`: unknown name returns `{"lines": [], "offset": 0, "reset": False, "error": "unknown"}`.
  - `Api.open_log(name)`: `os.startfile(log_dir)` for a known name (opens the folder, so all rotated files are visible). Unknown name returns `{"ok": False}`, otherwise `{"ok": True}`.
  - `monitor_checks.LABELS["camera"] = "Camera status"`; `monitor_checks.CAMERA_STATUS = ROOT/"instances"/"production"/"camera_status.json"`; `monitor_checks.camera_age() -> float|None` (seconds since mtime, None if missing). `run_round` appends after the tunnel row a `service:camera` status: `ok` "updated N min ago" when age < 900 s; else `stopped` when `stopped(8000)`; else `fail` "camera_status.json is N min old" / "camera_status.json missing".

- [ ] **Step 1: Failing tests**

`tests/test_monitor_processes.py`:
```python
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_processes as mp  # noqa: E402


def write_state(d, name, **kw):
    (d / f"{name}.json").write_text(json.dumps({"name": name, "runner_pid": 11, "child_pid": 22,
                                                 "started_at": 1000.0, "command": "x", **kw}), encoding="utf-8")


def test_info_running_and_exited(tmp_path):
    write_state(tmp_path, "production")
    (tmp_path / "production.log").write_text("a\n", encoding="utf-8")
    i = mp.info("production", log_dir=tmp_path, alive=lambda pid: True, now=lambda: 1060.0)
    assert i["running"] is True and i["pid"] == 22 and i["uptime_s"] == 60 and i["log_size"] == 2
    assert i["label"] == "Production"
    write_state(tmp_path, "test", exited_at=1050.0, exit_code=1)
    j = mp.info("test", log_dir=tmp_path, alive=lambda pid: True, now=lambda: 1060.0)
    assert j["running"] is False and j["exit_code"] == 1 and j["uptime_s"] is None


def test_info_dead_pid_or_missing(tmp_path):
    write_state(tmp_path, "enviro")
    assert mp.info("enviro", log_dir=tmp_path, alive=lambda pid: pid != 22)["running"] is False
    k = mp.info("camera", log_dir=tmp_path)
    assert k["running"] is False and k["pid"] is None and k["log_size"] == 0


def test_alive_real_and_bogus():
    import os
    assert mp.alive(os.getpid()) is True
    assert mp.alive(0) is False and mp.alive(None) is False
    assert mp.alive(2**31 - 7) is False


def test_tail_first_then_incremental(tmp_path):
    p = tmp_path / "production.log"
    p.write_bytes(b"one\ntwo\nthr")
    t = mp.tail("production", log_dir=tmp_path)
    assert t["lines"] == ["one", "two"] and t["offset"] == 8 and t["reset"] is False
    with open(p, "ab") as f:
        f.write(b"ee\nfour\n")
    t2 = mp.tail("production", t["offset"], log_dir=tmp_path)
    assert t2["lines"] == ["three", "four"] and t2["offset"] == p.stat().st_size


def test_tail_first_drops_partial_head(tmp_path):
    (tmp_path / "test.log").write_bytes(b"x" * 100 + b"\nkeep\n")
    assert mp.tail("test", log_dir=tmp_path, first_bytes=10)["lines"] == ["keep"]


def test_tail_rotated_and_missing(tmp_path):
    (tmp_path / "enviro.log").write_bytes(b"new\n")
    t = mp.tail("enviro", 5000, log_dir=tmp_path)
    assert t["reset"] is True and t["lines"] == ["new"]
    assert mp.tail("camera", None, log_dir=tmp_path) == {"lines": [], "offset": 0, "reset": False}
    assert mp.tail("camera", 40, log_dir=tmp_path)["reset"] is True
```

Add to `tests/test_monitor_app.py`:
```python
def test_processes_and_log_api(tmp_path, monkeypatch):
    import monitor_processes as mp
    monkeypatch.setattr(mp, "LOG_DIR", tmp_path)
    (tmp_path / "test.log").write_bytes(b"hello\n")
    api, _, _, _ = make(tmp_path)
    names = [p["name"] for p in api.processes()]
    assert names == ["production", "test", "enviro", "camera"]
    assert api.log_tail("test")["lines"] == ["hello"]
    assert api.log_tail("../../x").get("error") == "unknown"
    assert api.open_log("nope") == {"ok": False}
```
(`monitor_processes` functions must read the module-level `LOG_DIR` at call time: use `log_dir=None` defaults resolved inside the function, or have the Api pass `mp.LOG_DIR` explicitly.)

Add to `tests/test_monitor_checks.py`:
```python
def test_camera_check(monkeypatch):
    patch(monkeypatch, up={8000}, stopped={8001, 5050})
    monkeypatch.setattr(mc, "camera_age", lambda: 120.0)
    assert by_key(mc.run_round(gateway_due=False))["service:camera"]["state"] == "ok"
    monkeypatch.setattr(mc, "camera_age", lambda: 3600.0)
    assert by_key(mc.run_round(gateway_due=False))["service:camera"]["state"] == "fail"
    monkeypatch.setattr(mc, "camera_age", lambda: None)
    patch(monkeypatch, up=set(), stopped={8000, 8001, 5050})
    monkeypatch.setattr(mc, "camera_age", lambda: None)
    assert by_key(mc.run_round(gateway_due=False))["service:camera"]["state"] == "stopped"
```
(The existing `patch()` helper in that file does not patch `camera_age`, so the other tests must still pass with the real file. Make `patch()` also set `camera_age` to `lambda: 60.0`, then the camera test overrides it.)

- [ ] **Step 2: Run to verify failure**: `.venv/Scripts/python.exe -m pytest tests/test_monitor_processes.py tests/test_monitor_app.py tests/test_monitor_checks.py -v`

- [ ] **Step 3: Implement** `monitor_processes.py` with the interfaces above. Module docstring in the style of the other monitor modules. ctypes setup:

```python
import ctypes
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)
STILL_ACTIVE = 259


def alive(pid):
    if not pid or not isinstance(pid, int) or pid < 0 or pid > 0xFFFFFFFF:
        return False
    h = _k32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(_k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        _k32.CloseHandle(h)
```

Then the Api methods in `monitor_app.py`, which import `monitor_processes` and must not touch the real servers, and the camera check in `monitor_checks.py`.

- [ ] **Step 4: Run tests**: the three files, then `pytest tests -q`.

- [ ] **Step 5: Commit**

```bash
git add launch/monitor/monitor_processes.py launch/monitor/monitor_app.py launch/monitor/monitor_checks.py tests/test_monitor_processes.py tests/test_monitor_app.py tests/test_monitor_checks.py
git commit -m "feat(monitor): process state, log tail and open-log API; camera status check"
```

---

### Task 5: "Processes" page in the window

**Files:**
- Modify: `launch/monitor/ui/index.html`

**Interfaces:**
- Consumes: `api().processes()`, `api().log_tail(name, offset)`, `api().open_log(name)` (Task 4). It also uses the existing `action(target, verb)` for Start/Restart/Stop of production/test/enviro. Camera status has no action buttons: it follows production.

**Layout:**
- Sidebar: add `Processes` under `Events` (`data-page="processes"`).
- Header: title "Processes", subtitle "Servers running in the background · logs in launch\logs".
- A row of four cards (Production, Test, ENVIRO, Camera status). Each card shows:
  - a state pill `running` (ok colour) or `not running` (idle colour; `fail` colour when `exit_code` is non-zero);
  - `PID n · up 3 h 12 min`, or `exited <ago> (code c)`, or `never started hidden`;
  - the log size;
  - an `Open log` button;
  - for production/test/enviro, the same `⋯` Start/Restart/Stop menu and confirm dialog as the Overview cards.

  Clicking a card selects it; the default selection is Production.
- Below the cards, a log panel for the selected process:
  - a toolbar with the name, an `Errors only` toggle chip, a `Follow` toggle (on by default: auto-scroll to the bottom when new lines arrive), a `Clear` button (clears the view only) and `Open log`.
  - a monospace pane (`font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; white-space: pre-wrap`) with dark background, scrollable, about 60% of the window height.
  - line colours: `/\b(ERROR|CRITICAL|Traceback)\b|\[FAIL\]/` → `--fail`; `/\bWARNING\b|\[WARN\]/` → `--warn`; `--- .* (started|exited) ---` → `--accent`; else `--text`.
  - `Errors only` shows only red and yellow lines, plus the indented continuation lines that follow a red `Traceback` line until the next timestamped line that has no indent after the timestamp.
- Polling: while the Processes page is open, call `processes()` every 3 s and `log_tail(selected, offset)` every 1.5 s. Append new lines and keep at most 5000 lines in the DOM (drop the oldest). On `reset`, clear and append. On selection change, call `log_tail(name)` with no offset.
- Escape every log line with the existing `esc()`/textContent. Log text is untrusted.
- Do not re-render the log pane on the 5 s status poll: append-only updates to the pane, so selection and scroll survive.
- When `running` is false and the server port is answering (a `server:<target>` status is ok/warn), show the hint "running in a window (started with --window): no log here".

- [ ] **Step 1: Implement in index.html** following the existing code style (`S` state, `render*` functions, delegated click handler, `softRender`).

- [ ] **Step 2: Verify with a fake API in pywebview** (throwaway script in your scratch area, not the repo). Its methods must return made-up data, and its `action()` must only return `{"ok": True, "message": "fake"}`. Check:
  - no JS errors;
  - the four cards render;
  - lines are coloured;
  - `Errors only` hides an INFO line and keeps a Traceback block;
  - a `reset` clears the pane;
  - the pane keeps at most 5000 lines;
  - switching the selection loads that log.

  Do not open the page against the real Api.

- [ ] **Step 3: Run `pytest tests -q`**, then commit:

```bash
git add launch/monitor/ui/index.html
git commit -m "feat(monitor): Processes page with live logs for the hidden servers"
```

---

### Task 6 (controller): switch-over and live checks

Not for a subagent. Run by the controller after Tasks 1-5 are reviewed. The user authorized Claude to do this switch-over.
1. Restart the BKK Monitor collector and app (new code).
2. Start test hidden (`launch\test\start.bat`), see it in Processes with a live log, then stop it.
3. Production: run `launch\production\restart.bat` (kills the windowed server and camera window, starts hidden). Wait until `https://bkksmartstreet.com` and `127.0.0.1:8000/api/health` answer, then check `launch\logs\production.log` and `camera.log`.
4. ENVIRO: run `launch\enviro\restart.bat`. Check `https://bkksmartstreet.com/enviro/` answers.
5. Confirm there are no console windows left, the Processes page shows 3 running (test stopped), and the watchdog log is quiet for one cycle.
6. Update memory (live-server-location, bkk-monitor-app): servers run hidden; `--window` for the old console; logs in `launch\logs`.
