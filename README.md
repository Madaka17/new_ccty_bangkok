# BKK StreetSmart

A live view of Bangkok and the surrounding provinces: where the traffic is jammed, where it is flooding,
how the air is, and what is happening on the roads. Everything is on one site, written in plain Thai so
anyone can use it.

**Live at https://bkksmartstreet.com**

---

## What the site does

| Menu | What you can see |
|---|---|
| **Traffic overview** (ภาพรวมจราจร) | How bad the traffic is right now, the most jammed roads, and incidents on the road |
| **Traffic map** (แผนที่จราจร) | Congestion colours, cameras, water on the roads, rain, wind and PM2.5 dust |
| **AI cameras** (กล้อง AI) | AI counts vehicles on camera feeds and spots riders without helmets and wrong-way drivers |
| **Live cameras** (ดูกล้องสด) | Many traffic cameras on one screen |
| **Floods** (น้ำท่วม) | Water in dams nationwide, a 7-day flood outlook per province, flooded roads, the water coming down from the North, flood risk in each Bangkok district, and shelters |
| **Accidents** (อุบัติเหตุ) | Places in Bangkok where accidents happen often |
| **Alerts** (แจ้งเตือน) | Warnings, and alerts the site can send you |
| **Earthquakes** (แผ่นดินไหว) | Earthquake watch (served by the ENVIRO site at `/enviro/`) |
| **Ask AI** (ถาม AI) | Ask about traffic, floods or a route; the AI answers from the live data |
| **Report a flood** (แจ้งน้ำท่วม) | Anyone can report a flood with a photo |
| **Visitor stats** (สถิติผู้ใช้) | How many people use the site and which pages they open |

### The Floods page

| Tab | What it shows |
|---|---|
| Water nationwide (ระดับน้ำทั่วประเทศ) | Large dams now and in 7 days (million m³ against normal storage), full medium reservoirs, 7-day rain |
| Flood outlook (คาดการณ์น้ำท่วม) | Provinces flooded today, a daily 0-100 flood risk index for the next 7 days, and flood reports from people nationwide |
| Flooded roads (ถนนน้ำท่วม) | Highways flooded now, and main roads that may flood within 7 days, on a map |
| Situation summary (สรุปสถานการณ์) | An AI summary of all of the above and what people should do |
| Northern water route (เส้นทางน้ำเหนือ) | Where the water from the North goes, the provinces on the way (centimetres below or above the bank, today and 7 days), and a 3D map of the flow along the real rivers |
| Bangkok district flood risk (เขตเสี่ยงน้ำท่วมในกรุงเทพมหานคร) | All 50 districts: canals, main gauges, water on the roads, rain and reports, with a risk score |
| Shelters / People's reports | Nearby BMA shelters, and flood reports from Traffy Fondue |

---

## How it works

```
Live sources                       Server                                   Visitors
────────────                       ──────                                   ────────
574 BMA cameras        ──┐
iTIC / DOH cameras     ──┤         AI vision (YOLO)
Water level, rain, tide──┼──────►  vehicle counts, helmets, wrong way  ──►  bkksmartstreet.com
Road water sensors     ──┤         AI write-ups (Qwen / Gemini)              (through Cloudflare)
Dams, air, traffic     ──┘         statistics in SQLite
```

1. **Collect:** the server pulls camera images and water, rain, dam, air and traffic data from each agency
   itself, every 1-10 minutes (dams and forecasts every few hours).
2. **Let the AI look:** the AI counts vehicles on the BMA cameras every 3 minutes and looks for riders
   without helmets and wrong-way vehicles.
3. **Compute, then explain:** forecasts are computed from the numbers first (for example, a dam's storage
   in 7 days from its recent inflow and release, or a river's level from its discharge through the gauge's
   own rating curve). The AI then reads those numbers and writes a short plain-Thai explanation; it does not
   invent the figures.
4. **Show:** the pages refresh on their own; there is no need to reload.

If a source goes down (for example the BMA camera site `cpudapp.bangkok.go.th`), the site shows a warning
and never passes old data off as live.

### Where the data comes from

- **Cameras:** BMA traffic cameras (cpudapp.bangkok.go.th), iTIC, Department of Highways
- **Water:** National water data warehouse (ThaiWater, HII), Royal Irrigation Department (dams and river
  gauges), BMA Drainage Department
