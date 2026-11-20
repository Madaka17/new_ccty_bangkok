r"""
Keeps an SSH reverse tunnel open from this PC to the Raspberry Pi, so the Pi test server can reach Bionic.

Bionic (LM Studio) listens on 127.0.0.1 of this PC only. This script keeps this open:
    ssh -N -R 127.0.0.1:1235:127.0.0.1:1235 test@192.168.1.109
so 127.0.0.1:1235 on the Pi reaches Bionic here. The Pi side is launch/pi/bkk-test-bionic.conf.

    PI_SYNC_HOST     ssh target                     test@192.168.1.109
    PI_SYNC_KEY      ssh private key                C:\Users\user\.ssh\bkkpi_ed25519
    BIONIC_PORT      Bionic port, on both ends      1235

Nothing is forwarded while Bionic is down: the script waits until 127.0.0.1:BIONIC_PORT answers.
After the PC sleeps or the network drops, the Pi's sshd can keep the old forward and every new tunnel fails
with "remote port forwarding failed". Then the script kills the sshd process on the Pi that listens on the
port (and only if it is sshd) and reconnects. Retries every 30 s. One copy at a time (a lock file).
Log: launch\logs\pi_bionic_tunnel.log.

    pythonw launch\test\pi_bionic_tunnel.py          run hidden (the logon task runs this)
    python launch\test\pi_bionic_tunnel.py --once    one connection attempt, exits when ssh exits (testing)

Start at logon (run once; a Startup-folder shortcut, because "schtasks /SC ONLOGON" needs admin rights):
    powershell -NoProfile -ExecutionPolicy Bypass -File launch\test\install_pi_tunnel_startup.ps1

Model guard. Bionic loads a model by itself on the first request (after a reboot, for example) with its
own default context, which can be 123648 tokens and too much for the GPU. So while Bionic is up, a thread
checks GUARD_MODEL every GUARD_SECONDS and makes it match GUARD_CONTEXT and GUARD_PARALLEL. An instance
that reports a different context or parallel value is unloaded; an instance with missing settings is left
alone. A missing model is loaded with the right settings. A failed load is retried every
GUARD_RETRY_SECONDS, up to GUARD_LOAD_TRIES failures in a row, and then the guard waits GUARD_BACKOFF_SECONDS.
A failed unload waits GUARD_BACKOFF_SECONDS at once. A failed read of the model list is retried at the next
check. Logging never changes what the guard does. Settings by environment variable (a bad number is logged
once and the default is used):
    BIONIC_MODEL     model key                      unsloth/qwen3.5-4b
    BIONIC_CONTEXT   context length                 16384
    BIONIC_PARALLEL  parallel slots                 1
    BIONIC_GUARD     1 = on, 0 = off (no thread)    1
--once never starts the guard.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime

import msvcrt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(ROOT, "launch", "logs")
LOG_FILE = os.path.join(LOG_DIR, "pi_bionic_tunnel.log")
LOCK_FILE = os.path.join(LOG_DIR, "pi_bionic_tunnel.lock")

HOST = os.getenv("PI_SYNC_HOST", "test@192.168.1.109")
KEY = os.getenv("PI_SYNC_KEY", r"C:\Users\user\.ssh\bkkpi_ed25519")
PORT = int(os.getenv("BIONIC_PORT", "1235"))
RETRY_SECONDS = 30
LOG_KEEP = 2000          # log trimmed to its last LOG_KEEP lines when it grows past 2 x LOG_KEEP
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CONFIG_WARNINGS = []     # bad environment values, reported once by main() (not at import: no log writes here)


def _env_int(name, default):
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError:
        CONFIG_WARNINGS.append(f"{name}={raw!r} is not a whole number, using {default}")
        return default


GUARD_MODEL = os.getenv("BIONIC_MODEL", "unsloth/qwen3.5-4b")
GUARD_CONTEXT = _env_int("BIONIC_CONTEXT", 16384)
GUARD_PARALLEL = _env_int("BIONIC_PARALLEL", 1)
GUARD_ENABLED = os.getenv("BIONIC_GUARD", "1") != "0"
GUARD_SECONDS = 60           # check the model this often while Bionic answers
GUARD_RETRY_SECONDS = 15     # after a failed load, try again this soon ...
GUARD_LOAD_TRIES = 3         # ... this many failed loads in a row, then ...
GUARD_BACKOFF_SECONDS = 300  # ... wait this long before trying again

_LOG_LOCK = threading.Lock() # the tunnel loop and the guard thread both write the log


def ssh_command(key, host, port):
    """The ssh call that holds the reverse tunnel open (list form, no shell)."""
    return ["ssh", "-i", key, "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=15",
            "-R", f"127.0.0.1:{port}:127.0.0.1:{port}", host]


def cleanup_command(port):
    """Run on the Pi: kill the process that listens on the port, only if it is sshd (sshd-session from
    OpenSSH 9.8). ss needs sudo to name it: sshd marks its sessions non-dumpable, so even their own user
    cannot read their sockets. The kill needs no sudo, the session runs as the ssh user."""
    return (f'pid=$(sudo -n ss -ltnpH "sport = :{port}" | grep -o "pid=[0-9]*" | head -1 | cut -d= -f2); '
            'comm=$([ -n "$pid" ] && ps -o comm= -p "$pid"); '
            'case "$comm" in sshd|sshd-session) kill "$pid" && echo killed "$pid" ;; *) echo none ;; esac')


def is_forward_failure(stderr_text):
    return bool(stderr_text) and "remote port forwarding failed" in stderr_text


def _log(line):
    with _LOG_LOCK:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {line}\n")
        if os.path.getsize(LOG_FILE) > 200_000:
            with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if len(lines) > 2 * LOG_KEEP:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-LOG_KEEP:])
        if sys.stdout is not None:   # pythonw has no console
            try:
                print(f"{stamp} {line}")
            except (OSError, UnicodeError):
                pass   # the log file has it; a console that cannot show a character must not stop the loop


def _safe_log(line):
    """_log that never raises: a log problem must not stop the guard or change what it did."""
    try:
        _log(line)
    except Exception:  # noqa: BLE001 - logging is best effort
        pass


def bionic_up():
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=2).close()
        return True
    except OSError:
        return False


def take_lock():
    """An exclusive lock on LOCK_FILE for the life of the process; None when another copy holds it."""
    os.makedirs(LOG_DIR, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        return None
    return fd


def clear_stale_forward():
    """Ask the Pi to kill the sshd that still holds the port. Logs what it did; never raises."""
    cmd = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST, cleanup_command(PORT)]
    try:
        out = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW)
        _log(f"stale forward cleanup: {out.stdout.strip() or out.stderr.strip()[-160:]}")
    except Exception as e:  # noqa: BLE001 - the Pi may be off; the next try retries
        _log(f"stale forward cleanup failed: {type(e).__name__}: {str(e)[:160]}")


def run_tunnel():
    """One ssh connection; returns when ssh exits."""
    started = time.time()
    proc = subprocess.Popen(ssh_command(KEY, HOST, PORT), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    _, err_bytes = proc.communicate()
    err = err_bytes.decode("utf-8", "replace").strip()
    _log(f"ssh exit {proc.returncode} after {time.time() - started:.0f} s: {err[-300:]}")
    if is_forward_failure(err):
        clear_stale_forward()


def find_model(models_json, key):
    """The entry for key in a GET /api/v1/models answer; None when Bionic does not list it.
    Raises ValueError when the answer does not have the expected shape."""
    if not isinstance(models_json, dict) or not isinstance(models_json.get("models"), list):
        raise ValueError("unexpected /api/v1/models answer")
    for entry in models_json["models"]:
        if isinstance(entry, dict) and entry.get("key") == key:
            return entry
    return None


def is_wrong_instance(instance, ctx, par):
    """True only when the instance reports a context or parallel value that differs. A missing value
    is unknown, so it does not make the instance wrong."""
    cfg = instance.get("config") or {}
    if cfg.get("context_length") is not None and cfg["context_length"] != ctx:
        return True
    return cfg.get("parallel") is not None and cfg["parallel"] != par


def is_known_right_instance(instance, ctx, par):
    cfg = instance.get("config") or {}
    return cfg.get("context_length") == ctx and cfg.get("parallel") == par


def plan_actions(models_json, key, ctx, par):
    """What the guard must do for key: ("unload", instance_id) for each wrong instance, then ("load",)
    when no instance is left. The first instance that is not wrong is kept; a second one is unloaded
    only when it is known to be right too (one copy is enough); unknown extras are left alone."""
    entry = find_model(models_json, key) or {}
    actions = []
    kept = False
    for inst in entry.get("loaded_instances") or []:
        if is_wrong_instance(inst, ctx, par):
            actions.append(("unload", inst["id"]))
        elif not kept:
            kept = True
        elif is_known_right_instance(inst, ctx, par):
            actions.append(("unload", inst["id"]))
    if not kept:
        actions.append(("load",))
    return actions


def http_models():
    """GET /api/v1/models on Bionic, 5 s timeout. Returns the parsed JSON."""
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/models", timeout=5) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def http_post(path, body, timeout):
    """POST a JSON body to Bionic. Raises on HTTP errors; returns the parsed answer, or None when it is empty."""
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8", "replace")
    return json.loads(text) if text.strip() else None


def guard_once(fetch, post, state, clock=lambda: time.time()):
    """One check of GUARD_MODEL. Never raises. Returns the seconds until the next check.
    state["retry_at"]: no load or unload before this time, set after a failure.
    state["load_fails"]: failed loads in a row. Logs only when it acts or fails."""
    now = clock()
    if now < state.get("retry_at", 0.0):
        return min(state["retry_at"] - now, GUARD_SECONDS)
    try:
        models_json = fetch()
        actions = plan_actions(models_json, GUARD_MODEL, GUARD_CONTEXT, GUARD_PARALLEL)
    except Exception as e:  # noqa: BLE001 - Bionic may be busy or answer garbage; the next check tries again
        _safe_log(f"model guard: could not read Bionic models: {type(e).__name__}: {str(e)[:160]}")
        return GUARD_SECONDS
    if not actions:
        return GUARD_SECONDS
    old = {inst.get("id"): (inst.get("config") or {})
           for inst in (find_model(models_json, GUARD_MODEL) or {}).get("loaded_instances") or []}
    for action in actions:
        if action[0] == "unload":
            cfg = old.get(action[1], {})
            try:
                post("/api/v1/models/unload", {"instance_id": action[1]}, 60)
            except Exception as e:  # noqa: BLE001 - back off and try later; never leave the thread
                _safe_log(f"model guard: unload {action[1]} failed: {type(e).__name__}: {str(e)[:160]}, "
                          f"retry in {GUARD_BACKOFF_SECONDS} s")
                state["retry_at"] = clock() + GUARD_BACKOFF_SECONDS
                return GUARD_BACKOFF_SECONDS
            # the action is done; a log problem after this point must not count as a failure
            _safe_log(f"model guard: unloaded {action[1]} (context {cfg.get('context_length')} "
                      f"parallel {cfg.get('parallel')}, want {GUARD_CONTEXT}/{GUARD_PARALLEL})")
        else:
            try:
                post("/api/v1/models/load", {"model": GUARD_MODEL, "context_length": GUARD_CONTEXT,
                                             "flash_attention": True, "parallel": GUARD_PARALLEL}, 180)
            except Exception as e:  # noqa: BLE001 - retry soon, then back off; never leave the thread
                state["load_fails"] = state.get("load_fails", 0) + 1
                reason = f"{type(e).__name__}: {str(e)[:160]}"
                if state["load_fails"] < GUARD_LOAD_TRIES:
                    state["retry_at"] = clock() + GUARD_RETRY_SECONDS
                    _safe_log(f"model guard: load failed ({state['load_fails']} of {GUARD_LOAD_TRIES}): "
                              f"{reason}, retry in {GUARD_RETRY_SECONDS} s")
                    return GUARD_RETRY_SECONDS
                state["load_fails"] = 0
                state["retry_at"] = clock() + GUARD_BACKOFF_SECONDS
                _safe_log(f"model guard: load failed {GUARD_LOAD_TRIES} times in a row: {reason}, "
                          f"retry in {GUARD_BACKOFF_SECONDS} s")
                return GUARD_BACKOFF_SECONDS
            state["load_fails"] = 0
            _safe_log(f"model guard: loaded {GUARD_MODEL} context {GUARD_CONTEXT} parallel {GUARD_PARALLEL}")
    return GUARD_SECONDS


def guard_forever(fetch=http_models, post=http_post, clock=lambda: time.time()):
    """The guard thread: checks while Bionic answers on PORT, sleeping as guard_once asks (60 s normally,
    15 s between quick load retries). Never returns, never raises."""
    state = {"retry_at": 0.0}
    while True:
        wait = GUARD_SECONDS
        try:
            if bionic_up():
                wait = guard_once(fetch, post, state, clock=clock)
        except Exception as e:  # noqa: BLE001 - the guard must never die
            _safe_log(f"model guard error: {type(e).__name__}: {str(e)[:200]}")
        time.sleep(wait)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keep the Bionic reverse tunnel to the Pi open.")
    parser.add_argument("--once", action="store_true", help="one connection attempt, then exit")
    args = parser.parse_args(argv)

    lock = take_lock()
    if lock is None:
        if args.once:
            print("another pi_bionic_tunnel is running")
        return 0

    for line in CONFIG_WARNINGS:
        _safe_log(f"config: {line}")
    if not args.once:
        if GUARD_ENABLED:
            threading.Thread(target=guard_forever, name="bionic-model-guard", daemon=True).start()
        else:
            _safe_log("model guard off (BIONIC_GUARD=0)")

    down = False
    while True:
        try:
            if not bionic_up():
                if not down:
                    _log(f"Bionic not listening on :{PORT}, waiting")
                    down = True
                if args.once:
                    return 0
            else:
                if down:
                    _log("Bionic back")
                    down = False
                _log("connecting")
                run_tunnel()
        except Exception as e:  # noqa: BLE001 - never leave the loop
            _log(f"error: {type(e).__name__}: {str(e)[:200]}")
        if args.once:
            return 0
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
