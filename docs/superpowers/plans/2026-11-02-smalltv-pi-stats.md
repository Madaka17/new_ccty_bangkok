# SmallTV Pi Stats Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the GeekMagic SmallTV Ultra firmware with our own, so the screen shows the Raspberry Pi 4's CPU %, RAM %, estimated power draw and temperature.

**Architecture:** A stdlib-only Python service on the Pi samples `/proc` and `/sys` once per second and serves one JSON document. The SmallTV (ESP8266) joins WiFi, polls that JSON every 2 s and draws it on its 240x240 ST7789V screen. The firmware keeps an `/update` page so every later update goes over WiFi, without opening the case.

**Tech Stack:** Python 3 stdlib (`http.server`, `threading`), systemd; PlatformIO, Arduino core for ESP8266, TFT_eSPI, ArduinoJson 7, WiFiManager (tzapu), ESP8266HTTPUpdateServer; pytest; PlatformIO `native` env with Unity.

**Spec:** Chat decision 2026-11-02 (no separate spec file). Requirements:
- Device: GeekMagic SmallTV Ultra, ESP8266 (ESP-12E), at `192.168.1.104`. The stock firmware has `/update` and accepts `.bin` and `.bin.gz`.
- Source machine: Pi 4 at `192.168.1.109` (static IP), Debian 12 bookworm aarch64, user `test`, SSH key `C:\Users\user\.ssh\bkkpi_ed25519`.
- Show CPU %, RAM %, power in W, temperature in °C.
- The Pi 4 has no power sensor, so the power value is an estimate and the screen must mark it as an estimate (`~`).
- The user accepted the brick risk. Recovery needs opening the case and a 3.3 V USB-TTL adapter. The stock firmware cannot be backed up over WiFi.

## Global Constraints

- Display pins: SPI CLK `GPIO14`, MOSI `GPIO13`, DC `GPIO0`, RST `GPIO2`, no CS (`-1`). Backlight is PWM on `GPIO5` and is **inverted** (0 = full bright).
- Panel: ST7789V, 240x240, SPI mode 3, colour inversion on, BGR order, 40 MHz SPI.
- Stats endpoint: `http://192.168.1.109:9101/stats`, port `9101`, GET only, JSON.
- Power estimate: `watts = 2.7 + 3.7 * cpu / 100 + 1.0` (Pi 4 idle about 2.7 W, about 6.4 W at full load, plus about 1.0 W for the USB SSD). Round to 1 decimal.
- Python service: stdlib only, no pip packages, so it runs on the Pi system Python without a venv.
- Firmware fallback WiFi access point name: `BKK-Display`, no password, opened only when saved credentials fail for 20 s.
- Screen labels in English (`CPU`, `RAM`, `PWR`, `TEMP`): the default TFT_eSPI fonts have no Thai glyphs.
- Code lives in `device/pistats/` (Pi service) and `device/smalltv/` (firmware). The PlatformIO tool venv lives in `local/pio/.venv` and is not committed.

## Review Focus

1. Pi offline or service stopped: the screen must keep the last values greyed out and show `Pi offline` in red after 10 s without a good response. It must not freeze or reboot. Test: `test_is_stale_after_10s` (Task 2).
2. Pi rebooted: `/proc/stat` counters restart lower than the previous sample. CPU % must clamp to 0..100 and must never be negative. Test: `test_cpu_percent_counter_reset` (Task 1).
3. Malformed or partial JSON (proxy page, truncated body): the parser must return false and keep the old values. Test: `test_parse_rejects_bad_json`, `test_parse_rejects_missing_field` (Task 2).
4. Out-of-range values (cpu 130, ram -5): the bars must clamp and never draw outside 0..maxWidth. Test: `test_bar_width_clamps` (Task 2).
5. WiFi drops and comes back: the firmware must reconnect without a manual power cycle and must not open the `BKK-Display` AP while saved credentials still exist. Covered by the manual check in Task 4 Step 5 (router reboot or unplugging the access point is not needed; toggling the Pi service covers the HTTP path).

---

### Task 1: Pi stats service

**Files:**
- Create: `device/pistats/pistats.py`
- Create: `device/pistats/pistats.service`
- Test: `tests/test_pistats.py`

