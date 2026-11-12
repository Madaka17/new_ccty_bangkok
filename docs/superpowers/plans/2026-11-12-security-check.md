# Security Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The server records every request it blocks plus vulnerability probes (30 days). A double-click program on the PC builds a Thai HTML report showing how often the site was attacked and what to fix in the web config and on the Pi.

**Architecture:** `backend/core/security_log.py` buffers events in memory and a daemon thread flushes them every 30 s to `<INSTANCE_DIR>/security_events.db`, as hourly counts plus the latest 500 events. `access_guard.guard` records each deny and each probe path. `launch/security_check/` holds pure `evaluate_*` rule functions, collectors (HTTP, ssh read-only to the Pi, local) and an HTML renderer. `check.bat` runs it and opens the report.

**Tech Stack:** Python 3 stdlib (sqlite3, threading, urllib, ssl, subprocess, html), FastAPI middleware, pytest.

**Spec:** User decisions 2026-11-12 (this session): standalone program that writes a report; count everything blocked + vulnerability scans; check web config + Pi host (read-only, never auto-fix); keep 30 days.

## Global Constraints

- Report text in short plain Thai. Technical names (header names, ports, env keys) stay as-is.
- Never print or store secret values. `.env` checks report only "set / not set / length ≥ N" and on/off.
- Pi access is read-only: ssh with key `C:\Users\user\.ssh\bkkpi_ed25519`, user `test`, host `192.168.1.109`, `-o BatchMode=yes`. Commands may use `sudo -n` for read-only queries only. No writes on the Pi.
- Public HTTP checks send a browser User-Agent (`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36`), because Cloudflare returns 403 to Python's default User-Agent.
- Requests from trusted networks (`access_guard.is_trusted`) are never recorded.
- `security_log.record()` must not block or raise in the request path. A failing DB write is logged once and swallowed.
- Retention: hourly rows older than 30 days are deleted at flush; `recent` keeps the newest 500 rows.
- Reports go to `local/reports/security/security-YYYYmmdd-HHMM.html` (git-ignored).
- Tests run with the main tree's venv from the worktree root: `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests/<file> -q`.
- Ship to test :8001 first. A production deploy (Pi backend restart) happens only on the user's go.

## Review Focus

- Pi unreachable (ssh timeout/denied): the report must still render, with host and attack sections marked "ต่อ Pi ไม่ได้" instead of crashing. Test in Task 4.
- Empty or missing `security_events.db` (fresh install): `summary()` returns zeros and the report says "ยังไม่มีข้อมูล". Test in Task 1.
- A legitimate SPA route that looks like a probe (e.g. `/admin` is not a site route, but `/water`, `/map` are): `is_probe()` must not match real app routes. Test in Task 2.
- Thousands of events per minute from one IP (flood): the memory buffer is bounded (drop the oldest beyond 10 000 and count the drops). Test in Task 1.
- Public site behind SPA fallback returns 200 `text/html` for `/.env`: the web check must treat an HTML body as "not exposed". Test in Task 3.

---

### Task 1: Security event log

**Files:**
- Create: `backend/core/security_log.py`
- Test: `tests/test_security_log.py`

