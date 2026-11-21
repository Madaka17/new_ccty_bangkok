"""Tests for live_tail.py: the in-flight tracker that reads the newest Bionic log.

    E:\\new_ccty_bangkok\\.venv\\Scripts\\python.exe -m unittest discover -s E:\\new_ccty_bangkok\\launch\\bionic_usage -p "test_*.py"

Each test writes small fake log files into a temporary folder and polls the
tracker with a fake clock, so no real Bionic log is needed.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import live_tail
from test_collect import FLOOD_SYSTEM, error_line, prediction_block, request_block, running_line


def progress_line(model, percent, ts="2026-11-20 21:43:54"):
    return f"[{ts}][INFO][{model}] Prompt processing progress: {percent}%\n"


def load_line(model="m1", ts="2026-11-20 21:40:48"):
    """A model load call: a JSON body with a 'model' key that is not an inference request."""
    return (f"[{ts}][DEBUG] Received request: POST to /api/v1/models/load with body {{\n"
            f"  \"model\": \"{model}\"\n}}\n")


class TrackerTestBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "server-logs"
        (self.root / "2026-11").mkdir(parents=True)
        # Fake wall clock, set to the time of the logged requests (21:43:52 Bangkok).
        self.now = float(live_tail.collect._stamp_to_unix("[2026-11-20 21:43:52]"))
        self.tracker = live_tail.LiveTracker(self.root, clock=lambda: self.now)

    def tearDown(self):
        self._tmp.cleanup()

    def log_path(self, name="2026-11-20.1.log"):
        return self.root / "2026-11" / name

    def write(self, text, name="2026-11-20.1.log", mode="w"):
        with open(self.log_path(name), mode, encoding="utf-8", newline="\n") as f:
            f.write(text)

    def flights(self):
        return self.tracker.snapshot()["in_flight"]


class InFlightTests(TrackerTestBase):

    def test_request_is_in_flight_until_its_prediction_arrives(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:52"))
        self.tracker.poll()
        flights = self.flights()
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0]["model"], "m1")
        self.assertEqual(flights[0]["job"], "flood_cam")
        self.assertEqual(flights[0]["phase"], "waiting")
        self.assertIsNone(flights[0]["percent"])

        self.write(prediction_block("m1", ts="2026-11-20 21:43:53"), mode="a")
        self.tracker.poll()
        self.assertEqual(self.flights(), [])

    def test_error_line_finishes_the_request(self):
        self.write(request_block("m1", FLOOD_SYSTEM) + error_line("m1"))
        self.tracker.poll()
        self.assertEqual(self.flights(), [])

    def test_started_time_and_elapsed_seconds_use_the_log_clock(self):
        # 21:43:52 Bangkok time is 14:43:52 UTC.
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:52"))
        self.tracker.poll()
        self.now += 42.0
        flight = self.flights()[0]
        self.assertEqual(flight["started_ts"],
                         live_tail.collect._stamp_to_unix("[2026-11-20 21:43:52]"))
        self.assertEqual(flight["elapsed_s"], 42)

    def test_load_and_unload_calls_are_not_tracked(self):
        self.write(load_line() + "[2026-11-20 21:40:50][DEBUG] Received request: POST to "
                                 "/api/v1/models/unload with body {\n  \"model\": \"m1\"\n}\n")
        self.tracker.poll()
        self.assertEqual(self.flights(), [])

    def test_same_model_requests_finish_first_in_first_out(self):
        self.write(request_block("m1", "FIRST", ts="2026-11-20 21:43:40")
                   + request_block("m1", "SECOND", ts="2026-11-20 21:43:41")
                   + prediction_block("m1", ts="2026-11-20 21:43:42"))
        self.tracker.poll()
        flights = self.flights()
        self.assertEqual(len(flights), 1)
        self.assertEqual(flights[0]["job"], "SECOND"[:60])

    def test_other_models_do_not_finish_each_other(self):
        self.write(request_block("m1", FLOOD_SYSTEM) + request_block("m2", FLOOD_SYSTEM)
                   + prediction_block("m2", ts="2026-11-20 21:43:55"))
        self.tracker.poll()
        self.assertEqual([f["model"] for f in self.flights()], ["m1"])

    def test_answer_for_the_loaded_model_finishes_a_request_asked_for_another_model(self):
        # Bionic answers a request for an unloaded model with the loaded one.
        self.write(request_block("unsloth/qwen3.8-27b-nvfp4", FLOOD_SYSTEM, ts="2026-11-20 21:43:52")
                   + prediction_block("unsloth/qwen3.5-4b", ts="2026-11-20 21:43:55"))
        self.tracker.poll()
        self.assertEqual(self.flights(), [])

    def test_error_for_a_model_not_asked_for_finishes_the_oldest_request(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:40")
                   + request_block("m2", FLOOD_SYSTEM, ts="2026-11-20 21:43:41")
                   + error_line("m3", ts="2026-11-20 21:43:42"))
        self.tracker.poll()
        self.assertEqual([f["model"] for f in self.flights()], ["m2"])

    def test_answer_for_own_model_still_finishes_its_own_request_first(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:40")
                   + request_block("m2", FLOOD_SYSTEM, ts="2026-11-20 21:43:41")
                   + prediction_block("m2", ts="2026-11-20 21:43:42"))
        self.tracker.poll()
        self.assertEqual([f["model"] for f in self.flights()], ["m1"])

    def test_stale_request_older_than_an_hour_is_dropped(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:52"))
        self.tracker.poll()
        self.now += 3601
        self.assertEqual(self.flights(), [])


class ProgressTests(TrackerTestBase):

    def test_progress_below_hundred_is_prompt_phase_with_percent(self):
        self.write(request_block("m1", FLOOD_SYSTEM) + progress_line("m1", "28.6"))
        self.tracker.poll()
        flight = self.flights()[0]
        self.assertEqual(flight["phase"], "prompt")
        self.assertAlmostEqual(flight["percent"], 28.6)

    def test_hundred_percent_means_the_model_is_answering(self):
        self.write(request_block("m1", FLOOD_SYSTEM) + progress_line("m1", "100.0"))
        self.tracker.poll()
        flight = self.flights()[0]
        self.assertEqual(flight["phase"], "answering")
        self.assertAlmostEqual(flight["percent"], 100.0)

    def test_progress_is_attributed_to_the_head_of_that_models_queue(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:40")
                   + request_block("m2", FLOOD_SYSTEM, ts="2026-11-20 21:43:41")
                   + progress_line("m2", "50.0", ts="2026-11-20 21:43:42"))
        self.tracker.poll()
        by_model = {f["model"]: f for f in self.flights()}
        self.assertEqual(by_model["m2"]["phase"], "prompt")
        self.assertEqual(by_model["m1"]["phase"], "waiting")

    def test_new_request_after_a_finished_one_starts_without_old_progress(self):
        self.write(request_block("m1", FLOOD_SYSTEM) + progress_line("m1", "100.0")
                   + prediction_block("m1", ts="2026-11-20 21:43:57")
                   + request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:44:00"))
        self.tracker.poll()
        flight = self.flights()[0]
        self.assertEqual(flight["phase"], "waiting")


class ReadingTests(TrackerTestBase):

    def test_block_split_across_two_polls_is_seen_once_complete(self):
        full = request_block("m1", FLOOD_SYSTEM)
        cut = full.rindex("\n}\n")
        self.write(full[:cut])
        self.tracker.poll()
        self.assertEqual(self.flights(), [])
        self.write(full[cut:], mode="a")
        self.tracker.poll()
        self.assertEqual(len(self.flights()), 1)

    def test_bytes_already_read_are_not_read_again(self):
        # Re-reading the same request would queue it twice.
        self.write(request_block("m1", FLOOD_SYSTEM))
        self.tracker.poll()
        self.tracker.poll()
        self.tracker.poll()
        self.assertEqual(len(self.flights()), 1)

    def test_reads_are_bounded_and_catch_up_over_several_polls(self):
        self.write(request_block("m1", FLOOD_SYSTEM))
        tracker = live_tail.LiveTracker(self.root, clock=lambda: self.now,
                                        tail_bytes=10_000_000, max_read=64)
        tracker.poll()
        # 64 bytes cannot hold the whole request block, so it is not known yet.
        self.assertEqual(tracker.snapshot()["in_flight"], [])
        for _ in range(200):
            tracker.poll()
            if tracker.snapshot()["in_flight"]:
                break
        self.assertEqual(len(tracker.snapshot()["in_flight"]), 1)

    def test_start_reads_only_the_tail_of_a_big_file(self):
        old = request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 08:00:00")
        padding = "[2026-11-20 08:00:01][INFO] padding\n" * 300
        self.write(old + padding)
        tracker = live_tail.LiveTracker(self.root, clock=lambda: self.now, tail_bytes=200)
        tracker.poll()
        # The old request sits before the tail window, so it is not reported.
        self.assertEqual(tracker.snapshot()["in_flight"], [])

    def test_follows_the_newest_file_when_a_new_day_starts(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 23:00:00"),
                   name="2026-11-20.1.log")
        self.tracker.poll()
        self.assertEqual(len(self.flights()), 1)
        self.write(request_block("m2", FLOOD_SYSTEM, ts="2026-11-21 00:00:05"),
                   name="2026-11-21.1.log")
        self.tracker.poll()
        self.assertEqual([f["model"] for f in self.flights()], ["m1", "m2"])

    def test_unanswered_request_is_answered_in_the_next_day_file(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:50"),
                   name="2026-11-20.1.log")
        self.tracker.poll()
        self.write(request_block("m2", FLOOD_SYSTEM, ts="2026-11-21 00:00:05"),
                   name="2026-11-21.1.log")
        self.tracker.poll()
        self.write(prediction_block("m1", ts="2026-11-21 00:00:09"),
                   name="2026-11-21.1.log", mode="a")
        self.tracker.poll()
        self.assertEqual([f["model"] for f in self.flights()], ["m2"])

    def test_rotation_10_is_newer_than_rotation_9(self):
        # .9 is read first. When .10 appears it must become the newest file, so the
        # tracker switches to it and the prediction in .10 finishes the m-new request.
        self.write(request_block("m-old", FLOOD_SYSTEM, ts="2026-11-20 21:43:40"),
                   name="2026-11-20.9.log")
        self.tracker.poll()
        self.write(request_block("m-new", FLOOD_SYSTEM, ts="2026-11-20 21:43:41")
                   + prediction_block("m-new", ts="2026-11-20 21:43:45"),
                   name="2026-11-20.10.log")
        self.tracker.poll()
        self.assertEqual([f["model"] for f in self.flights()], ["m-old"])

    def test_overlong_partial_line_is_dropped_and_logged_once(self):
        logged = []
        tracker = live_tail.LiveTracker(self.root, clock=lambda: self.now,
                                        max_carry=50, log=logged.append)
        self.write("[2026-11-20 21:43:50][INFO] " + "x" * 200)  # no newline yet
        tracker.poll()
        self.write("y" * 200, mode="a")  # still no newline: must stay dropped
        tracker.poll()
        self.assertEqual(len(logged), 1)
        self.assertIn("dropped", logged[0])
        # The line ends, and the next request is read normally.
        self.write("\n" + request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:55"), mode="a")
        tracker.poll()
        self.assertEqual([f["model"] for f in tracker.snapshot()["in_flight"]], ["m1"])

    def test_truncated_file_is_read_again_from_the_start(self):
        self.write(request_block("m1", FLOOD_SYSTEM) + ("filler line\n" * 40))
        self.tracker.poll()
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 22:00:00"))
        self.tracker.poll()
        self.assertEqual(len(self.flights()), 1)

    def test_missing_log_folder_gives_no_flights(self):
        tracker = live_tail.LiveTracker(Path(self._tmp.name) / "nope", clock=lambda: self.now)
        tracker.poll()
        self.assertEqual(tracker.snapshot(), {"in_flight": [], "newest_log_ts": None})

    def test_newest_log_time_is_the_last_stamp_read(self):
        self.write(request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:43:52")
                   + running_line("m1", ts="2026-11-20 21:43:59"))
        self.tracker.poll()
        self.assertEqual(self.tracker.snapshot()["newest_log_ts"],
                         live_tail.collect._stamp_to_unix("[2026-11-20 21:43:59]"))


if __name__ == "__main__":
    unittest.main()
