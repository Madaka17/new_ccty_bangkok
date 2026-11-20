"""launch/test/pi_bionic_tunnel.py: the ssh command for the Bionic reverse tunnel and the forward-failure check."""
import pytest

# The script runs on the Windows PC only (msvcrt file lock); CI runs on Linux
pytest.importorskip("msvcrt")

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "launch" / "test" / "pi_bionic_tunnel.py"
_spec = importlib.util.spec_from_file_location("pi_bionic_tunnel_under_test", _PATH)
tunnel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tunnel)


def test_ssh_command_is_the_reverse_tunnel_to_bionic():
    cmd = tunnel.ssh_command(r"C:\keys\bkkpi_ed25519", "test@192.168.1.109", 1235)
    assert cmd == [
        "ssh", "-i", r"C:\keys\bkkpi_ed25519", "-N",
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ConnectTimeout=15",
        "-R", "127.0.0.1:1235:127.0.0.1:1235",
        "test@192.168.1.109",
    ]


def test_ssh_command_uses_the_given_port_for_both_ends():
    cmd = tunnel.ssh_command("k", "u@h", 9999)
    assert cmd[cmd.index("-R") + 1] == "127.0.0.1:9999:127.0.0.1:9999"
    assert cmd[-1] == "u@h"


def test_forward_failure_is_detected_in_stderr():
    stderr = "Warning: remote port forwarding failed for listen port 1235\r\n"
    assert tunnel.is_forward_failure(stderr) is True


def test_other_ssh_errors_are_not_forward_failures():
    assert tunnel.is_forward_failure("Permission denied (publickey).") is False
    assert tunnel.is_forward_failure("") is False
    assert tunnel.is_forward_failure(None) is False


def test_cleanup_command_names_the_listener_with_sudo_and_kills_only_sshd():
    cmd = tunnel.cleanup_command(1235)
    assert 'sudo -n ss -ltnpH "sport = :1235"' in cmd
    assert "sshd|sshd-session) kill" in cmd
    assert "*) echo none" in cmd
