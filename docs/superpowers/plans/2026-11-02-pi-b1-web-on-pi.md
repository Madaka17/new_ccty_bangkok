# Pi B1: the web server runs on the Raspberry Pi with YOLO off — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The BKK StreetSmart server starts and serves on the Pi 4 (192.168.1.109) as a LAN-only test on :8001, with YOLO forced off and without fetching from BMA, while the PC keeps running production and the tunnel.

**Architecture:** The Pi uses the same code and the same `requirements.txt`, with CPU-only torch (uv `--torch-backend cpu`), so nothing has to be split out of the server. Two environment guards make a Pi run safe: `YOLO_ALLOWED=0` keeps every YOLO model unloaded even if someone presses the switch, and `BMA_FETCH=0` stops the BMA scan loop and archiver so the Pi never doubles our BMA traffic. systemd units in `launch/pi/` run the servers; only the test unit is used in B1.

**Tech Stack:** Python 3.14 (uv venv on the Pi), torch 2.15 CPU, FastAPI/uvicorn, systemd, Debian 12 aarch64.

**Spec:** chat decisions of 2026-11-02 (no separate spec file):
- Pi later runs production :8000, ENVIRO :5050, cloudflared, BMA fetching, DBs, backup and monitor web. The PC keeps YOLO, Bionic :1235, test :8001 and web builds.
- The user chose torch CPU on the Pi over a torch-free server.
- The AI worker on the PC (:8100 `/detect`) is a later plan, B2.
- Test before production. Never run cloudflared on the Pi while the PC tunnel runs.

## Global Constraints

- Pi: user `test`, repo at `/mnt/ssd/new_ccty_bangkok`, SSD mounted at `/mnt/ssd` (fstab `nofail`), SSH key `%USERPROFILE%\.ssh\bkkpi_ed25519`.
- Python on the Pi: `uv` CPython 3.14 in `/mnt/ssd/new_ccty_bangkok/.venv`; torch from the CPU backend, never the CUDA wheels (they pull about 20 `nvidia-*` packages).
- `YOLO_ALLOWED=0` and `BMA_FETCH=0` are set in every Pi unit used in B1. Unset (the PC) means today's behaviour exactly.
- The B1 test is LAN only. Do not start, enable or configure cloudflared on the Pi. Do not touch the PC's production :8000, test :8001, ENVIRO or tunnel.
- The production and ENVIRO units are written and checked with `systemd-analyze verify`, but not installed or enabled in B1.
- Docs and UI text in plain Thai, like the rest of `docs/MIGRATE_MACHINE.md`.

## Review Focus

1. Something calls `YOLO(...)` while YOLO is off: `BmaScanner._detect` falls back to a local model, and the helmet, wrong-way and violation patrols load lazily. On the Pi, ultralytics would download weights and run on the CPU. Expect: with `YOLO_ALLOWED=0` no code path constructs a YOLO model (Task 1 test pins the switch; Task 5 checks the log for "Downloading").
2. A unit starts before `/mnt/ssd` is mounted after a power cut. Expect: the unit waits for the mount (`RequiresMountsFor=/mnt/ssd`) instead of failing or writing to the SD card.
3. OpenCV needs system libraries (`libGL.so.1`) that the Pi image may lack. Expect: Task 3's import check catches it, and `setup.sh` installs them.
4. Memory and CPU after an hour on the Pi. Expect: resident memory under 2 GB and idle CPU under 25 % on the test unit (Task 5 records both).
5. `.env` carries API keys. Expect: it is copied to the Pi with mode 600 and never committed.

---

### Task 1: `YOLO_ALLOWED=0` keeps YOLO off

**Files:**
- Modify: `backend/vision/yolo_switch.py` (`YoloSwitch.__init__`, `YoloSwitch.set`, `_status`)
- Modify: `backend/services.py:87` (pass the env value)
- Test: `tests/test_yolo_switch.py`

**Interfaces:**
- Produces: `YoloSwitch(state_path, cuda=_default_cuda, allowed=True)`. With `allowed=False`, `enabled` is `False` whatever the saved state says. `set(True)` loads nothing, keeps `enabled=False`, does not write the state file, and returns the status with `errors == {"switch": "YOLO is not allowed on this machine (YOLO_ALLOWED=0)"}`. `status()["allowed"]` is the flag.

- [ ] **Step 1: Write the failing tests**

```python
def test_not_allowed_ignores_saved_on_state(tmp_path):
    p = tmp_path / "yolo_switch.json"
    p.write_text('{"enabled": true, "changed_at": 5}')
    sw = YoloSwitch(str(p), cuda=None, allowed=False)
    assert sw.enabled is False
    assert sw.status()["allowed"] is False

def test_not_allowed_refuses_to_switch_on(tmp_path):
    holder = FakeHolder()                      # the file's existing fake; records load_models calls
    p = tmp_path / "yolo_switch.json"
    sw = YoloSwitch(str(p), cuda=None, allowed=False)
    sw.register("detector", holder)
    out = sw.set(True)
    assert out["enabled"] is False
    assert "YOLO_ALLOWED=0" in out["errors"]["switch"]
    assert holder.loads == 0
    assert not p.exists()
```