**Interfaces:**
- Produces (JSON at `GET /stats`): `{"cpu": float, "ram": float, "ram_used_mb": int, "ram_total_mb": int, "temp_c": float, "watts": float, "watts_est": true, "uptime_s": int}`. `cpu` and `ram` are percent 0..100 with 1 decimal. Any other path returns 404.
- Produces (Python, used only by tests): `parse_proc_stat(text: str) -> tuple[int, int]` returns `(idle, total)` from the `cpu ` line, where idle = idle + iowait. `cpu_percent(prev: tuple[int, int], cur: tuple[int, int]) -> float`. `parse_meminfo(text: str) -> tuple[int, int]` returns `(used_mb, total_mb)` with used = MemTotal - MemAvailable. `estimate_watts(cpu: float) -> float`.

- [ ] **Step 1: Write the failing tests** in `tests/test_pistats.py`. Import the module by path with `importlib.util.spec_from_file_location`, because `device/` is not a package.

```python
STAT = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 2 3 4 5 6 7 8 9 10\n"
def test_parse_proc_stat():            assert parse_proc_stat(STAT) == (800, 1000)
def test_cpu_percent_basic():          assert cpu_percent((800, 1000), (850, 1100)) == 50.0
def test_cpu_percent_counter_reset():  assert cpu_percent((800, 1000), (10, 20)) == 0.0
def test_cpu_percent_no_change():      assert cpu_percent((800, 1000), (800, 1000)) == 0.0
MEM = "MemTotal:        8000000 kB\nMemFree:  100 kB\nMemAvailable:    6000000 kB\n"
def test_parse_meminfo():              assert parse_meminfo(MEM) == (1953, 7812)
def test_estimate_watts_idle():        assert estimate_watts(0) == 3.7
def test_estimate_watts_full():        assert estimate_watts(100) == 7.4
def test_estimate_watts_clamps():      assert estimate_watts(250) == 7.4
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv\Scripts\python -m pytest tests/test_pistats.py -v`
Expected: FAIL. The module file does not exist yet.

- [ ] **Step 3: Implement `device/pistats/pistats.py`**

Implement the four pure functions above. Add a sampler thread that reads `/proc/stat`, `/proc/meminfo`, `/sys/class/thermal/thermal_zone0/temp` (millidegrees) and `/proc/uptime` once per second, and stores the latest dict under a lock. Serve it with `ThreadingHTTPServer` on `0.0.0.0:9101`. A `--port` argument overrides the port. The module must be importable on Windows: no file reads at import time, only inside `main()`. `cpu_percent` returns 0.0 when total delta <= 0, and clamps the result to 0..100.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv\Scripts\python -m pytest tests/test_pistats.py -v`
Expected: 8 passed.

- [ ] **Step 5: Write `device/pistats/pistats.service`**

Use a systemd unit with `ExecStart=/usr/bin/python3 /mnt/ssd/device/pistats/pistats.py`, `User=test`, `Restart=always`, `RestartSec=5`, `After=network-online.target`, and `WantedBy=multi-user.target`.

- [ ] **Step 6: Deploy to the Pi and verify**

Copy `device/pistats/` to `/mnt/ssd/device/pistats/` with `scp -i $env:USERPROFILE\.ssh\bkkpi_ed25519 -r`. Then run `sudo cp .../pistats.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now pistats`.
Run from the PC: `curl.exe -s http://192.168.1.109:9101/stats`
Expected: JSON with all 8 keys, `cpu` between 0 and 100, `temp_c` between 20 and 90, and `watts` between 3.7 and 7.4.

- [ ] **Step 7: Commit**

```bash
git add device/pistats tests/test_pistats.py
git commit -m "feat(device): Pi stats JSON service for the desk display"
```

---

### Task 2: Firmware project and stats logic

**Files:**
- Create: `device/smalltv/platformio.ini`
- Create: `device/smalltv/src/stats.h`, `device/smalltv/src/stats.cpp`
- Test: `device/smalltv/test/test_stats/test_stats.cpp`
- Create: `local/pio/.venv` (not committed: `pip install platformio`)

**Interfaces:**
- Produces:

