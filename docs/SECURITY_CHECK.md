# Security check

The security check looks at how the site is being probed and whether the server and the Raspberry Pi
are set up safely. It writes one HTML report per run.

## What gets recorded

The public-exposure guard (`backend/core/access_guard.py`) refuses some requests from outside the
trusted networks. Each refused request is recorded by `backend/core/security_log.py` with:
time, kind, client address, path, method and user agent. Headers, cookies and request bodies are
never stored.

- Requests from trusted networks (localhost and the home LAN) are never recorded.
- Scanner paths such as `/.env`, `/.git`, `/wp-`, `/phpmyadmin` and `.php` are answered 404 and
  recorded as kind `probe`. The list is `PROBE_PATH` in `access_guard.py`.
- Recording is in memory first. A background thread writes it to the database every 30 seconds.
- The database keeps hourly counts for 30 days, and the newest 500 raw events.

## Where the data lives

- Database: `<INSTANCE_DIR>/security_events.db` (for production, the Pi's instance folder; for
  test, `instances/test/`).
- Print the summary by hand: `python -m backend.core.security_log --summary-json --days 30`.
  The command only reads. It never creates the database.

## Run a check

Double-click `launch\security_check\check.bat`, or run it from a terminal:

    launch\security_check\check.bat --target test
    launch\security_check\check.bat --target production --days 30

Options:

- `--target production` (default): reads the Pi over ssh, read-only (event summary, config flags,
  SSH and firewall settings, pending updates), and checks the public site over HTTPS.
- `--target test`: checks the test server on localhost:8001 and its `instances/test/.env`. It does
  not check the outside fence (docs pages, `/.env`, API without cookie), because localhost is always
  trusted, so those answers mean nothing. Use `--target production` for those.
- `--days N`: how far back to count attacks (default 30).
- `--no-open`: do not open the report in the browser.

The report is saved as `local\reports\security\security-<target>-<date>-<time>.html`. The last line
of the output is the overall verdict, `ผลรวม: ปลอดภัยดี`, `ควรดู` or `ต้องแก้` (ok, warn, fail).

For the Pi connection settings (address, user, key), see the `PI` block at the top of
`launch/security_check/collect.py`.

## What the kinds mean

These are the labels shown in the report (`KIND_TH` in `launch/security_check/rules.py`).

| Kind | Label in report | Meaning |
|---|---|---|
| `probe` | สแกนหาช่องโหว่ | Scanner asking for known weak paths |
| `bad_path` | path อันตราย | URL with a backslash, `..` or `:` |
| `docs_probe` | แอบดูหน้าเอกสาร API | Outsider asking for `/docs`, `/redoc`, `/openapi.json` |
| `control_denied` | สั่งปุ่มควบคุมจากนอกบ้าน | Outsider trying a control button (POST/PUT/DELETE) |
| `not_browser` | สคริปต์ดึง API | Script calling the API, not the site's own page |
| `no_session` | เรียก API ไม่ผ่านหน้าเว็บ | API call without the page session cookie |
| `rate_limited` | ยิงถี่เกิน | Too many requests per minute or per day |
| `chat_limited` | ใช้แชท AI ถี่เกิน | Chat over its per-minute or per-day limit |
| `report_limited` | แจ้งเหตุถี่เกิน | Public flood report or "car park full" over its limit |
| `too_large` | ส่งข้อมูลใหญ่เกิน | Body larger than the cap |
| `dropped` | นับไม่ทัน (ทิ้ง) | Events lost because the in-memory buffer was full |

## Deploy the server part

The recording only starts after the server runs the new code. Until then the report shows
"the Pi has not been updated yet" for attacks.

- Test server: on the PC, run `launch\test\restart.bat` (or `stop.bat`, then `start.bat`).
- Production (Raspberry Pi, systemd unit `bkk-production`): only with the owner's go-ahead.
  1. On the Pi, pull the latest code in the project folder.
  2. Run `sudo systemctl restart bkk-production`.
  3. Check that it came back: `systemctl status bkk-production`.

Restarting production briefly takes the public site offline, so do it when people are not using it.
