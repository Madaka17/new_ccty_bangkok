"""Tests for report.py. Run with the repo venv:

    E:\\new_ccty_bangkok\\.venv\\Scripts\\python.exe -m unittest discover -s E:\\new_ccty_bangkok\\launch\\bionic_usage -p "test_*.py"
"""

import re
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import collect
import report

BANGKOK = collect.BANGKOK
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=BANGKOK)


def unix(text):
    """Return Unix seconds for a Bangkok wall-clock time 'YYYY-MM-DD HH:MM'."""
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=BANGKOK).timestamp())


class ReportTestBase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = self.tmp / "usage.db"
        collect.run(self.tmp / "no-logs", self.db)  # creates an empty schema

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, when, model="unsloth/qwen3.5-4b", job="flood_cam",
            endpoint="/v1/chat/completions", prompt=100, completion=50, ms=800.0, ok=1):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO requests(ts, model, job, endpoint, prompt_tokens, completion_tokens, "
            "reasoning_tokens, total_ms, ok, log_file, line_no) VALUES (?,?,?,?,?,?,0,?,?,?,?)",
            (unix(when), model, job, endpoint, prompt, completion, ms, ok, "f.log",
             self.next_line()))
        con.commit()
        con.close()

    def next_line(self):
        self._line = getattr(self, "_line", 0) + 1
        return self._line

    def rows(self):
        return report.load_rows(self.db)


class SummaryTests(ReportTestBase):

    def seed(self):
        self.add("2026-11-20 10:00", prompt=100, completion=50, ms=800.0)
        self.add("2026-11-20 11:00", prompt=100, completion=50, ms=1200.0)
        self.add("2026-11-20 11:30", prompt=0, completion=0, ms=None, ok=0)
        self.add("2026-11-18 10:00", prompt=1000, completion=500, ms=600.0)
        self.add("2026-11-02 09:00", prompt=7, completion=3, ms=100.0)

    def test_period_tiles_count_calls_tokens_and_errors(self):
        self.seed()
        tiles = report.summarize(self.rows(), NOW)
        self.assertEqual(tiles["today"], {"calls": 3, "prompt": 200, "completion": 100,
                                          "total": 300, "errors": 1})
        self.assertEqual(tiles["week"]["calls"], 4)
        self.assertEqual(tiles["week"]["total"], 300 + 1500)
        self.assertEqual(tiles["month"]["calls"], 5)
        self.assertEqual(tiles["all"]["calls"], 5)
        self.assertEqual(tiles["all"]["total"], 300 + 1500 + 10)

    def test_week_means_seven_calendar_days_including_today(self):
        self.add("2026-11-13 23:59", prompt=5, completion=5)  # 7 days before today: outside
        self.add("2026-11-14 00:00", prompt=9, completion=1)  # today plus 6 earlier days: inside
        tiles = report.summarize(self.rows(), NOW)
        self.assertEqual(tiles["week"]["calls"], 1)
        self.assertEqual(tiles["week"]["total"], 10)

    def test_html_shows_thousands_separators(self):
        self.seed()
        html = report.build_html(self.db, NOW)
        self.assertIn("1,800", html)  # week total 300 + 1500
        self.assertIn("อัปเดต", html)
        self.assertIn(str(self.db), html)

    def test_newest_log_record_time_is_shown(self):
        self.seed()
        html = report.build_html(self.db, NOW)
        self.assertIn("2026-11-20 11:30", html)


class TableTests(ReportTestBase):

    def test_daily_table_covers_last_thirty_days_only(self):
        self.add("2026-11-20 10:00", prompt=100, completion=50)
        self.add("2026-10-20 10:00", prompt=1, completion=1)  # 31 days before today
        days = report.daily_rows(self.rows(), NOW)
        dates = [d["date"] for d in days]
        self.assertEqual(len(days), 30)
        self.assertIn("2026-11-20", dates)
        self.assertNotIn("2026-10-20", dates)
        today = next(d for d in days if d["date"] == "2026-11-20")
        self.assertEqual((today["calls"], today["prompt"], today["completion"]), (1, 100, 50))

    def test_job_table_has_all_time_and_seven_day_counts(self):
        self.add("2026-11-20 10:00", job="flood_cam", prompt=100, completion=100)
        self.add("2026-11-01 10:00", job="flood_cam", prompt=50, completion=50)
        self.add("2026-11-19 10:00", job="(no system prompt)", prompt=10, completion=0, ms=None)
        jobs = {j["job"]: j for j in report.job_rows(self.rows(), NOW)}
        flood = jobs["flood_cam"]
        self.assertEqual(flood["calls"], 2)
        self.assertEqual(flood["total"], 300)
        self.assertEqual(flood["per_call"], 150)
        self.assertEqual(flood["calls_7d"], 1)
        self.assertEqual(jobs["(no system prompt)"]["avg_ms"], None)

    def test_model_table_lists_first_and_last_seen(self):
        self.add("2026-11-18 10:00", model="unsloth/qwen3.5-4b")
        self.add("2026-11-20 11:00", model="unsloth/qwen3.5-4b")
        self.add("2026-11-19 08:00", model="qwen3.5-9b")
        models = {m["model"]: m for m in report.model_rows(self.rows())}
        self.assertEqual(models["unsloth/qwen3.5-4b"]["first"], "2026-11-18 10:00")
        self.assertEqual(models["unsloth/qwen3.5-4b"]["last"], "2026-11-20 11:00")
        self.assertEqual(models["unsloth/qwen3.5-4b"]["calls"], 2)
        self.assertEqual(models["qwen3.5-9b"]["calls"], 1)