Use the fake holder already defined in `tests/test_yolo_switch.py`; adapt the attribute name to it.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests/test_yolo_switch.py -q`
Expected: 2 failed with `TypeError: ... unexpected keyword argument 'allowed'`

- [ ] **Step 3: Implement the `allowed` flag in `YoloSwitch`, then pass `allowed=os.getenv("YOLO_ALLOWED", "1") != "0"` in `backend/services.py`. Print `[YOLO] not allowed on this machine (YOLO_ALLOWED=0)` at start when false.**

- [ ] **Step 4: Run the YOLO tests**

Run: `.venv\Scripts\python -m pytest tests/test_yolo_switch.py tests/test_yolo_api.py tests/test_yolo_holders.py tests/test_yolo_off_callers.py -q`
Expected: all pass

- [ ] **Step 5: Commit** `feat(yolo): YOLO_ALLOWED=0 keeps every model off on machines without a GPU`

### Task 2: `BMA_FETCH=0` stops the BMA scan loop and archiver

**Files:**
- Modify: `backend/bma/bma_service.py` (`BmaScanner.__init__`, around the `archiver.run_forever()` call and the `auto_scan_thread` start)
- Test: `tests/test_bma_fetch_off.py` (new)

**Interfaces:**
- Produces: module function `bma_fetch_enabled(env=os.environ) -> bool`, false only when `env.get("BMA_FETCH") == "0"`. With it false, `BmaScanner` starts neither the archiver loop nor `auto_scan_thread`, and prints `[BMA Scanner] BMA_FETCH=0: no fetching from BMA on this machine`. Everything else (camera list, cached frames, analytics cache) still loads, so pages that read cached data keep working.

- [ ] **Step 1: Write the failing tests**

```python
def test_fetch_on_by_default():
    assert bma_fetch_enabled({}) is True

def test_fetch_off_with_zero():
    assert bma_fetch_enabled({"BMA_FETCH": "0"}) is False

def test_fetch_on_with_other_values():
    assert bma_fetch_enabled({"BMA_FETCH": "1"}) is True
```

Also check whether any other module starts its own BMA requests at import or in `services.start()` (grep `bma_site`, `BmaSession`). If one does, add it behind the same function and ledger a ruling.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest tests/test_bma_fetch_off.py -q`
Expected: ImportError for `bma_fetch_enabled`

- [ ] **Step 3: Implement `bma_fetch_enabled` and use it in `BmaScanner.__init__`.**

- [ ] **Step 4: Run the BMA tests**

Run: `.venv\Scripts\python -m pytest tests/test_bma_fetch_off.py tests/test_bma_yolo_off.py -q`
Expected: all pass

- [ ] **Step 5: Commit** `feat(bma): BMA_FETCH=0 starts no BMA fetching, for a second machine on the same IP`

### Task 3: Pi setup script

**Files:**
- Create: `launch/pi/setup.sh`

**Interfaces:**
- Produces: `bash launch/pi/setup.sh`, run on the Pi from the repo root. It is idempotent. It installs the apt packages OpenCV and the server need (at least `libgl1 libglib2.0-0 ffmpeg sqlite3`), creates `.venv` with `uv venv --python 3.14`, runs `uv pip install -p .venv -r requirements.txt --torch-backend cpu`, does the same for `ENVIRO/.venv` with `ENVIRO/requirements.txt`, and ends with an import check.

- [ ] **Step 1: Write the script.** The last step prints the import check:
  `.venv/bin/python -c "import torch, cv2, ultralytics, fastapi; print(torch.__version__, torch.cuda.is_available(), cv2.__version__)"`

- [ ] **Step 2: Pull the branch on the Pi and run it**

Run (from the PC): `ssh -i %USERPROFILE%\.ssh\bkkpi_ed25519 test@192.168.1.109 "cd /mnt/ssd/new_ccty_bangkok && git fetch -q && git checkout feat/pi-b1 && bash launch/pi/setup.sh"`
Expected: last line like `2.15.0+cpu False 5.0.0`, and `uv pip list -p .venv | grep -ci nvidia` prints `0`.

  The Pi clone has no access to an unpushed local branch. Push the branch to GitHub first only with the user's go; otherwise copy the changed files with `scp`. Ledger which way was used.

- [ ] **Step 3: Run the test suite on the Pi**

