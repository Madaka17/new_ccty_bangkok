# ENVIRO Seismic Command

Edge AI–IoT earthquake detection and early-warning platform — working full-stack
prototype (Flask + SQLite + WebSocket backend, vanilla-JS frontend), built from
the 6-menu system outline in "แพลตฟอร์มอัจฉริยะ Edge AI–IoT...docx".

## Run it

```bash
cd /Users/wj/Desktop/ENVIRO
pip3 install -r requirements.txt   # first time only
python3 main.py
```

Open **http://localhost:5050**. Demo accounts (password `enviro2026` for all):

| Username | Role | Can do |
|---|---|---|
| `admin.wanchana` | admin | everything, incl. running backups |
| `operator.suda` | operator | send test alerts, cannot run backups |
| `auditor.kritt` | auditor | read-only |
| `partner.api` | partner | read-only (external-partner API access) |

The port defaults to 5050 (5000 collides with macOS AirPlay Receiver on most
Macs). Override with `PORT=8080 python3 main.py`.

On the public server, start it with `launch\enviro\start.bat` (or
`restart.bat` / `stop.bat`) instead. It is public at https://enviro.bkksmartstreet.com
and at /enviro/ next to BKK StreetSmart (https://cctv.bkksmartstreet.com/enviro/, whose
"Earthquake" page shows it in a frame) through Cloudflare Tunnel (`launch\cloudflare`), and at
https://cctv-bangkok.tail95e28b.ts.net/enviro/ through Tailscale Funnel. Funnel strips the
/enviro prefix; the tunnel does not, so `server/app.py` strips it itself. Before
each start it replaces the demo passwords above and the PROTO-01 node key with
random ones, and writes them to `data/accounts.txt` (not in git).

Visitors who have not logged in see the dashboard read-only as a guest
(`server/auth.py: GUEST`). Sending alerts, simulating quakes and changing
settings still need an admin or operator login ("เข้าสู่ระบบ" in the rail).

The "AI วิเคราะห์แผ่นดินไหว" tab (`server/quake_brief.py`, `/api/world/brief`) is rewritten when the
events change, and at least every 15 minutes. It uses the last 7 days of real quakes: M4.5+ worldwide and
the events near Thailand. The server computes the facts: nearest plate boundary (PB2002, downloaded once to
`data/pb2002_boundaries.json`), nearest GEM active fault, and predicted MMI for every provincial capital,
with +1 MMI on Bangkok's soft clay. An AI model then writes the Thai text from those facts only. The model
is the OpenAI-compatible `LOCAL_LLM_URL` / `LOCAL_LLM_MODEL` / `LOCAL_LLM_API_KEY` / `LOCAL_LLM_EXTRA`, read
from the environment or from BKK StreetSmart's `.env` one folder up. With no model set, a Thai template
writes the text.

Delete `data/enviro.db` to reset all state (events, audit log, users) back to
the seeded starting point.

## Alert levels: Predicted MMI, not magnitude

The alert **level** (1–6) is gated on **predicted Modified Mercalli Intensity
(MMI) at a fixed reference location** ("you are here" — currently the
BKK-201 station), not on the earthquake's magnitude. This follows USGS's own
guidance that magnitude and intensity are different things: the same event
shakes different places very differently depending on distance, depth, and
site conditions, so a public alert level should reflect predicted local
shaking, not one global magnitude threshold. See `server/db.py: LEVELS` for
the full citation trail (USGS Magnitude-vs-Intensity, the MMI scale,
ShakeAlert's thresholds, CDC's during/after guidance, NOAA/NWS for the
tsunami overlay).

Magnitude estimation, multi-node corroboration, and confidence-tier
climbing (ต่ำ → ปานกลาง → สูง → สูงมาก → ยืนยันแล้ว) all still work exactly as
before and are still real, live-computed logic — they just feed into
*predicted MMI*, which is what actually picks the level. Station count only
raises **confidence** in an already-classified severity, never the severity
itself.

A **tsunami-risk flag** can overlay any of the 6 levels: a simplified,
explicitly-illustrative heuristic (`Simulator._assess_tsunami_risk`) flags a
shallow, large (M7+) event whose epicenter falls in a rough Andaman Sea
bounding box — not an official warning, just a demo overlay in the same
spirit as the rest of the ladder.

## Full-ladder demo, alert sound, Telegram

- **Top-right "จำลองแผ่นดินไหว" button** — Thailand's real named faults all
  sit 150–700km+ from the reference station, so even a M9 there only
  predicts a low MMI back at the reference point (that's honest physics, not
  a bug — a large distant earthquake really is only mildly felt far away).
  So this button instead asks the server for a **target level** (5 or 6): it
  solves the (magnitude, short distance) pair that would realistically reach
  that level's MMI floor from a small dedicated demo point near the
  reference station (`DEMO_EPICENTER_NEAR_REFERENCE` in
  `server/routes/admin.py`) — explicitly labelled "จุดสาธิตใกล้ตำแหน่งอ้างอิง
  (ไม่ใช่รอยเลื่อนจริง)" in the resulting event, never presented as a real
  fault. Runs at 12x wave speed (labelled on-screen as accelerated). Watch
  the level pill jump straight to 5/6 and the confidence badge climb
  ต่ำ → ... → ยืนยันแล้ว as stations corroborate. The Admin page's own
  manual simulate-quake panel uses a **real** named fault + your chosen
  magnitude instead, at real wave speed by default — a good way to see the
  magnitude-vs-intensity point directly: a big magnitude on a far fault can
  land at a *lower* level than you'd expect, because it's a smaller shake by
  the time it reaches the reference location.