```cpp
struct Stats { float cpu, ram, tempC, watts; int ramUsedMb, ramTotalMb; };
bool parseStats(const char* json, Stats& out);   // false on bad JSON or a missing key; out is unchanged on false
int  barWidth(float pct, int maxW);              // clamps pct to 0..100, returns 0..maxW
uint16_t levelColor(float pct);                  // < 60 green 0x07E0, < 85 yellow 0xFFE0, else red 0xF800
bool isStale(uint32_t nowMs, uint32_t lastOkMs); // true when nowMs - lastOkMs > 10000 (wrap-safe unsigned math)
```

- [ ] **Step 1: Install PlatformIO.** Run `py -m venv local\pio\.venv` and then `local\pio\.venv\Scripts\pip install platformio`. Check with `local\pio\.venv\Scripts\pio --version`.
- [ ] **Step 2: Write `platformio.ini`.** It needs two envs:
  - `[env:smalltv]`: `platform = espressif8266`, `board = esp12e`, `framework = arduino`, `board_build.ldscript = eagle.flash.4m1m.ld`, `lib_deps = bodmer/TFT_eSPI, bblanchon/ArduinoJson@^7, tzapu/WiFiManager`.
  - TFT_eSPI is set by `build_flags` with `-D USER_SETUP_LOADED=1`, `-D ST7789_DRIVER=1`, `-D TFT_WIDTH=240`, `-D TFT_HEIGHT=240`, `-D TFT_MOSI=13`, `-D TFT_SCLK=14`, `-D TFT_CS=-1`, `-D TFT_DC=0`, `-D TFT_RST=2`, `-D TFT_INVERSION_ON=1`, `-D TFT_RGB_ORDER=TFT_BGR`, `-D TFT_SPI_MODE=SPI_MODE3`, `-D SPI_FREQUENCY=40000000`, `-D LOAD_GLCD=1`, `-D LOAD_FONT2=1`, `-D LOAD_FONT4=1`, `-D LOAD_FONT7=1`, `-D SMOOTH_FONT=0`.
  - `[env:native]`: `platform = native`, `lib_deps = bblanchon/ArduinoJson@^7`, `build_src_filter = +<stats.cpp>`, `test_build_src = yes`.
- [ ] **Step 3: Write the failing Unity tests:**
  - `test_parse_ok`: the Task 1 JSON gives cpu 12.5, watts 4.2.
  - `test_parse_rejects_bad_json`: input `"<html>"` returns false and leaves `out` unchanged.
  - `test_parse_rejects_missing_field`: JSON without `watts` returns false.
  - `test_bar_width_clamps`: `barWidth(130,200)==200`, `barWidth(-5,200)==0`, `barWidth(50,200)==100`.
  - `test_level_color`: 59.9 gives green, 60 gives yellow, 85 gives red.
  - `test_is_stale_after_10s`: `isStale(10001,0)` is true, `isStale(10000,0)` is false, `isStale(5,4294967290u)` is false (wrap).
- [ ] **Step 4:** Run `local\pio\.venv\Scripts\pio test -d device/smalltv -e native`. Expected: FAIL, `stats.h` not found. The native env needs a host C++ compiler (MinGW `g++` on PATH). If none exists, install `winget install BrechtSanders.WinLibs.POSIX.UCRT` first.
- [ ] **Step 5:** Implement `stats.cpp` with ArduinoJson `JsonDocument` and `deserializeJson`. Parse into a temporary `Stats` and copy it to `out` only when every key exists (`doc["cpu"].is<float>()` and the same for each key).
- [ ] **Step 6:** Run the tests again. Expected: 6 tests, 0 failures.
- [ ] **Step 7: Commit:** `git add device/smalltv` with `git commit -m "feat(device): SmallTV firmware project and stats parsing"`.

---

### Task 3: Firmware main loop

**Files:**
- Create: `device/smalltv/src/main.cpp`
- Create: `device/smalltv/src/config.h`

**Interfaces:**
- Consumes: `Stats`, `parseStats`, `barWidth`, `levelColor`, `isStale` from Task 2.
- Produces: the firmware image `device/smalltv/.pio/build/smalltv/firmware.bin` and an HTTP server on the device: `/update` (ESP8266HTTPUpdateServer, same form fields `firmware` and `filesystem` as the stock page) and `/` (plain text: firmware version, stats URL, last fetch result).

