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
venv_python = (os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe") if sys.platform == "win32"
               else os.path.join(BASE_DIR, ".venv", "bin", "python"))
if os.path.exists(venv_python) and sys.prefix == sys.base_prefix and os.path.normcase(sys.executable) != os.path.normcase(venv_python):
    import subprocess
    print("[Auto-Env] Switching to virtual environment (.venv)...")
    code = subprocess.call([venv_python] + sys.argv)
    sys.exit(code)

import time
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))  # ANTHROPIC_API_KEY for the traffic assistant
except ImportError:
    pass
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
        my_pid = os.getpid()
        killed = False
        if sys.platform != "win32":
            # macOS / Linux: lsof lists the processes listening on the port
            import signal
            res = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
            for pid in (int(p) for p in res.stdout.split() if p.isdigit()):
                if pid != my_pid:
                    print(f"[Server] Closing old process PID {pid} on port {port}...")
                    os.kill(pid, signal.SIGTERM)
                    killed = True
            if killed:
                time.sleep(1.0)
            return
        res = subprocess.run(f'netstat -ano | findstr :{port}', shell=True, capture_output=True, text=True)
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

from backend.core.instance import PORT, DATA_DIR, IS_STAGE
free_port_if_needed(PORT)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import services   # builds the detector, scanner, watchers and agents (see backend/services.py)
from backend.api import bma, cameras, chat, flood, insights, live_ai, patrols, site, system, traffic, water, weather
from backend.core import access_guard
from backend.services import WEB_BUILT, WEB_DIST, detector

app = FastAPI(title="BKK StreetSmart CCTV & YOLO Vehicle Detection")

# CORS: the UI is served from this same origin (and Vite dev proxies /api), so no other website may
# read the API from a visitor's browser. ALLOWED_ORIGINS (comma separated) adds origins if ever needed.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Admin-Token"])
# Public-exposure guard: control endpoints operator-only, /api/chat rate limited (see access_guard.py)
app.middleware("http")(access_guard.guard)

# The API, one module per topic (backend/api/)
ROUTERS = (system, cameras, bma, live_ai, traffic, weather, patrols, flood, water, chat, insights, site)
for module in ROUTERS:
    app.include_router(module.router)

# Static files for the web frontend, after every API route
if WEB_BUILT:
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")
    # Only the UI folder is exposed (never the project root: .env, *.db, *.py, cameras_bma.json ...)
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="static")

services.start()
site.alerts.start()

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
    free_port_if_needed(PORT)
    if os.getenv("OPEN_BROWSER") == "1":
        start_browser_when_ready(f"http://localhost:{PORT}")
    print("=" * 60)
    print("  BKK StreetSmart CCTV & YOLO Vehicle Detection Server")
    print(f"  Model: {detector.model_name} | Processing Rate: {detector.target_fps:g} FPS")
    print("  Detected Classes: รถยนต์ (Cars), มอไซ (Motorcycles), รถบรรทุก (Trucks)")
    print(f"  Running at http://localhost:{PORT}" + (f"  [TEST instance, data in {DATA_DIR}]" if IS_STAGE else ""))
    print("=" * 60)
    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info", server_header=False)
    except BaseException as e:
        print(f"[Server] Exited with {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

