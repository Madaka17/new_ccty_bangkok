"""Tests for live.py: state building, Bionic status, HTTP routes, single instance and auto-exit.

    E:\\new_ccty_bangkok\\.venv\\Scripts\\python.exe -m unittest discover -s E:\\new_ccty_bangkok\\launch\\bionic_usage -p "test_*.py"

No real Bionic server is contacted: the Bionic fetch is passed in as a fake.
"""

import http.client
import json
import socket
import sqlite3
import tempfile
import threading
import time
import os
import unittest
import urllib.error
import urllib.request
from unittest import mock
from datetime import datetime
from pathlib import Path

import collect
import live

BANGKOK = collect.BANGKOK
# 2026-11-20 12:00:00 Bangkok, as Unix seconds.
NOW = int(datetime(2026, 11, 20, 12, 0, tzinfo=BANGKOK).timestamp())


def at(hours_before=0, minutes_before=0):
    """Unix seconds that are the given amount before NOW."""
    return NOW - hours_before * 3600 - minutes_before * 60


class DbTestBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "usage.db"
        collect.run(self.tmp / "no-logs", self.db)  # creates an empty schema
        self._line = 0

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, ts, model="m1", job="flood_cam", prompt=100, completion=50,
            reasoning=0, ms=800.0, ok=1):
        self._line += 1
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO requests(ts, model, job, endpoint, prompt_tokens, completion_tokens, "
            "reasoning_tokens, total_ms, ok, log_file, line_no) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (ts, model, job, "/v1/chat/completions", prompt, completion, reasoning, ms, ok,
             "f.log", self._line))
        con.commit()
        con.close()


class ReadDbTests(DbTestBase):

    def test_totals_cover_last_hour_today_and_all_time(self):
        self.add(at(minutes_before=10), prompt=100, completion=50)      # last hour, today
        self.add(at(hours_before=2), prompt=10, completion=5)           # today, not last hour
        self.add(at(hours_before=24 * 3), prompt=1000, completion=500)  # older, all time
        parts = live.read_db_parts(self.db, NOW)
        self.assertEqual(parts["totals"]["hour"]["calls"], 1)
        self.assertEqual(parts["totals"]["hour"]["tokens"], 150)
        self.assertEqual(parts["totals"]["today"]["calls"], 2)
        self.assertEqual(parts["totals"]["today"]["tokens"], 165)
        self.assertEqual(parts["totals"]["all"]["calls"], 3)
        self.assertEqual(parts["totals"]["all"]["tokens"], 1665)

    def test_today_starts_at_bangkok_midnight(self):
        self.add(at(hours_before=12) - 60, prompt=7, completion=0)  # 23:59 the day before
        self.add(at(hours_before=12) + 60, prompt=9, completion=0)  # 00:01 today
        parts = live.read_db_parts(self.db, NOW)
        self.assertEqual(parts["totals"]["today"]["calls"], 1)

    def test_errors_are_counted_in_totals(self):
        self.add(at(minutes_before=5), ok=0, prompt=0, completion=0)
        self.assertEqual(live.read_db_parts(self.db, NOW)["totals"]["hour"]["errors"], 1)

    def test_per_minute_has_sixty_buckets_ending_at_the_current_minute(self):
        self.add(at(minutes_before=0), prompt=5, completion=5)    # this minute
        self.add(at(minutes_before=59), prompt=3, completion=0)   # oldest bucket
        self.add(at(minutes_before=60), prompt=100, completion=0)  # outside the window
        per_minute = live.read_db_parts(self.db, NOW)["per_minute"]
        self.assertEqual(len(per_minute), 60)
        self.assertEqual(per_minute[-1], 10)
        self.assertEqual(per_minute[0], 3)
        self.assertEqual(sum(per_minute), 13)

    def test_recent_lists_last_fifty_newest_first(self):
        for i in range(55):
            self.add(at(minutes_before=55 - i), model=f"m{i}")
        recent = live.read_db_parts(self.db, NOW)["recent"]
        self.assertEqual(len(recent), 50)
        self.assertEqual(recent[0]["model"], "m54")
        self.assertEqual(recent[-1]["model"], "m5")
        self.assertTrue(recent[0]["ts"] > recent[-1]["ts"])

    def test_recent_row_carries_token_split_timing_and_ok_flag(self):
        self.add(at(minutes_before=1), job="flood_cam", prompt=749, completion=46,
                 reasoning=12, ms=856.14, ok=1)
        row = live.read_db_parts(self.db, NOW)["recent"][0]
        self.assertEqual(row["job"], "flood_cam")
        self.assertEqual((row["prompt"], row["completion"], row["reasoning"]), (749, 46, 12))
        self.assertAlmostEqual(row["total_ms"], 856.14)
        self.assertIs(row["ok"], True)

    def test_missing_database_gives_empty_parts_and_does_not_create_it(self):
        missing = self.tmp / "absent.db"
        parts = live.read_db_parts(missing, NOW)
        self.assertEqual(parts["recent"], [])
        self.assertEqual(parts["totals"]["all"]["calls"], 0)
        self.assertEqual(len(parts["per_minute"]), 60)
        self.assertFalse(missing.exists())

    def test_locked_or_broken_database_reports_an_error_without_raising(self):
        self.db.write_bytes(b"not a database at all, just text" * 100)
        parts = live.read_db_parts(self.db, NOW)
        self.assertIsNotNone(parts["db_error"])