- [ ] **Step 1: `config.h`:** `STATS_URL "http://192.168.1.109:9101/stats"`, `POLL_MS 2000`, `FW_VERSION "1.0.0"`, `AP_NAME "BKK-Display"`, `WIFI_WAIT_MS 20000`, `PIN_BL 5`.
- [ ] **Step 2: `main.cpp` setup.**
  1. Turn the backlight on with `analogWriteRange(1023)` and `analogWrite(PIN_BL, 1023 - 800)` (inverted).
  2. Init `TFT_eSPI`, then draw `BKK Pi Monitor` with the FW version and `WiFi...`.
  3. Run `WiFi.mode(WIFI_STA)` and `WiFi.begin()` without arguments, so the SDK reuses the credentials the stock firmware saved. Wait up to `WIFI_WAIT_MS`.
  4. If WiFi still fails, run `WiFiManager.autoConnect(AP_NAME)`. Show on screen `Join WiFi BKK-Display` and `open 192.168.4.1`.
  5. Start the web server with `/` and `/update`.
- [ ] **Step 3: `main.cpp` loop.**
  - Call `server.handleClient()` on every pass.
  - Every `POLL_MS`, fetch `STATS_URL` with `HTTPClient` (timeout 1500 ms) and `parseStats`. Set `lastOkMs` on success.
  - Draw with a sprite or partial redraws, so the screen does not flicker:
    - title `Raspberry Pi`
    - rows `CPU 12%` and `RAM 34%`, each with a bar coloured by `levelColor`
    - `PWR ~4.2 W`
    - `TEMP 48 C`
    - small IP text at the bottom
  - When `isStale(millis(), lastOkMs)` is true: draw the values in grey (`0x8410`) and show `Pi offline` in red.
  - Do not call `WiFiManager` again in the loop. The ESP8266 core auto-reconnect handles WiFi drops.
- [ ] **Step 4: Build.** Run `local\pio\.venv\Scripts\pio run -d device/smalltv -e smalltv`. Expected: `SUCCESS` and Flash usage under 60 % of the 1 MB sketch area (the stock OTA must fit the image).
- [ ] **Step 5: Make the gzip image.** Run `.venv\Scripts\python -c "import gzip,shutil;shutil.copyfileobj(open(r'device/smalltv/.pio/build/smalltv/firmware.bin','rb'),gzip.open(r'device/smalltv/.pio/build/smalltv/firmware.bin.gz','wb',9))"`. Report both sizes.
- [ ] **Step 6: Commit:** `git add device/smalltv/src` with `git commit -m "feat(device): SmallTV screen shows Pi CPU, RAM, power, temperature"`.

---

### Task 4: Flash and verify on the device (controller does this, not a subagent)

**Files:**
- Create: `device/README.md`

- [ ] **Step 1:** Confirm that Task 1 Step 6 returns JSON from the PC.
- [ ] **Step 2: Flash over WiFi.** Run `curl.exe -F "firmware=@device/smalltv/.pio/build/smalltv/firmware.bin.gz" http://192.168.1.104/update`.
  - Expected: `Update Success` and the device reboots.
  - If the result is `Not Enough Space`, stop and report to the user. The fallback is a minimal OTA-only loader image first, then the full image.
- [ ] **Step 3:** Wait 30 s. Check `curl.exe -s http://192.168.1.104/`. Expected: text with `1.0.0` and the stats URL.
- [ ] **Step 4:** Ask the user to look at the screen. Expected: four rows with values that match `curl` within 2 s. If the colours are wrong or the screen is blank, change `TFT_INVERSION_ON` / `TFT_RGB_ORDER` and reflash through the device's own `/update`.
- [ ] **Step 5:** Run `sudo systemctl stop pistats` on the Pi. Within 12 s the screen must show `Pi offline`. Then run `sudo systemctl start pistats`; the values must come back without a power cycle.
- [ ] **Step 6:** Write `device/README.md`: what each part does, how to rebuild, how to flash over WiFi, the recovery path (open the case, USB-TTL 3.3 V, GPIO0 to GND at power-up, `esptool write_flash 0x0`), and that the power value is an estimate. Commit.
- [ ] **Step 7:** Update the Claude memory `raspberry-pi-target.md` with the display IP, port 9101 and the firmware location.
