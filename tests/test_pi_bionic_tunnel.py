"""launch/test/pi_bionic_tunnel.py: the ssh command for the Bionic reverse tunnel, the forward-failure check
and the model guard (keeps unsloth/qwen3.5-4b loaded with the right context and parallel slots)."""
import pytest

# The script runs on the Windows PC only (msvcrt file lock); CI runs on Linux
pytest.importorskip("msvcrt")

import importlib.util
import threading
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "launch" / "test" / "pi_bionic_tunnel.py"
_spec = importlib.util.spec_from_file_location("pi_bionic_tunnel_under_test", _PATH)
tunnel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tunnel)

KEY = "unsloth/qwen3.5-4b"


class StopLoop(BaseException):
    """Ends the endless loops (main, guard_forever) inside a test."""


@pytest.fixture(autouse=True)
def log_to_list(monkeypatch):
    """Keeps every test away from the real log file; returns the list of log lines."""
    lines = []
    monkeypatch.setattr(tunnel, "_log", lambda line: lines.append(line))
    return lines


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


# ---- model guard -------------------------------------------------------------------------------

def inst(instance_id, ctx=16384, par=1):
    """One loaded instance as GET /api/v1/models lists it."""
    return {"id": instance_id, "config": {"context_length": ctx, "parallel": par, "flash_attention": True}}


def listing(loaded=(), key=KEY):
    """A GET /api/v1/models answer: the model with the given loaded instances, plus one other model."""
    return {"models": [
        {"key": key, "loaded_instances": list(loaded)},
        {"key": "qwen3.5-9b", "loaded_instances": []},
    ]}


def make_post(fail_on=None, fail_times=None):
    """A fake Bionic POST: records (path, body, timeout). Raises for the path in fail_on, for the first
    fail_times calls to it when given, otherwise always."""
    calls = []
    fails_left = [fail_times]

    def post(path, body, timeout):
        calls.append((path, body, timeout))
        if path == fail_on:
            if fails_left[0] is None or fails_left[0] > 0:
                if fails_left[0] is not None:
                    fails_left[0] -= 1
                raise OSError("Bionic said no")
        return {}

    return post, calls


def test_plan_nothing_loaded_means_load():
    assert tunnel.plan_actions(listing(), KEY, 16384, 1) == [("load",)]


def test_plan_correct_instance_means_no_action():
    assert tunnel.plan_actions(listing([inst(KEY)]), KEY, 16384, 1) == []


def test_plan_wrong_context_unloads_then_loads():
    assert tunnel.plan_actions(listing([inst(KEY, ctx=123648)]), KEY, 16384, 1) == [
        ("unload", KEY), ("load",)]


def test_plan_wrong_parallel_unloads_then_loads():
    assert tunnel.plan_actions(listing([inst(KEY, par=4)]), KEY, 16384, 1) == [
        ("unload", KEY), ("load",)]


def test_plan_two_instances_one_correct_unloads_only_the_wrong_one():
    loaded = [inst(KEY, ctx=123648), inst(KEY + ":2")]
    assert tunnel.plan_actions(listing(loaded), KEY, 16384, 1) == [("unload", KEY)]


def test_plan_two_correct_instances_keeps_one_and_unloads_the_other():
    loaded = [inst(KEY), inst(KEY + ":2")]
    assert tunnel.plan_actions(listing(loaded), KEY, 16384, 1) == [("unload", KEY + ":2")]


def test_plan_model_absent_from_the_list_means_load():
    answer = {"models": [{"key": "other/x", "loaded_instances": []}]}
    assert tunnel.plan_actions(answer, KEY, 16384, 1) == [("load",)]


def test_plan_garbage_answer_raises_value_error():
    for garbage in ("<html>", None, {"nope": 1}, {"models": "x"}):
        with pytest.raises(ValueError):
            tunnel.plan_actions(garbage, KEY, 16384, 1)


def test_plan_empty_config_is_unknown_so_the_instance_is_left_alone():
    assert tunnel.plan_actions(listing([{"id": KEY, "config": {}}]), KEY, 16384, 1) == []


def test_plan_instance_without_a_config_block_is_left_alone():
    assert tunnel.plan_actions(listing([{"id": KEY}]), KEY, 16384, 1) == []


def test_plan_only_a_present_differing_value_makes_an_instance_wrong():
    only_ctx_wrong = listing([{"id": KEY, "config": {"context_length": 123648}}])
    assert tunnel.plan_actions(only_ctx_wrong, KEY, 16384, 1) == [("unload", KEY), ("load",)]
    only_par_right = listing([{"id": KEY, "config": {"parallel": 1}}])
    assert tunnel.plan_actions(only_par_right, KEY, 16384, 1) == []