**Interfaces:**
- Produces:
  - `KINDS: tuple[str, ...] = ("bad_path", "docs_probe", "control_denied", "not_browser", "no_session", "rate_limited", "chat_limited", "report_limited", "too_large", "probe")`
  - `class SecurityLog(db_path: str, clock=time.time, buffer_max=10_000)`
    - `record(kind: str, ip: str, path: str, method: str = "GET", ua: str = "") -> None`: appends to the buffer. Thread-safe. Never raises. Truncates `path` to 300 chars and `ua` to 200. An unknown kind is stored as given.
    - `flush() -> int`: writes the buffered events and returns their count. Upserts `hourly(hour TEXT 'YYYY-MM-DDTHH', kind TEXT, n INTEGER, PRIMARY KEY(hour, kind))` in local time, inserts into `recent(ts REAL, kind, ip, path, method, ua)`, keeps the newest 500 `recent` rows, and deletes `hourly` rows older than 30 days. Buffer overflow drops are added as kind `dropped`.
    - `start(interval: float = 30.0) -> None`: starts one daemon thread that calls `flush()` every interval. Idempotent.
    - `summary(days: int = 30) -> dict`: returns `{"days": int, "total": int, "by_kind": {kind: n}, "by_day": [{"day": "YYYY-MM-DD", "n": int}] (oldest first, every day in the range, zeros included), "top_ips": [{"ip", "n"}] (top 10 from recent), "top_paths": [{"path", "n"}] (top 10 from recent), "recent": [last 50 events newest first as dicts], "generated": ISO time}`. A missing DB returns the same shape with zeros.
  - Module singleton `log = SecurityLog(os.path.join(DATA_DIR, "security_events.db"))`.
  - CLI `python -m backend.core.security_log --summary-json [--days N]`: prints `json.dumps(log.summary(N), ensure_ascii=False)`. Reads only; never creates the DB file.

- [ ] **Step 1: Write failing tests** in `tests/test_security_log.py`. Use `tmp_path` and a fake clock.

```python
def test_flush_counts_by_hour_and_kind(tmp_path): ...
    # record 3 'probe' + 1 'rate_limited' at the same hour -> flush() == 4;
    # summary()["by_kind"] == {"probe": 3, "rate_limited": 1}; summary()["total"] == 4
def test_summary_missing_db_is_zero(tmp_path):
    s = SecurityLog(str(tmp_path / "none.db")).summary(30)
    assert s["total"] == 0 and len(s["by_day"]) == 30 and all(d["n"] == 0 for d in s["by_day"])
    assert not (tmp_path / "none.db").exists()
def test_recent_capped_at_500(tmp_path): ...       # 600 events -> 500 rows in recent
def test_old_hours_pruned_after_30_days(tmp_path): ...  # event at day 0, flush at day 31 -> gone from summary
def test_buffer_overflow_counts_dropped(tmp_path): ...  # buffer_max=5, record 8 -> by_kind["dropped"] == 3
def test_top_ips_and_paths(tmp_path): ...          # ip A x3, B x1 -> top_ips[0] == {"ip": "A", "n": 3}
def test_record_never_raises(tmp_path):            # db_path in a missing, unwritable dir -> flush() returns 0, no exception
```

- [ ] **Step 2:** Run `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests/test_security_log.py -q`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `backend/core/security_log.py` per the Interfaces. Use one `sqlite3` connection per flush or summary, opened with `timeout=5`, and WAL mode on create.
- [ ] **Step 4:** Re-run. Expected: all pass.
- [ ] **Step 5: Commit** `git add backend/core/security_log.py tests/test_security_log.py && git commit -m "feat(security): record blocked requests to a 30-day event log"`

### Task 2: Guard records denies and probes

**Files:**
- Modify: `backend/core/access_guard.py` (the `guard` function and `_deny` call sites)
- Modify: `server.py` (start the flusher next to the guard middleware, ~line 97)
- Test: `tests/test_access_guard.py` (append)

**Interfaces:**
- Consumes: `security_log.log.record(kind, ip, path, method, ua)` and `security_log.log.start()` from Task 1.
- Produces:
  - `access_guard.PROBE_PATH`: compiled case-insensitive regex for vulnerability-scan paths: `/\.env`, `/\.git(/|$)`, `/wp-`, `/wordpress`, `phpmyadmin`, `\.php(\?|$)`, `/cgi-bin/`, `/actuator`, `/server-status`, `/\.aws`, `/\.ssh`, `/vendor/phpunit`, `/boaform`, `/HNAP1`, `/\.DS_Store`, `xmlrpc`, `/admin(/|$)`, `/config\.(json|yml|yaml)$`, `/backup`, `\.sql$`.
  - `access_guard.is_probe(path: str) -> bool`.
  - Behaviour: for an untrusted request whose path matches `is_probe`, record `probe` and return `_deny(404, "not found")` before routing. Every existing `_deny` for an untrusted request records its kind first: 400 bad path → `bad_path`; docs → `docs_probe`; control 403 → `control_denied`; parking/user-report 429 → `report_limited`; chat 429 → `chat_limited`; 413 (both) → `too_large`; browser-only 403 → `not_browser`; session 403 → `no_session`; general 429 → `rate_limited`. For `bad_path`, compute trust first so trusted requests are not recorded. The `ua` argument is the `user-agent` header.