- **Alert sound** — each level plays a distinct synthesized tone (Web Audio,
  no audio files) matching the `siren` text specified per level in
  `server/db.py`, plus real browser text-to-speech (Web Speech API) for the
  level-4/6 voice prompts. Level 6 repeats (siren + voice) every 5s until
  acknowledged via the "รับทราบ — หยุดเสียง" bar — but only for a genuine
  escalation to level 6, never re-armed by a routine confidence-tier update
  on the same event (the backend broadcasts a `level_changed` flag
  specifically so the frontend can tell the two apart). Toggle sound with the
  "เสียงแจ้งเตือน" chip in the topbar; browsers block audio until a user
  gesture, so it arms on your first click anywhere.
- **Telegram** — real Bot API integration (`server/telegram_notify.py`),
  configured from Admin → "การแจ้งเตือนผ่าน Telegram". It needs *your own*
  bot token (free via @BotFather) and chat id; with nothing configured it's a
  silent no-op. The "ส่งข้อความทดสอบ" button calls the real API and shows
  Telegram's actual response.

## What's real here vs. what's simulated

This is the honest boundary — it matters for anyone deciding what to build on
top of this next.

**Genuinely real, working code:**
- Flask REST API + WebSocket (`/ws`) backend, SQLite persistence, token-based
  auth with 4 roles enforced server-side (`server/auth.py`)
- STA/LTA detection, FFT spectrum, and multi-station correlation are computed
  with NumPy on live signal buffers (`server/signal.py`) — not lookup tables
- The Edge AI source classifier (`signal.classify_source`) genuinely
  distinguishes earthquake shaking from a passing vehicle, machinery, or
  background noise using three real signal properties evaluated in order: an
  STA/LTA activity gate, spectral peakiness (broadband vs. tonal), and
  cross-station coherence (only counted once the neighbour station is itself
  active — before that, "not yet corroborated" is correctly treated as
  different from "confirmed not an earthquake")
- Multi-node corroboration is tracked per-station (a station only counts once
  its own signal crosses threshold) and the confidence badge **upgrades
  live** (ต่ำ → ... → ยืนยันแล้ว) as more (simulated) stations feel the wave —
  watch the Audit Log after a fresh start to see it happen in real time. It
  no longer gates the alert *level* itself — see "Alert levels" above
- Predicted MMI is computed from a real, cited GMICE (Wald, Quitoriano,
  Heaton & Kanamori 1999) fed this simulator's own synthetic PGA-at-distance
  model (`predict_mmi` in `server/simulator.py`) — the formula is real, the
  PGA it converts is still simulator-synthetic
- SQLite backups in Admin → "สำรองข้อมูลตอนนี้" write real `.db` files to
  `backups/` using `sqlite3`'s native backup API
- USGS integration (`server/sources_usgs.py`) polls the real public
  `earthquake.usgs.gov` GeoJSON feed every 5 minutes — no API key needed.
  Check the "เปรียบเทียบแหล่งข้อมูล" page; if it says "เชื่อมต่อจริง" it's
  showing an actual current earthquake somewhere in the world (not the same
  event as the simulated Thai quake — that's expected, it's proof the live
  connection itself works)
- EMSC integration (`server/sources_emsc.py`) — a second real, independent,
  no-key live feed (`seismicportal.eu`, ~65 national seismic networks
  worldwide), giving genuine cross-source validation, not just one API
- GEOFON integration (`server/sources_geofon.py`, and merged into the world
  map via `server/world_quakes.py`) — a third real, independent, no-key feed
  from GFZ Potsdam's FDSN Event webservice (`format=text`, since it doesn't
  support GeoJSON). USGS + EMSC + GEOFON are the three primary catalogs this
  project cross-checks the Edge AI against, per the earthquake-severity
  reference doc
- TMD's live map feed (`earthquake.tmd.go.th/map-events.json` — an
  undocumented but genuinely public endpoint, found by reading that page's
  own `<script>` source) is merged into the same world map, tagged `source:
  "TMD"` and given a bolder marker ring. It's the only source here that
  actually detects small earthquakes *inside* Thailand (down to ~M1.5) —
  USGS/EMSC/GEOFON's thresholds mostly only catch regional events in
  neighbouring countries. Events from the last `RECENT_QUAKE_MINUTES` (60)
  blink on the map (`is_recent` computed server-side)
