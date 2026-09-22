import os
import sys
import io

os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# 1. Auto-detect and switch to .venv if running under global Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if os.path.exists(venv_python) and sys.prefix == sys.base_prefix and os.path.normcase(sys.executable) != os.path.normcase(venv_python):
    import subprocess
    print(f"[Auto-Env] Switching to virtual environment (.venv)...")
    code = subprocess.call([venv_python] + sys.argv)
    sys.exit(code)

import json
import time
from datetime import datetime
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))  # ANTHROPIC_API_KEY for the traffic assistant
except ImportError:
    pass
import asyncio
import shutil
import threading
import socket

def free_port_if_needed(port=8000):
    """Ensure port is available, stopping old hung processes if needed."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return  # Port is free
        
        print(f"[Server] Port {port} is occupied. Attempting to free it...")
        import subprocess
        res = subprocess.run(f'netstat -ano | findstr :{port}', shell=True, capture_output=True, text=True)
        my_pid = os.getpid()
        killed = False
        for line in res.stdout.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                try:
                    pid = int(parts[4])
                    if pid != my_pid and pid > 0:
                        print(f"[Server] Closing old process PID {pid} on port {port}...")
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                        killed = True
                except ValueError:
                    pass
        if killed:
            time.sleep(1.0)
    except Exception as e:
        print(f"[Server] Note during port check: {e}")

free_port_if_needed(8000)
from fastapi import FastAPI, Request, Query, Body, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from yolo_detector import VehicleDetectorYOLO11x
from vehicle_log import VehicleLog
from count_workers import CountManager
from survey import SurveyManager
from incident_service import IncidentManager
from violation_service import ViolationMonitor
from traffic_service import traffic, get_traffic_tile, get_osm_tile
from guidance_service import GuidanceService
from helmet_service import HelmetPatrol
from air_service import air
import chat_service
import water_service
import rsc_service
from bma_events import bma_feed
from bma_service import BmaScanner
import analytics_service
from telemetry_service import telemetry
import access_guard

app = FastAPI(title="BKK StreetSmart CCTV & YOLO11x Vehicle Detection")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Public-exposure guard: control endpoints operator-only, /api/chat rate limited (see access_guard.py)
app.middleware("http")(access_guard.guard)

# Paths
# Stock COCO yolo26x by default. AI_MODEL=yolo26x_bkk.pt (or any .pt) in .env / env switches weights;
# the fine-tuned file is no longer picked up just because it exists (the first run missed motorcycles).
MODEL_PATH = os.path.join(BASE_DIR, os.getenv("AI_MODEL", "yolo26x.pt"))
if not os.path.exists(MODEL_PATH):
    print(f"[AI] {MODEL_PATH} not found, falling back to yolo26x.pt")
    MODEL_PATH = os.path.join(BASE_DIR, "yolo26x.pt")
CAMERAS_FILE = os.path.join(BASE_DIR, "cameras_bkk.json")
# Legacy vanilla UI (local/legacy_ui) is only the fallback when web/dist has not been built
LEGACY_UI = os.path.join(BASE_DIR, "local", "legacy_ui")
STATIC_DIR = LEGACY_UI
INDEX_HTML = os.path.join(LEGACY_UI, "index.html")
# New React UI (web/dist) takes precedence when built
WEB_DIST = os.path.join(BASE_DIR, "web", "dist")
if os.path.exists(os.path.join(WEB_DIST, "index.html")):
    STATIC_DIR = WEB_DIST
    INDEX_HTML = os.path.join(WEB_DIST, "index.html")

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

# Initialize YOLO11x Vehicle Detector (Target: 10 FPS for smoother playback)
vehicle_log = VehicleLog(os.path.join(BASE_DIR, "vehicle_counts.db"))
detector = VehicleDetectorYOLO11x(model_path=MODEL_PATH, target_fps=10.0, conf_threshold=0.15, vehicle_log=vehicle_log)
# Background counting on user-selected cameras (lower fps to prioritize live camera)
counter = CountManager(detector, vehicle_log, os.path.join(BASE_DIR, "count_cameras.json"), target_fps=0.5, max_cameras=4)
counter.load({c["camid"]: c for c in cameras_data})
# Round-robin survey sampling: default 0 workers to prevent FFmpeg C-level crashes on corrupt Longdo HLS streams
survey_workers = int(os.getenv("SURVEY_WORKERS", "0"))
survey = SurveyManager(detector, vehicle_log, lambda: cameras_data, lambda: set(counter.workers),
                       workers=survey_workers, sample_seconds=12.0, target_fps=0.5)
survey.start()
# Accident / breakdown detection (camera AI + Claude vision) and Longdo accident reports
incidents = IncidentManager(vehicle_log, lambda: {c["camid"]: c for c in cameras_data},
                            os.path.join(BASE_DIR, "cache", "incidents"))
detector.incidents = incidents
analytics_service.configure(incidents=incidents)
# Wrong-way + no-helmet detection on the live AI camera (shares the incident vision provider)
violations = ViolationMonitor(os.path.join(BASE_DIR, "vehicle_counts.db"), vision=incidents,
                              cameras_by_id=lambda: {c["camid"]: c for c in cameras_data})
detector.violations = violations

# BMA Traffic Scanner & YOLO Vehicle Counter for all cameras
bma_scanner = BmaScanner(detector=detector)
# Helmet patrol over every BMA camera: motorcycle crops -> helmet agent -> evidence on the data drive
helmet = HelmetPatrol(os.path.join(BASE_DIR, "vehicle_counts.db"), vision=incidents, scanner=bma_scanner)
bma_scanner.helmet = helmet
# Corridor dispersal guidance rebuilt every minute from the live Longdo lines + camera counts
guidance = GuidanceService(traffic, incidents=incidents, bma=bma_scanner, cameras=lambda: cameras_data)

# Start detector on initial Bangkok camera (Default: first BMA camera)
if cameras_data:
    init_cam = cameras_data[0]
    stream_url = init_cam.get("hls_url") or init_cam.get("vdourl")
    if stream_url:
        detector.start_stream(stream_url, init_cam)

# API Endpoints
# ---------------------------------------------------------------- Health (watchdog / uptime monitor)
SERVER_START = time.time()

@app.get("/api/health")
def health():
    """One call for a watchdog: 200 + ok=true when the scanner ran recently and the detector answers.
    Returns 503 when the BMA scan is stale (> 3 cycles) so an external monitor can restart the server."""
    now = time.time()
    scan = bma_scanner.get_status()
    last_scan = scan.get("last_scan_time") or 0
    scan_age = int(now - last_scan) if last_scan else None
    # Fresh process: the first cycle over 574 cameras takes a few minutes, so give it a grace period
    scan_ok = (scan_age is not None and scan_age < 15 * 60) or (not last_scan and now - SERVER_START < 20 * 60)
    gpu = None
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            gpu = {"name": torch.cuda.get_device_name(0), "used_mb": int((total - free) / 2**20), "total_mb": int(total / 2**20)}
    except Exception:  # noqa: BLE001
        pass
    try:
        disk = shutil.disk_usage(os.getenv("BMA_DATA_DIR", BASE_DIR))
        data_disk = {"path": os.getenv("BMA_DATA_DIR", BASE_DIR), "free_gb": round(disk.free / 2**30, 1), "total_gb": round(disk.total / 2**30, 1)}
    except OSError:
        data_disk = None
    hs = helmet.status()
    body = {
        "ok": scan_ok and (SERVER_START < now),
        "uptime_s": int(now - SERVER_START),
        "scan": {"cycle": scan.get("cycle_count"), "age_s": scan_age, "running": scan.get("is_scanning"), "ok": scan_ok},
        "ai_fps": detector.get_stats().get("fps"),
        "helmet": {"agent": hs.get("agent"), "agent_error": hs.get("agent_error"), "queue": hs.get("queue")},
        "gpu": gpu, "data_disk": data_disk,
        "db_mb": round(os.path.getsize(os.path.join(BASE_DIR, "vehicle_counts.db")) / 2**20, 1),
    }
    return JSONResponse(body, status_code=200 if body["ok"] else 503)

@app.get("/api/cameras")
def get_cameras():
    return {"total": len(cameras_data), "items": cameras_data}

_longdo_cams_cache = {"time": 0, "data": None}

@app.get("/api/cameras/longdo")
def get_longdo_cameras():
    """Returns all cameras from Longdo Traffic API with disk and memory caching."""
    import urllib.request
    import re
    now = time.time()
    if now - _longdo_cams_cache["time"] < 300 and _longdo_cams_cache["data"] is not None:
        return _longdo_cams_cache["data"]

    cache_file = os.path.join(BASE_DIR, "cache", "longdo_cameras.json")
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

# BMA Traffic & YOLO Vehicle Counting Endpoints
@app.get("/api/bma/cameras")
def get_bma_cameras():
    """Returns all BMA cameras with latest detection counts, road, district, and status."""
    cams = bma_scanner.db.get_all_latest()
    if not cams:
        cams = bma_scanner.cameras
    return {"total": len(bma_scanner.cameras), "items": cams}

@app.get("/api/bma/analytics")
def get_bma_analytics():
    """Returns comprehensive data analysis for BMA cameras vehicle counts."""
    return bma_scanner.get_analytics()

@app.post("/api/bma/scan")
def trigger_bma_scan():
    """Start an immediate scan of all BMA cameras."""
    return bma_scanner.start_scan()

@app.get("/api/bma/scan/status")
def get_bma_scan_status():
    """Returns current scanning progress across all BMA cameras."""
    return bma_scanner.get_status()

@app.get("/api/bma/snapshot/{camid}")
async def get_bma_snapshot(camid: str, live: bool = False, annotate: bool = True):
    """Returns annotated or raw snapshot for a BMA camera. If live=True, fetches latest real-time frame."""
    loop = asyncio.get_running_loop()
    if live:
        try:
            jpeg_bytes, stats = await loop.run_in_executor(
                None, lambda: bma_scanner.get_live_snapshot(camid, annotate=annotate)
            )
            if jpeg_bytes:
                return Response(
                    content=jpeg_bytes,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
                )
        except Exception as e:
            print(f"[Live Snapshot Error] {e}")

    cache_file = os.path.join(BASE_DIR, "cache", "bma_snapshots", f"{camid}.jpg")
    if os.path.exists(cache_file):
        return FileResponse(cache_file, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    try:
        raw = await loop.run_in_executor(None, lambda: bma_scanner.session.fetch_snapshot(str(camid), timeout=4.0))
        if raw:
            return Response(content=raw, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    except Exception:
        pass
    return Response(status_code=404)

@app.get("/api/bma/stream/{camid}")
async def stream_bma_camera(camid: str, fps: float = 2.0):
    """Live MJPEG video stream with real-time YOLO detection overlay for any BMA camera."""
    async def _stream():
        cam = next((c for c in bma_scanner.cameras if str(c.get('camid')) == str(camid)), None)
        if not cam:
            return
        
        # 1. Immediately yield cached snapshot so client never experiences a black screen!
        cache_file = os.path.join(BASE_DIR, "cache", "bma_snapshots", f"{camid}.jpg")
        last_frame = None
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "rb") as f:
                    last_frame = f.read()
                if last_frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + last_frame + b'\r\n')
            except Exception:
                pass

        interval = 1.0 / max(0.5, min(5.0, fps))
        loop = asyncio.get_running_loop()
        while True:
            t0 = time.time()
            try:
                raw = await loop.run_in_executor(None, lambda: bma_scanner.session.fetch_snapshot(str(camid), timeout=7.0))
                if raw:
                    jpeg_bytes, _ = await loop.run_in_executor(None, lambda: bma_scanner.process_image_and_detect(cam, raw))
                    if jpeg_bytes:
                        last_frame = jpeg_bytes
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
                elif last_frame:
                    # Keep yielding last frame to prevent stream connection from stalling
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + last_frame + b'\r\n')
            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception:
                pass
            
            elapsed = time.time() - t0
            sleep_time = max(0.5, interval - elapsed)
            await asyncio.sleep(sleep_time)

    return StreamingResponse(
        _stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/bma/live_analysis/{camid}")
async def get_bma_live_analysis(camid: str):
    """Fetches a real-time snapshot, runs YOLO, and returns live vehicle detection analysis."""
    loop = asyncio.get_running_loop()
    try:
        jpeg_bytes, stats = await loop.run_in_executor(
            None, lambda: bma_scanner.get_live_snapshot(camid, annotate=True)
        )
        if stats:
            return {
                "camid": camid,
                "cars": stats["cars"],
                "motorcycles": stats["motorcycles"],
                "trucks": stats["trucks"],
                "total": stats["total"],
                "level": stats["level"],
                "ts": stats["timestamp"],
                "detections": stats.get("detections", []),
                "live": True
            }
    except Exception as e:
        print(f"[Live Analysis Error] {e}")
    
    c = bma_scanner.db.get_camera_latest(camid)
    if c:
        return c
    return {"error": "Camera unavailable", "camid": camid}

@app.get("/api/bma/export/csv")
def export_bma_csv():
    """Export BMA vehicle count data as CSV."""
    import csv
    cams = bma_scanner.db.get_all_latest()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Camera ID", "Camera Code", "Location", "Road", "District",
        "Cars", "Motorcycles", "Trucks/Buses", "Total Vehicles",
        "Traffic Level", "Status", "Timestamp"
    ])
    for c in cams:
        ts_val = c.get('ts')
        ts_str = datetime.fromtimestamp(ts_val).strftime('%Y-%m-%d %H:%M:%S') if ts_val else ""
        writer.writerow([
            c.get('camid', ''), c.get('camera_code', ''), c.get('title', ''),
            c.get('road', ''), c.get('district', ''),
            c.get('cars', 0), c.get('motorcycles', 0), c.get('trucks', 0), c.get('total', 0),
            c.get('level', ''), c.get('status', ''), ts_str
        ])
    output.seek(0)
    return Response(
        content=output.getvalue().encode('utf-8-sig'),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bma_traffic_vehicle_counts.csv"}
    )

@app.get("/api/bma/cycle")
def get_bma_cycle():
    """Automatic count cycle: running totals since the last reset and when the next reset happens."""
    return bma_scanner.get_cycle_status()

@app.get("/api/bma/comparison")
def get_bma_comparison(period: str = Query("day", pattern="^(day|week|month)$")):
    """Returns comparative data analysis across Day, Week, and Month periods."""
    return bma_scanner.get_comparison(period=period)

@app.get("/api/bma/drive_d_status")
def get_bma_drive_d_status():
    """Folder layout under the CSV export directory (D:\\Data by default)."""
    return bma_scanner.archiver.files_status()

@app.get("/api/ai/stats")
def get_ai_stats():
    return detector.get_stats()

@app.post("/api/ai/reset_passed")
def reset_ai_passed():
    """Restart the passed-vehicle counter of the live camera (start of a manual count)."""
    return detector.reset_passed()

@app.get("/api/ai/accuracy")
def get_ai_accuracy(limit: int = Query(50, ge=1, le=500)):
    """Manual-vs-AI checks: per-row absolute error / accuracy plus MAE and mean accuracy."""
    return vehicle_log.accuracy_checks(limit=limit)

@app.post("/api/ai/accuracy")
def add_ai_accuracy(payload: dict = Body(...)):
    """Save one check. ai_count defaults to the live camera's passed_total since the last reset."""
    try:
        manual = int(payload.get("manual_count"))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "manual_count must be an integer"})
    if manual < 0:
        return JSONResponse(status_code=400, content={"error": "manual_count must be >= 0"})
    st = detector.get_stats()
    camid = payload.get("camid") or st.get("camid") or ""
    title = payload.get("title") or (st.get("title") if camid == st.get("camid") else None)
    if not title:
        cam = next((c for c in cameras_data if c["camid"] == camid), None)
        title = cam.get("short_title", cam.get("title")) if cam else camid
    ai = payload.get("ai_count")
    duration = payload.get("duration_s")
    if ai is None:
        if camid != st.get("camid"):
            return JSONResponse(status_code=400, content={"error": "ai_count required when camera is not the live one"})
        ai = st.get("passed_total", 0)
        if duration is None and st.get("passed_since"):
            duration = int(time.time()) - int(st["passed_since"])
    try:
        ai = int(ai)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "ai_count must be an integer"})
    row = vehicle_log.add_accuracy_check(camid, title, manual, ai, duration_s=duration, note=(payload.get("note") or None))
    return row

