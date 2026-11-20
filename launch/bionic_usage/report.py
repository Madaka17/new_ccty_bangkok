"""Write the Bionic usage report as one self-contained HTML page.

The page reads local\\bionic_usage\\usage.db (filled by collect.py) and writes
local\\bionic_usage\\report.html. It has inline CSS and inline SVG only: no
scripts, no fonts and no external links, so it opens offline.

Run with:  python report.py           (writes the file)
           python report.py --open    (writes it and opens it in the browser)
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import collect

DEFAULT_DB = collect.DEFAULT_DB
DEFAULT_OUT = DEFAULT_DB.parent / "report.html"
BANGKOK = collect.BANGKOK

CHART_HOURS = 48
DAILY_DAYS = 30

# Chart geometry in SVG user units.
CHART_W, CHART_H = 960, 240
PLOT_LEFT, PLOT_RIGHT, PLOT_TOP, PLOT_BOTTOM = 56, 944, 16, 200

CSS = """
:root {
  color-scheme: light;
  --bg: #fcfcfb;
  --surface: #ffffff;
  --text: #0b0b0b;
  --text-2: #52514e;
  --text-3: #7a7974;
  --border: #e4e3de;
  --grid: #e9e8e3;
  --series-1: #2a78d6;
  --error: #c4362f;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #1a1a19;
    --surface: #222220;
    --text: #f0efec;
    --text-2: #c3c2b7;
    --text-3: #98978e;
    --border: #35342f;
    --grid: #2d2c28;
    --series-1: #3987e5;
    --error: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #1a1a19;
  --surface: #222220;
  --text: #f0efec;
  --text-2: #c3c2b7;
  --text-3: #98978e;
  --border: #35342f;
  --grid: #2d2c28;
  --series-1: #3987e5;
  --error: #e66767;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 16px;
  background: var(--bg);
  color: var(--text);
  font-family: "Leelawadee UI", "Tahoma", "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.45;
}
h1 { font-size: 22px; margin: 4px 0 14px; }
h2 { font-size: 17px; margin: 26px 0 8px; }
.note { color: var(--text-2); margin: 0 0 12px; }
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}
.tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
}
.tile .label { color: var(--text-2); font-size: 14px; }
.tile .big { font-size: 26px; font-weight: 600; margin: 2px 0; font-variant-numeric: tabular-nums; }
.tile .small { color: var(--text-2); font-size: 13px; }
.tile .err { color: var(--error); font-size: 13px; }
.chart {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
}
.chart svg { width: 100%; height: auto; display: block; }
.table-wrap {
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}
table { border-collapse: collapse; width: 100%; min-width: 560px; font-size: 14px; }
th, td { padding: 7px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { text-align: left; color: var(--text-2); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
.footer { color: var(--text-3); font-size: 13px; margin-top: 26px; }
"""


def load_rows(db_path: Path) -> list[dict]:
    """Read every stored call. Returns an empty list when there is no database yet."""
    if not Path(db_path).exists():
        return []
    con = collect.open_db(Path(db_path))
    try:
        cur = con.execute("SELECT ts, model, job, prompt_tokens, completion_tokens, "
                          "total_ms, ok FROM requests")
        names = [c[0] for c in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]
    finally:
        con.close()


def summarize(rows: list[dict], now: datetime) -> dict:
    """Totals for today, the last 7 calendar days, this month and all time."""
    today = _day_start(now)
    periods = {
        "today": today,
        "week": today - timedelta(days=6),
        "month": datetime(now.year, now.month, 1, tzinfo=BANGKOK),
        "all": None,
    }
    return {name: _totals([r for r in rows if start is None or r["ts"] >= start.timestamp()])
            for name, start in periods.items()}


def daily_rows(rows: list[dict], now: datetime) -> list[dict]:
    """One entry per day for the last 30 days, oldest first, zero days included."""
    today = _day_start(now)
    out = []
    for offset in range(DAILY_DAYS - 1, -1, -1):
        start = today - timedelta(days=offset)
        end = start + timedelta(days=1)
        day = [r for r in rows if start.timestamp() <= r["ts"] < end.timestamp()]
        totals = _totals(day)
        out.append({
            "date": start.strftime("%Y-%m-%d"),
            "calls": totals["calls"],
            "prompt": totals["prompt"],
            "completion": totals["completion"],
            "avg_ms": _avg_ms(day),
            "errors": totals["errors"],
        })
    return out


def job_rows(rows: list[dict], now: datetime) -> list[dict]:
    """Per job: all-time calls and tokens, plus the calls of the last 7 days."""
    week_start = (_day_start(now) - timedelta(days=6)).timestamp()
    by_job: dict[str, list[dict]] = {}
    for r in rows:
        by_job.setdefault(r["job"] or "(ไม่ระบุ)", []).append(r)
    out = []
    for job, items in by_job.items():
        totals = _totals(items)
        out.append({
            "job": job,
            "calls": totals["calls"],
            "total": totals["total"],
            "per_call": round(totals["total"] / totals["calls"]) if totals["calls"] else 0,
            "avg_ms": _avg_ms(items),
            "calls_7d": sum(1 for r in items if r["ts"] >= week_start),
        })
    return sorted(out, key=lambda j: (-j["total"], j["job"]))


def model_rows(rows: list[dict]) -> list[dict]:
    """Per model: calls, tokens, and the first and last time it was seen."""
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        by_model.setdefault(r["model"] or "(ไม่ระบุ)", []).append(r)
    out = []
    for model, items in by_model.items():
        totals = _totals(items)
        stamps = [r["ts"] for r in items]
        out.append({
            "model": model,
            "calls": totals["calls"],
            "total": totals["total"],
            "first": _fmt_local(min(stamps)),
            "last": _fmt_local(max(stamps)),
        })
    return sorted(out, key=lambda m: (-m["calls"], m["model"]))


def hourly_buckets(rows: list[dict], now: datetime) -> list[dict]:
    """Total tokens per clock hour for the last 48 hours, oldest first."""
    hour_end = now.replace(minute=0, second=0, microsecond=0)
    out = []
    for back in range(CHART_HOURS - 1, -1, -1):
        start = hour_end - timedelta(hours=back)
        end = start + timedelta(hours=1)
        total = sum(_tokens(r) for r in rows if start.timestamp() <= r["ts"] < end.timestamp())
        out.append({"hour": start.strftime("%Y-%m-%d %H:00"), "start": start, "total": total})
    return out


def build_html(db_path: Path, now: datetime | None = None) -> str:
    """Return the whole report page as one string."""
    now = now or datetime.now(BANGKOK)
    rows = load_rows(Path(db_path))
    tiles = summarize(rows, now)
    newest = max((r["ts"] for r in rows), default=None)

    parts = [
        "<!doctype html>",
        '<html lang="th"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Bionic usage</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        "<h1>การใช้งาน Bionic</h1>",
    ]
    if not rows:
        parts.append('<p class="note">ยังไม่มีข้อมูล รัน collect.py ก่อน แล้วรายงานจะแสดงตัวเลขจริง</p>')
    parts.append(_tiles_html(tiles))
    parts.append("<h2>โทเคนต่อชั่วโมง (48 ชั่วโมงล่าสุด)</h2>")
    parts.append(f'<div class="chart">{_chart_svg(hourly_buckets(rows, now))}</div>')
    parts.append("<h2>รายวัน (30 วันล่าสุด)</h2>")
    parts.append(_daily_table(daily_rows(rows, now)))
    parts.append("<h2>แยกตามงาน</h2>")
    parts.append(_job_table(job_rows(rows, now)))
    parts.append("<h2>แยกตามโมเดล</h2>")
    parts.append(_model_table(model_rows(rows)))
    parts.append(
        '<div class="footer">'
        f"อัปเดต {_esc(now.strftime('%Y-%m-%d %H:%M:%S'))}<br>"
        f"ฐานข้อมูล: {_esc(str(db_path))}<br>"
        f"ข้อมูลล่าสุดในบันทึก: {_esc(_fmt_local(newest) if newest is not None else '-')}"
        "</div>")
    parts.append("</body></html>")
    return "\n".join(parts)


def write_report(db_path: Path, out_path: Path, now: datetime | None = None) -> Path:
    """Write the report to out_path (UTF-8) and return that path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(Path(db_path), now), encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None, opener=None, now: datetime | None = None) -> int:
    """Command line entry. `opener` and `now` exist so tests can avoid the browser and the clock."""
    parser = argparse.ArgumentParser(description="Write the Bionic usage report.")
    parser.add_argument("--open", action="store_true", help="open the report in the browser")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    out = write_report(Path(args.db), Path(args.out), now)
    if args.open:
        (opener or _open_in_browser)(str(out))
    if sys.stdout is not None:
        print(f"report: {out}")
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _totals(items: list[dict]) -> dict:
    """Sum calls, tokens and errors for a list of call rows."""
    prompt = sum(_int(r["prompt_tokens"]) for r in items)
    completion = sum(_int(r["completion_tokens"]) for r in items)
    return {
        "calls": len(items),
        "prompt": prompt,
        "completion": completion,
        "total": prompt + completion,
        "errors": sum(1 for r in items if not r["ok"]),
    }


def _tokens(row: dict) -> int:
    """Prompt plus completion tokens for one call row."""
    return _int(row["prompt_tokens"]) + _int(row["completion_tokens"])


def _avg_ms(items: list[dict]) -> float | None:
    """Average latency over calls that have a timing, or None when there are none."""
    timed = [r["total_ms"] for r in items if r["total_ms"] is not None]
    return sum(timed) / len(timed) if timed else None


def _int(value: object) -> int:
    """Return an integer, treating missing values as zero."""
    return int(value) if isinstance(value, (int, float)) else 0


def _day_start(now: datetime) -> datetime:
    """Midnight in Bangkok on the day of `now`."""
    local = now.astimezone(BANGKOK)
    return datetime(local.year, local.month, local.day, tzinfo=BANGKOK)


def _fmt_local(ts: int) -> str:
    """Format Unix seconds as Bangkok wall-clock time."""
    return datetime.fromtimestamp(ts, BANGKOK).strftime("%Y-%m-%d %H:%M")


def _num(value: float | int | None) -> str:
    """Thousands-separated integer, or a dash when there is no value."""
    if value is None:
        return "-"
    return f"{round(value):,}"


def _esc(text: str) -> str:
    """HTML-escape any text that came from the database or the log."""
    return html.escape(text, quote=True)


def _tiles_html(tiles: dict) -> str:
    """Four summary tiles: today, 7 days, this month, all time."""
    labels = [("today", "วันนี้"), ("week", "7 วัน"), ("month", "เดือนนี้"), ("all", "ทั้งหมด")]
    cards = []
    for key, label in labels:
        t = tiles[key]
        cards.append(
            '<div class="tile">'
            f'<div class="label">{label}</div>'
            f'<div class="big">{_num(t["calls"])} ครั้ง</div>'
            f'<div class="small">โทเคน {_num(t["total"])}</div>'
            f'<div class="small">รับ {_num(t["prompt"])} · ตอบ {_num(t["completion"])}</div>'
            f'<div class="err">ผิดพลาด {_num(t["errors"])}</div>'
            "</div>")
    return f'<div class="tiles">{"".join(cards)}</div>'


def _chart_svg(buckets: list[dict]) -> str:
    """Inline SVG bar chart: one bar per hour, one series, hover title per bar."""
    peak = max((b["total"] for b in buckets), default=0) or 1
    plot_h = PLOT_BOTTOM - PLOT_TOP
    slot = (PLOT_RIGHT - PLOT_LEFT) / len(buckets)
    gap = 2
    radius_max = 4
    parts = [f'<svg viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
             'aria-label="โทเคนต่อชั่วโมง 48 ชั่วโมงล่าสุด">']
    for frac in (0, 0.5, 1):
        y = PLOT_BOTTOM - frac * plot_h
        label = f"{round(peak * frac):,}"
        parts.append(f'<line x1="{PLOT_LEFT}" x2="{PLOT_RIGHT}" y1="{y:.1f}" y2="{y:.1f}" '
                     'stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{PLOT_LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="12" fill="var(--text-3)">{label}</text>')
    for i, b in enumerate(buckets):
        x0 = PLOT_LEFT + i * slot
        x1 = x0 + slot
        tooltip = f"{b['hour']}: {_num(b['total'])} โทเคน"
        if b["total"] > 0:
            bar_w = slot - gap
            bar_h = max(1.0, b["total"] / peak * plot_h)
            r = min(radius_max, bar_h / 2, bar_w / 2)
            left, right = x0 + gap / 2, x0 + gap / 2 + bar_w
            top = PLOT_BOTTOM - bar_h
            d = (f"M{left:.1f},{PLOT_BOTTOM} V{top + r:.1f} "
                 f"Q{left:.1f},{top:.1f} {left + r:.1f},{top:.1f} "
                 f"H{right - r:.1f} Q{right:.1f},{top:.1f} {right:.1f},{top + r:.1f} "
                 f"V{PLOT_BOTTOM} Z")
            parts.append(f'<path d="{d}" fill="var(--series-1)"><title>{_esc(tooltip)}</title></path>')
        parts.append(f'<rect x="{x0:.1f}" y="{PLOT_TOP}" width="{x1 - x0:.1f}" height="{plot_h}" '
                     f'fill="transparent"><title>{_esc(tooltip)}</title></rect>')
        if i % 6 == 0:
            label = b["start"].strftime("%d/%m %H:00") if b["start"].hour == 0 else b["start"].strftime("%H:00")
            parts.append(f'<text x="{x0 + slot / 2:.1f}" y="{PLOT_BOTTOM + 18}" text-anchor="middle" '
                         f'font-size="12" fill="var(--text-3)">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _daily_table(days: list[dict]) -> str:
    """Table with one row per day."""
    head = ("<tr><th>วันที่</th><th class=\"num\">ครั้ง</th><th class=\"num\">โทเคนรับ</th>"
            "<th class=\"num\">โทเคนตอบ</th><th class=\"num\">รวม</th>"
            "<th class=\"num\">เฉลี่ย ms/ครั้ง</th><th class=\"num\">ผิดพลาด</th></tr>")
    body = []
    for d in days:
        body.append(
            f"<tr><td>{_esc(d['date'])}</td><td class=\"num\">{_num(d['calls'])}</td>"
            f"<td class=\"num\">{_num(d['prompt'])}</td><td class=\"num\">{_num(d['completion'])}</td>"
            f"<td class=\"num\">{_num(d['prompt'] + d['completion'])}</td>"
            f"<td class=\"num\">{_num(d['avg_ms'])}</td><td class=\"num\">{_num(d['errors'])}</td></tr>")
    return f'<div class="table-wrap"><table><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _job_table(jobs: list[dict]) -> str:
    """Table with one row per job, all time and last-7-days call counts."""
    if not jobs:
        return '<p class="note">ยังไม่มีงาน</p>'
    head = ("<tr><th>งาน</th><th class=\"num\">ครั้ง (ทั้งหมด)</th><th class=\"num\">ครั้ง (7 วัน)</th>"
            "<th class=\"num\">โทเคนรวม</th><th class=\"num\">เฉลี่ยโทเคน/ครั้ง</th>"
            "<th class=\"num\">เฉลี่ย ms</th></tr>")
    body = []
    for j in jobs:
        body.append(
            f"<tr><td>{_esc(j['job'])}</td><td class=\"num\">{_num(j['calls'])}</td>"
            f"<td class=\"num\">{_num(j['calls_7d'])}</td><td class=\"num\">{_num(j['total'])}</td>"
            f"<td class=\"num\">{_num(j['per_call'])}</td><td class=\"num\">{_num(j['avg_ms'])}</td></tr>")
    return f'<div class="table-wrap"><table><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _model_table(models: list[dict]) -> str:
    """Table with one row per model, with first and last time seen."""
    if not models:
        return '<p class="note">ยังไม่มีโมเดล</p>'
    head = ("<tr><th>โมเดล</th><th class=\"num\">ครั้ง</th><th class=\"num\">โทเคนรวม</th>"
            "<th>เห็นครั้งแรก</th><th>เห็นล่าสุด</th></tr>")
    body = []
    for m in models:
        body.append(
            f"<tr><td>{_esc(m['model'])}</td><td class=\"num\">{_num(m['calls'])}</td>"
            f"<td class=\"num\">{_num(m['total'])}</td><td>{_esc(m['first'])}</td>"
            f"<td>{_esc(m['last'])}</td></tr>")
    return f'<div class="table-wrap"><table><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _open_in_browser(path: str) -> None:
    """Open a file in the default browser (Windows)."""
    os.startfile(path)  # noqa: S606 - Windows only, by design


if __name__ == "__main__":
    sys.exit(main())
