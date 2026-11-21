# SmallTV PC Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The SmallTV desk display at 192.168.1.111 shows the Windows PC's CPU %, RAM %, VRAM % (RTX 3080) and GPU temperature instead of the Raspberry Pi's stats.

**Architecture:** A new stdlib-only Python service `pcstats.py` runs on the PC (192.168.1.188). It samples CPU and RAM through Win32 `ctypes` calls and VRAM and GPU temperature through `nvidia-smi` once per second. It serves JSON at `GET :9101/stats`, with the same contract as `pistats.py` (503 when the sampler stalls). Firmware 1.4.0 parses the new JSON and draws a new built-in look. The stored Screen Studio design is reset, so only the built-in look is used.

**Tech Stack:** Python 3.14 stdlib (`ctypes`, `subprocess`, `http.server`), pytest; ESP8266 Arduino with TFT_eSPI and ArduinoJson 7.4.3, PlatformIO with Unity native tests.

**Spec:** User decisions from the chat on 2026-11-21:
- Show the PC, not the Pi.
- Show CPU %, RAM %, VRAM % and GPU temperature.
- Use the built-in look and reset the stored design. Update Screen Studio later.
- Start the server at logon from Task Scheduler, with a firewall rule.

## Global Constraints

- Work in worktree `E:\new_ccty_bangkok-pcstats` on branch `feat/smalltv-pc-stats`. Commit locally only and do not push.
- Python tests: `E:\new_ccty_bangkok\.venv\Scripts\python -m pytest tests/test_pcstats.py -q` (run from the worktree root).
- Firmware tests: `E:\new_ccty_bangkok\local\pio\.venv\Scripts\pio test -d device/smalltv -e native`. Build: `... pio run -d device/smalltv -e smalltv`. `g++` (WinLibs) is already on PATH.
- `pcstats.py` uses the stdlib only. It must run under `pythonw.exe` with no console, so pass `creationflags=subprocess.CREATE_NO_WINDOW` to every `subprocess.run`.
- Port `9101`, path `/stats`, GET only. Bind `0.0.0.0`.
- Firmware version `1.4.0`. Default `STATS_URL` is `"http://192.168.1.188:9101/stats"`.
- Comments and docs are in plain English, in the style of the existing files.
- Never flash the display without asking the user first.

## JSON contract (`GET /stats`, 200)

```json
{"cpu": 12.5, "ram": 41.0, "ram_used_mb": 13420, "ram_total_mb": 32684,
 "vram": 85.8, "vram_used_mb": 8789, "vram_total_mb": 10240, "temp_c": 55.0, "uptime_s": 12345}
```

When `nvidia-smi` fails, times out or gives unparsable output, the JSON has `"vram": null, "vram_used_mb": 0, "vram_total_mb": 0, "temp_c": null`. The other keys stay.

## Review Focus

- `nvidia-smi` hangs or is missing (driver update, no GPU). The sampler must not stall: use `timeout=3`, return VRAM and temperature as null, and keep serving CPU and RAM. Task 1: `test_sample_survives_gpu_failure`.
- `vram` is null. The display must show `--%` with an empty bar, never a garbage bar from NaN. Task 2: `test_bar_width_nan_is_zero` and `test_parse_vram_null`.
- `pythonw` has no console. A `subprocess.run` without `CREATE_NO_WINDOW` flashes a console window every second. Task 1: `test_gpu_query_hides_console`.
- The PC is asleep or the server is not running. The display greys out and shows `PC offline`, not `Pi offline`. Task 2: string check in step 5.
- The display EEPROM still holds the custom URL `http://192.168.1.109:9101/stats`, so the new default never applies. Task 3 sets the URL explicitly with `/set`.

---

### Task 1: PC stats service

**Files:**
- Create: `device/pcstats/pcstats.py`
- Test: `tests/test_pcstats.py` (load the module by path, like `tests/test_pistats.py` lines 1-9)