def test_plan_two_unknown_instances_keeps_the_first_and_leaves_the_second():
    loaded = [{"id": KEY, "config": {}}, {"id": KEY + ":2", "config": {}}]
    assert tunnel.plan_actions(listing(loaded), KEY, 16384, 1) == []


def test_guard_empty_config_does_nothing_and_logs_nothing(log_to_list):
    post, calls = make_post()
    tunnel.guard_once(lambda: listing([{"id": KEY, "config": {}}]), post, {"retry_at": 0.0})
    assert calls == []
    assert log_to_list == []


def test_guard_nothing_loaded_loads_with_the_settings(log_to_list):
    post, calls = make_post()
    tunnel.guard_once(lambda: listing(), post, {"retry_at": 0.0})
    assert calls == [("/api/v1/models/load",
                      {"model": KEY, "context_length": 16384, "flash_attention": True, "parallel": 1},
                      180)]
    assert any("loaded" in line and "16384" in line for line in log_to_list)


def test_guard_correct_instance_does_nothing_and_logs_nothing(log_to_list):
    post, calls = make_post()
    tunnel.guard_once(lambda: listing([inst(KEY)]), post, {"retry_at": 0.0})
    assert calls == []
    assert log_to_list == []


def test_guard_wrong_context_unloads_then_loads_and_logs_old_and_new(log_to_list):
    post, calls = make_post()
    tunnel.guard_once(lambda: listing([inst(KEY, ctx=123648)]), post, {"retry_at": 0.0})
    assert [c[0] for c in calls] == ["/api/v1/models/unload", "/api/v1/models/load"]
    assert calls[0][1] == {"instance_id": KEY}
    assert calls[1][1]["context_length"] == 16384
    assert any("123648" in line and "16384" in line for line in log_to_list)


def test_guard_wrong_parallel_unloads_then_loads():
    post, calls = make_post()
    tunnel.guard_once(lambda: listing([inst(KEY, par=4)]), post, {"retry_at": 0.0})
    assert [c[0] for c in calls] == ["/api/v1/models/unload", "/api/v1/models/load"]
    assert calls[1][1]["parallel"] == 1


def test_guard_two_instances_one_correct_unloads_the_extra_only():
    post, calls = make_post()
    loaded = [inst(KEY), inst(KEY + ":2", ctx=123648)]
    tunnel.guard_once(lambda: listing(loaded), post, {"retry_at": 0.0})
    assert calls == [("/api/v1/models/unload", {"instance_id": KEY + ":2"}, 60)]


def test_guard_model_absent_from_the_list_loads():
    post, calls = make_post()
    answer = {"models": [{"key": "other/x", "loaded_instances": []}]}
    tunnel.guard_once(lambda: answer, post, {"retry_at": 0.0})
    assert [c[0] for c in calls] == ["/api/v1/models/load"]


def test_guard_garbage_answer_does_no_action_logs_and_does_not_raise(log_to_list):
    post, calls = make_post()
    tunnel.guard_once(lambda: "<html>Bionic is busy</html>", post, {"retry_at": 0.0})
    assert calls == []
    assert len(log_to_list) == 1 and "could not read Bionic models" in log_to_list[0]


def test_guard_http_error_does_no_action_logs_and_returns_the_normal_60_second_wait(log_to_list):
    def fetch():
        raise OSError("HTTP Error 500")

    post, calls = make_post()
    state = {"retry_at": 0.0}
    wait = tunnel.guard_once(fetch, post, state)
    assert calls == []
    assert wait == 60
    assert state["retry_at"] == 0.0            # a failed read does not back off
    assert len(log_to_list) == 1 and "HTTP Error 500" in log_to_list[0]


def test_failed_unload_stops_before_the_load_and_backs_off_300_seconds():
    now = [1000.0]
    state = {"retry_at": 0.0}
    post, calls = make_post(fail_on="/api/v1/models/unload")
    wait = tunnel.guard_once(lambda: listing([inst(KEY, ctx=123648)]), post, state, clock=lambda: now[0])
    assert [c[0] for c in calls] == ["/api/v1/models/unload"]
    assert state["retry_at"] == 1300.0
    assert wait == 300