@app.delete("/api/ai/accuracy/{check_id}")
def delete_ai_accuracy(check_id: int):
    if not vehicle_log.delete_accuracy_check(check_id):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"deleted": check_id}

@app.get("/api/ai/history")
def get_ai_history(range: str = Query("24h", pattern="^(24h|7d|30d)$"), date: str = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), camid: str = Query(None)):
    """Vehicles that passed each camera: hourly for 24h or a given date, daily for 7d/30d."""
    return vehicle_log.history(range_=range, date=date, camid=camid)

@app.get("/api/count/cameras")
def get_count_cameras():
    return counter.status()

@app.get("/api/survey/ranking")
def get_survey_ranking():
    """Every camera with its latest measurement: continuous counters plus round-robin survey samples."""
    now = int(time.time())
    items = []
    for c in counter.status()["cameras"]:
        if c["active"]:
            items.append({"camid": c["camid"], "title": c["title"], "ts": now, "source": "count",
                          "rate_per_min": c["rate_per_min"], "visible": c["total"],
                          "moving_pct": c["moving_pct"], "level": c["level"], "error": ""})
    sv = survey.status()
    items += sv["cameras"]
    return {"cycle_seconds": sv["cycle_seconds"], "sample_seconds": sv["sample_seconds"],
            "total_cameras": len(cameras_data), "cameras": items}