class BionicStatusTests(unittest.TestCase):

    def test_loaded_models_are_the_ids_of_loaded_instances(self):
        body = json.dumps({"models": [
            {"key": "unsloth/qwen3.5-4b", "loaded_instances": [{"id": "unsloth/qwen3.5-4b"}]},
            {"key": "other/model", "loaded_instances": []},
        ]})
        self.assertEqual(live.parse_loaded_models(body), ["unsloth/qwen3.5-4b"])

    def test_bad_models_json_is_an_error(self):
        with self.assertRaises(ValueError):
            live.parse_loaded_models("<html>not json</html>")

    def test_status_is_up_with_models_when_bionic_answers(self):
        body = json.dumps({"models": [{"key": "m1", "loaded_instances": [{"id": "m1"}]}]})
        status = live.BionicStatus(fetch=lambda: body, clock=lambda: 100.0)
        status.check()
        self.assertEqual(status.snapshot(),
                         {"up": True, "loaded": ["m1"], "checked_ts": 100, "error": None})

    def test_status_is_down_when_bionic_does_not_answer(self):
        def fail():
            raise OSError("connection refused")
        status = live.BionicStatus(fetch=fail, clock=lambda: 100.0)
        status.check()
        snap = status.snapshot()
        self.assertFalse(snap["up"])
        self.assertEqual(snap["loaded"], [])
        self.assertIn("connection refused", snap["error"])

    def test_status_before_first_check_is_unknown(self):
        snap = live.BionicStatus(fetch=lambda: "", clock=lambda: 1.0).snapshot()
        self.assertIsNone(snap["up"])


class BuildStateTests(DbTestBase):

    def test_state_has_every_section_the_page_needs(self):
        self.add(at(minutes_before=1), job="flood_cam")
        tracker_snap = {"in_flight": [{"model": "m1", "job": "flood_cam", "started_ts": NOW - 5,
                                       "elapsed_s": 5, "phase": "prompt", "percent": 40.0}],
                        "newest_log_ts": NOW - 1}
        bionic = {"up": True, "loaded": ["m1"], "checked_ts": NOW, "error": None}
        state = live.build_state(self.db, tracker_snap, bionic, NOW)
        for key in ("now", "bionic", "in_flight", "recent", "totals", "per_minute",
                    "newest_log_ts", "db_error", "poll_ms"):
            self.assertIn(key, state)
        self.assertEqual(state["now"], NOW)
        self.assertEqual(state["in_flight"][0]["phase"], "prompt")
        self.assertEqual(state["newest_log_ts"], NOW - 1)
        self.assertEqual(len(state["recent"]), 1)

    def test_state_is_plain_json(self):
        self.add(at(minutes_before=1))
        state = live.build_state(self.db, {"in_flight": [], "newest_log_ts": None},
                                 {"up": None, "loaded": [], "checked_ts": None, "error": None}, NOW)
        json.dumps(state)  # must not raise


class IdleTests(unittest.TestCase):

    def test_idle_for_fifteen_minutes_expires(self):
        self.assertTrue(live.idle_expired(last_seen=NOW - 901, now=NOW))
        self.assertFalse(live.idle_expired(last_seen=NOW - 899, now=NOW))

    def test_custom_limit_is_respected(self):
        self.assertTrue(live.idle_expired(last_seen=0, now=11, limit=10))