def test_failed_load_is_retried_every_15_seconds_then_backs_off_300_after_the_third_failure(log_to_list):
    now = [1000.0]
    state = {"retry_at": 0.0}
    post, calls = make_post(fail_on="/api/v1/models/load")

    assert tunnel.guard_once(lambda: listing(), post, state, clock=lambda: now[0]) == 15
    assert state["retry_at"] == 1015.0
    now[0] = 1015.0
    assert tunnel.guard_once(lambda: listing(), post, state, clock=lambda: now[0]) == 15
    assert state["retry_at"] == 1030.0
    now[0] = 1030.0
    assert tunnel.guard_once(lambda: listing(), post, state, clock=lambda: now[0]) == 300
    assert len(calls) == 3
    assert state["retry_at"] == 1330.0
    assert any("3 times" in line and "300 s" in line for line in log_to_list)

    now[0] = 1329.0
    tunnel.guard_once(lambda: listing(), post, state, clock=lambda: now[0])
    assert len(calls) == 3                  # still backing off after the third failure


def test_unload_ok_then_load_fails_twice_then_succeeds_within_the_quick_retries():
    now = [1000.0]
    state = {"retry_at": 0.0}
    post, calls = make_post(fail_on="/api/v1/models/load", fail_times=2)

    tunnel.guard_once(lambda: listing([inst(KEY, ctx=123648)]), post, state, clock=lambda: now[0])
    assert [c[0] for c in calls] == ["/api/v1/models/unload", "/api/v1/models/load"]
    assert state["retry_at"] == 1015.0

    now[0] = 1015.0                          # the model is now unloaded, so the next check plans a load
    tunnel.guard_once(lambda: listing(), post, state, clock=lambda: now[0])
    assert [c[0] for c in calls].count("/api/v1/models/load") == 2
    assert state["retry_at"] == 1030.0

    now[0] = 1030.0
    tunnel.guard_once(lambda: listing(), post, state, clock=lambda: now[0])
    assert [c[0] for c in calls].count("/api/v1/models/load") == 3   # third try succeeds
    assert state["load_fails"] == 0
    assert calls[-1][0] == "/api/v1/models/load"


def test_guard_forever_retries_a_failed_load_on_the_15_second_and_300_second_schedule(monkeypatch):
    now = [0.0]
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds
        if len(sleeps) == 3:
            raise StopLoop

    monkeypatch.setattr(tunnel, "bionic_up", lambda: True)
    monkeypatch.setattr(tunnel.time, "sleep", fake_sleep)
    post, calls = make_post(fail_on="/api/v1/models/load")
    with pytest.raises(StopLoop):
        tunnel.guard_forever(lambda: listing(), post, clock=lambda: now[0])
    assert sleeps == [15, 15, 300]
    assert len(calls) == 3


def test_guard_forever_checks_only_while_bionic_is_up_every_60_seconds(monkeypatch):
    ups = iter([False, True])
    monkeypatch.setattr(tunnel, "bionic_up", lambda: next(ups))
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(tunnel.time, "sleep", fake_sleep)
    fetched = []

    def fetch():
        fetched.append(1)
        return listing([inst(KEY)])

    post, _ = make_post()
    with pytest.raises(StopLoop):
        tunnel.guard_forever(fetch, post)
    assert fetched == [1]           # the first pass saw Bionic down, so no fetch
    assert sleeps == [60, 60]


def test_guard_forever_survives_an_exception_and_keeps_going(monkeypatch, log_to_list):
    monkeypatch.setattr(tunnel, "bionic_up", lambda: True)
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    monkeypatch.setattr(tunnel.time, "sleep", fake_sleep)

    def fetch():
        raise RuntimeError("boom")

    post, _ = make_post()
    with pytest.raises(StopLoop):
        tunnel.guard_forever(fetch, post)
    assert sleeps == [60, 60]


def test_a_failing_log_cannot_turn_a_successful_unload_into_a_backoff(monkeypatch):
    def broken_log(line):
        raise OSError("disk full")

    monkeypatch.setattr(tunnel, "_log", broken_log)
    state = {"retry_at": 0.0}
    post, calls = make_post()
    wait = tunnel.guard_once(lambda: listing([inst(KEY, ctx=123648)]), post, state, clock=lambda: 1000.0)
    assert [c[0] for c in calls] == ["/api/v1/models/unload", "/api/v1/models/load"]
    assert state["retry_at"] == 0.0
    assert wait == 60


def test_safe_log_swallows_every_exception(monkeypatch):
    def broken_log(line):
        raise RuntimeError("anything")

    monkeypatch.setattr(tunnel, "_log", broken_log)
    tunnel._safe_log("hello")          # must not raise


