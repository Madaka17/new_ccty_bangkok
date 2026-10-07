"""
The services every API module shares, built once when this module is first imported: the live AI detector and
its counters, the BMA scanner and its patrols, flood and traffic watchers, the AI agents. start() starts their
background jobs. Moved out of server.py (Oct 2026) without changing what is built or in which order.
"""
import json
import os
import re
import time

from backend.agents.flood_agent import FloodAgent
from backend.agents.riskbkk_agent import RiskAgent
from backend.agents.traffy_agent import TraffyAgent
from backend.agents.traffy_history import TraffyHistory
from backend.bma.bma_events import bma_feed
from backend.bma.bma_service import BmaScanner
from backend.core.instance import BASE_DIR, DATA_DIR
from backend.core.news_feed import news_feed
from backend.core.telemetry_service import telemetry
from backend.traffic import analytics_service, area_roads, rsc_service
from backend.traffic.area_traffic import area_traffic
from backend.traffic.flood_route import FloodRouter, gather, sensor_spots
from backend.traffic.guidance_service import GuidanceService
from backend.traffic.road_service import road_risk
from backend.traffic.traffic_service import traffic
from backend.vision.camera_health import CameraHealth
from backend.vision.count_workers import CountManager
from backend.vision.doh_cameras import doh_cameras
from backend.vision.flood_cam_service import FloodCamWatch
from backend.vision.helmet_service import HelmetPatrol
from backend.vision.incident_service import IncidentManager
from backend.vision.itic_frames import IticFrames
from backend.vision.survey import SurveyManager
from backend.vision.vehicle_log import VehicleLog
from backend.vision.violation_service import ViolationMonitor
from backend.vision.world_cameras import world_cameras
from backend.vision.wrongway_service import WrongWayPatrol
from backend.vision.yolo_detector import VehicleDetectorYOLO11x
from backend.water import north_flow, water_service
from backend.water.air_service import air
from backend.water.bkk_districts import BkkDistricts
from backend.water.flood_feeds import hdms_floods, js100_floods, tmd_warnings, traffy_reports
from backend.water.flood_service import flood_roads
from backend.water.nasa_feeds import nasa_feeds
from backend.water.national_forecast import NationalForecast
from backend.water.north_route import NorthRoute
from backend.water.province_flood import ProvinceFlood
from backend.water.user_reports import UserReports

# ids that end up in file names: letters, digits, _ . - only (never a path)
SAFE_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}")


# Paths
# Stock COCO yolo26x by default. AI_MODEL=yolo26x_bkk.pt (or any .pt) in .env / env switches weights;
# the fine-tuned file is no longer picked up just because it exists (the first run missed motorcycles).
MODEL_PATH = os.path.join(BASE_DIR, os.getenv("AI_MODEL", "yolo26x.pt"))
if not os.path.exists(MODEL_PATH):
    print(f"[AI] {MODEL_PATH} not found, falling back to yolo26x.pt")
    MODEL_PATH = os.path.join(BASE_DIR, "yolo26x.pt")
CAMERAS_FILE = os.path.join(BASE_DIR, "config", "cameras_bkk.json")
# React UI (<instance>/dist, built by launch\build_web.bat). Without a build the API still runs and "/" says how to build it.
# Each instance serves its own build, so building the test server's UI leaves the live UI alone. WEB_DIST: another build folder.
WEB_DIST = os.getenv("WEB_DIST") or os.path.join(DATA_DIR, "dist")
INDEX_HTML = os.path.join(WEB_DIST, "index.html")
WEB_BUILT = os.path.exists(INDEX_HTML)
if not WEB_BUILT:
    print(f"[Warning] {INDEX_HTML} not found: run launch\\build_web.bat (Windows) or launch/build_web.sh (macOS) (needs Node.js), then restart. Serving the API only.")