class WatchIdleTests(unittest.TestCase):

    def test_server_is_shut_down_after_the_idle_limit(self):
        clock_value = [1000.0]
        app = live.App(db_path=Path("unused.db"), report_out=Path("unused.html"),
                       tracker=FakeTracker(), bionic=FakeBionic(), clock=lambda: clock_value[0])
        shut = []

        class FakeServer:
            def shutdown(self):
                shut.append(True)

        stop = threading.Event()
        clock_value[0] = 1000.0 + 901  # 15 minutes and a second with no state request
        live.watch_idle(app, FakeServer(), stop, limit=900, interval=0.01, log=lambda m: None)
        self.assertEqual(shut, [True])

    def test_server_stays_up_while_the_page_keeps_asking(self):
        clock_value = [1000.0]
        app = live.App(db_path=Path("unused.db"), report_out=Path("unused.html"),
                       tracker=FakeTracker(), bionic=FakeBionic(), clock=lambda: clock_value[0])
        shut = []

        class FakeServer:
            def shutdown(self):
                shut.append(True)

        stop = threading.Event()
        threading.Timer(0.05, stop.set).start()  # stop the loop after a few checks
        app.last_seen = clock_value[0]
        live.watch_idle(app, FakeServer(), stop, limit=900, interval=0.01, log=lambda m: None)
        self.assertEqual(shut, [])


class TickTests(unittest.TestCase):

    def test_each_job_runs_only_when_due_and_is_rescheduled(self):
        calls = []
        due = {"collect": 0.0, "bionic": 0.0}
        new_due = live.tick(10.0, due, {
            "collect": lambda: calls.append("collect"),
            "bionic": lambda: calls.append("bionic"),
        })
        self.assertEqual(sorted(calls), ["bionic", "collect"])
        self.assertEqual(new_due["collect"], 13.0)
        self.assertEqual(new_due["bionic"], 20.0)

    def test_job_not_yet_due_is_skipped(self):
        calls = []
        new_due = live.tick(1.0, {"collect": 3.0, "bionic": 0.0},
                            {"collect": lambda: calls.append("c"),
                             "bionic": lambda: calls.append("b")})
        self.assertEqual(calls, ["b"])
        self.assertEqual(new_due["collect"], 3.0)

    def test_a_failing_job_is_logged_and_does_not_stop_the_others(self):
        calls = []
        logged = []

        def boom():
            raise RuntimeError("db busy")
        new_due = live.tick(5.0, {"collect": 0.0, "bionic": 0.0},
                            {"collect": boom, "bionic": lambda: calls.append("b")},
                            log=logged.append)
        self.assertEqual(calls, ["b"])
        self.assertTrue(any("db busy" in m for m in logged))
        self.assertEqual(new_due["collect"], 8.0)  # still rescheduled


class PortAndPageTests(unittest.TestCase):

    def test_port_comes_from_env_with_default(self):
        self.assertEqual(live.port_from_env({}), 8199)
        self.assertEqual(live.port_from_env({"BIONIC_USAGE_PORT": "8300"}), 8300)
        self.assertEqual(live.port_from_env({"BIONIC_USAGE_PORT": "nope"}), 8199)

    def test_page_is_self_contained(self):
        html = live.PAGE_HTML
        self.assertIn("<!doctype html>", html.lower())
        self.assertNotIn("<script src", html.lower())
        self.assertNotIn("<link", html.lower())
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertIn("ตัวดูสดหยุดทำงาน", html)
        self.assertIn("กำลังตอบ", html)
        self.assertIn("/api/state", html)
        self.assertIn("/report", html)

    def test_log_error_appends_and_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "live.log"
            live.log_error(target, "poll failed")
            self.assertIn("poll failed", target.read_text(encoding="utf-8"))
        live.log_error(Path("Z:/no/such/dir/x/live.log"), "still fine")  # must not raise


