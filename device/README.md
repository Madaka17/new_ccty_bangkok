# Desk display: Raspberry Pi stats on the GeekMagic SmallTV Ultra

The SmallTV Ultra (ESP8266, 240x240 ST7789V screen) on the desk shows the Raspberry Pi 4's
CPU %, RAM %, power draw and temperature. It runs our own firmware, not the GeekMagic one.

| Part | Where | What it does |
|---|---|---|
| `pistats/pistats.py` | Pi, `/mnt/ssd/device/pistats/`, systemd unit `pistats` | Samples `/proc` and `/sys` every second and serves JSON at `http://192.168.1.109:9101/stats` |
| `smalltv/` | SmallTV at `192.168.1.111` | Polls that JSON every 2 s and draws it. `/` shows status, `/update` takes a new firmware |

The power value is an **estimate** (the screen shows `~`). The Pi 4 has no power sensor, so
`watts = 2.7 + 3.7 * cpu / 100 + 1.0` (idle, CPU load, USB SSD). A USB power meter is needed for a real reading.

When the screen gets no good answer for 10 s, the values turn grey and `Pi offline` shows in red.
They come back by themselves when the service answers again.

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

Settings are in `smalltv/src/config.h` (stats URL, poll interval, backlight level).
Display pins are in `smalltv/platformio.ini`: SPI CLK GPIO14, MOSI GPIO13, DC GPIO0, RST GPIO2,
no CS, backlight PWM GPIO5 (inverted), SPI mode 3, colour inversion on, BGR.

## WiFi

At boot the firmware uses the WiFi saved in flash and keeps trying for 3 minutes, then restarts
and tries again. A slow router after a power cut never opens the setup access point.

The setup access point `BKK-Display` (no password) opens only when no WiFi is saved, or when the
router rejects the saved password. Join it with a phone, open `192.168.4.1` and pick the WiFi.
After 5 minutes without setup it restarts and tries again.

When WiFi drops later, the screen greys out and shows `No WiFi`. The firmware asks for a reconnect
every 30 s and restarts after 5 minutes without WiFi. `Pi offline` means WiFi is fine but the Pi
service does not answer (or answers 503 because its sampler stalled).

A Pi that is off or unreachable blocks each poll for at most about 1.5 s (checked 2026-11-02 by
dropping the Pi's replies to the display for 30 s).

`/update` has no password, like the stock firmware: anyone on the home LAN can flash the display.

## Recovery when a firmware does not boot

The GeekMagic firmware was not backed up (it cannot be read over WiFi).

1. Remove the 2 screws at the bottom and slide the case open from the back.
2. Connect a 3.3 V USB-TTL adapter: TX, RX, GND. Never use 5 V.
3. Hold GPIO0 to GND while powering on, to enter flash mode.
4. `esptool --port COMx write_flash 0x0 device/smalltv/.pio/build/smalltv/firmware.bin`