# Load cameras (strictly verified live streams)
cameras_data = []
if os.path.exists(CAMERAS_FILE):
    try:
        with open(CAMERAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            cameras_data = data.get("items", [])
            print(f"[Server] Loaded {len(cameras_data)} verified active cameras from {CAMERAS_FILE}")
    except Exception as e:
        print(f"[Warning] Failed to load cameras_bkk.json: {e}")

# Initialize the YOLO vehicle detector (model from AI_MODEL, target 10 FPS for smoother playback)
vehicle_log = VehicleLog(os.path.join(DATA_DIR, "vehicle_counts.db"))
detector = VehicleDetectorYOLO11x(model_path=MODEL_PATH, target_fps=10.0, conf_threshold=0.15, vehicle_log=vehicle_log)
# Background counting on user-selected cameras (lower fps to prioritize live camera)
counter = CountManager(detector, vehicle_log, os.path.join(DATA_DIR, "count_cameras.json"), target_fps=0.5, max_cameras=4)
counter.load({c["camid"]: c for c in cameras_data})
# Round-robin survey sampling: default 0 workers to prevent FFmpeg C-level crashes on corrupt Longdo HLS streams
survey_workers = int(os.getenv("SURVEY_WORKERS", "0"))
survey = SurveyManager(detector, vehicle_log, lambda: cameras_data, lambda: set(counter.workers),
                       workers=survey_workers, sample_seconds=12.0, target_fps=0.5)
survey.start()
# Accident / breakdown detection (camera AI + Claude vision) and Longdo accident reports
incidents = IncidentManager(vehicle_log, lambda: {c["camid"]: c for c in cameras_data},
                            os.path.join(DATA_DIR, "cache", "incidents"))
detector.incidents = incidents
analytics_service.configure(incidents=incidents)
# Wrong-way + no-helmet detection on the live AI camera (shares the incident vision provider)
violations = ViolationMonitor(os.path.join(DATA_DIR, "vehicle_counts.db"), vision=incidents,
                              cameras_by_id=lambda: {c["camid"]: c for c in cameras_data})
detector.violations = violations
# Which live-AI cameras answer right now (the camera search marks the ones without signal)
camera_health = CameraHealth(lambda: cameras_data)
camera_health.start()

# BMA Traffic Scanner & YOLO Vehicle Counter for all cameras
bma_scanner = BmaScanner(detector=detector)
# Helmet patrol over every BMA camera: motorcycle crops -> helmet agent -> evidence on the data drive
helmet = HelmetPatrol(os.path.join(DATA_DIR, "vehicle_counts.db"), vision=incidents, scanner=bma_scanner)
bma_scanner.helmet = helmet
# Wrong-way patrol over every BMA camera: heading detector + per-camera learned lane directions -> agent -> evidence
wrongway = WrongWayPatrol(os.path.join(DATA_DIR, "vehicle_counts.db"), vision=incidents, scanner=bma_scanner)
bma_scanner.wrongway = wrongway
# Flood watch over every BMA camera: frames tiled 3x3 -> Qwen vision -> water on the road? -> map layer
flood_cams = FloodCamWatch(bma_scanner.cameras)
bma_scanner.flood = flood_cams
# ...and over the iTIC cameras around Bangkok (the Longdo list on the map), one frame from each HLS stream every 5 min
itic_frames = IticFrames(flood_cams, lambda: (longdo_cameras() or {}).get("items", []))
# Flood reports from the public (pin, depth, photo), checked by the same vision model before they reach the maps
user_reports = UserReports()
# Corridor dispersal guidance rebuilt every minute from the live Longdo lines + camera counts
guidance = GuidanceService(traffic, incidents=incidents, bma=bma_scanner, cameras=lambda: cameras_data)

# Start detector on initial Bangkok camera (Default: first BMA camera)
if cameras_data:
    init_cam = cameras_data[0]
    stream_url = init_cam.get("hls_url") or init_cam.get("vdourl")
    if stream_url:
        detector.start_stream(stream_url, init_cam)

# When this process started: the health check's uptime
SERVER_START = time.time()

_longdo_cams_cache = {"time": 0, "data": None}

def longdo_cameras():
    """Returns all cameras from Longdo Traffic API with disk and memory caching."""
    import urllib.request
    import re
    now = time.time()
    if now - _longdo_cams_cache["time"] < 300 and _longdo_cams_cache["data"] is not None:
        return _longdo_cams_cache["data"]

    cache_file = os.path.join(DATA_DIR, "cache", "longdo_cameras.json")
    try:
        req = urllib.request.Request("https://traffic.longdo.com/camera.json", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            items = data.get("item", [])
            if items:
                formatted = []
                for it in items:
                    title = (it.get("title") or "").strip()
                    m = re.match(r"^\(([^)]+)\)", title)
                    prov = m.group(1).replace("จ.", "").strip() if m else ""
                    formatted.append({
                        "camid": it.get("camid", ""),
                        "title": title,
                        "short_title": re.sub(r"^\([^)]+\)\s*", "", title),
                        "province": prov or "กรุงเทพมหานคร",
                        "organization": it.get("organization") or "Longdo Traffic",
                        "hls_url": it.get("hls_url") or "",
                        "vdourl": it.get("vdourl") or "",
                        "imgurl": it.get("imgurl") or "",
                        "latitude": float(it.get("latitude") or 0),
                        "longitude": float(it.get("longitude") or 0),
                        "geocode": str(it.get("geocode") or ""),
                        "lastupdate": it.get("lastupdate") or ""
                    })
                res_data = {"total": len(formatted), "items": formatted}
                _longdo_cams_cache["time"] = now
                _longdo_cams_cache["data"] = res_data
                try:
                    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(res_data, f, ensure_ascii=False)
                except Exception:
                    pass
                return res_data
    except Exception as e:
        print(f"[Warning] Failed to fetch live Longdo cameras: {e}")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                res_data = json.load(f)
                _longdo_cams_cache["data"] = res_data
                return res_data
        except Exception:
            pass

    return {"total": len(cameras_data), "items": cameras_data}

# ---------------------------------------------------------------- routes for the traffic assistant
def route_hazards():
    """Flooded spots for the chat bot's routes, and the sources that could not be read (flood_route.gather).
    `avoid` = keep the route out (deep enough to stop a car, or reported flooded with no depth); the rest is
    shallow water the answer only mentions."""
    return gather([
        ("เซ็นเซอร์น้ำ กทม.", lambda: sensor_spots(flood_roads.status())),
        ("กล้อง กทม. (AI)", lambda: [
            {"lat": float(c["lat"]), "lng": float(c["lng"]), "name": c.get("title"), "source": "กล้อง กทม. (AI)",
             "depth_text": c.get("level_th"), "avoid": c.get("level") in ("flooded", "severe")}
            for c in flood_cams.status()["items"] if c.get("lat") and c.get("lng") and not c.get("stale")]),
        ("ประชาชนแจ้ง", lambda: [
            {"lat": r["lat"], "lng": r["lng"], "name": r["note"] or "ประชาชนแจ้งน้ำท่วม", "source": "ประชาชนแจ้ง",
             "depth_cm": r["depth_cm"], "depth_text": r["depth_th"], "avoid": (r["depth_cm"] or 0) >= 20}
            for r in user_reports.recent()["items"]]),
        ("Longdo Traffic", lambda: [
            {"lat": f["lat"], "lng": f["lng"], "name": f["place"] or f["title"], "source": "Longdo Traffic",
             "avoid": "ผ่านได้" not in (f["place"] or "") + (f["description"] or "")}
            for f in incidents.floods()["items"] if f["active"]]),
        ("กรมทางหลวง", lambda: [
            {"lat": h["lat"], "lng": h["lng"], "name": h.get("place") or h.get("title"), "source": "กรมทางหลวง",
             "depth_cm": h.get("depth_cm"), "avoid": True}
            for h in hdms_floods.status()["items"] if h.get("active") and h.get("lat") and h.get("lng")]),
        ("ศูนย์จราจร กทม.", lambda: [
            {"lat": e["lat"], "lng": e["lng"], "name": e.get("title") or "น้ำท่วม", "source": "ศูนย์จราจร กทม.", "avoid": True}
            for e in bma_feed.get(kind="flood", hours=6, limit=100)["items"]
            if e.get("lat") is not None and e.get("lng") is not None]),
    ])

def route_jams():
    """Congested stretches of the live traffic roads, for the routes."""
    return [{"road": r["name"], "lat": h["lat"], "lng": h["lon"], "km": h["km"]}
            for r in traffic.get_roads(limit=5000) for h in r.get("hotspots") or []]

flood_router = FloodRouter(hazards=route_hazards, jams=route_jams)

# ---------------------------------------------------------------- Flood analyst agent (local model)
flood_agent = FloodAgent(DATA_DIR, {
    "flood": flood_roads.status, "water": water_service.get_summary, "north_flow": north_flow.brief,
    "forecast": lambda: analytics_service.get_summary().get("flood"),
    "traffy": traffy_reports.status, "tmd": tmd_warnings.status,
    "road_risk": lambda: road_risk.status(limit=2000),
    "bma_events": lambda: bma_feed.get(kind="flood", hours=6, limit=20),
    "longdo_floods": lambda: incidents.floods(hours=6),
})

def citizen_flood_reports():
    """Floods people report, for the province tab: Longdo Traffic in every province (still open; not the
    "DOH Admin" posts, which are the DOH highway tickets the tab already counts), this site's report form
    (published) and Traffy Fondue (Bangkok)."""
    out = [{"source": "Longdo Traffic", "title": f["title"], "text": f["description"], "depth": None,
            "ts": f["ts"], "lat": f["lat"], "lng": f["lng"]}
           for f in incidents.floods(national=True)["items"] if f["active"] and f["contributor"] != "DOH Admin"]
    out += [{"source": "แจ้งผ่านเว็บนี้", "title": r["note"] or "คนแจ้งน้ำท่วม", "text": r["ai_note"], "depth": r["depth_th"],
             "ts": r["ts"], "lat": r["lat"], "lng": r["lng"]} for r in user_reports.recent()["items"]]
    out += [{"source": "Traffy Fondue", "title": f"เขต{t['district']} กรุงเทพฯ" if t["district"] else "กรุงเทพมหานคร",
             "text": t["text"], "depth": t["depth"], "ts": t["ts"], "lat": t["lat"], "lng": t["lng"]}
            for t in traffy_reports.status()["items"] if t["lat"] is not None]
    return out

# Flood situation in every province, with the same local model's analysis
province_flood = ProvinceFlood(DATA_DIR, reports=citizen_flood_reports)
# 7-day outlook for dams, provinces and roads in the whole country, read by the same model
national_forecast = NationalForecast(DATA_DIR, province_flood)
# Where the northern water goes, the provinces on the way and its 7-day trend, read by the same model
north_route = NorthRoute(DATA_DIR, national_forecast)
# Each Bangkok district: canals, main gauges, road water, rain and Traffy reports, read by the same model
bkk_districts = BkkDistricts(DATA_DIR, {
    "water": water_service.get_map, "roads": flood_roads.status, "rain": water_service.rain_stations,
    "reports": lambda: traffy_reports.status()["items"],
    "river": lambda: next((p["days"] for p in north_route.status().get("provinces") or [] if p["province"] == "นนทบุรี-กรุงเทพฯ"), []),
})

# ---------------------------------------------------------------- BMA traffic-risk analyst (local model)
risk_agent = RiskAgent(DATA_DIR, os.path.join(BASE_DIR, "web", "public", "riskbkk"))

# ---------------------------------------------------------------- Traffy flood-report analyst (local model)
traffy_agent = TraffyAgent(DATA_DIR, traffy_reports.status)

# Every Traffy flood report kept in vehicle_counts.db, for day-to-day / week-to-week comparison
traffy_history = TraffyHistory(os.path.join(DATA_DIR, "vehicle_counts.db"), traffy_reports.status)

def start():
    """Start every background job, in the order server.py always used."""
    traffic.start()
    area_traffic.start()
    area_roads.warm()
    guidance.start()
    air.start()
    nasa_feeds.start()
    flood_roads.start()
    flood_cams.start()
    itic_frames.start()
    doh_cameras.start()
    world_cameras.start()
    user_reports.start()
    traffy_reports.start()
    tmd_warnings.start()
    hdms_floods.start()
    province_flood.start()
    national_forecast.start()
    north_route.start()
    bkk_districts.start()
    news_feed.start()
    js100_floods.start()
    # Heartbeats stamped by a wrong clock would otherwise sit in the online count forever
    telemetry.purge_future()
    road_risk.traffic, road_risk.flood, road_risk.water = traffic, flood_roads, water_service
    road_risk.start()
    water_service.warm()
    north_flow.start()
    rsc_service.warm(bma_scanner.cameras)
    bma_feed.start()
    flood_agent.start()
    risk_agent.start()
    traffy_agent.start()
    traffy_history.start()