**Interfaces:**
- Produces: HTTP `GET /stats` with the JSON contract above. CLI: `pythonw pcstats.py [--port 9101]`.
- Module functions, all pure except the readers:
  - `cpu_percent(prev: tuple[int,int], cur: tuple[int,int]) -> float`: same behaviour as `pistats.cpu_percent`. Copy it, because the Pi and the PC deploy separately.
  - `parse_nvidia_smi(text: str) -> tuple[int, int, float] | None`: input is the output of `nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits`. Use the first line only. Return `(used_mb, total_mb, temp_c)`, or `None` on an empty line or a non-number such as `[N/A]`.
  - `build_stats(cpu: float, ram: tuple[int,int], gpu: tuple[int,int,float] | None, uptime_s: int) -> dict`: builds the contract dict. Round percents to 1 decimal, and give 0.0 when a total is 0.
  - `read_cpu_times() -> tuple[int,int]`: `(idle, total)` from `GetSystemTimes`. total = kernel + user (kernel already includes idle).
  - `read_memory() -> tuple[int,int]`: `(used_mb, total_mb)` from `GlobalMemoryStatusEx` (`ullTotalPhys - ullAvailPhys`).
  - `read_gpu(run=subprocess.run) -> str | None`: runs the nvidia-smi command above with `capture_output=True, text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW`. Return stdout, or `None` on `OSError`, `subprocess.SubprocessError` or a nonzero exit.
  - `class Sampler(read_cpu=read_cpu_times, read_mem=read_memory, read_gpu=read_gpu, clock=time.monotonic)`: has `sample()`, `latest() -> (dict, ts|None)` and `run()`, the same shape as `pistats.Sampler`. `uptime_s` comes from `ctypes.windll.kernel32.GetTickCount64() // 1000`. Inject it as `uptime=` with that default, so the tests can fake it.
  - `is_fresh`, `MAX_AGE_S = 5.0` and `make_handler` work as in `pistats.py`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pcstats.py`:
  - `test_cpu_percent_basic`: `cpu_percent((800, 1000), (850, 1100)) == 50.0`
  - `test_cpu_percent_counter_reset`: `cpu_percent((800, 1000), (10, 20)) == 0.0`
  - `test_parse_nvidia_smi`: `parse_nvidia_smi("8789, 10240, 55\n") == (8789, 10240, 55.0)`
  - `test_parse_nvidia_smi_first_gpu_only`: input `"100, 200, 40\n300, 400, 50\n"` returns `(100, 200, 40.0)`
  - `test_parse_nvidia_smi_bad`: `""`, `"[N/A], 10240, 55"` and `"garbage"` each return `None`
  - `test_build_stats_full`: `build_stats(12.5, (13420, 32684), (8789, 10240, 55.0), 99)` equals the contract example, except `"ram": 41.1`, `"vram": 85.8`, `"uptime_s": 99`. Compute the expected ram as `round(100*13420/32684, 1)`.
  - `test_build_stats_no_gpu`: with `gpu=None`, the result has `vram is None`, `vram_used_mb == 0`, `vram_total_mb == 0` and `temp_c is None`. The CPU and RAM keys are still present.
  - `test_sample_survives_gpu_failure`: build a `Sampler` with fake readers (cpu returns `(800,1000)` then `(850,1100)`, mem `(1000, 4000)`, gpu returns `None`, uptime `lambda: 5`). Call `sample()`. `latest()[0]["cpu"] == 50.0`, `["ram"] == 25.0` and `["vram"] is None`.
  - `test_gpu_query_hides_console`: call `read_gpu(run=fake)`, where `fake` records its kwargs and returns `SimpleNamespace(returncode=0, stdout="1, 2, 3\n")`. Assert `kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW`, `kwargs["timeout"] == 3` and the result `== "1, 2, 3\n"`.
  - `test_gpu_query_timeout`: `fake` raises `subprocess.TimeoutExpired("nvidia-smi", 3)`, and `read_gpu(run=fake) is None`.
  - `test_is_fresh_old_sample`: `is_fresh(100.0, 105.1) is False`.
- [ ] **Step 2:** Run `E:\new_ccty_bangkok\.venv\Scripts\python -m pytest tests/test_pcstats.py -q`. Expected: FAIL (the module file is missing).
- [ ] **Step 3:** Implement `device/pcstats/pcstats.py` to the interfaces above. Write a module docstring like the one in `pistats.py`. Use a `FILETIME`/`MEMORYSTATUSEX` `ctypes.Structure`, and set `dwLength` before the call.
- [ ] **Step 4:** Run the tests. Expected: all PASS.
- [ ] **Step 5: Live check.** Start `E:\new_ccty_bangkok\.venv\Scripts\python device/pcstats/pcstats.py --port 9199` in the background, then run `curl -s http://127.0.0.1:9199/stats` after 3 s. Expected: JSON with every contract key, `vram_total_mb` 10240 and a `temp_c` number. Stop the process.
- [ ] **Step 6: Commit**
```bash
git add device/pcstats/pcstats.py tests/test_pcstats.py
git commit -m "feat(device): PC stats service for the SmallTV (CPU, RAM, VRAM, GPU temp)"
```