def test_log_writes_under_a_lock(tmp_path, monkeypatch):
    mod = load_tunnel_with_env(monkeypatch)
    entered = []

    class Lock:
        def __enter__(self):
            entered.append(1)

        def __exit__(self, *exc):
            return False

    mod._LOG_LOCK = Lock()
    mod.LOG_DIR = str(tmp_path)
    mod.LOG_FILE = str(tmp_path / "t.log")
    mod._log("hi")
    assert entered == [1]
    assert "hi" in (tmp_path / "t.log").read_text(encoding="utf-8")


def test_http_models_gets_the_list_with_a_5_second_timeout(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"models": []}'

    def fake_urlopen(req, timeout=None):
        seen["url"] = req if isinstance(req, str) else req.full_url
        seen["method"] = "GET" if isinstance(req, str) else req.get_method()
        seen["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.http_models() == {"models": []}
    assert seen == {"url": "http://127.0.0.1:1235/api/v1/models", "method": "GET", "timeout": 5}


def test_http_post_sends_json_with_the_given_timeout(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b""

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["body"] = req.data
        seen["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(tunnel.urllib.request, "urlopen", fake_urlopen)
    assert tunnel.http_post("/api/v1/models/unload", {"instance_id": KEY}, 60) is None
    assert seen == {"url": "http://127.0.0.1:1235/api/v1/models/unload", "method": "POST",
                    "body": b'{"instance_id": "unsloth/qwen3.5-4b"}', "timeout": 60}


def load_tunnel_with_env(monkeypatch, **env):
    """A fresh copy of the script, read with the given environment variables set."""
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("pi_bionic_tunnel_env_test", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main_with_fake_thread(monkeypatch, mod, argv, lines=None):
    """Runs main() with the lock and Bionic faked; returns the targets of the threads it started."""
    started = []

    class FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            started.append({"target": target, "daemon": daemon})

        def start(self):
            pass

    monkeypatch.setattr(mod.threading, "Thread", FakeThread)
    monkeypatch.setattr(mod, "_log", (lambda line: lines.append(line)) if lines is not None else (lambda line: None))
    monkeypatch.setattr(mod, "take_lock", lambda: 7)
    monkeypatch.setattr(mod, "bionic_up", lambda: False)

    def fake_sleep(seconds):
        raise StopLoop

    monkeypatch.setattr(mod.time, "sleep", fake_sleep)
    try:
        mod.main(argv)
    except StopLoop:
        pass
    return started


def test_guard_on_starts_one_daemon_thread_running_the_guard(monkeypatch):
    mod = load_tunnel_with_env(monkeypatch, BIONIC_GUARD="1")
    started = _run_main_with_fake_thread(monkeypatch, mod, [])
    assert len(started) == 1
    assert started[0]["target"] is mod.guard_forever
    assert started[0]["daemon"] is True


def test_guard_0_does_not_start_the_thread(monkeypatch):
    mod = load_tunnel_with_env(monkeypatch, BIONIC_GUARD="0")
    started = _run_main_with_fake_thread(monkeypatch, mod, [])
    assert started == []


def test_once_does_not_start_the_guard_thread(monkeypatch):
    mod = load_tunnel_with_env(monkeypatch, BIONIC_GUARD="1")
    started = _run_main_with_fake_thread(monkeypatch, mod, ["--once"])
    assert started == []


def test_guard_settings_come_from_the_environment(monkeypatch):
    mod = load_tunnel_with_env(monkeypatch, BIONIC_MODEL="other/m", BIONIC_CONTEXT="8192",
                               BIONIC_PARALLEL="2")
    assert (mod.GUARD_MODEL, mod.GUARD_CONTEXT, mod.GUARD_PARALLEL) == ("other/m", 8192, 2)
    assert (tunnel.GUARD_MODEL, tunnel.GUARD_CONTEXT, tunnel.GUARD_PARALLEL) == (KEY, 16384, 1)


def test_bad_context_or_parallel_falls_back_to_the_default_and_is_reported_once(monkeypatch):
    mod = load_tunnel_with_env(monkeypatch, BIONIC_CONTEXT="16k", BIONIC_PARALLEL="")
    assert (mod.GUARD_CONTEXT, mod.GUARD_PARALLEL) == (16384, 1)
    assert len(mod.CONFIG_WARNINGS) == 2
    lines = []
    _run_main_with_fake_thread(monkeypatch, mod, [], lines=lines)
    assert sum("BIONIC_CONTEXT" in line for line in lines) == 1
    assert sum("BIONIC_PARALLEL" in line for line in lines) == 1
