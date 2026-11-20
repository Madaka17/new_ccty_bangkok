# Desk display: PC stats on the GeekMagic SmallTV Ultra

The SmallTV Ultra (ESP8266, 240x240 ST7789V screen) on the desk shows the PC's CPU %, RAM %,
VRAM % and GPU temperature. It runs our own firmware, not the GeekMagic one.

| Part | Where | What it does |
|---|---|---|
| `pcstats/pcstats.py` | PC, `C:\Users\user\Tools\pcstats\`, Task Scheduler task `PCStats`, firewall rule `PC stats 9101 (SmallTV)` (see PC service below) | Serves the JSON at `http://192.168.1.188:9101/stats` (CPU, RAM, VRAM, GPU temp) |
| `pistats/pistats.py` | Pi, `/mnt/ssd/device/pistats/`, systemd unit `pistats` | Still exists for the Pi, but the display no longer reads it |
| `smalltv/` | SmallTV at `192.168.1.111` | Polls the PC JSON every 2 s and draws it. `/` shows status, `/update` takes a new firmware |

When the screen gets no good answer for 10 s, the values turn grey and `PC offline` shows in red.
They come back by themselves when the service answers again.

## Stored design (firmware 1.3.0 and later)

Screen Studio can upload a design. Without one, the screen shows the built-in look above.

| Endpoint | Body | Limits | Stored as |
|---|---|---|---|
| `POST /design/base` | multipart file | exactly 115200 bytes (240x240 RGB565, big-endian) | `/base.rgb` |
| `POST /design/layout` | multipart file | at most 2048 bytes, must pass the layout check | `/layout.json` |
| `POST /design/anim` | multipart file | sprite v2: 48-byte header plus at most 4096 cells; an empty file removes it | `/anim.bin` |
| `POST /design/reset` | none | removes all three files and any leftover `.tmp` upload, then goes back to the built-in look | |
| `GET /info` | none | JSON: `model`, `fw`, `design`, `ip`, `uptime_s`, `free_heap`, `fs_free`, `reset_reason` | |

None of these need the `/update` password, like `/update` itself. Each upload goes to `<name>.tmp`
first, is checked, and only then replaces the file. A rejected upload gets `400` with a short reason,
and the old file stays. A power cut during an upload keeps the old file.

The design is drawn only when `/base.rgb` has 115200 bytes and `/layout.json` passes the check.
Otherwise, or when LittleFS fails to mount, the built-in look is drawn. A missing or invalid
`/anim.bin` only means no sprite. `/update`, `/`, `/set` and the WiFi policy work the same in every state.

After a boot caused by a crash or watchdog (reset reasons 1, 2 or 3) the stored design is skipped for
that boot, so a design that crashes the display cannot put it in a boot loop. The next normal restart,
or a new upload, loads the design again. The RAM and VRAM detail lines are muted while the stale values show.

The layout file is version 2, `{"v":2,"c":[...],"w":{...}}`. Its `w` object has exactly the ten PC
widgets, in the same order as `WidgetId` in `layout.h`:

| Key | Font | Draws |
|---|---|---|
| `cpu_value` | 4 | `12%` |
| `cpu_bar` | 0 (bar) | CPU level bar |
| `ram_value` | 4 | `41%` |
| `ram_bar` | 0 (bar) | RAM level bar |
| `vram_value` | 4 | `86%`, or `--%` when there is no VRAM reading |
| `vram_bar` | 0 (bar) | VRAM level bar, empty when there is no VRAM reading |
| `temp` | 4 | `55 C`, or `-- C` |
| `ram_detail` | 2 | `RAM 13.1/31.9 GB` (muted) |
| `vram_detail` | 2 | `VRAM 8.6/10.0 GB`, or `VRAM --` when the VRAM total is 0 (muted) |
| `status` | 2 | `PC offline` or `No WiFi` (critical), only when the values are stale |

Every key must be present and no other key is allowed. A version 1 layout (the 1.4.0 keys, including
`power`) is rejected, so the built-in look is drawn until a version 2 layout is uploaded. Upload
the layout again after flashing 1.5.0.

## PC service

`device/pcstats/pcstats.py` runs on the PC and serves the stats JSON on port 9101. It uses only the
Python standard library. It is installed as `C:\Users\user\Tools\pcstats\pcstats.py`.

Task Scheduler runs it through the task `PCStats`:

- Trigger: at logon of the user.
- Action: `C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe "C:\Users\user\Tools\pcstats\pcstats.py"`
- Restart: 3 times, every 1 minute.
- Time limit: none.

After a power cut, the service does not start until someone logs on. Until then the display shows `PC offline`.

### Update or redeploy

From the repo root, in PowerShell:

```powershell
Copy-Item device\pcstats\pcstats.py C:\Users\user\Tools\pcstats\pcstats.py -Force
Stop-ScheduledTask PCStats; Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object CommandLine -match 'pcstats' | ForEach-Object { Stop-Process -Id $_.ProcessId }
Start-ScheduledTask PCStats
curl.exe -s http://127.0.0.1:9101/stats
```