- Real Thailand map (Leaflet) at real lat/lng for every station, fault, and
  event — with a genuine basemap switcher (OpenStreetMap street / Esri World
  Imagery satellite, top-right control on the map). Real Google Maps satellite
  tiles are deliberately **not** wired in: Google's tile endpoints require a
  billed Maps Platform API key, and hot-linking the bare tile URLs without one
  violates their Terms of Service. Esri World Imagery is a free, ToS-compliant
  equivalent — if you have a Google Maps API key, see "Wiring in a real Google
  Maps key" below for what changes
- "จำลองแผ่นดินไหว" (Simulate Earthquake) in Admin — unlike the sandboxed Safe
  Test Alert, this actually injects a synthetic waveform burst at a
  real fault location you pick, and lets the full real pipeline (STA/LTA →
  PGA estimate → multi-node corroboration → level classification, all the
  way through the live level upgrades) run again from scratch. Distances,
  wave-arrival timing, and per-station attenuation are computed from real
  haversine distance to whichever station is nearest the picked epicenter

**Simulated (clearly labelled in the UI), by necessity:**
- The 15 named sensor stations don't exist — `server/simulator.py` generates
  synthetic 3-axis waveforms (ambient noise + a scripted quake burst ~10s
  after boot, with realistic P/S-wave travel-time delays per station
  distance). Everything downstream of the raw sample (detection, PGA
  estimate, classification) is real logic operating on fake input — replacing
  the simulator with a real MQTT subscriber from actual ENVIRO Node One
  devices would need no other code changes
- TMD's row in the *source-comparison* table (`server/db.py: sources_static`)
  is still an illustrative reference value, as are GISTDA and NASA there —
  that page compares against the *same simulated Thai event*, and no public
  no-key API exists for TMD in that form. This is separate from TMD's *world
  map* feed above, which is genuinely real and live
- The tsunami-risk flag (`Simulator._assess_tsunami_risk`) is a simplified
  bounding-box + magnitude/depth heuristic, explicitly not an official
  warning — a real one would come from PTWC/TMD directly
- The 7-day forecast is a statistical extrapolation from the seeded risk
  scores, not a prediction model — the UI carries an explicit disclaimer
  because no earthquake-prediction technology exists that could honestly
  claim more
- Regional station-fleet totals (1,842 stations) are a seeded administrative
  figure — only the 15 named stations have real per-station buffers
- The fault-line traces on the map are real *locations* (real lat/lng for each
  named fault zone) but schematic *geometry* (two-point line segments) — exact
  fault-trace GIS data would come from Thailand's Department of Mineral
  Resources, which has no public API checked here
- The magnitude → PGA scaling in the simulator (`magnitude_amp_multiplier` in
  `server/simulator.py`) is a simple, clearly-approximate curve chosen to give
  a visible spread across alert levels — it is not a real ground-motion
  prediction equation (GMPE). `MMI_PGA_SCALE` is a separate calibration
  constant (not the admin-configurable `pga_calibration` trigger-sensitivity
  knob) chosen so realistic (magnitude, distance) pairs land in a realistic
  absolute PGA range for the real GMICE formula to convert — see the comment
  above its definition for the reasoning

## Wiring in a real Google Maps API key

If you have a billed Google Maps Platform key and want literal Google
satellite imagery instead of Esri's, the change is small: add a third
`L.tileLayer` in `ensureMap()` (`frontend/index.html`) pointing at Google's
tile service through their official Maps JS API (not the bare `mt0.google.com`
URLs), add it to `baseLayers`, and keep your key server-side (proxy tile
requests through a Flask route) rather than embedding it in the shipped HTML.

## What it would actually take to make the rest real

From the previous conversation, still true and worth repeating:

- **Hardware & firmware**: real MEMS accelerometers + edge inference on real
  devices, talking MQTT to `server/simulator.py`'s replacement
- **Telecom integration**: Cell Broadcast / SMS gateway agreements with
  Thai carriers — this is the hardest non-technical blocker for Level 4–5 alerts
- **Agency data-sharing**: TMD, GISTDA, DDPM coordination for real feeds and
  for legal authority to issue public warnings
- **Security & SRE**: this is life-safety infrastructure — needs real secret
  management (the demo passwords are plaintext-seeded on purpose), HTTPS,
  rate limiting, redundancy, and 24/7 on-call, none of which belong in a
  prototype
- **PDPA / regulatory review** before handling any real citizen location or
  contact data

## Project layout

```
main.py                  entrypoint (python3 main.py)
server/
  app.py                 Flask app factory, wires everything together
  db.py                  schema + seed data
  schema.sql             table definitions
  auth.py                token auth + role decorators
  signal.py              STA/LTA, FFT, correlation (NumPy)
  simulator.py           background sensor-fleet simulation + detection loop
  sources_usgs.py        live USGS public feed poller
  sources_emsc.py        live EMSC public feed poller
  geo.py                 haversine distance
  ws.py                  WebSocket broadcast + /ws endpoint
  quake_brief.py         "AI วิเคราะห์แผ่นดินไหว": facts from the live feeds + the AI's Thai text
  routes/                one blueprint per menu (situation/warning/stations/…)
frontend/index.html      single-page dashboard (fetch + WebSocket client)
backups/                 real SQLite backups land here
data/enviro.db           SQLite database (gitignore this in real use)
```