- [ ] **Step 1: Write failing tests** (append to `tests/test_access_guard.py`). Build a small FastAPI app with `app.middleware("http")(access_guard.guard)` and one `GET /api/ping` route, monkeypatch `access_guard.security_log.log` (or the module attribute the guard uses) with a fake that collects calls, and set `client=("203.0.113.9", 1234)` via `TestClient(app, client=(...))` where available, else monkeypatch `access_guard.is_trusted`/`client_ip`.

```python
def test_probe_path_recorded_and_404(): ...        # GET /.env from untrusted -> 404, fake got ("probe", ip, "/.env", "GET", ua)
def test_probe_from_trusted_not_recorded(): ...    # same from 127.0.0.1 -> no record
def test_app_routes_are_not_probes():
    for p in ("/", "/map", "/water", "/assets/index-abc.js", "/api/traffic/summary", "/enviro/", "/admin-guide"):
        assert not access_guard.is_probe(p)
    for p in ("/.env", "/wp-login.php", "/.git/HEAD", "/phpmyadmin/", "/admin", "/cgi-bin/x", "/db.sql"):
        assert access_guard.is_probe(p)
def test_session_denial_recorded_as_no_session(): ...  # untrusted /api/ping with same-origin header, no cookie -> 403 and kind "no_session"
def test_control_denial_recorded(): ...            # untrusted POST /api/ping -> 403, kind "control_denied"
```

- [ ] **Step 2:** Run `... -m pytest tests/test_access_guard.py -q`. Expected: new tests FAIL.
- [ ] **Step 3: Implement** in `access_guard.py`: `from backend.core import security_log`, `PROBE_PATH`, `is_probe`, and a helper `_block(request, ip, kind, status, msg)` that calls `security_log.log.record(...)` and returns `_deny(status, msg)`. In `server.py`, after `app.middleware("http")(access_guard.guard)`, call `security_log.log.start()`.
- [ ] **Step 4:** Re-run the full guard file plus `tests/test_security_log.py`. Expected: all pass. Then run the whole suite: `... -m pytest tests -q -x`. Expected: no new failures (compare the failure list with `main` if any test already fails there).
- [ ] **Step 5: Commit** `git commit -am "feat(security): guard records blocked requests and probe scans"`

### Task 3: Rules that turn facts into findings

**Files:**
- Create: `launch/security_check/__init__.py` (empty), `launch/security_check/rules.py`
- Test: `tests/test_security_rules.py`