class ServerTests(DbTestBase):

    def start(self, tracker_snap=None):
        app = live.App(db_path=self.db, report_out=self.tmp / "report.html",
                       tracker=FakeTracker(tracker_snap), bionic=FakeBionic(),
                       clock=lambda: NOW)
        server = live.make_server(app, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return app, server.server_address[1]

    def get(self, port, path):
        url = f"http://127.0.0.1:{port}{path}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()

    def test_root_serves_the_page(self):
        _, port = self.start()
        status, ctype, body = self.get(port, "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"<!doctype html>", body.lower())

    def test_api_state_returns_json_and_counts_as_a_visit(self):
        self.add(at(minutes_before=1))
        app, port = self.start({"in_flight": [], "newest_log_ts": NOW})
        app.last_seen = 0.0
        status, ctype, body = self.get(port, "/api/state")
        self.assertEqual(status, 200)
        self.assertIn("application/json", ctype)
        data = json.loads(body)
        self.assertEqual(data["now"], NOW)
        self.assertEqual(app.last_seen, NOW)

    def test_report_is_rebuilt_and_served(self):
        self.add(at(minutes_before=1), model="m-report-check")
        _, port = self.start()
        status, ctype, body = self.get(port, "/report")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"m-report-check", body)

    def test_unknown_path_is_404(self):
        _, port = self.start()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get(port, "/nope")
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()

    def test_server_does_not_allow_a_second_bind_to_the_same_port(self):
        self.assertFalse(live.LiveServer.allow_reuse_address)


class SingleInstanceTests(unittest.TestCase):

    def test_busy_port_opens_the_browser_and_exits_zero(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        self.addCleanup(sock.close)
        port = sock.getsockname()[1]
        opened = []
        code = live.main(["--port", str(port)], opener=opened.append, log=lambda m: None)
        self.assertEqual(code, 0)
        self.assertEqual(opened, [f"http://127.0.0.1:{port}/"])

    def test_no_open_flag_skips_the_browser_when_port_is_busy(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        self.addCleanup(sock.close)
        opened = []
        code = live.main(["--port", str(sock.getsockname()[1]), "--no-open"],
                         opener=opened.append, log=lambda m: None)
        self.assertEqual(code, 0)
        self.assertEqual(opened, [])


class HostCheckTests(unittest.TestCase):

    def test_only_loopback_names_with_the_port_are_allowed(self):
        self.assertTrue(live.host_allowed("127.0.0.1:8199", 8199))
        self.assertTrue(live.host_allowed("localhost:8199", 8199))
        self.assertFalse(live.host_allowed("evil.example:8199", 8199))
        self.assertFalse(live.host_allowed("127.0.0.1:9999", 8199))
        self.assertFalse(live.host_allowed("127.0.0.1", 8199))
        self.assertFalse(live.host_allowed(None, 8199))


class HostHeaderServerTests(DbTestBase):

    def test_foreign_host_header_gets_403_and_loopback_gets_the_page(self):
        app = live.App(db_path=self.db, report_out=self.tmp / "r.html",
                       tracker=FakeTracker(), bionic=FakeBionic(), clock=lambda: NOW)
        server = live.make_server(app, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/state", headers={"Host": "evil.example"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 403)
        resp.read()
        conn.close()

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/", headers={"Host": f"localhost:{port}"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        resp.read()
        conn.close()


class SafeWriteTests(unittest.TestCase):

    def test_tab_closed_mid_reply_is_not_an_error(self):
        class Gone:
            def write(self, data):
                raise ConnectionAbortedError("tab closed")
        self.assertFalse(live.write_body(Gone(), b"x"))

    def test_broken_pipe_is_not_an_error(self):
        class Gone:
            def write(self, data):
                raise BrokenPipeError("pipe")
        self.assertFalse(live.write_body(Gone(), b"x"))

    def test_normal_write_returns_true(self):
        class Ok:
            data = b""

            def write(self, chunk):
                self.data += chunk
        ok = Ok()
        self.assertTrue(live.write_body(ok, b"abc"))
        self.assertEqual(ok.data, b"abc")


class ReportLockTests(DbTestBase):

    def test_concurrent_report_requests_do_not_overlap(self):
        app = live.App(db_path=self.db, report_out=self.tmp / "r.html",
                       tracker=FakeTracker(), bionic=FakeBionic(), clock=lambda: NOW)
        real_write = live.report.write_report
        active = [0]
        peak = [0]
        guard = threading.Lock()

        def slow_write(db, out, now=None):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            real_write(db, out, now)
            with guard:
                active[0] -= 1

        with mock.patch.object(live.report, "write_report", side_effect=slow_write):
            threads = [threading.Thread(target=app.report_html) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        self.assertEqual(peak[0], 1)


class FakeTunnel:
    def __init__(self, snap=None):
        self._snap = snap
        self.local_calls = 0
        self.pi_calls = 0

    def check_local(self):
        self.local_calls += 1

    def check_pi(self):
        self.pi_calls += 1

    def snapshot(self):
        return self._snap


TUNNEL_SNAP = {
    "runner_pid": 10, "ssh_pid": 11, "link_up": True, "bionic_listening": True,
    "pi_conns": 1, "local_clients": [], "pi_seen_60s": 2, "pi_seen_total": 5,
    "pi": {"http": 200, "ms": 12.5, "errors_5min": 0, "checked_ts": NOW, "error": None},
    "log_tail": ["line"], "checked_ts": NOW, "local_error": None,
    "state": "ok", "reason_th": "tunnel ทำงานปกติ",
}


class TunnelPartTests(DbTestBase):

    def app(self, tunnel):
        return live.App(db_path=self.db, report_out=self.tmp / "r.html",
                        tracker=FakeTracker(), bionic=FakeBionic(), clock=lambda: NOW,
                        tunnel=tunnel)

    def test_app_state_includes_the_tunnel_part(self):
        state = self.app(FakeTunnel(TUNNEL_SNAP)).state()
        self.assertTrue(state["tunnel"]["available"])
        self.assertEqual(state["tunnel"]["state"], "ok")
        json.dumps(state)

    def test_no_tunnel_module_means_unavailable_but_state_still_works(self):
        state = self.app(None).state()
        self.assertFalse(state["tunnel"]["available"])
        self.assertIn("reason_th", state["tunnel"])
        self.assertIn("in_flight", state)

    def test_broken_tunnel_snapshot_does_not_break_the_state(self):
        class Broken:
            def snapshot(self):
                raise RuntimeError("boom")
        state = self.app(Broken()).state()
        self.assertFalse(state["tunnel"]["available"])
        self.assertIn("boom", state["tunnel"]["reason_th"])

    def test_build_state_takes_the_tunnel_snapshot(self):
        state = live.build_state(self.db, {"in_flight": [], "newest_log_ts": None},
                                 {"up": None, "loaded": [], "checked_ts": None, "error": None},
                                 NOW, tunnel_snap=TUNNEL_SNAP)
        self.assertEqual(state["tunnel"], TUNNEL_SNAP)


class TunnelWiringTests(unittest.TestCase):

    def test_tunnel_jobs_have_the_agreed_intervals(self):
        self.assertEqual(live.INTERVALS["tunnel_local"], 2.0)
        self.assertEqual(live.INTERVALS["tunnel_pi"], 30.0)

    def test_tick_runs_the_local_check_when_due(self):
        tunnel = FakeTunnel(TUNNEL_SNAP)
        new_due = live.tick(10.0, {"tunnel_local": 0.0}, {"tunnel_local": tunnel.check_local})
        self.assertEqual(tunnel.local_calls, 1)
        self.assertEqual(new_due["tunnel_local"], 12.0)

    def test_make_jobs_adds_tunnel_jobs_only_when_there_is_a_tunnel(self):
        bionic = FakeBionic()
        without = live.make_jobs(lambda: None, bionic, None, lambda m: None)
        self.assertEqual(sorted(without), ["bionic", "collect"])
        tunnel = FakeTunnel(TUNNEL_SNAP)
        with_tunnel = live.make_jobs(lambda: None, bionic, tunnel, lambda m: None)
        self.assertIn("tunnel_local", with_tunnel)
        self.assertIn("tunnel_pi", with_tunnel)
        with_tunnel["tunnel_local"]()
        self.assertEqual(tunnel.local_calls, 1)

    def test_load_tunnel_status_returns_none_when_import_fails(self):
        def factory():
            raise ImportError("No module named psutil")
        self.assertIsNone(live.load_tunnel_status(factory))

    def test_load_tunnel_status_returns_the_object(self):
        sentinel = object()
        self.assertIs(live.load_tunnel_status(lambda: sentinel), sentinel)


class StartOnceTests(unittest.TestCase):

    def wait_until(self, predicate):
        for _ in range(500):
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_second_call_is_skipped_while_the_first_still_runs(self):
        gate = threading.Event()
        calls = []

        def slow():
            calls.append(1)
            gate.wait(5)
        self.assertTrue(live.start_once(slow, "test-slow", log=lambda m: None))
        self.assertFalse(live.start_once(slow, "test-slow", log=lambda m: None))
        gate.set()
        self.assertTrue(self.wait_until(lambda: live.start_once(
            lambda: None, "test-slow", log=lambda m: None)))
        self.assertEqual(len(calls), 1)

    def test_a_failing_job_is_logged_and_does_not_escape(self):
        logged = []

        def boom():
            raise RuntimeError("ssh timeout")
        live.start_once(boom, "test-boom", log=logged.append)
        self.assertTrue(self.wait_until(lambda: logged))
        self.assertIn("ssh timeout", logged[0])


class PanelPageTests(unittest.TestCase):

    def test_page_has_the_tunnel_panel_with_plain_thai_labels(self):
        html = live.PAGE_HTML
        for text in ("ทางเชื่อม Pi → Bionic", "เว็บจริงบน Pi", "อย่างน้อย", "โปรแกรมบน PC"):
            self.assertIn(text, html)


class FakeTracker:
    def __init__(self, snap=None):
        self._snap = snap or {"in_flight": [], "newest_log_ts": None}

    def poll(self):
        pass

    def snapshot(self):
        return self._snap


class FakeBionic:
    def check(self):
        pass

    def snapshot(self):
        return {"up": True, "loaded": [], "checked_ts": NOW, "error": None}


if __name__ == "__main__":
    unittest.main()


class ServerIdReloadTests(unittest.TestCase):
    """An open page reloads itself when the server it polls was restarted."""

    def test_state_carries_server_id(self):
        import live
        self.assertTrue(live.SERVER_ID)
        self.assertIn(str(os.getpid()), live.SERVER_ID)

    def test_page_reloads_on_new_server_id(self):
        from live_page import PAGE_HTML
        self.assertIn("s.server_id !== serverId", PAGE_HTML)
        self.assertIn("location.reload()", PAGE_HTML)


class PerMinuteCallsTests(DbTestBase):

    def test_per_minute_calls_counts_requests_per_minute(self):
        self.add(at(minutes_before=0), prompt=5, completion=5)
        self.add(at(minutes_before=0), prompt=0, completion=0)
        self.add(at(minutes_before=59), prompt=3, completion=0)
        self.add(at(minutes_before=60), prompt=100, completion=0)  # outside the window
        parts = live.read_db_parts(self.db, NOW)
        self.assertEqual(len(parts["per_minute_calls"]), 60)
        self.assertEqual(parts["per_minute_calls"][-1], 2)
        self.assertEqual(parts["per_minute_calls"][0], 1)
        self.assertEqual(sum(parts["per_minute_calls"]), 3)

    def test_state_carries_per_minute_calls_with_the_same_minute_start(self):
        self.add(at(minutes_before=1))
        state = live.build_state(self.db, {"in_flight": [], "newest_log_ts": None},
                                 {"up": None, "loaded": [], "checked_ts": None, "error": None}, NOW)
        self.assertEqual(len(state["per_minute_calls"]), 60)
        self.assertEqual(sum(state["per_minute_calls"]), 1)
        self.assertEqual(state["minute_start"], NOW - 59 * 60)


class ChartWindowTests(unittest.TestCase):

    def test_window_is_eleven_full_buckets_before_the_current_one(self):
        # 12:00 Bangkok is on a five-minute mark; the window starts at 11:05.
        self.assertEqual(live.chart_window_start(NOW), NOW - 55 * 60)

    def test_window_start_snaps_down_to_a_five_minute_mark(self):
        self.assertEqual(live.chart_window_start(NOW + 150), NOW - 55 * 60)  # 12:02:30


class FiveMinuteBucketTests(DbTestBase):

    def test_twelve_buckets_count_calls_and_tokens_by_clock_aligned_start(self):
        self.add(at(minutes_before=55), prompt=10, completion=0)      # 11:05 -> bucket 0
        self.add(at(minutes_before=20), prompt=30, completion=20)     # 11:40 -> bucket 7
        self.add(at(minutes_before=0), prompt=1, completion=1)        # 12:00 -> bucket 11 (filling)
        self.add(at(minutes_before=0), prompt=2, completion=0)        # same bucket, second call
        parts = live.read_db_parts(self.db, NOW)
        self.assertEqual(parts["bucket_start"], NOW - 55 * 60)
        self.assertEqual(len(parts["bucket_calls"]), 12)
        self.assertEqual(parts["bucket_calls"][0], 1)
        self.assertEqual(parts["bucket_tokens"][0], 10)
        self.assertEqual(parts["bucket_calls"][7], 1)
        self.assertEqual(parts["bucket_tokens"][7], 50)
        self.assertEqual(parts["bucket_calls"][11], 2)
        self.assertEqual(parts["bucket_tokens"][11], 4)

    def test_a_request_just_before_the_window_is_not_in_any_bucket(self):
        self.add(at(minutes_before=55) - 1, prompt=999, completion=0)  # 11:04:59
        parts = live.read_db_parts(self.db, NOW)
        self.assertEqual(sum(parts["bucket_tokens"]), 0)
        self.assertEqual(sum(parts["per_minute_calls"]), 1)  # still in the 60-minute list

    def test_state_chart_gives_both_metrics_with_summary_fields(self):
        self.add(at(minutes_before=20), prompt=30, completion=20)
        state = live.build_state(self.db, {"in_flight": [], "newest_log_ts": None},
                                 {"up": None, "loaded": [], "checked_ts": None, "error": None}, NOW)
        chart = state["chart"]
        self.assertEqual(chart["bucket_minutes"], 5)
        self.assertEqual(chart["start"], NOW - 55 * 60)
        self.assertEqual(chart["count"], 12)
        self.assertEqual(chart["calls"]["values"][7], 1)
        self.assertEqual(chart["calls"]["total"], 1)
        self.assertEqual(chart["calls"]["peak"], 1)
        self.assertEqual(chart["calls"]["peak_index"], 7)
        self.assertEqual(chart["tokens"]["values"][7], 50)
        self.assertEqual(chart["tokens"]["total"], 50)
        json.dumps(state)


class NiceScaleTests(unittest.TestCase):

    def test_small_count_peak_gets_round_steps(self):
        self.assertEqual(live.nice_scale(61), (80, 20))

    def test_token_peak_gets_thousand_steps(self):
        self.assertEqual(live.nice_scale(45618), (60000, 20000))

    def test_round_peak_is_its_own_top(self):
        self.assertEqual(live.nice_scale(100), (100, 25))

    def test_axis_has_three_or_four_steps_above_zero(self):
        for peak in (7, 61, 157, 999, 45618, 745527):
            top, step = live.nice_scale(peak)
            self.assertGreaterEqual(top, peak)
            self.assertIn(round(top / step), (3, 4), msg=f"peak {peak}")

    def test_peak_of_one_gives_whole_steps(self):
        self.assertEqual(live.nice_scale(1), (1, 1))

    def test_zero_peak_gives_a_small_neutral_axis(self):
        self.assertEqual(live.nice_scale(0), (30, 10))


class ChartMetricTests(unittest.TestCase):

    def test_total_average_and_peak_of_a_metric(self):
        values = [40, 42, 61, 50, 40, 40, 42, 41, 42, 43, 42, 42]  # total 525
        metric = live.chart_metric(values)
        self.assertEqual(metric["values"], values)
        self.assertEqual(metric["total"], 525)
        self.assertEqual(metric["average"], 44)  # 525 / 12 = 43.75
        self.assertEqual(metric["peak"], 61)
        self.assertEqual(metric["peak_index"], 2)
        self.assertEqual((metric["axis_top"], metric["axis_step"]), (80, 20))

    def test_all_zero_metric_has_no_peak_index(self):
        metric = live.chart_metric([0] * 12)
        self.assertEqual(metric["total"], 0)
        self.assertEqual(metric["average"], 0)
        self.assertIsNone(metric["peak_index"])


class ChartPageTests(unittest.TestCase):

    def test_page_offers_calls_and_tokens_toggle_with_plain_thai(self):
        html = live.PAGE_HTML
        for text in ("ครั้ง", "token", "ตอนนี้", "เฉลี่ย", "ต่อ 5 นาที", "กำลังเก็บ"):
            self.assertIn(text, html)

    def test_page_remembers_the_chosen_metric_in_storage(self):
        html = live.PAGE_HTML
        self.assertIn("localStorage", html)
        self.assertIn("bionicChartMetric", html)

    def test_old_token_per_minute_heading_is_gone(self):
        self.assertNotIn("โทเคนต่อนาที", live.PAGE_HTML)