@app.get("/api/incidents")
def get_incidents():
    return incidents.status()

@app.get("/api/incidents/history")
def get_incident_history(hours: int = Query(24, ge=1, le=168)):
    items = vehicle_log.recent_incidents(hours) + incidents.recent_longdo(hours)
    return {"hours": hours, "items": sorted(items, key=lambda i: -i['ts'])}

@app.get("/api/incidents/{incident_id}/image")
def get_incident_image(incident_id: str):
    path = incidents.snapshot_path(incident_id)
    if not path:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

@app.put("/api/count/cameras")
def set_count_cameras(payload: dict = Body(...)):
    camids = payload.get("camids") or []
    if not isinstance(camids, list) or len(camids) > counter.max_cameras:
        return JSONResponse(status_code=400, content={"error": f"camids must be a list of at most {counter.max_cameras}"})
    by_id = {c["camid"]: c for c in cameras_data}
    counter.set_cameras([by_id[c] for c in camids if c in by_id])
    return counter.status()

@app.post("/api/ai/switch_camera")
def switch_camera(
    camid: str = Query(..., description="Camera ID"),
    stream_url: str = Query(None, description="Direct stream URL"),
    title: str = Query(None, description="Camera title"),
    province: str = Query(None, description="Camera province")
):
    cam = next((c for c in cameras_data if c["camid"] == camid), None)
    
    if not cam and stream_url:
        # Create dynamic camera entry from frontend parameters
        cam = {
            "camid": camid,
            "title": title or camid,
            "short_title": title or camid,
            "province": province or "กรุงเทพมหานคร",
            "hls_url": stream_url
        }
        cameras_data.append(cam)
    
    if not cam:
        return JSONResponse(status_code=404, content={"error": f"Camera {camid} not found"})

    target_url = stream_url or cam.get("hls_url") or cam.get("vdourl")
    if not target_url:
        return JSONResponse(status_code=400, content={"error": "Camera has no stream URL"})

    detector.start_stream(target_url, cam)
    return {"status": "success", "camid": camid, "title": cam.get("short_title", cam.get("title"))}