**Interfaces:**
- Produces (all pure, no I/O):
  - `Finding = dict` with keys `area` ("attack" | "web" | "config" | "host"), `level` ("ok" | "info" | "warn" | "fail"), `title` (Thai), `detail` (Thai, may be ""), `fix` (Thai, "" when level is ok/info).
  - `evaluate_attacks(summary: dict | None) -> list[Finding]`: `None` gives one `info` finding "ต่อ Pi ไม่ได้ ดูยอดโจมตีไม่ได้". `total == 0` gives `ok` "ยังไม่มีข้อมูล / ไม่พบการโจมตี". Otherwise: one `info` with the total and the top kinds in Thai. `warn` if `probe` ≥ 100 in the period ("มีการสแกนหาช่องโหว่บ่อย", fix: add a Cloudflare WAF rule that blocks the top paths, or block the top IPs). `warn` if one IP accounts for ≥ 50 % of `recent` and ≥ 50 events (fix: block that IP in Cloudflare → Security → WAF → Tools). `warn` if `rate_limited` + `chat_limited` ≥ 500 (fix: turn on Cloudflare Rate Limiting). `info` if `dropped` > 0.
  - Thai kind labels `KIND_TH` for all `KINDS` plus `dropped`: probe "สแกนหาช่องโหว่", bad_path "path อันตราย", docs_probe "แอบดูหน้าเอกสาร API", control_denied "สั่งปุ่มควบคุมจากนอกบ้าน", not_browser "สคริปต์ดึง API", no_session "เรียก API ไม่ผ่านหน้าเว็บ", rate_limited "ยิงถี่เกิน", chat_limited "ใช้แชท AI ถี่เกิน", report_limited "แจ้งเหตุถี่เกิน", too_large "ส่งข้อมูลใหญ่เกิน", dropped "นับไม่ทัน (ทิ้ง)".
  - `evaluate_web(checks: dict) -> list[Finding]`, with input keys: `headers` (dict, lowercase names, of `GET /`), `status` ({path: (code, content_type, body_head)} for `/docs`, `/openapi.json`, `/.env`, `/.git/HEAD`, `/api/traffic/summary`), `cert_days_left` (int | None). Rules: each of `content-security-policy`, `strict-transport-security`, `x-frame-options`, `x-content-type-options`, `referrer-policy` missing → `fail`. `/docs` or `/openapi.json` code 200 with a non-HTML body → `fail`. `/.env` or `/.git/HEAD` code 200 whose content type is not `text/html` (the SPA fallback is HTML) → `fail` ("ไฟล์ลับเปิดให้โหลดได้"). `/api/traffic/summary` without a cookie returning 200 → `warn` (API_SESSION off). `cert_days_left` < 14 → `warn`, < 3 → `fail`. A `server` header containing a version number → `info`. Missing keys are skipped, never treated as failures.
  - `evaluate_config(flags: dict | None) -> list[Finding]`, with input keys: `admin_token_len` (int), `api_session` (bool), `api_browser_only` (bool), `general_rate_per_min` (int), `chat_rate_per_day` (int). `None` gives `info` "อ่านค่าตั้งไม่ได้". Rules: `admin_token_len` 0 → `warn` (not set; LAN-only control); 1–23 → `fail` (too short, fix: 32+ random characters). `api_session` False → `warn`. `api_browser_only` False → `warn`. Either rate 0 → `warn` (limit off).
  - `evaluate_host(raw: dict | None) -> list[Finding]`, with input keys: `listen` (list of "addr:port" strings from `ss -Htln`), `sshd` ({"passwordauthentication": "yes"|"no", "permitrootlogin": ..., "kbdinteractiveauthentication": ...}), `firewall` ("active" | "inactive" | "none"), `upgradable` (int), `unattended` (bool), `reboot_required` (bool), `fail2ban` (bool). `None` gives `info` "ต่อ Pi ไม่ได้". Rules: `passwordauthentication` yes → `fail` (fix: set `PasswordAuthentication no` in `/etc/ssh/sshd_config`; the key already works). `permitrootlogin` not in ("no", "prohibit-password") → `fail`. Firewall not active → `warn` (fix: `sudo ufw allow from 192.168.1.0/24` then `sudo ufw enable`). Ports on 0.0.0.0, `*` or `[::]` other than the known set {22: SSH, 8000: เว็บ, 5050: ENVIRO, 9101: pistats, 8090: monitor} → `warn` per port; 5900 → `warn` "VNC เปิดให้ทั้งวง LAN". `upgradable` ≥ 20 → `warn` (fix: `sudo apt update && sudo apt upgrade`). `unattended` False → `info`. `reboot_required` → `warn`. `fail2ban` False → `info`.
  - `overall(findings: list[Finding]) -> str`: "fail" if any fail, else "warn" if any warn, else "ok".