class ChartTests(ReportTestBase):

    def test_hourly_buckets_cover_48_hours_ending_this_hour(self):
        self.add("2026-11-20 11:15", prompt=100, completion=50)
        self.add("2026-11-18 13:30", prompt=7, completion=3)  # first hour of the window
        self.add("2026-11-18 12:30", prompt=99, completion=99)  # just outside it
        buckets = report.hourly_buckets(self.rows(), NOW)
        self.assertEqual(len(buckets), 48)
        self.assertEqual(buckets[0]["hour"], "2026-11-18 13:00")
        self.assertEqual(buckets[-1]["hour"], "2026-11-20 12:00")
        self.assertEqual(buckets[-1]["total"], 0)
        by_hour = {b["hour"]: b["total"] for b in buckets}
        self.assertEqual(by_hour["2026-11-20 11:00"], 150)
        self.assertEqual(by_hour["2026-11-18 13:00"], 10)
        self.assertEqual(sum(by_hour.values()), 160)

    def test_svg_chart_has_bars_with_hover_titles_and_no_script(self):
        self.add("2026-11-20 11:15", prompt=100, completion=50)
        html = report.build_html(self.db, NOW)
        svg = re.search(r"<svg.*?</svg>", html, re.S)
        self.assertIsNotNone(svg)
        self.assertGreaterEqual(svg.group(0).count("<rect"), 48)  # one hover target per hour
        self.assertIn("<title>", svg.group(0))


class PageTests(ReportTestBase):

    def test_empty_database_renders_zeros_and_note(self):
        html = report.build_html(self.db, NOW)
        self.assertIn("ยังไม่มีข้อมูล", html)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("0", html)

    def test_page_has_no_scripts_or_external_resources(self):
        self.add("2026-11-20 11:00")
        html = report.build_html(self.db, NOW)
        self.assertNotIn("<script", html.lower())
        self.assertIsNone(re.search(r"(src|href)\s*=\s*[\"']?https?:", html, re.I))
        self.assertNotIn("@import", html)
        self.assertNotIn("url(http", html)

    def test_theme_uses_custom_properties_and_dark_media_query(self):
        html = report.build_html(self.db, NOW)
        self.assertIn(":root", html)
        self.assertIn("--", html)
        self.assertIn("prefers-color-scheme: dark", html)
        self.assertIn("overflow-x", html)

    def test_model_name_is_escaped(self):
        self.add("2026-11-20 11:00", model="<b>evil</b>")
        html = report.build_html(self.db, NOW)
        self.assertNotIn("<b>evil</b>", html)
        self.assertIn("&lt;b&gt;evil&lt;/b&gt;", html)

    def test_write_report_creates_file(self):
        self.add("2026-11-20 11:00")
        out = self.tmp / "report.html"
        returned = report.write_report(self.db, out, NOW)
        self.assertEqual(returned, out)
        self.assertGreater(out.stat().st_size, 1000)

    def test_main_without_open_does_not_open_browser(self):
        opened = []
        report.main(["--db", str(self.db), "--out", str(self.tmp / "r.html")],
                    opener=opened.append, now=NOW)
        self.assertEqual(opened, [])
        self.assertTrue((self.tmp / "r.html").exists())

    def test_main_with_open_opens_the_report_once(self):
        opened = []
        out = self.tmp / "r.html"
        report.main(["--open", "--db", str(self.db), "--out", str(out)],
                    opener=opened.append, now=NOW)
        self.assertEqual(opened, [str(out)])


if __name__ == "__main__":
    unittest.main()