### Task 2: Firmware 1.4.0 shows the PC stats

**Files:**
- Modify: `device/smalltv/src/stats.h`, `stats.cpp`, `layout.cpp` (`changedWidgets`), `main.cpp`, `config.h`
- Test: `device/smalltv/test/test_stats/test_stats.cpp`, `device/smalltv/test/test_layout/test_main.cpp`
- Docs: `device/README.md`

**Interfaces:**
- Consumes: the Task 1 JSON contract.
- Produces:
  - `struct Stats { float cpu, ram, vram, tempC; int ramUsedMb, ramTotalMb, vramUsedMb, vramTotalMb; };`. `watts` is removed. `vram` and `tempC` are `NAN` when their JSON value is null.
  - `parseStats`: the keys `cpu, ram, ram_used_mb, ram_total_mb, vram_used_mb, vram_total_mb` must be numbers. The keys `vram` and `temp_c` must be present, as a number or null. A missing key fails. Generalise the existing `temp_c` null logic into a helper that `vram` uses too.
  - `barWidth(NAN, w) == 0`.
  - `struct Screen { int cpu, ram, vram, temp, ramUsedMb, ramTotalMb, vramUsedMb, vramTotalMb; bool stale, wifiDown; }`. Rename `SCREEN_NO_TEMP` to `SCREEN_NONE = -10000` and use it for both `vram` and `temp`. Update `screenOf` and `sameScreen` to match.
  - `changedWidgets`: the `W_POWER` bit now follows `vram`. The layout JSON key stays `"power"`, so stored layouts still parse. In design mode, `W_POWER` draws `"VRAM 86%"` (or `"VRAM --%"`).
- The built-in look (`drawFrame` and `drawStats` in `main.cpp`). Coordinates are for a 240x240 screen. Values are right-aligned at x=230 with font 4 and pad 90, unless stated otherwise:

| Item | Content | Position |
|---|---|---|
| Title | `PC`, white, font 4 | TL (10,6) |
| GPU temp | `GPU 55 C` / `GPU -- C`, font 4, pad 130 | TR (230,6) |
| Labels | `CPU` / `RAM` / `VRAM`, grey, font 2 | TL (10,44) / (10,92) / (10,140) |
| Values | `12%` / `41%` / `86%` (`--%` when vram is NaN) | TR y=38 / 86 / 134 |
| Bars | `drawBar` (stays grey when stale or NaN) | y=68 / 116 / 164 |
| Detail | `RAM 13.1/31.9 GB` and `VRAM 8.6/10.0 GB` (MB/1024, 1 decimal; `VRAM --` when vramTotalMb is 0), grey, font 2, pad 220 | TL (10,182) / (10,202) |
| Footer | IP, grey, font 1 | BL (10,238) |
| Status | `PC offline` / `No WiFi`, red, font 2, only when stale | BR (230,238) |

  Make other copy changes: the splash title `BKK PC Monitor`, the `handleRoot` first line `SmallTV PC monitor fw ...`, and the design-mode status `PC offline`. Update the header comment of `main.cpp` and the comment in `platformio.ini` line 1.