- [ ] **Step 1: Write failing tests** (`tests/test_security_rules.py`, `sys.path` insert of `launch/` or import `launch.security_check.rules` — use whichever import works with conftest's root on sys.path; add `launch/__init__.py` only if needed and say so):

```python
def test_attacks_none_is_info(): assert evaluate_attacks(None)[0]["level"] == "info"
def test_attacks_zero_is_ok(): ...
def test_many_probes_warns(): ...                  # by_kind probe=150 -> a warn whose title mentions "ช่องโหว่"
def test_one_ip_dominates_warns(): ...             # recent: 60 of 80 events from one IP -> warn
def test_web_missing_csp_fails(): ...
def test_web_env_html_fallback_is_ok():
    f = evaluate_web({"status": {"/.env": (200, "text/html; charset=utf-8", "<!doctype html>")}})
    assert all(x["level"] != "fail" for x in f)
def test_web_env_plain_text_fails(): ...           # (200, "text/plain", "ADMIN_TOKEN=...") -> fail
def test_web_missing_keys_skipped(): assert evaluate_web({}) == [] or all(x["level"] in ("ok", "info") for x in evaluate_web({}))
def test_config_short_token_fails(): ...           # admin_token_len 10 -> fail
def test_config_never_contains_secret_text(): ...  # no finding text contains the digits of the length? -> just assert no key "value" in output
def test_host_password_ssh_fails(): ...
def test_host_unknown_port_warns(): ...            # listen ["0.0.0.0:3306"] -> warn mentioning 3306
def test_host_loopback_ports_ignored(): ...        # ["127.0.0.1:8001", "127.0.0.2:8000"] -> no port warn
def test_overall(): ...
```

- [ ] **Step 2:** Run `... -m pytest tests/test_security_rules.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `rules.py` per the Interfaces. Each finding's Thai text is short and plain.
- [ ] **Step 4:** Re-run. Expected: all pass.
- [ ] **Step 5: Commit** `git add launch/security_check tests/test_security_rules.py && git commit -m "feat(security): rules that turn checks into Thai findings"`

### Task 4: Collectors, report and launcher

**Files:**
- Create: `launch/security_check/collect.py`, `launch/security_check/report.py`, `launch/security_check/main.py`, `launch/security_check/check.bat`
- Modify: `.gitignore` (add `local/reports/`)
- Test: `tests/test_security_report.py`

**Interfaces:**
- Consumes: `rules.*` (Task 3); the CLI `python -m backend.core.security_log --summary-json` (Task 1).
- Produces:
  - `collect.py`:
    - `PI = {"host": "192.168.1.109", "user": "test", "key": r"C:\Users\user\.ssh\bkkpi_ed25519", "repo": "/mnt/ssd/new_ccty_bangkok"}`
    - `ssh(cmd: str, timeout: int = 20) -> str | None`: runs `ssh -i KEY -o BatchMode=yes -o ConnectTimeout=8 user@host cmd` and returns stdout, or None on any failure/timeout.
    - `pi_attack_summary(days=30) -> dict | None`: ssh `cd REPO && INSTANCE_DIR=REPO/instances/production .venv/bin/python -m backend.core.security_log --summary-json --days N`, parsed JSON or None.
    - `local_attack_summary(instance_dir: str, days=30) -> dict | None`: same through the local `.venv` python, run as a subprocess with cwd = repo root.
    - `pi_config_flags() -> dict | None`: ssh runs a Python one-liner in REPO that loads `.env` with `dotenv_values` and prints JSON `{admin_token_len, api_session, api_browser_only, general_rate_per_min, chat_rate_per_day}`. Defaults follow `access_guard`: API_SESSION/API_BROWSER_ONLY on unless "0", 600/min, 60/day. Never print values.
    - `local_config_flags(env_path: str) -> dict`: same logic on a local `.env` path.
    - `pi_host_raw() -> dict | None`: one ssh call that runs `ss -Htln`, `sudo -n sshd -T 2>/dev/null | grep -Ei '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication) '`, `sudo -n ufw status 2>/dev/null | head -1` (no ufw → `none`), `apt list --upgradable 2>/dev/null | grep -c upgradable`, `dpkg -s unattended-upgrades >/dev/null 2>&1 && echo yes`, `test -f /var/run/reboot-required && echo yes`, `systemctl is-active fail2ban`. Sections are separated by marker lines (`@@listen`, `@@sshd`, ...) and parsed into the `evaluate_host` input shape. The parser is `parse_host_output(text: str) -> dict`, a separate pure function.
    - `web_checks(base_url: str) -> dict`: urllib with the browser User-Agent and a 15 s timeout. Fetches `GET /` (headers) and the status paths from Task 3 (status, content type and the first 200 bytes; urllib HTTPError still yields its code). For https, reads cert expiry via `ssl` to give `cert_days_left`. Returns the `evaluate_web` input shape.
  - `report.py`: `render(target: str, sections: dict[str, list[Finding]], summary: dict | None, generated: str) -> str`. A self-contained HTML page (inline CSS, no external requests, dark near-black + orange like the site, `lang="th"`, font stack `"Noto Sans Thai Looped", system-ui, sans-serif`), all text escaped with `html.escape`. It has:
    - A headline verdict ("ปลอดภัยดี" / "ควรดู" / "ต้องแก้") from `overall`.
    - Attack totals: big number of blocked requests in N days, a per-day bar strip drawn as inline SVG or CSS bars, a table by kind (Thai label + count), and top IPs and top paths.
    - A "ควรแก้อะไร" list: every warn/fail finding sorted fail first, with its `fix`.
    - All checks grouped by area with ✓/!/✗ status text (not colour alone).
  - `main.py`: `main(argv=None) -> int`. Args: `--target production|test` (default production), `--days 30`, `--no-open`. Production: Pi summary + Pi config + Pi host + web `https://bkksmartstreet.com`. Test: local summary for `instances/test` + local `.env` + web `http://localhost:8001` + no host checks (host section: `info` "ตรวจเครื่อง Pi เฉพาะ production"). Writes `local/reports/security/security-<target>-YYYYmmdd-HHMM.html` and opens it with `webbrowser.open` unless `--no-open`. Prints the path and the overall verdict. Exit code 0 even when findings fail; 1 only on a crash.
  - `check.bat`: `chcp 65001`, cd to the repo root, run `.venv\Scripts\python.exe -m launch.security_check.main %*`, then `pause`.

- [ ] **Step 1: Write failing tests** (`tests/test_security_report.py`):

```python
def test_parse_host_output(): ...       # fixture text with @@ markers -> listen list, sshd dict, firewall "inactive", upgradable 12, unattended True
def test_parse_host_output_garbage_is_safe(): assert isinstance(parse_host_output("nonsense"), dict)
def test_render_escapes_and_shows_verdict(): ...  # finding title "<script>" -> "&lt;script&gt;" in html; "ต้องแก้" present when a fail exists
def test_render_without_summary(): ...  # summary None -> html contains "ต่อ Pi ไม่ได้" or "ยังไม่มีข้อมูล", no exception
def test_main_pi_unreachable(monkeypatch, tmp_path): ...
    # monkeypatch collect.ssh -> None and collect.web_checks -> {}; main(["--no-open", ...]) returns 0 and writes a file
    # (monkeypatch the reports dir to tmp_path)
def test_local_config_flags_never_returns_values(tmp_path): ...  # .env with ADMIN_TOKEN=supersecretvalue123 -> json dump of result has no "supersecret"
```

- [ ] **Step 2:** Run `... -m pytest tests/test_security_report.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `collect.py`, `report.py`, `main.py`, `check.bat`, and the `.gitignore` line.
- [ ] **Step 4:** Re-run the three new test files. Expected: all pass.
- [ ] **Step 5: Smoke run** (no browser): `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m launch.security_check.main --target production --no-open`. Expected: prints a report path and a verdict. The Pi attack section may say there is no data yet, because the Pi has no event log until deploy. Then report which findings came out.
- [ ] **Step 6: Commit** `git add launch/security_check .gitignore tests/test_security_report.py && git commit -m "feat(security): security check program with Thai HTML report"`

### Task 5: Docs

**Files:**
- Create: `docs/SECURITY_CHECK.md`: what it records, where the DB lives, how to run `launch\security_check\check.bat` (`--target test`), what each Thai kind means, and how to deploy the server part (restart the instance).

- [ ] **Step 1:** Write the doc in plain English, ≤ 80 lines.
- [ ] **Step 2: Commit** `git add docs/SECURITY_CHECK.md && git commit -m "docs: security check guide"`