- **Weather and air:** Thai Meteorological Department, Open-Meteo, MET Norway, Air4Thai, AirBKK
- **Traffic and incidents:** Longdo Traffic, Traffy Fondue, JS100, Department of Highways (HDMS), ThaiRSC
- **Maps:** OpenStreetMap (river courses and main roads, through the Overpass API)

---

## Run it on your own machine

### Requirements

- Windows 10/11 or macOS
- Python 3 (the live server runs 3.14)
- Node.js 18 or newer (to build the web pages)
- An NVIDIA GPU is optional, but the vision AI is much slower without one (on a Mac it runs on the CPU)

### Install (Windows)

```bash
git clone https://github.com/Madaka17/new_ccty_bangkok.git
cd new_ccty_bangkok

python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# With an NVIDIA GPU: install the GPU build of PyTorch
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
```

### Install (macOS)

```bash
brew install python node        # if you do not have Python 3 and Node.js yet
git clone https://github.com/Madaka17/new_ccty_bangkok.git
cd new_ccty_bangkok
bash launch/setup.sh            # creates .venv and installs the Python and web packages
```

You do not need to build the web pages yourself: on the first start, `start.bat` / `start.sh` builds them
(Node.js must be installed).

### Configure

Create a `.env` file in the project folder with whatever you have. The site opens without any keys, but the
AI write-ups and the chat then fall back to simple rule-based text.

```
GEMINI_API_KEY=        # AI chat and image checks (free key at https://aistudio.google.com/apikey)
LOCAL_LLM_URL=         # OpenAI-compatible endpoint of the Qwen model used for the write-ups and image checks
LOCAL_LLM_MODEL=
LOCAL_LLM_API_KEY=
BMA_DATA_DIR=D:\Data   # where statistics and evidence images go (default: D:\Data on Windows,
                       # instances/production/data on macOS)
```

Never commit `.env` to GitHub: it holds secret keys.

### Start the site

**Windows**
1. Double-click `launch\production\start.bat`
2. Wait a moment, then open http://localhost:8000
3. Stop: `launch\production\stop.bat` · Restart: `launch\production\restart.bat`

**macOS** (in a Terminal at the project folder)
1. `bash launch/production/start.sh` (the server runs in that Terminal window)
2. Wait a moment, then open http://localhost:8000
3. Stop: press Ctrl+C or `bash launch/production/stop.sh` · Restart: `bash launch/production/restart.sh`
4. Test server (:8001): `bash launch/test/start.sh` · `stop.sh` · `restart.sh`

The AI model files (`*.pt`) are not on GitHub because they are too large. The vehicle counting model
`yolo26x.pt` downloads itself on the first start; the helmet and wrong-way models have to be trained or
requested from the maintainers.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| The home page returns `503` | The web pages are not built yet: install Node.js, then run `launch\build_web.bat` (Windows) or `bash launch/build_web.sh` (Mac) |
| Red banner "BMA camera site down" | The BMA camera site is not sending images; this is not on our side. The server retries every 3 minutes |
| BMA camera images show daylight at night | It is the last image before the BMA camera site went down; wait for it to come back |
| No wind on the map | Open-Meteo limits calls per day; wait for the next day |
| Fewer "roads that may flood" than usual | The public Overpass servers were busy; the next refresh asks again |
| The vision AI is very slow | The machine is using the CPU; install the GPU build of PyTorch (see Install) |

---

## For developers

- **Code structure, every `.env` setting and how to run the servers:** [docs/DEVELOPER.md](docs/DEVELOPER.md)
- **Run the tests:** `.venv\Scripts\python -m pytest tests` (Mac: `.venv/bin/python -m pytest tests`)
- **Rebuild the river courses** for the northern water map: `.venv\Scripts\python local\pipeline\fetch_north_rivers.py`
- **Layout:**

```
server.py      server entry point (FastAPI)
backend/       server code by topic: BMA cameras, traffic, water, vision, AI agents
web/           web pages (React + Tailwind)
config/        camera lists, river courses and district outlines
launch/        start / stop scripts and the Cloudflare Tunnel
local/         scripts for collecting images, training models and rebuilding map data (run locally)
instances/     each server's databases and caches (not in Git)
ENVIRO/        the earthquake and environment site served at /enviro/
```

All data is for monitoring and decision support only. AI results (helmet and wrong-way checks, flood
outlooks and write-ups) can be wrong and should be checked by a person before they are acted on.