@app.post("/api/ai/set_fps")
def set_fps(fps: float = Query(5.0, ge=1.0, le=30.0)):
    detector.set_target_fps(fps)
    return {"status": "success", "target_fps": fps}

@app.post("/api/ai/set_conf")
def set_conf(conf: float = Query(0.20, ge=0.05, le=0.9)):
    detector.set_confidence(conf)
    return {"status": "success", "conf_threshold": conf}

@app.post("/api/ai/set_night_mode")
def set_night_mode(enabled: bool = Query(True)):
    detector.set_night_mode(enabled)
    return {"status": "success", "night_mode": enabled}

async def generate_mjpeg_stream():
    """Generator for MJPEG video stream regulated at detector's target FPS (~5 FPS)"""
    try:
        while True:
            frame = detector.get_latest_frame()
            if frame is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            await asyncio.sleep(detector.frame_interval)
    except (asyncio.CancelledError, GeneratorExit):
        pass
    except Exception:
        pass

@app.get("/api/ai/stream")
async def video_feed(camid: str = None, url: str = None):
    # If a specific camid is requested and different from current, switch
    if camid:
        current_camid = detector.latest_stats.get("camid")
        if current_camid != camid:
            cam = next((c for c in cameras_data if c["camid"] == camid), None)
            if cam:
                target_url = url or cam.get("hls_url") or cam.get("vdourl")
                if target_url:
                    detector.start_stream(target_url, cam)
            elif url:
                new_cam = {"camid": camid, "title": camid, "short_title": camid, "province": "กรุงเทพมหานคร"}
                detector.start_stream(url, new_cam)

    return StreamingResponse(
        generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# ---------------------------------------------------------------- Traffic map + assistant
@app.get("/api/traffic/summary")
def traffic_summary(top: int = Query(8, ge=1, le=30)):
    return traffic.get_summary(top=top)

@app.get("/api/weather/wind")
def weather_wind():
    """Current wind / rain / cloud on a 7x7 grid over Bangkok (Open-Meteo) for the map overlay."""
    return water_service.get_wind_grid()

@app.get("/api/air/stations")
def air_stations():
    """PM2.5 / AQI per monitoring station in Bangkok + surrounding provinces (Air4Thai)."""
    return air.status()

@app.get("/api/traffic/guidance")
def traffic_guidance():
    """Live dispersal guidance per main corridor: hotspots, bypass roads with live flow, advice text."""
    return guidance.status()

# ---------------------------------------------------------------- Helmet patrol (all BMA cameras)
@app.get("/api/helmet/status")
def helmet_status():
    return helmet.status()

@app.get("/api/helmet/recent")
def helmet_recent(hours: int = Query(24, ge=1, le=720), verdict: str = Query(None, pattern="^(pending|helmet|no_helmet|suspect|unclear|error)$"),
                  camid: str = Query(None), limit: int = Query(200, ge=1, le=1000)):
    return helmet.recent(hours=hours, verdict=verdict, camid=camid, limit=limit)

@app.get("/api/helmet/cameras")
def helmet_cameras():
    return helmet.cameras()

@app.post("/api/helmet/check/{camid}")
async def helmet_check(camid: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: helmet.check_now(camid))

@app.post("/api/helmet/reanalyse_pending")
async def helmet_reanalyse_pending(agent: str = Query("cloud", pattern="^(cloud)$"), limit: int = Query(40, ge=1, le=300), hours: int = Query(24, ge=1, le=168)):
    """Send every unclear / failed capture of the last hours through the chosen agent again."""
    return helmet.reanalyse_pending(agent=agent, limit=limit, hours=hours)

@app.post("/api/helmet/{hid}/reanalyse")
async def helmet_reanalyse(hid: str, agent: str = Query("cloud", pattern="^(cloud)$")):
    """Run one capture through the cloud agent (Gemini/Claude) again."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: helmet.reanalyse(hid, agent))

@app.get("/api/helmet/{hid}/crop")
def helmet_crop(hid: str):
    p = helmet.crop_path(hid)
    if not os.path.exists(p):
        raise HTTPException(404, "no image")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

@app.get("/api/helmet/{hid}/frame")
def helmet_frame(hid: str):
    p = helmet.frame_path(hid)
    if not os.path.exists(p):
        raise HTTPException(404, "no image")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

@app.get("/api/traffic/roads")
def traffic_roads(q: str = Query(None), limit: int = Query(50, ge=1, le=500)):
    return {"items": traffic.get_roads(q, limit)}

@app.get("/api/traffic/road_cameras")
def traffic_road_cameras(name: str = Query(...), max_km: float = Query(0.25, ge=0.05, le=2.0)):
    """Cameras located on / next to the named road, nearest first."""
    return {"name": name, "items": traffic.cameras_on_road(name, cameras_data, max_km)}

@app.get("/api/traffic/tile/{z}/{x}/{y}.pbf")
def traffic_tile(z: int, x: int, y: int):
    data, stale = get_traffic_tile(z, x, y)
    if not data:
        return Response(status_code=204)
    return Response(content=data, media_type="application/vnd.mapbox-vector-tile",
                    headers={"Content-Encoding": "gzip", "Cache-Control": "max-age=60",
                             "X-Stale": "1" if stale else "0"})

@app.get("/api/tiles/base/{z}/{x}/{y}.png")
def base_tile(z: int, x: int, y: int):
    try:
        data = get_osm_tile(z, x, y)
    except Exception:
        return Response(status_code=204)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "max-age=86400"})

# ---------------------------------------------------------------- Water outlook (ThaiWater / HII + BMA)
@app.get("/api/water/summary")
def water_summary():
    try:
        return water_service.get_summary()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e), "api_key": water_service.key_status()})

@app.get("/api/water/forecast")
def water_forecast(station: int = Query(..., ge=1)):
    """Observed + official (HII) or local tidal-harmonic outlook for one telemetry station."""
    try:
        return water_service.get_forecast(station)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

@app.get("/api/water/bma_events")
def water_bma_events(kind: str = Query(None), hours: int = Query(24, ge=1, le=168), limit: int = Query(60, ge=1, le=200)):
    """Live BMA traffic-centre reports (flooded roads, accidents, closures), polled every minute."""
    return bma_feed.get(kind=kind, hours=hours, limit=limit)

# ---------------------------------------------------------------- Traffic violations (wrong way / no helmet)
@app.get("/api/ai/violations")
def ai_violations(hours: int = Query(24, ge=1, le=168), camid: str = Query(None), kind: str = Query(None, pattern="^(wrong_way|no_helmet)$"), limit: int = Query(100, ge=1, le=500)):
    """Logged violations from the live AI camera, newest first, with evidence image links."""
    return violations.recent(hours=hours, camid=camid, kind=kind, limit=limit)

@app.get("/api/ai/violations/status")
def ai_violations_status(camid: str = Query(None)):
    """How much of each camera's direction-of-travel map is learned, and whether helmet checks are on."""
    return violations.status(camid=camid)

@app.get("/api/ai/violations/{vid}/image")
def ai_violation_image(vid: str):
    p = violations.image_path(vid)
    if not p:
        return Response(status_code=404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

# ---------------------------------------------------------------- Road accidents (Thai RSC)
@app.get("/api/rsc/summary")
def rsc_summary():
    """Bangkok accident stats (today / YTD / by vehicle / by hour / by district) joined with BMA camera load."""
    try:
        return rsc_service.get_summary()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

@app.get("/api/rsc/camera_risk")
def rsc_camera_risk(limit: int = Query(None, ge=1, le=600), district: str = Query(None)):
    """BMA cameras ranked by accident points within RADIUS_M (current + previous year)."""
    return rsc_service.get_camera_risk(limit=limit, district=district)

@app.get("/api/rsc/points")
def rsc_points(camid: str = Query(None), lat: float = Query(None), lon: float = Query(None), radius: int = Query(None, ge=50, le=3000), limit: int = Query(500, ge=1, le=5000)):
    """Accident points near one camera (victim identity removed)."""
    return rsc_service.get_points(camid=camid, cameras=bma_scanner.cameras, radius_m=radius, lat=lat, lon=lon, limit=limit)

@app.get("/api/rsc/points.geojson")
def rsc_points_geojson():
    return rsc_service.get_points_geojson()

@app.post("/api/rsc/rebuild")
def rsc_rebuild(force: bool = Query(False)):
    """Re-fetch accident points from Thai RSC and rescore every camera (background)."""
    return rsc_service.build_camera_risk(bma_scanner.cameras, force=force)

# ---------------------------------------------------------------- Urban analytics (5 sections) + visitor telemetry
@app.get("/api/analytics/summary")
def analytics_summary(refresh: bool = Query(False)):
    """Traffic overview, flood watch + 1-6 h outlook, density tiers, black spots, dashboard visitors."""
    return analytics_service.get_summary(force=refresh)

@app.get("/api/analytics/export")
def analytics_export(format: str = Query("json", pattern="^(json|csv)$"),
                     section: str = Query("traffic", pattern="^(traffic|flood|density|accidents|visitors)$")):
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if format == "csv":
        return Response(content=analytics_service.export_csv(section), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="analytics-{section}-{stamp}.csv"'})
    body = json.dumps(analytics_service.get_summary(), ensure_ascii=False, indent=1)
    return Response(content=body, media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="analytics-{stamp}.json"'})

@app.get("/api/telemetry/online")
def telemetry_online():
    return {"ok": True, "online": telemetry.online_count()}

@app.post("/api/telemetry/view")
def telemetry_view(payload: dict = Body(...)):
    return {"ok": telemetry.view(payload.get("sid"), payload.get("view"))}

@app.post("/api/telemetry/heartbeat")
def telemetry_heartbeat(payload: dict = Body(...)):
    return {"ok": telemetry.heartbeat(payload.get("sid"), payload.get("view"))}

@app.post("/api/chat")
def chat_endpoint(payload: dict = Body(...)):
    messages = payload.get("messages") or []
    messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    if not messages:
        return JSONResponse(status_code=400, content={"error": "messages required"})
    try:
        water = water_service.get_summary()
    except Exception:
        water = None
    extra = {}
    for key, fn in (("incidents", incidents.status), ("bma_events", lambda: bma_feed.get(hours=12, limit=20)),
                    ("bma_analytics", bma_scanner.get_analytics), ("rsc", rsc_service.get_summary),
                    ("camera_risk", lambda: rsc_service.get_camera_risk(limit=8))):
        try:
            extra[key] = fn()
        except Exception as e:
            print(f"[Chat] {key} unavailable: {e}")
    return chat_service.chat(traffic, messages, detector.get_stats(), water, extra)

# Static files for web frontend
@app.get("/")
def read_root():
    # never cache the shell so a rebuilt bundle is picked up on the next reload
    return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})

@app.get("/cameras_bkk.json")
def read_cameras_json():
    # the React app fetches this directly; serve the live root copy, not the stale one bundled in web/dist
    return FileResponse(CAMERAS_FILE, media_type="application/json", headers={"Cache-Control": "no-cache"})

if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")
# Only the UI folder is exposed (never the project root: .env, *.db, *.py, cameras_bma.json ...)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

traffic.start()
guidance.start()
air.start()
water_service.warm()
rsc_service.warm(bma_scanner.cameras)
bma_feed.start()

def start_browser_when_ready(url="http://localhost:8000"):
    """Opens browser only when server is confirmed responsive."""
    def _poll_and_open():
        import urllib.request
        import webbrowser
        for _ in range(40):
            time.sleep(0.6)
            try:
                with urllib.request.urlopen(f"{url}/api/ai/stats", timeout=1.5) as resp:
                    if resp.status == 200:
                        print(f"[Server] Server is ready! Opening browser at {url} ...")
                        webbrowser.open(url)
                        return
            except Exception:
                pass
    threading.Thread(target=_poll_and_open, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    free_port_if_needed(8000)
    if os.getenv("OPEN_BROWSER") == "1":
        start_browser_when_ready("http://localhost:8000")
    print("=" * 60)
    print("  BKK StreetSmart CCTV & YOLO11x Vehicle Detection Server")
    print("  Model: YOLO11x | Processing Rate: 5 FPS")
    print("  Detected Classes: รถยนต์ (Cars), มอไซ (Motorcycles), รถบรรทุก (Trucks)")
    print("  Running at http://localhost:8000")
    print("=" * 60)
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except BaseException as e:
        print(f"[Server] Exited with {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