The last line should print the JSON.

### Firewall

Run once, in an admin PowerShell. The rule lets only the display reach port 9101:

```powershell
New-NetFirewallRule -DisplayName "PC stats 9101 (SmallTV)" -Direction Inbound -Protocol TCP -LocalPort 9101 -RemoteAddress 192.168.1.111 -Action Allow -Profile Any
```

### PC address

The PC address is `192.168.1.188`. It comes from DHCP, so it can change. The address appears in:

- `smalltv/src/config.h`, the default `STATS_URL`.
- The URL stored on the display.

The firewall rule does not hold the PC address. Its `RemoteAddress` is the display (`192.168.1.111`).

Reserve `192.168.1.188` for the PC in the router, so it does not change. If it does change, point the
display at the new address:

```powershell
curl.exe "http://192.168.1.111/set?url=http://NEW_IP:9101/stats"
```

### After flashing 1.4.0 on a display that ran 1.3.0

Two things from the old setup can still be on the display:

1. The stored stats URL may still point at the Pi. Set it to the PC:

   ```powershell
   curl.exe "http://192.168.1.111/set?url=http://192.168.1.188:9101/stats"
   ```

2. An old Screen Studio design has the Pi labels baked into its base image. Remove the stored design
   so the built-in look shows:

   ```powershell
   curl.exe -X POST http://192.168.1.111/design/reset
   ```

Tests (on the PC): `.venv\Scripts\python -m pytest tests/test_pcstats.py`

## Pi service

```bash
# from the PC
scp -i %USERPROFILE%\.ssh\bkkpi_ed25519 device\pistats\pistats.py device\pistats\pistats.service test@192.168.1.109:/mnt/ssd/device/pistats/
# on the Pi
sudo cp /mnt/ssd/device/pistats/pistats.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now pistats
curl -s http://127.0.0.1:9101/stats
```

Tests (on the PC): `.venv\Scripts\python -m pytest tests/test_pistats.py`

## Firmware

PlatformIO lives in its own venv (not in git):

```powershell
py -m venv local\pio\.venv
local\pio\.venv\Scripts\pip install platformio
```

Build, then flash over WiFi:

```powershell
local\pio\.venv\Scripts\pio run -d device/smalltv -e smalltv
.venv\Scripts\python -c "import gzip,shutil;s=r'device/smalltv/.pio/build/smalltv/firmware.bin';shutil.copyfileobj(open(s,'rb'),gzip.open(s+'.gz','wb',9))"
curl.exe -F "firmware=@device/smalltv/.pio/build/smalltv/firmware.bin.gz" http://192.168.1.111/update
```

Unit tests for the parsing and drawing maths run on the PC. They need a host `g++`
(WinLibs: `winget install BrechtSanders.WinLibs.POSIX.UCRT`) on PATH:

```powershell
local\pio\.venv\Scripts\pio test -d device/smalltv -e native
```

Settings are in `smalltv/src/config.h` (default stats URL, poll interval, backlight level).
The stats URL can also be changed without a new build, and the change survives restarts:
`http://192.168.1.111/set?url=http://HOST:9101/stats` (`url=default` goes back to the built-in one).

The screen redraws only when a shown value changes. A GPU temperature the PC cannot read shows as `-- C`,
and a VRAM value it cannot read shows as `--%`.
Display pins are in `smalltv/platformio.ini`: SPI CLK GPIO14, MOSI GPIO13, DC GPIO0, RST GPIO2,
no CS, backlight PWM GPIO5 (inverted), SPI mode 3, colour inversion on, BGR.

## WiFi

At boot the firmware uses the WiFi saved in flash and keeps trying for 3 minutes, then restarts
and tries again. A slow router after a power cut never opens the setup access point.

The setup access point `BKK-Display` (no password) opens only when no WiFi is saved, or when the
router rejects the saved password. Join it with a phone, open `192.168.4.1` and pick the WiFi.
After 5 minutes without setup it restarts and tries again.

When WiFi drops later, the screen greys out and shows `No WiFi`. The firmware asks for a reconnect
every 30 s and restarts after 5 minutes without WiFi. `PC offline` means WiFi is fine but the PC
service does not answer (or answers 503 because its sampler stalled).

A PC that is off or unreachable blocks each poll for at most about 1.5 s (the timing was checked
2026-11-02 on the Pi, by dropping its replies to the display for 30 s).

`/update` has no password, like the stock firmware: anyone on the home LAN can flash the display.

## Recovery when a firmware does not boot

The GeekMagic firmware was not backed up (it cannot be read over WiFi).

1. Remove the 2 screws at the bottom and slide the case open from the back.
2. Connect a 3.3 V USB-TTL adapter: TX, RX, GND. Never use 5 V.
3. Hold GPIO0 to GND while powering on, to enter flash mode.
4. `esptool --port COMx write_flash 0x0 device/smalltv/.pio/build/smalltv/firmware.bin`
