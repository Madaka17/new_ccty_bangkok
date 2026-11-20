"""Tests for collect.py. Run with the repo venv:

    E:\\new_ccty_bangkok\\.venv\\Scripts\\python.exe -m unittest discover -s E:\\new_ccty_bangkok\\launch\\bionic_usage -p "test_*.py"

Each test builds small fake Bionic log files in a temporary folder, runs the
collector against a temporary SQLite database and checks the rows it wrote.
"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import collect

FLOOD_SYSTEM = (
    "You are the flood-watch agent of the Bangkok traff... <Truncated in logs> "
    "...ture, copied exactly; empty when there is none>\"}."
)


def request_block(model, system="FLOOD", ts="2026-11-20 21:43:52",
                  endpoint="/v1/chat/completions"):
    """Return the log text of one 'Received request' block with a JSON body."""
    messages = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": "One camera."})
    body = json.dumps({"model": model, "temperature": 0.1, "messages": messages},
                      indent=2, ensure_ascii=False)
    body_lines = body.split("\n")
    assert body_lines[0] == "{"
    header = f"[{ts}][DEBUG] Received request: POST to {endpoint} with body {{"
    return "\n".join([header] + body_lines[1:]) + "\n"


def running_line(model, ts="2026-11-20 21:43:52"):
    return f"[{ts}][INFO][{model}] Running chat completion on conversation with 2 messages.\n"


def total_time_line(ms, tokens=798):
    return (f"0.11.975.173 I slot print_timing: id  0 | task 0 |       total time = "
            f"{ms:.2f} ms /   {tokens} tokens\n")


def prediction_block(model, prompt=749, completion=46, reasoning=0,
                     ts="2026-11-20 21:43:53", with_usage=True):
    """Return the log text of one 'Generated prediction' block."""
    obj = {"id": "chatcmpl-test", "object": "chat.completion", "model": model,
           "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop"}]}
    if with_usage:
        obj["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion,
                        "total_tokens": prompt + completion,
                        "completion_tokens_details": {"reasoning_tokens": reasoning}}
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    body_lines = body.split("\n")
    assert body_lines[0] == "{"
    header = f"[{ts}][INFO][{model}] Generated prediction: {{"
    return "\n".join([header] + body_lines[1:]) + "\n"


def error_line(model, ts="2026-11-20 21:44:10"):
    return f"[{ts}][ERROR][{model}] Model crashed while generating.\n"


class CollectTestBase(unittest.TestCase):
    """Creates a temporary log folder and database for each test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "server-logs"
        (self.root / "2026-11").mkdir(parents=True)
        self.db = Path(self._tmp.name) / "out" / "usage.db"

    def tearDown(self):
        self._tmp.cleanup()

    def write_log(self, name, text, mode="w"):
        path = self.root / "2026-11" / name
        with open(path, mode, encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def run_collect(self):
        return collect.run(self.root, self.db)

    def rows(self, sql="SELECT model, job, endpoint, prompt_tokens, completion_tokens, "
                       "reasoning_tokens, total_ms, ok, ts, line_no FROM requests ORDER BY id"):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()


class ExchangeParsingTests(CollectTestBase):

    def test_one_exchange_becomes_one_row_with_all_fields(self):
        log_text = (request_block("unsloth/qwen3.5-4b", FLOOD_SYSTEM)
                    + running_line("unsloth/qwen3.5-4b")
                    + total_time_line(856.14)
                    + prediction_block("unsloth/qwen3.5-4b", 749, 46, 0))
        path = self.write_log("2026-11-20.1.log", log_text)

        result = self.run_collect()

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.new_rows, 1)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        model, job, endpoint, prompt, completion, reasoning, total_ms, ok, ts, line_no = rows[0]
        self.assertEqual(model, "unsloth/qwen3.5-4b")
        self.assertEqual(job, "flood_cam")
        self.assertEqual(endpoint, "/v1/chat/completions")
        self.assertEqual((prompt, completion, reasoning), (749, 46, 0))
        self.assertAlmostEqual(total_ms, 856.14)
        self.assertEqual(ok, 1)
        # 21:43:52 in Asia/Bangkok (UTC+7, no DST) is 14:43:52 UTC.
        self.assertEqual(ts, int(datetime(2026, 11, 20, 14, 43, 52, tzinfo=timezone.utc).timestamp()))
        # line_no is the 1-based line of the "Generated prediction" header.
        prediction_line = log_text.split("\n").index(
            "[2026-11-20 21:43:53][INFO][unsloth/qwen3.5-4b] Generated prediction: {") + 1
        self.assertEqual(line_no, prediction_line)

    def test_running_twice_adds_no_rows(self):
        self.write_log("2026-11-20.1.log",
                       request_block("m1", FLOOD_SYSTEM) + prediction_block("m1"))
        first = self.run_collect()
        second = self.run_collect()
        self.assertEqual(first.new_rows, 1)
        self.assertEqual(second.new_rows, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_half_written_prediction_waits_for_next_run(self):
        full = request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
        # Cut the prediction before its closing brace at column 0.
        cut = full.rindex("\n}\n")
        partial = full[:cut]
        path = self.write_log("2026-11-20.1.log", partial)

        self.assertEqual(self.run_collect().new_rows, 0)
        self.assertEqual(self.rows(), [])

        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(full[cut:])
        self.assertEqual(self.run_collect().new_rows, 1)
        self.assertEqual(self.run_collect().new_rows, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_request_logged_in_one_run_is_answered_in_the_next(self):
        self.write_log("2026-11-20.1.log", request_block("m1", FLOOD_SYSTEM))
        self.assertEqual(self.run_collect().new_rows, 0)
        self.write_log("2026-11-20.1.log",
                       prediction_block("m1", ts="2026-11-20 21:43:54"), mode="a")
        self.assertEqual(self.run_collect().new_rows, 1)
        rows = self.rows()
        self.assertEqual(rows[0][1], "flood_cam")


class PairingTests(CollectTestBase):

    def test_interleaved_models_pair_first_in_first_out_per_model(self):
        text = (request_block("m1", "FIRST for m1", ts="2026-11-20 10:00:00")
                + request_block("m2", "ONLY for m2", ts="2026-11-20 10:00:01")
                + request_block("m1", "SECOND for m1", ts="2026-11-20 10:00:02")
                + prediction_block("m2", 10, 1, ts="2026-11-20 10:00:03")
                + prediction_block("m1", 20, 2, ts="2026-11-20 10:00:04")
                + prediction_block("m1", 30, 3, ts="2026-11-20 10:00:05"))
        self.write_log("2026-11-20.1.log", text)

        self.run_collect()
        rows = self.rows("SELECT model, job, prompt_tokens FROM requests ORDER BY id")
        self.assertEqual(rows, [("m2", "ONLY for m2", 10),
                                ("m1", "FIRST for m1", 20),
                                ("m1", "SECOND for m1", 30)])

    def test_load_and_unload_posts_do_not_steal_predictions(self):
        load = ("[2026-11-20 21:40:48][DEBUG] Received request: POST to /api/v1/models/load "
                "with body {\n  \"model\": \"m1\"\n}\n")
        text = load + request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
        self.write_log("2026-11-20.1.log", text)

        self.run_collect()
        rows = self.rows("SELECT endpoint, prompt_tokens FROM requests")
        self.assertEqual(rows, [("/v1/chat/completions", 749)])

    def test_unanswered_request_is_not_counted(self):
        self.write_log("2026-11-20.1.log", request_block("m1", FLOOD_SYSTEM))
        self.run_collect()
        self.assertEqual(self.rows(), [])

    def test_error_line_records_a_failed_call_with_zero_tokens(self):
        text = request_block("m1", FLOOD_SYSTEM) + error_line("m1")
        self.write_log("2026-11-20.1.log", text)

        result = self.run_collect()
        self.assertEqual(result.new_rows, 1)
        rows = self.rows()
        model, job, endpoint, prompt, completion, reasoning, total_ms, ok, ts, line_no = rows[0]
        self.assertEqual((model, job, ok), ("m1", "flood_cam", 0))
        self.assertEqual((prompt, completion, reasoning), (0, 0, 0))
        self.assertIsNone(total_ms)

    def test_total_time_is_none_when_log_has_no_total_line(self):
        self.write_log("2026-11-20.1.log",
                       request_block("m1", FLOOD_SYSTEM) + prediction_block("m1"))
        self.run_collect()
        self.assertIsNone(self.rows()[0][6])

    def test_latest_total_time_before_prediction_wins(self):
        text = (request_block("m1", FLOOD_SYSTEM)
                + running_line("m1")
                + total_time_line(100.0)
                + total_time_line(250.5)
                + prediction_block("m1"))
        self.write_log("2026-11-20.1.log", text)
        self.run_collect()
        self.assertAlmostEqual(self.rows()[0][6], 250.5)

    def test_missing_usage_block_counts_zero_tokens(self):
        self.write_log("2026-11-20.1.log",
                       request_block("m1", FLOOD_SYSTEM)
                       + prediction_block("m1", with_usage=False))
        self.run_collect()
        rows = self.rows("SELECT prompt_tokens, completion_tokens, reasoning_tokens FROM requests")
        self.assertEqual(rows, [(0, 0, 0)])


class JobLabelTests(CollectTestBase):

    def job_for(self, system):
        self.write_log("2026-11-20.1.log",
                       request_block("m1", system) + prediction_block("m1"))
        self.run_collect()
        return self.rows("SELECT job FROM requests")[0][0]

    def test_known_prefix_maps_to_friendly_name(self):
        self.assertEqual(self.job_for(FLOOD_SYSTEM), "flood_cam")

    def test_unknown_system_prompt_uses_first_sixty_characters(self):
        system = "Summarize the weather report for Bangkok in Thai, please. " * 3
        self.assertEqual(self.job_for(system), system[:60])

    def test_text_before_truncation_marker_is_used(self):
        self.assertEqual(self.job_for("Short label ... <Truncated in logs> ...tail"),
                         "Short label")

    def test_no_system_message_is_labelled(self):
        self.assertEqual(self.job_for(None), "(no system prompt)")


class RobustnessTests(CollectTestBase):

    def test_bad_json_block_is_skipped_and_parsing_continues(self):
        broken = ("[2026-11-20 21:43:52][DEBUG] Received request: POST to /v1/chat/completions "
                  "with body {\n  \"model\": \"m1\", \"messages\": [\n}\n")
        text = broken + request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
        self.write_log("2026-11-20.1.log", text)

        result = self.run_collect()
        self.assertEqual(result.new_rows, 1)
        self.assertEqual(len(self.rows()), 1)

    def test_empty_log_folder_gives_zero_rows(self):
        result = self.run_collect()
        self.assertEqual((result.files_scanned, result.new_rows), (0, 0))
        self.assertTrue(self.db.exists())

    def test_non_utf8_bytes_do_not_crash(self):
        path = self.root / "2026-11" / "2026-11-20.1.log"
        path.write_bytes(b"[2026-11-20 21:00:00][INFO] caf\xe9 bytes\n"
                         + (request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")).encode("utf-8"))
        self.assertEqual(self.run_collect().new_rows, 1)

    def test_summary_line_is_printed(self):
        self.write_log("2026-11-20.1.log",
                       request_block("m1", FLOOD_SYSTEM) + prediction_block("m1"))
        line = collect.summary_line(collect.RunResult(files_scanned=2, new_rows=5))
        self.assertIn("2", line)
        self.assertIn("5", line)


class ReviewFixTests(CollectTestBase):
    """Regression tests for the review round: line counts, chunking, corrupt blocks, locks, truncation."""

    def log_path(self):
        return self.root / "2026-11" / "2026-11-20.1.log"

    def test_line_count_is_stored_and_not_recounted_on_later_runs(self):
        # Fix 1: the files table keeps the line count; runs must not re-read the prefix.
        self.write_log("2026-11-20.1.log",
                       request_block("m1", FLOOD_SYSTEM) + prediction_block("m1"))
        self.run_collect()
        con = sqlite3.connect(self.db)
        stored = con.execute("SELECT lines FROM files").fetchone()[0]
        con.close()
        self.assertEqual(stored, self.log_path().read_bytes().count(b"\n"))

        self.write_log("2026-11-20.1.log",
                       request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:50:00")
                       + prediction_block("m1", ts="2026-11-20 21:50:01"), mode="a")
        with mock.patch.object(collect, "_count_newlines_before",
                               side_effect=AssertionError("prefix must not be re-read")):
            self.assertEqual(self.run_collect().new_rows, 1)

    def test_line_numbers_continue_correctly_after_an_append(self):
        first = request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
        self.write_log("2026-11-20.1.log", first)
        self.run_collect()
        second = request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 21:50:00") + \
            prediction_block("m1", ts="2026-11-20 21:50:01")
        self.write_log("2026-11-20.1.log", second, mode="a")
        self.run_collect()
        rows = self.rows("SELECT line_no FROM requests ORDER BY id")
        whole = (first + second).split("\n")
        expected = whole.index("[2026-11-20 21:50:01][INFO][m1] Generated prediction: {") + 1
        self.assertEqual(rows[-1][0], expected)

    def test_old_database_gets_lines_column_on_open(self):
        # Fix 1: an existing DB without the column is migrated, with counts taken once.
        text = request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
        self.write_log("2026-11-20.1.log", text)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE files (path TEXT PRIMARY KEY, offset INT)")
        con.execute("INSERT INTO files VALUES (?, ?)",
                    (str(self.log_path()), len(text.encode("utf-8"))))
        con.commit()
        con.close()

        con = collect.open_db(self.db)
        columns = [row[1] for row in con.execute("PRAGMA table_info(files)")]
        lines = con.execute("SELECT lines FROM files").fetchone()[0]
        con.close()
        self.assertIn("lines", columns)
        self.assertEqual(lines, text.count("\n"))
        self.assertEqual(self.run_collect().new_rows, 0)

    def test_long_single_line_and_tiny_chunks_still_parse(self):
        # Fix 2: reads come in bounded chunks; a line bigger than a chunk must still work.
        big_system = "You are the flood-watch agent of the Bangkok traff... " + "A" * 3000
        self.write_log("2026-11-20.1.log",
                       request_block("m1", big_system) + prediction_block("m1", 11, 12))
        with mock.patch.object(collect, "CHUNK_BYTES", 64):
            self.assertEqual(self.run_collect().new_rows, 1)
            self.assertEqual(self.run_collect().new_rows, 0)
        rows = self.rows("SELECT job, prompt_tokens, completion_tokens FROM requests")
        self.assertEqual(rows, [("flood_cam", 11, 12)])

    def test_request_without_closing_brace_is_given_up_at_next_record(self):
        # Fix 3: a corrupt block must not pin the offset; the next record is still parsed.
        corrupt = ("[2026-11-20 21:43:50][DEBUG] Received request: POST to /v1/chat/completions "
                   "with body {\n  \"model\": \"m1\",\n  \"messages\": [\n")
        text = corrupt + running_line("m1", ts="2026-11-20 21:43:51") \
            + request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
        self.write_log("2026-11-20.1.log", text)
        result = self.run_collect()
        self.assertEqual(result.new_rows, 1)
        log_text = (self.db.parent / "collect.log").read_text(encoding="utf-8")
        self.assertIn("no closing brace", log_text)

    def test_open_db_retries_while_the_database_is_locked(self):
        # Fix 4: a locked first start waits and retries instead of raising.
        real_init = collect._init_schema
        attempts = []

        def flaky(con):
            attempts.append(1)
            if len(attempts) == 1:
                raise sqlite3.OperationalError("database is locked")
            real_init(con)

        with mock.patch.object(collect, "_init_schema", side_effect=flaky), \
                mock.patch.object(collect.time, "sleep"):
            con = collect.open_db(self.db)
        con.close()
        self.assertEqual(len(attempts), 2)

    def test_truncated_file_logs_a_warning_and_is_read_from_the_start(self):
        # Fix 5: a file smaller than its stored offset is warned about and re-read from 0.
        long_text = (request_block("m1", FLOOD_SYSTEM) + prediction_block("m1")
                     + "filler line\n" * 50)
        self.write_log("2026-11-20.1.log", long_text)
        self.run_collect()

        short_text = (running_line("m1", ts="2026-11-20 22:00:00")
                      + request_block("m1", FLOOD_SYSTEM, ts="2026-11-20 22:00:01")
                      + prediction_block("m1", 5, 6, ts="2026-11-20 22:00:02"))
        self.assertLess(len(short_text.encode("utf-8")), len(long_text.encode("utf-8")))
        self.write_log("2026-11-20.1.log", short_text, mode="w")
        result = self.run_collect()

        self.assertEqual(result.new_rows, 1)
        log_text = (self.db.parent / "collect.log").read_text(encoding="utf-8")
        self.assertIn("smaller", log_text)
        self.assertIn("read again from the start", log_text)
        self.assertEqual(len(self.rows()), 2)


if __name__ == "__main__":
    unittest.main()
