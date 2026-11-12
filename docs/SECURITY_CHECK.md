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
| `self_check` | ตรวจโดยโปรแกรมนี้เอง (ไม่นับ) | The checker's own test requests, left out of the totals |
| `dropped` | นับไม่ทัน (ทิ้ง) | Events lost because the in-memory buffer was full |

## The program's own test requests

The checker probes the site like an outsider, so the server would count those requests as attacks.
Before the web checks it asks the server for a short code (`python -m backend.core.security_log
--self-check-token`, derived from the server's session secret, valid 10 to 20 minutes) and sends it in
the `X-BKK-Self-Check` header. The request is still blocked exactly like any outsider's; the only
difference is that it is recorded as `self_check` and left out of every total. The header grants no access.
If the code cannot be read, the run still works and its probes are counted as attacks (the report says so).

## Deploy the server part

The recording only starts after the server runs the new code. Until then the report shows
"the Pi has not been updated yet" for attacks.

- Test server: on the PC, run `launch\test\restart.bat` (or `stop.bat`, then `start.bat`).
- Production (Raspberry Pi, systemd unit `bkk-production`): only with the owner's go-ahead.
  1. On the Pi, pull the latest code in the project folder.
  2. Run `sudo systemctl restart bkk-production`.
  3. Check that it came back: `systemctl status bkk-production`.

Restarting production briefly takes the public site offline, so do it when people are not using it.

## Live view

`launch\security_check\live.bat` (Desktop icon "BKK Security Live") starts a small receiver on this PC,
hidden, and opens http://127.0.0.1:8770/ in the browser. The page shows attacks as they happen: a world
map with an arc from the attacker's country to Bangkok, big counters, a live feed and alert banners.
A second launch only opens the browser again; the receiver quits by itself about 90 seconds after the
last browser tab is closed.

How it works:
- One long-lived read-only ssh connection to the Pi runs `python -m backend.core.security_stream`, which
  prints one JSON line per blocked web request (read from the security log, polled every 2 s) and per SSH
  login event (from the journal). It writes nothing and opens no port on the Pi. If the connection drops,
  the receiver reconnects (2 s, doubling up to 60 s).
- The receiver (`live.py`) adds owner / country / coordinates to each event and serves the page, `/state`
  and `/events` (Server-Sent Events) on 127.0.0.1 only. Foreign Host headers are refused.
- Events from the owner (own public IP, home network, loopback) are dimmed or hidden and never counted
  or drawn. The checker's own test requests (`self_check`) are never shown.
- `python -m launch.security_check.live --target test` runs the same thing against the local test
  instance (no ssh, no SSH events). Log: `local\logs\security_live.log`.

### LINE alerts (optional)

Alerts always appear on the page. To get them on your phone too (LINE Notify is discontinued, so this
uses the LINE Messaging API):
1. Open https://developers.line.biz/ and log in; create a Provider.
2. In the provider create a Messaging API channel.
3. Channel "Basic settings" tab: copy "Your user ID" (starts with `U`).
4. Channel "Messaging API" tab: issue "Channel access token (long-lived)" and copy it.
5. On the same tab scan the bot's QR code with LINE and add the bot as a friend (it can only push to friends).
6. Put both values in the repo `.env` (never commit them or paste them in chat):
   `LINE_CHANNEL_ACCESS_TOKEN=...` and `LINE_USER_ID=U...`
7. Test: `.venv\Scripts\python.exe -m launch.security_check.alerts --test` prints OK or failed
   (the token is never printed). Restart the live view; the page pill then says "LINE เปิด".

Rules (outside-the-house events only):

| Rule | Fires when |
|---|---|
| SSH login succeeded | any successful SSH login from a non-owner IP (once per IP per 30 min) |
| Web flood | 100 or more blocked web requests in 60 s |
| SSH guessing | 20 or more failed / invalid SSH attempts in 5 min |

Each rule has a 30 minute cooldown. At most 20 LINE messages a day (counter in
`local\logs\security_live_alerts.json`); after that one last message says the cap was reached and the
page keeps showing alerts. A failed send is logged (status code only) and shown as "LINE ส่งไม่สำเร็จ".

### Deploy note

The Pi must run the new code before the live view shows web attacks quickly: pull the repo on the Pi and
restart production (`sudo systemctl restart bkk-production`, with the owner's go-ahead). The restart brings
the 5 s security-log flush (was 30 s) and the `backend/core/security_stream.py` module that the PC starts
over ssh. Until then the page connects but shows no events.
