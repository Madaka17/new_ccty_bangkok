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

Logon task (run once):
    schtasks /Create /TN "BKK Bionic tunnel to Pi" /SC ONLOGON /RL LIMITED /F /TR "\"E:\new_ccty_bangkok\.venv\Scripts\pythonw.exe\" \"E:\new_ccty_bangkok\launch\test\pi_bionic_tunnel.py\""
"""
import argparse
import os
import socket
import subprocess
import sys
import time
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


def ssh_command(key, host, port):
    """The ssh call that holds the reverse tunnel open (list form, no shell)."""
    return ["ssh", "-i", key, "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=15",
            "-R", f"127.0.0.1:{port}:127.0.0.1:{port}", host]


def cleanup_command(port):
    """Run on the Pi: kill the process that listens on the port, only if it is sshd."""
    return (f'pid=$(ss -ltnpH "sport = :{port}" | grep -o "pid=[0-9]*" | head -1 | cut -d= -f2); '
            'if [ -n "$pid" ] && [ "$(ps -o comm= -p "$pid")" = sshd ]; then kill "$pid" && echo killed "$pid"; '
            'else echo none; fi')


def is_forward_failure(stderr_text):
    return bool(stderr_text) and "remote port forwarding failed" in stderr_text


def _log(line):
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
        print(f"{stamp} {line}")


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keep the Bionic reverse tunnel to the Pi open.")
    parser.add_argument("--once", action="store_true", help="one connection attempt, then exit")
    args = parser.parse_args(argv)

    lock = take_lock()
    if lock is None:
        if args.once:
            print("another pi_bionic_tunnel is running")
        return 0

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
