import os
import sys

# 1. Auto-detect and switch to .venv if running under global Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if os.path.exists(venv_python) and os.path.normcase(sys.executable) != os.path.normcase(venv_python):
    import subprocess
    print(f"[Auto-Env] Switching to virtual environment (.venv)...")
    code = subprocess.call([venv_python] + sys.argv)
    sys.exit(code)

import json
import time
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))  # ANTHROPIC_API_KEY for the traffic assistant
except ImportError:
    pass
import asyncio
import threading
import socket
from fastapi import FastAPI, Request, Query, Body
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from yolo_detector import VehicleDetectorYOLO11x
from traffic_service import traffic, get_traffic_tile, get_osm_tile
import chat_service

app = FastAPI(title="BKK Traffic CCTV & YOLO11x Vehicle Detection")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
MODEL_PATH = os.path.join(BASE_DIR, "yolo11x.pt")
CAMERAS_FILE = os.path.join(BASE_DIR, "cameras_bkk.json")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")
# New React UI (web/dist) takes precedence when built
WEB_DIST = os.path.join(BASE_DIR, "web", "dist")
if os.path.exists(os.path.join(WEB_DIST, "index.html")):
    INDEX_HTML = os.path.join(WEB_DIST, "index.html")

# Load cameras
cameras_data = []
if os.path.exists(CAMERAS_FILE):
    try:
        with open(CAMERAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            cameras_data = data.get("items", [])
    except Exception as e:
        print(f"[Warning] Failed to load cameras_bkk.json: {e}")

# Fetch live Longdo cameras in background to enrich camera list
def update_cameras_from_longdo():
    global cameras_data
    try:
        import urllib.request
        url = 'https://traffic.longdo.com/camera.json'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            items = data.get('item', [])
            bkk_provs = ['กรุงเทพมหานคร', 'นนทบุรี', 'ปทุมธานี', 'สมุทรปราการ', 'สมุทรสาคร', 'นครปฐม']
            existing_ids = {c['camid'] for c in cameras_data}
            added = 0
            for it in items:
                camid = it.get('camid', '')
                if not camid or camid in existing_ids:
                    continue
                title = it.get('title', '')
                geo = str(it.get('geocode', '')).strip()
                if any(p in title for p in bkk_provs) or geo.startswith(('10', '11', '12', '13', '73', '74')):
                    cameras_data.append({
                        'camid': camid,
                        'title': title,
                        'short_title': title.split(')', 1)[-1].strip() if ')' in title else title,
                        'province': 'กรุงเทพมหานคร' if geo.startswith('10') or 'กรุงเทพ' in title else 'ปริมณฑล',
                        'organization': it.get('organization', 'Longdo'),
                        'hls_url': it.get('hls_url', ''),
                        'vdourl': it.get('vdourl', ''),
                        'imgurl': it.get('imgurl', ''),
                    })
                    existing_ids.add(camid)
                    added += 1
            if added > 0:
                print(f"[Server] Enriched camera list with {added} cameras from Longdo (Total: {len(cameras_data)})")
    except Exception as e:
        print(f"[Server] Live camera sync info: {e}")

threading.Thread(target=update_cameras_from_longdo, daemon=True).start()

# Initialize YOLO11x Vehicle Detector (Target: 5 FPS)
detector = VehicleDetectorYOLO11x(model_path=MODEL_PATH, target_fps=5.0, conf_threshold=0.30)

# Start detector on initial Bangkok camera
if cameras_data:
    # Prefer Rama 4 or Vibhavadi
    init_cam = next((c for c in cameras_data if c["camid"] == "ITICM_BMAMI0074"), cameras_data[0])
    stream_url = init_cam.get("hls_url") or init_cam.get("vdourl")
    if stream_url:
        detector.start_stream(stream_url, init_cam)

# API Endpoints
@app.get("/api/cameras")
def get_cameras():
    return {"total": len(cameras_data), "items": cameras_data}

@app.get("/api/ai/stats")
def get_ai_stats():
    return detector.get_stats()

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
def set_conf(conf: float = Query(0.30, ge=0.1, le=0.9)):
    detector.set_confidence(conf)
    return {"status": "success", "conf_threshold": conf}

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
def video_feed(camid: str = None, url: str = None):
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

@app.get("/api/traffic/roads")
def traffic_roads(q: str = Query(None), limit: int = Query(50, ge=1, le=500)):
    return {"items": traffic.get_roads(q, limit)}

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

@app.post("/api/chat")
def chat_endpoint(payload: dict = Body(...)):
    messages = payload.get("messages") or []
    messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    if not messages:
        return JSONResponse(status_code=400, content={"error": "messages required"})
    return chat_service.chat(traffic, messages, detector.get_stats())

# Static files for web frontend
@app.get("/")
def read_root():
    return FileResponse(INDEX_HTML)

if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

traffic.start()

def free_port_if_needed(port=8000):
    """Ensure port 8000 is available, stopping old hung processes if needed."""
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
    start_browser_when_ready("http://localhost:8000")
    print("=" * 60)
    print("  BKK Traffic CCTV & YOLO11x Vehicle Detection Server")
    print("  Model: YOLO11x | Processing Rate: 5 FPS")
    print("  Detected Classes: รถยนต์ (Cars), มอไซ (Motorcycles), รถบรรทุก (Trucks)")
    print("  Running at http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

