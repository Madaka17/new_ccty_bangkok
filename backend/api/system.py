"""
Health, the web UI shell and the files served next to it.
"""
import os
import shutil
import time
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.core.instance import DATA_DIR, IS_STAGE, PORT
from backend.services import bma_scanner, CAMERAS_FILE, detector, helmet, INDEX_HTML, SERVER_START, WEB_BUILT, WEB_DIST, wrongway

router = APIRouter()


@router.get("/api/health")
def health():
    """One call for a watchdog: 200 + ok=true when the scanner ran recently and the detector answers.
    Returns 503 when the BMA scan is stale (> 3 cycles) so an external monitor can restart the server."""
    now = time.time()
    scan = bma_scanner.get_status()
    # bma_service stores last_scan_time as "%Y-%m-%d %H:%M:%S" text (the UI shows it as is)
    last_scan = scan.get("last_scan_time")
    last_scan = datetime.strptime(last_scan, "%Y-%m-%d %H:%M:%S").timestamp() if last_scan else 0
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
        disk = shutil.disk_usage(os.getenv("BMA_DATA_DIR", DATA_DIR))
        data_disk = {"path": os.getenv("BMA_DATA_DIR", DATA_DIR), "free_gb": round(disk.free / 2**30, 1), "total_gb": round(disk.total / 2**30, 1)}
    except OSError:
        data_disk = None
    hs = helmet.status()
    body = {
        "ok": scan_ok and (SERVER_START < now),
        "uptime_s": int(now - SERVER_START),
        "scan": {"cycle": scan.get("cycle_count"), "age_s": scan_age, "running": scan.get("is_scanning"), "ok": scan_ok},
        "bma_source": scan.get("source"),
        "ai_fps": detector.get_stats().get("fps"),
        "helmet": {"agent": hs.get("agent"), "agent_error": hs.get("agent_error"), "queue": hs.get("queue")},
        "wrongway": {"enabled": wrongway.enabled(), "queue": wrongway._queue.qsize()},
        "gpu": gpu, "data_disk": data_disk,
        "db_mb": round(os.path.getsize(os.path.join(DATA_DIR, "vehicle_counts.db")) / 2**20, 1),
        "instance": {"port": PORT, "stage": IS_STAGE, "data_dir": DATA_DIR},
    }
    return JSONResponse(body, status_code=200 if body["ok"] else 503)

# Static files for web frontend
@router.get("/")
def read_root():
    if not WEB_BUILT:
        return Response("Web UI not built: run launch\\build_web.bat (Windows) or launch/build_web.sh (macOS) (needs Node.js), then restart the server.\n",
                        status_code=503, media_type="text/plain")
    # never cache the shell so a rebuilt bundle is picked up on the next reload
    return FileResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})

@router.get("/sw.js")
def service_worker():
    # no-cache like the shell: Cloudflare would otherwise keep a .js without Cache-Control for hours after a deploy
    path = os.path.join(WEB_DIST, "sw.js")
    if not os.path.exists(path):
        return Response(status_code=404)
    return FileResponse(path, media_type="text/javascript", headers={"Cache-Control": "no-cache"})

@router.get("/robots.txt")
def robots_txt():
    # no crawling, no indexing: the data is for people using the site, not for harvesting
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")

@router.get("/cameras_bkk.json")
def read_cameras_json():
    # the React app fetches this directly (vite dev proxies it here too); config/cameras_bkk.json is the only copy
    return FileResponse(CAMERAS_FILE, media_type="application/json", headers={"Cache-Control": "no-cache"})