Run: `.venv/bin/python -m pytest -q -p no:cacheprovider` on the Pi
Expected: same pass count as on the PC (571 plus this plan's new tests). Tests that need a GPU or Windows may skip; ledger each failure as a ruling (fix, or why it is PC-only).

- [ ] **Step 4: Commit** `feat(pi): setup script for the Raspberry Pi (CPU torch, ENVIRO venv)`

### Task 4: systemd units

**Files:**
- Create: `launch/pi/bkk-test.service`, `launch/pi/bkk-production.service`, `launch/pi/bkk-enviro.service`, `launch/pi/install_units.sh`

**Interfaces:**
- Produces: units with `User=test`, `WorkingDirectory=/mnt/ssd/new_ccty_bangkok` (ENVIRO: `.../ENVIRO`), `RequiresMountsFor=/mnt/ssd`, `After=network-online.target`, `Restart=always`, `RestartSec=5`, `EnvironmentFile=-/mnt/ssd/new_ccty_bangkok/.env`, and `ExecStart` running `.venv/bin/python server.py` directly (no web build on the Pi).
  - `bkk-test`: `PORT=8001 INSTANCE_DIR=.../instances/test BMA_DATA_DIR=.../instances/test/data YOLO_ALLOWED=0 BMA_FETCH=0 OPENCV_FFMPEG_LOGLEVEL=-8`.
  - `bkk-production`: `PORT=8000 INSTANCE_DIR=.../instances/production YOLO_ALLOWED=0 OPENCV_FFMPEG_LOGLEVEL=-8`; BMA fetching on (the Pi takes it over at cutover). A comment says it is enabled only at cutover (step D).
  - `bkk-enviro`: `PORT=5050`, `ExecStart=.../ENVIRO/.venv/bin/python main.py`. Run `lock_accounts.py` as `ExecStartPre`, like `launch/enviro/start.bat`.
  - `install_units.sh <unit>...` copies the named units to `/etc/systemd/system/` and runs `daemon-reload`. It never enables anything.

- [ ] **Step 1: Write the units and the script.**

- [ ] **Step 2: Verify the units on the Pi**

Run: `systemd-analyze verify launch/pi/*.service`
Expected: no output except possibly a warning about `.env` not existing yet.

- [ ] **Step 3: Commit** `feat(pi): systemd units for test, production and ENVIRO on the Pi`

### Task 5: Smoke test on the Pi :8001, then the runbook

**Files:**
- Modify: `docs/MIGRATE_MACHINE.md` (new section "ย้ายไป Raspberry Pi")

- [ ] **Step 1: Copy what the test server needs from the PC to the Pi**, read-only on the PC:
  - `.env`, then `chmod 600` on the Pi.
  - `instances/test/dist/` (the web build).
  - The files `launch/test/start.sh` seeds from `instances/production` (`cache/longdo_cameras.json`, `cache/bma_events.json`, `cache/traffic_history.json`, `cache/twa_key.json`, `cache/rsc/`, `vehicle_counts.db`, `count_cameras.json`) into the Pi's `instances/test/`.
  - Any `config/` file the server reads that git does not track.
  Use `scp -r`. The Pi side is empty, so nothing is overwritten.

- [ ] **Step 2: Start the test unit**

Run on the Pi: `bash launch/pi/install_units.sh bkk-test.service && sudo systemctl start bkk-test && sleep 60 && journalctl -u bkk-test -n 80 --no-pager`
Expected:
  - `[YOLO] not allowed on this machine (YOLO_ALLOWED=0)` and `BMA_FETCH=0`.
  - No `Traceback` and no `Downloading`.
  - Uvicorn is listening on :8001.

- [ ] **Step 3: Check it from the PC**

Run: `curl -s -o NUL -w "%{http_code}" http://192.168.1.109:8001/`, then open `http://192.168.1.109:8001/` in a browser and look at the home page, the map and a camera page.
Expected: `200`, and the pages render with cached data. Live AI shows as off.

- [ ] **Step 4: Check the switch refuses**

In the browser, press YOLO on in the admin page, or POST to the `yolo_set` route from `backend/api/live_ai.py` with the browser session.
Expected: it stays off and shows the `YOLO_ALLOWED=0` error.

- [ ] **Step 5: Measure after one hour**

Run on the Pi: `systemctl show bkk-test -p MemoryCurrent; top -bn1 | head -15`
Expected: memory under 2 GB, idle CPU under 25 %. Ledger the numbers.

- [ ] **Step 6: Stop the test unit and leave it disabled**

Run: `sudo systemctl stop bkk-test`
Expected: inactive, and `systemctl is-enabled bkk-test` prints `disabled`.

- [ ] **Step 7: Write the runbook section** in plain Thai:
  - what runs where;
  - `setup.sh`;
  - the two environment guards and why;
  - the units;
  - "never start cloudflared on the Pi while the PC tunnel runs";
  - steps C (first data copy) and D (cutover) as outlines that say they are not done yet.

- [ ] **Step 8: Commit** `docs(migrate): Raspberry Pi section — what runs where, setup, units`
