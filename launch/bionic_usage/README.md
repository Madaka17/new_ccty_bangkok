# Bionic usage logger

Counts every request that the local Bionic server (LM Studio rebrand, port 1235)
serves: calls and tokens, per model and per job. Tokens and call counts only, no
prices. The data is kept forever in SQLite, and an HTML report is rebuilt from it.

## What it does

- `collect.py` reads Bionic's daily server logs, pairs each request with its
  answer per model, and writes one row per call into the database. It resumes
  from a saved byte offset for each log file, so repeated runs add nothing new.
- `report.py` writes `report.html`: totals for today, 7 days, this month and all
  time; a 48-hour token chart; a 30-day table; per-job and per-model tables.
  The page is self-contained (inline CSS and SVG, no scripts, no external links).
- `scheduled_run.py` runs both, quietly, for the scheduled task.

## Where data lives

- Bionic logs (the only source): `%USERPROFILE%\.lmstudio\apps\bionic\server-logs\YYYY-MM\YYYY-MM-DD.N.log`
- Database: `E:\new_ccty_bangkok\local\bionic_usage\usage.db` (WAL mode)
- Report: `E:\new_ccty_bangkok\local\bionic_usage\report.html`
- Skipped records and failures: `E:\new_ccty_bangkok\local\bionic_usage\collect.log`

## Install and uninstall

Install (per user, no admin): creates the scheduled task "BKK Bionic usage collect"
(every 10 minutes, hidden, only while logged on) and a Desktop shortcut "Bionic Usage".

    powershell -ExecutionPolicy Bypass -File E:\new_ccty_bangkok\launch\bionic_usage\install.ps1

Uninstall: removes both.

    powershell -ExecutionPolicy Bypass -File E:\new_ccty_bangkok\launch\bionic_usage\install.ps1 -Uninstall

Manual run: `launch\bionic_usage\run.bat` (collects, rebuilds, opens the report).

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

- A call with no answer in the log is not counted. A request with no answer for
  more than an hour (by log time) is dropped from the pending queue.
- An `[ERROR]` line for a model counts as a failed call with zero tokens. No such
  line exists in the logs yet, so that format is a guess until one appears.
- Tests: `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m unittest discover -s E:\new_ccty_bangkok\launch\bionic_usage -p "test_*.py"`
