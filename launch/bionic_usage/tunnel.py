"""SSH reverse tunnel status: is the Raspberry Pi test server reaching Bionic?

The Pi test server (192.168.1.109) uses the Bionic model on this PC through an
SSH reverse tunnel. launch/test/pi_bionic_tunnel.py runs under pythonw and keeps
one child ssh.exe open with `-R 127.0.0.1:1235:127.0.0.1:1235`. This module reads
the state of that tunnel for the live usage page. It never changes anything.

Every request from the Pi arrives as an ESTABLISHED TCP connection owned by the
ssh.exe pid, from 127.0.0.1:<port> to 127.0.0.1:1235. The ssh pid also holds one
ESTABLISHED connection to 192.168.1.109:22 (the link to the Pi).

Two checks run in the background:
  * check_local() every 2 s: finds the runner and ssh.exe, reads the TCP table,
    counts Pi requests and local clients, and reads the tunnel log tail;
  * check_pi() every 30 s: asks the Pi (over ssh) whether /v1/models on its
    127.0.0.1:1235 answers HTTP 200, and counts "Connection refused" or
    "no free slot" lines in the last 5 minutes of bkk-test's journal.

pi_seen_60s is a lower bound: a connection that opens and closes between two
2-second polls is not seen, and HTTP keep-alive can carry several requests on
one connection. pi_seen_total counts distinct connections seen since start, with
the same limit. Neither is a request count.

Wiring into live.py (done by the other session):
1. `tunnel = TunnelStatus()` in main(); jobs {"tunnel_local": tunnel.check_local,
   "tunnel_pi": tunnel.check_pi} in background_loop with INTERVALS 2 and 30 seconds;
2. build_state adds "tunnel": tunnel.snapshot();
3. the page draws the flow Pi test :8001 -> Pi 127.0.0.1:1235 -> ssh link -> ssh.exe
   -> Bionic :1235, colouring each hop from link_up / bionic_listening / pi.http and
   showing pi_conns, pi_seen_60s, local_clients and the last log line.

Errors are stored in the snapshot (local_error, pi.error); nothing here prints or
raises, because live.py runs under pythonw.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

import psutil

PORT = int(os.environ.get("BIONIC_PORT") or 1235)
PI_HOST_IP = os.environ.get("PI_SYNC_HOST_IP") or "192.168.1.109"
PI_SSH = os.environ.get("PI_SYNC_HOST") or "test@192.168.1.109"
PI_KEY = os.environ.get("PI_SYNC_KEY") or r"C:\Users\user\.ssh\bkkpi_ed25519"
TUNNEL_LOG = Path(os.environ.get("BIONIC_TUNNEL_LOG")
                  or r"E:\new_ccty_bangkok-tunnel\launch\logs\pi_bionic_tunnel.log")
WINDOW = 60  # seconds for pi_seen_60s
RUNNER_NAME = "pi_bionic_tunnel.py"
SSH_NAMES = ("ssh", "ssh.exe")
SSH_ARG = f"127.0.0.1:{PORT}:127.0.0.1:{PORT}"
PI_SSH_TIMEOUT = 20
PI_SSH_CONNECT_TIMEOUT = 5
LOG_TAIL_BYTES = 8 * 1024
REMOTE = (
    f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}' -m 5 "
    f"http://127.0.0.1:{PORT}/v1/models; echo; "
    "journalctl -u bkk-test --since -5min -o cat --no-pager "
    "| grep -cE 'Connection refused|no free slot'"
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def find_tunnel(procs) -> dict:
    """Find the tunnel runner and its ssh.exe child from a list of process dicts.

    Each process is {"pid", "name", "cmdline": list[str] or None}.
    """
    runner_pid = None
    ssh_pid = None
    for item in procs:
        cmdline = item.get("cmdline") or []
        if runner_pid is None and RUNNER_NAME in " ".join(cmdline):
            runner_pid = item["pid"]
        name = str(item.get("name") or "").lower()
        if (ssh_pid is None and name in SSH_NAMES and "-R" in cmdline
                and any(SSH_ARG in arg for arg in cmdline)):
            ssh_pid = item["pid"]
    return {"runner_pid": runner_pid, "ssh_pid": ssh_pid}


def _addr(value):
    """Return (ip, port) from an object with .ip/.port or a plain pair; None if empty."""
    if not value:
        return None
    if hasattr(value, "ip") and hasattr(value, "port"):
        return (value.ip, value.port)
    return (value[0], value[1])


def read_conns(conns, ssh_pid, port, pi_ip) -> dict:
    """Summarise TCP connections for the tunnel view. See the module docstring."""
    bionic_listening = False
    link_up = False
    pi_ports = set()
    local_clients: dict = {}
    for item in conns:
        laddr = _addr(item.laddr)
        raddr = _addr(item.raddr)
        if item.status == "LISTEN" and laddr and laddr[1] == port:
            bionic_listening = True
        if item.pid is None:
            continue
        if item.pid == ssh_pid and item.status == "ESTABLISHED":
            if raddr == (pi_ip, 22):
                link_up = True
            if raddr and raddr[0] == "127.0.0.1" and raddr[1] == port and laddr:
                pi_ports.add(laddr[1])
        if (item.status == "ESTABLISHED" and item.pid != ssh_pid
                and raddr == ("127.0.0.1", port)):
            local_clients[item.pid] = local_clients.get(item.pid, 0) + 1
    return {
        "bionic_listening": bionic_listening,
        "link_up": bool(ssh_pid is not None and link_up),
        "pi_ports": sorted(pi_ports),
        "local_clients": local_clients,
    }


def parse_pi_check(stdout) -> dict:
    """Parse the two lines printed on the Pi. Never raises; bad parts become None."""
    result = {"http": None, "ms": None, "errors_5min": None}
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if lines:
        parts = lines[0].split()
        try:
            result["http"] = int(parts[0])
        except (IndexError, ValueError):
            pass
        try:
            result["ms"] = round(float(parts[1]) * 1000)
        except (IndexError, ValueError):
            pass
    if len(lines) > 1:
        try:
            result["errors_5min"] = int(lines[1])
        except ValueError:
            pass
    return result


def overall(snap) -> tuple:
    """Return (state, reason_th) where state is "down", "degraded" or "ok"."""
    if snap.get("ssh_pid") is None:
        return ("down", "tunnel ไม่ได้รัน")
    if not snap.get("link_up"):
        return ("down", "ssh ยังไม่ต่อถึง Pi")
    if not snap.get("bionic_listening"):
        return ("down", "Bionic ไม่ได้เปิด port 1235")
    pi = snap.get("pi")
    if pi is not None and pi.get("http") != 200:
        return ("degraded", "Pi เรียก Bionic ไม่ผ่าน")
    if pi is not None and (pi.get("errors_5min") or 0) > 0:
        return ("degraded", f"เทสบน Pi มี error {pi['errors_5min']} ครั้งใน 5 นาที")
    return ("ok", "tunnel ทำงานปกติ")


def tail_lines(path, n=3) -> list:
    """Last n non-empty lines of a text file, reading at most the last 8 KB. [] if missing."""
    try:
        path = Path(path)
        size = path.stat().st_size
        with open(path, "rb") as handle:
            start = max(0, size - LOG_TAIL_BYTES)
            handle.seek(start)
            data = handle.read()
    except OSError:
        return []
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # the first line may be cut in the middle
    lines = [line for line in lines if line.strip()]
    return lines[-n:]


# ---------------------------------------------------------------------------
# Live status
# ---------------------------------------------------------------------------

def _default_processes():
    """Yield {"pid", "name", "cmdline"} for each process, skipping ones that vanish."""
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            yield dict(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def _default_connections():
    return psutil.net_connections(kind="tcp")


class TunnelStatus:
    """Keeps the last tunnel check. Thread-safe: the local and Pi checks run on separate threads."""

    def __init__(self, process_iter=None, net_connections=None, run=None,
                 clock=time.time, log_path=TUNNEL_LOG) -> None:
        self._process_iter = process_iter or _default_processes
        self._net_connections = net_connections or _default_connections
        self._run = run or subprocess.run
        self._clock = clock
        self._log_path = Path(log_path)
        self._lock = threading.Lock()
        self._open_ports: set = set()
        self._events: deque = deque()  # first-seen times of Pi connections
        self._pi_seen_total = 0
        self._local = {
            "runner_pid": None, "ssh_pid": None, "link_up": False,
            "bionic_listening": False, "pi_ports": [], "local_clients": [],
            "pi_seen_60s": 0, "log_tail": [], "checked_ts": None, "local_error": None,
        }
        self._pi = None

    def check_local(self) -> None:
        """Read the tunnel state from this PC. Never raises."""
        now = self._clock()
        try:
            procs = list(self._process_iter())
            found = find_tunnel(procs)
            facts = read_conns(list(self._net_connections()), found["ssh_pid"], PORT, PI_HOST_IP)
            names = {item["pid"]: item.get("name") or "?" for item in procs}
            clients = [
                {"pid": pid, "name": names.get(pid, "?"), "conns": count}
                for pid, count in sorted(facts["local_clients"].items())
            ]
            new_local = {
                "runner_pid": found["runner_pid"],
                "ssh_pid": found["ssh_pid"],
                "link_up": facts["link_up"],
                "bionic_listening": facts["bionic_listening"],
                "pi_ports": facts["pi_ports"],
                "local_clients": clients,
                "log_tail": tail_lines(self._log_path),
                "checked_ts": int(now),
                "local_error": None,
            }
            with self._lock:
                current = set(facts["pi_ports"])
                for port in current - self._open_ports:
                    self._events.append(now)
                    self._pi_seen_total += 1
                self._open_ports = current
                while self._events and now - self._events[0] >= WINDOW:
                    self._events.popleft()
                new_local["pi_seen_60s"] = len(self._events)
                new_local["pi_seen_total"] = self._pi_seen_total
                self._local = {**self._local, **new_local}
        except Exception as exc:  # any failure is shown on the page, never raised
            with self._lock:
                self._local = {**self._local, "local_error": f"{type(exc).__name__}: {exc}"}

    def check_pi(self) -> None:
        """Ask the Pi over ssh whether Bionic answers there. Never raises."""
        now = self._clock()
        cmd = ["ssh", "-i", PI_KEY, "-o", "BatchMode=yes",
               "-o", f"ConnectTimeout={PI_SSH_CONNECT_TIMEOUT}", PI_SSH, REMOTE]
        try:
            proc = self._run(
                cmd, timeout=PI_SSH_TIMEOUT, capture_output=True, text=True,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            result = {**parse_pi_check(proc.stdout), "checked_ts": int(now), "error": None}
        except Exception as exc:
            result = {"http": None, "ms": None, "errors_5min": None,
                      "checked_ts": int(now), "error": f"{type(exc).__name__}: {exc}"}
        with self._lock:
            self._pi = result

    def snapshot(self) -> dict:
        """A copy of the current state, with the overall state and reason."""
        with self._lock:
            local = dict(self._local)
            local["local_clients"] = [dict(item) for item in self._local["local_clients"]]
            local["pi_ports"] = list(self._local["pi_ports"])
            local["log_tail"] = list(self._local["log_tail"])
            pi = dict(self._pi) if self._pi is not None else None
            total = self._pi_seen_total
        state, reason = overall({
            "ssh_pid": local["ssh_pid"], "link_up": local["link_up"],
            "bionic_listening": local["bionic_listening"], "pi": pi,
        })
        return {
            "runner_pid": local["runner_pid"],
            "ssh_pid": local["ssh_pid"],
            "link_up": local["link_up"],
            "bionic_listening": local["bionic_listening"],
            "pi_conns": len(local["pi_ports"]),
            "local_clients": local["local_clients"],
            "pi_seen_60s": local.get("pi_seen_60s", 0),
            "pi_seen_total": total,
            "pi": pi,
            "log_tail": local["log_tail"],
            "checked_ts": local["checked_ts"],
            "local_error": local["local_error"],
            "state": state,
            "reason_th": reason,
        }
