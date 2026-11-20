# Bionic usage logger

Counts every request that the local Bionic server (LM Studio rebrand, port 1235)
serves: calls and tokens, per model and per job. Tokens and call counts only, no
prices. The data is kept forever in SQLite. A live page shows what is running now,
and a static HTML report is rebuilt from the same data.

## What it does

- `collect.py` reads Bionic's daily server logs, pairs each request with its
  answer per model, and writes one row per call into the database. It resumes
  from a saved byte offset for each log file, so repeated runs add nothing new.
- `live.py` is the realtime page. It runs a small local web server on
  `127.0.0.1` (see below). While it runs it collects every 3 s, reads the newest
  Bionic log to show requests still in progress, and asks Bionic which models are
  loaded every 10 s.
- `report.py` writes `report.html`: totals for today, 7 days, this month and all
  time; a 48-hour token chart; a 30-day table; per-job and per-model tables.
  The page is self-contained (inline CSS and SVG, no scripts, no external links).
- `scheduled_run.py` runs collect and report, quietly, for the scheduled task.

## The live page

Desktop icon "Bionic Usage" runs `run.bat`, which starts `pythonw live.py`. That
opens the browser at `http://127.0.0.1:8199/`. The page shows:

- Bionic up or down, and the models that are loaded (VRAM is not shown).
- "กำลังทำงานอยู่": every request in progress, with a running timer, its job
  and its stage (อ่านคำถาม N%, then กำลังตอบ).
- Totals for the last 60 minutes, today and all time: calls and tokens.
- A bar chart of tokens per minute for the last 60 minutes.
- "ล่าสุด 50 ครั้ง": the last 50 calls, newest first. New rows flash once.
- A link "ดูรายงานเต็ม" to `/report`, the full static report, rebuilt on click.

The page polls `/api/state` every 2 seconds. If the server stops answering, a
banner says the viewer stopped and it keeps retrying.

- "ทางเชื่อม Pi → Bionic": the path the Pi production server uses to reach Bionic
  (Pi :8000 → Pi 127.0.0.1:1235 → SSH link → ssh.exe on this PC → Bionic :1235).
  Each hop shows an icon and a word as well as a colour. It also shows how many
  Pi connections are open, how many the page has seen (at least, not an exact count),
  which programs on this PC call Bionic directly, the last Pi check and the last
  tunnel log line. The state comes from `tunnel.py`; if that module cannot load
  (for example, psutil is missing), the page still works and shows the panel as unavailable.

Routes: `/` (page), `/api/state` (JSON), `/report` (full report). Requests whose
Host header is not `127.0.0.1:<port>` or `localhost:<port>` get 403, which blocks
DNS-rebinding attacks from other websites.

### Port

Default port 8199. Change it with the environment variable `BIONIC_USAGE_PORT`
or with `--port`. The server only listens on 127.0.0.1, so other PCs cannot reach it.

### Single instance and auto-exit

- If the port is already in use, `live.py` does not start a second server. It
  opens the browser to the running one and exits.
- The server stops itself when no `/api/state` request has arrived for 15 minutes,
  so it does not stay in the background after the browser is closed.
- `--no-open` starts the server without opening a browser.

### Errors

Errors go to `E:\new_ccty_bangkok\local\bionic_usage\live.log`. pythonw has no
console, so nothing is printed. A failed poll is logged and the next one still runs.

## Where data lives

- Bionic logs (the only source): `%USERPROFILE%\.lmstudio\apps\bionic\server-logs\YYYY-MM\YYYY-MM-DD.N.log`
- Database: `E:\new_ccty_bangkok\local\bionic_usage\usage.db` (WAL mode)
- Report: `E:\new_ccty_bangkok\local\bionic_usage\report.html`
- Skipped records and failures: `E:\new_ccty_bangkok\local\bionic_usage\collect.log`
- Live page errors: `E:\new_ccty_bangkok\local\bionic_usage\live.log`

## Install and uninstall

Install (per user, no admin): creates the scheduled task "BKK Bionic usage collect"
(every 10 minutes, hidden, only while logged on) and a Desktop shortcut "Bionic Usage".

    powershell -ExecutionPolicy Bypass -File E:\new_ccty_bangkok\launch\bionic_usage\install.ps1

Uninstall: removes both.

    powershell -ExecutionPolicy Bypass -File E:\new_ccty_bangkok\launch\bionic_usage\install.ps1 -Uninstall

Manual run:

- `launch\bionic_usage\run.bat` starts the live page and opens the browser.
- `launch\bionic_usage\run.bat --report` collects, rebuilds `report.html` and opens it.

## The scheduled task keeps history

The scheduled task runs `scheduled_run.py` every 10 minutes whether or not the live
page is open. Closing the page does not stop collection, so no calls are lost while
you are away. The live page also collects, but it uses the same database and the
same offsets, so the two never count a call twice.

## Important: keep Bionic's logs

Bionic's own server logs are the only source of truth. The collector only sees
what is still in those files, so the logs must be kept long enough between runs
(the task runs every 10 minutes; keeping at least a few days is safe). If Bionic
deletes or truncates its logs before the collector reads them, those calls are
lost for good.

If a log file shrinks (replaced or truncated), the collector writes a WARNING to
`collect.log` and reads that file again from the top. Known limitation: a new
record whose (file, line) pair was already stored is ignored by the unique key,
so it is not counted. A replaced file with the same line numbers as before
loses those calls.

## Notes

- A call with no answer in the log is not counted on the report. A request with
  no answer for more than an hour (by log time) is dropped from the pending queue.
  The live page shows an unanswered request as in progress for up to an hour.
- An `[ERROR]` line for a model counts as a failed call with zero tokens. No such
  line exists in the logs yet, so that format is a guess until one appears.
- Tests (run each file by name if a stray test file sits in this folder):
  `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m unittest discover -s E:\new_ccty_bangkok\launch\bionic_usage -p "test_*.py"`