- [ ] **Step 1: Update the tests first.**
  - Make `GOOD` in `test_stats.cpp` the contract example. Update `sentinel()` and `test_parse_ok` to assert `vram` 85.8, `vramUsedMb` 8789 and `vramTotalMb` 10240.
  - Add `test_parse_vram_null`: with `"vram": null`, the parse succeeds and `isnan(s.vram)` is true.
  - Add `test_parse_rejects_missing_vram`: the parse fails when the `vram` key is missing.
  - Add `test_bar_width_nan_is_zero`: `barWidth(NAN, 200) == 0`.
  - Add `test_screen_vram_none`: `screenOf` with `vram` NaN gives `vram == SCREEN_NONE`.
  - In `test_main.cpp`, change the `watts10` change test so it sets `b.vram`, and still expect `1 << W_POWER`.
  - Replace every `SCREEN_NO_TEMP` with `SCREEN_NONE`.
- [ ] **Step 2:** Run `pio test -d device/smalltv -e native`. Expected: compile FAIL (no `vram` member).
- [ ] **Step 3:** Implement the `stats.h`/`stats.cpp`/`layout.cpp` changes.
- [ ] **Step 4:** Run the native tests. Expected: all PASS.
- [ ] **Step 5:** Implement the `main.cpp` built-in look and the copy changes, and set `config.h` to `FW_VERSION "1.4.0"` and the new `STATS_URL`. Check: `git grep -n "Pi offline\|Raspberry Pi\|watts" device/smalltv/src` returns nothing.
- [ ] **Step 6:** Build: `pio run -d device/smalltv -e smalltv`. Expected: `SUCCESS`. Then gzip the bin as in `device/README.md`.
- [ ] **Step 7:** Update `device/README.md`:
  - The title and intro now say PC: CPU, RAM, VRAM, GPU temp.
  - Add a `pcstats` row to the parts table, with its install location `C:\Users\user\Tools\pcstats\`, the Task Scheduler task `PCStats`, and firewall rule `PC stats 9101 (SmallTV)`.
  - Remove the power estimate paragraph, and say that `pistats` still exists for the Pi but the display no longer reads it.
  - Note that the layout key `power` now shows VRAM.
- [ ] **Step 8: Commit**
```bash
git add device/smalltv device/README.md
git commit -m "feat(device): SmallTV fw 1.4.0 shows PC CPU, RAM, VRAM and GPU temp"
```

### Task 3: Install, flash and verify (controller runs this, not a subagent)

Not code, so there is no TDD cycle. Each step has a check.

- [ ] **Step 1:** Copy `device/pcstats/pcstats.py` to `C:\Users\user\Tools\pcstats\pcstats.py`.
- [ ] **Step 2:** Register the Task Scheduler task `PCStats`. It runs at logon of the current user, with `C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe "C:\Users\user\Tools\pcstats\pcstats.py"`. Set restart on failure 3 times every 1 minute and no execution time limit. Then `Start-ScheduledTask PCStats`. Check: `curl http://127.0.0.1:9101/stats` returns 200 with the contract keys.
- [ ] **Step 3:** Add the firewall rule. It needs admin, so the user approves UAC once: `New-NetFirewallRule -DisplayName "PC stats 9101 (SmallTV)" -Direction Inbound -Protocol TCP -LocalPort 9101 -RemoteAddress 192.168.1.111 -Action Allow -Profile Any`. Also list any `Block` rules for `pythonw.exe`/`python.exe` (a block rule beats an allow rule) and tell the user if one exists.
- [ ] **Step 4: Ask the user before flashing.** Then POST the gzip to `http://192.168.1.111/update`. Check: `GET /info` shows `"fw":"1.4.0"`.
- [ ] **Step 5:** `curl -X POST http://192.168.1.111/design/reset`, then `curl "http://192.168.1.111/set?url=http://192.168.1.188:9101/stats"`. Check: `GET /` shows `last fetch: ok`, the new URL, and `seconds since good fetch` of 0-2. `/info` shows `"design":false`.
- [ ] **Step 6:** Ask the user to look at the screen and confirm the numbers match Task Manager (RAM %, dedicated GPU memory).
