"""Tests for tunnel.py: finding the SSH reverse tunnel, reading connections, Pi checks, status.

    E:\\new_ccty_bangkok\\.venv\\Scripts\\python.exe -m pytest launch\\bionic_usage\\test_tunnel.py -q

No real ssh, Pi or psutil call is made: every source is a fake passed into TunnelStatus.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

import tunnel

PORT = tunnel.PORT
PI_IP = tunnel.PI_HOST_IP
SSH_ARG = f"127.0.0.1:{PORT}:127.0.0.1:{PORT}"


def proc(pid, name, cmdline):
    return {"pid": pid, "name": name, "cmdline": cmdline}


def runner(pid=100):
    return proc(pid, "pythonw.exe", ["pythonw.exe", "launch\\test\\pi_bionic_tunnel.py"])


def ssh(pid=200, name="ssh.exe", args=None):
    if args is None:
        args = ["ssh.exe", "-N", "-R", SSH_ARG, "-o", "ExitOnForwardFailure=yes", tunnel.PI_SSH]
    return proc(pid, name, args)


def addr(ip, port):
    return SimpleNamespace(ip=ip, port=port)


def conn(pid, status, laddr, raddr):
    return SimpleNamespace(pid=pid, status=status, laddr=laddr, raddr=raddr)


def pi_conn(port, pid=200):
    """A Pi request arriving at ssh.exe: 127.0.0.1:<port> -> 127.0.0.1:<PORT>."""
    return conn(pid, "ESTABLISHED", ("127.0.0.1", port), ("127.0.0.1", PORT))


def link_conn(pid=200):
    return conn(pid, "ESTABLISHED", ("192.168.1.50", 55000), (PI_IP, 22))


# ---------------------------------------------------------------------------
# find_tunnel
# ---------------------------------------------------------------------------

def test_find_tunnel_finds_runner_and_ssh():
    procs = [proc(1, "python.exe", ["python.exe", "x.py"]), runner(100), ssh(200)]
    assert tunnel.find_tunnel(procs) == {"runner_pid": 100, "ssh_pid": 200}


def test_find_tunnel_ignores_ssh_without_dash_r():
    procs = [runner(100), ssh(200, args=["ssh.exe", tunnel.PI_SSH])]
    assert tunnel.find_tunnel(procs) == {"runner_pid": 100, "ssh_pid": None}


def test_find_tunnel_ignores_ssh_for_another_port():
    other = ["ssh.exe", "-R", "127.0.0.1:9999:127.0.0.1:9999", tunnel.PI_SSH]
    assert tunnel.find_tunnel([ssh(200, args=other)])["ssh_pid"] is None


@pytest.mark.parametrize("name", ["ssh.exe", "ssh", "SSH.EXE", "Ssh.Exe"])
def test_find_tunnel_name_is_case_insensitive(name):
    assert tunnel.find_tunnel([ssh(200, name=name)])["ssh_pid"] == 200


def test_find_tunnel_skips_none_cmdline():
    procs = [proc(5, "ssh.exe", None), proc(6, "pythonw.exe", None)]
    assert tunnel.find_tunnel(procs) == {"runner_pid": None, "ssh_pid": None}


def test_find_tunnel_nothing_running():
    assert tunnel.find_tunnel([]) == {"runner_pid": None, "ssh_pid": None}


# ---------------------------------------------------------------------------
# read_conns
# ---------------------------------------------------------------------------

def test_link_up_needs_ssh_pid_port_22_and_pi_ip():
    result = tunnel.read_conns([link_conn(200)], 200, PORT, PI_IP)
    assert result["link_up"] is True


def test_link_up_false_without_ssh_pid():
    assert tunnel.read_conns([link_conn(200)], None, PORT, PI_IP)["link_up"] is False


def test_link_up_false_for_other_pid():
    assert tunnel.read_conns([link_conn(300)], 200, PORT, PI_IP)["link_up"] is False


def test_link_up_false_for_other_port_or_ip_or_state():
    conns = [
        conn(200, "ESTABLISHED", ("192.168.1.50", 1), (PI_IP, 2222)),
        conn(200, "ESTABLISHED", ("192.168.1.50", 1), ("10.0.0.9", 22)),
        conn(200, "TIME_WAIT", ("192.168.1.50", 1), (PI_IP, 22)),
    ]
    assert tunnel.read_conns(conns, 200, PORT, PI_IP)["link_up"] is False


def test_pi_ports_only_from_ssh_pid_to_port():
    conns = [
        pi_conn(50123),
        pi_conn(50001),
        pi_conn(50999, pid=300),  # another program on 127.0.0.1:1235
        conn(200, "TIME_WAIT", ("127.0.0.1", 50555), ("127.0.0.1", PORT)),
        conn(200, "ESTABLISHED", ("127.0.0.1", 50777), ("10.0.0.5", PORT)),
        link_conn(200),
    ]
    assert tunnel.read_conns(conns, 200, PORT, PI_IP)["pi_ports"] == [50001, 50123]


def test_bionic_listening_on_listen_only():
    listen = conn(999, "LISTEN", ("127.0.0.1", PORT), None)
    assert tunnel.read_conns([listen], None, PORT, PI_IP)["bionic_listening"] is True

    other_port = conn(999, "LISTEN", ("127.0.0.1", 9999), None)
    assert tunnel.read_conns([other_port], None, PORT, PI_IP)["bionic_listening"] is False

    established = conn(999, "ESTABLISHED", ("127.0.0.1", PORT), ("127.0.0.1", 50000))
    assert tunnel.read_conns([established], None, PORT, PI_IP)["bionic_listening"] is False


def test_local_clients_counts_by_pid_and_excludes_ssh_and_none():
    conns = [
        pi_conn(50001, pid=200),  # the ssh pid itself: not a local client
        conn(300, "ESTABLISHED", ("127.0.0.1", 51000), ("127.0.0.1", PORT)),
        conn(300, "ESTABLISHED", ("127.0.0.1", 51001), ("127.0.0.1", PORT)),
        conn(400, "ESTABLISHED", ("127.0.0.1", 51002), ("127.0.0.1", PORT)),
        conn(None, "ESTABLISHED", ("127.0.0.1", 51003), ("127.0.0.1", PORT)),
    ]
    assert tunnel.read_conns(conns, 200, PORT, PI_IP)["local_clients"] == {300: 2, 400: 1}


def test_attribute_address_form_is_accepted():
    conns = [
        conn(200, "ESTABLISHED", addr("127.0.0.1", 50001), addr("127.0.0.1", PORT)),
        conn(200, "ESTABLISHED", addr("192.168.1.50", 55000), addr(PI_IP, 22)),
        conn(999, "LISTEN", addr("127.0.0.1", PORT), None),
    ]
    result = tunnel.read_conns(conns, 200, PORT, PI_IP)
    assert result["pi_ports"] == [50001]
    assert result["link_up"] is True
    assert result["bionic_listening"] is True


def test_empty_addresses_do_not_raise():
    conns = [conn(200, "LISTEN", (), ()), conn(200, "ESTABLISHED", None, None)]
    result = tunnel.read_conns(conns, 200, PORT, PI_IP)
    assert result["pi_ports"] == []
    assert result["link_up"] is False
    assert result["bionic_listening"] is False


# ---------------------------------------------------------------------------
# parse_pi_check
# ---------------------------------------------------------------------------

def test_parse_pi_check_good_output():
    assert tunnel.parse_pi_check("200 0.0126\n0\n") == {"http": 200, "ms": 13, "errors_5min": 0}


def test_parse_pi_check_partial_output():
    assert tunnel.parse_pi_check("503 1.5") == {"http": 503, "ms": 1500, "errors_5min": None}


def test_parse_pi_check_garbage_gives_none():
    assert tunnel.parse_pi_check("hello\nworld") == {"http": None, "ms": None, "errors_5min": None}


@pytest.mark.parametrize("text", ["", None])
def test_parse_pi_check_empty_gives_none(text):
    assert tunnel.parse_pi_check(text) == {"http": None, "ms": None, "errors_5min": None}


# ---------------------------------------------------------------------------
# overall
# ---------------------------------------------------------------------------

def snap(**changes):
    base = {"ssh_pid": 200, "link_up": True, "bionic_listening": True,
            "pi": {"http": 200, "errors_5min": 0}}
    base.update(changes)
    return base


def test_overall_no_ssh_is_down():
    assert tunnel.overall(snap(ssh_pid=None, link_up=False)) == ("down", "tunnel ไม่ได้รัน")


def test_overall_link_down_is_down():
    assert tunnel.overall(snap(link_up=False)) == ("down", "ssh ยังไม่ต่อถึง Pi")


def test_overall_bionic_not_listening_is_down():
    assert tunnel.overall(snap(bionic_listening=False)) == (
        "down", "Bionic ไม่ได้เปิด port 1235")


def test_overall_pi_http_not_200_is_degraded():
    assert tunnel.overall(snap(pi={"http": 503, "errors_5min": 0})) == (
        "degraded", "Pi เรียก Bionic ไม่ผ่าน")


def test_overall_pi_http_unknown_is_degraded():
    assert tunnel.overall(snap(pi={"http": None, "errors_5min": None}))[0] == "degraded"


def test_overall_pi_errors_is_degraded():
    assert tunnel.overall(snap(pi={"http": 200, "errors_5min": 3})) == (
        "degraded", "เทสบน Pi มี error 3 ครั้งใน 5 นาที")


def test_overall_no_pi_check_yet_is_ok():
    assert tunnel.overall(snap(pi=None)) == ("ok", "tunnel ทำงานปกติ")


def test_overall_healthy_is_ok():
    assert tunnel.overall(snap()) == ("ok", "tunnel ทำงานปกติ")


# ---------------------------------------------------------------------------
# TunnelStatus
# ---------------------------------------------------------------------------

class Fakes:
    """Mutable stand-ins for psutil and the clock. Tests change these between checks."""

    def __init__(self):
        self.procs = []
        self.conns = []
        self.now = 0.0
        self.calls = []
        self.run_result = None
        self.run_error = None

    def processes(self):
        return list(self.procs)

    def connections(self):
        return list(self.conns)

    def clock(self):
        return self.now

    def run(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.run_error is not None:
            raise self.run_error
        return self.run_result


@pytest.fixture
def fakes():
    f = Fakes()
    f.procs = [runner(), ssh(), proc(300, "chrome.exe", ["chrome.exe"])]
    return f


@pytest.fixture
def status(fakes, tmp_path):
    return tunnel.TunnelStatus(
        process_iter=fakes.processes,
        net_connections=fakes.connections,
        run=fakes.run,
        clock=fakes.clock,
        log_path=tmp_path / "missing.log",
    )


def test_snapshot_before_any_check(status):
    snapshot = status.snapshot()
    assert snapshot["pi"] is None
    assert snapshot["pi_seen_total"] == 0
    assert snapshot["state"] == "down"


def test_pi_seen_counts_new_ports_and_forgets_them_after_60s(fakes, status):
    fakes.conns = [pi_conn(50001)]
    fakes.now = 0
    status.check_local()
    assert status.snapshot()["pi_seen_60s"] == 1

    fakes.conns = []  # the request closes before the next poll
    fakes.now = 5
    status.check_local()

    fakes.conns = [pi_conn(50002)]
    fakes.now = 10
    status.check_local()
    snapshot = status.snapshot()
    assert snapshot["pi_seen_60s"] == 2
    assert snapshot["pi_seen_total"] == 2

    fakes.now = 61  # 50001 (seen at 0) is older than 60 s; 50002 (seen at 10) is not
    status.check_local()
    snapshot = status.snapshot()
    assert snapshot["pi_seen_60s"] == 1
    assert snapshot["pi_seen_total"] == 2

    fakes.now = 71
    status.check_local()
    snapshot = status.snapshot()
    assert snapshot["pi_seen_60s"] == 0
    assert snapshot["pi_seen_total"] == 2


def test_check_local_stores_tunnel_facts(fakes, status):
    fakes.procs.append(proc(301, "python.exe", ["python.exe", "tool.py"]))
    fakes.conns = [
        link_conn(200),
        conn(999, "LISTEN", ("127.0.0.1", PORT), None),
        pi_conn(50001),
        conn(301, "ESTABLISHED", ("127.0.0.1", 51000), ("127.0.0.1", PORT)),
    ]
    status.check_local()
    snapshot = status.snapshot()
    assert snapshot["runner_pid"] == 100
    assert snapshot["ssh_pid"] == 200
    assert snapshot["link_up"] is True
    assert snapshot["bionic_listening"] is True
    assert snapshot["pi_conns"] == 1
    assert snapshot["local_clients"] == [{"pid": 301, "name": "python.exe", "conns": 1}]
    assert snapshot["local_error"] is None
    assert snapshot["state"] == "ok"


def test_check_local_error_is_stored_not_raised(fakes, status):
    def broken():
        raise PermissionError("denied")

    status._net_connections = broken
    status.check_local()  # must not raise
    assert status.snapshot()["local_error"] == "PermissionError: denied"


def test_check_pi_stores_parsed_values(fakes, status):
    fakes.run_result = SimpleNamespace(stdout="200 0.0126\n2\n")
    fakes.now = 1000.7
    status.check_pi()

    cmd, kwargs = fakes.calls[0]
    assert cmd[0] == "ssh"
    assert "-i" in cmd and tunnel.PI_KEY in cmd
    assert tunnel.PI_SSH in cmd
    assert f"http://127.0.0.1:{PORT}/v1/models" in cmd[-1]
    assert "bkk-test" in cmd[-1]
    assert kwargs["timeout"] == 20
    assert kwargs["text"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL

    pi = status.snapshot()["pi"]
    assert pi == {"http": 200, "ms": 13, "errors_5min": 2, "checked_ts": 1000, "error": None}


def test_check_pi_timeout_is_stored_not_raised(fakes, status):
    fakes.run_error = subprocess.TimeoutExpired(cmd="ssh", timeout=20)
    status.check_pi()  # must not raise
    pi = status.snapshot()["pi"]
    assert pi["http"] is None
    assert pi["error"].startswith("TimeoutExpired:")


def test_snapshot_is_a_copy(fakes, status):
    fakes.conns = [pi_conn(50001)]
    status.check_local()
    first = status.snapshot()
    first["local_clients"].append({"pid": 1})
    first["log_tail"].append("x")
    assert status.snapshot()["local_clients"] == []
    assert status.snapshot()["log_tail"] == []


# ---------------------------------------------------------------------------
# tail_lines
# ---------------------------------------------------------------------------

def test_tail_lines_returns_last_non_empty_lines(tmp_path):
    path = tmp_path / "t.log"
    path.write_text("a\n\nb\nc\nd\n", encoding="utf-8")
    assert tunnel.tail_lines(path) == ["b", "c", "d"]
    assert tunnel.tail_lines(path, n=2) == ["c", "d"]


def test_tail_lines_missing_path(tmp_path):
    assert tunnel.tail_lines(tmp_path / "nope.log") == []


def test_tail_lines_reads_only_the_end_of_a_big_file(tmp_path):
    path = tmp_path / "big.log"
    path.write_text(("x" * 99 + "\n") * 300 + "END\n", encoding="utf-8")  # about 30 KB
    assert tunnel.tail_lines(path) == ["x" * 99, "x" * 99, "END"]


def test_tail_lines_handles_thai_text(tmp_path):
    path = tmp_path / "th.log"
    path.write_text("สวัสดี\n", encoding="utf-8")
    assert tunnel.tail_lines(path) == ["สวัสดี"]
