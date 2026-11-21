"""
Health, the web UI shell and the files served next to it.
"""
import os
import shutil
import tempfile
import threading
import time
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.core.instance import DATA_DIR, IS_STAGE, PORT
from backend.core.env_flags import flag_on
from backend.vision.yolo_switch import gpu_memory
from backend.services import bma_scanner, CAMERAS_FILE, detector, helmet, INDEX_HTML, SERVER_START, WEB_BUILT, WEB_DIST, wrongway

router = APIRouter()


def _scan_state(now):
    """(scan status dict, age in seconds or None, fresh?) for the BMA scanner. Fresh = last cycle under 15 min,
    or a fresh process still in its first-cycle grace period (the first cycle over 574 cameras takes minutes)."""
    scan = bma_scanner.get_status()
    # bma_service stores last_scan_time as "%Y-%m-%d %H:%M:%S" text (the UI shows it as is)
    last_scan = scan.get("last_scan_time")
    last_scan = datetime.strptime(last_scan, "%Y-%m-%d %H:%M:%S").timestamp() if last_scan else 0
    scan_age = int(now - last_scan) if last_scan else None
    scan_ok = (scan_age is not None and scan_age < 15 * 60) or (not last_scan and now - SERVER_START < 20 * 60)
    return scan, scan_age, scan_ok


def _scan_ok(now) -> bool:
    return _scan_state(now)[2]


def _disk_ok() -> bool:
    """Write a tiny uniquely named file in the data directory, then remove it. False only when the create or the
    write fails, e.g. a read-only filesystem. A unique name keeps concurrent probes from clashing."""
    try:
        fd, path = tempfile.mkstemp(prefix=".healthz-", dir=os.getenv("BMA_DATA_DIR", DATA_DIR))
    except OSError:
        return False
    try:
        try:
            os.write(fd, str(time.time()).encode("ascii"))
            ok = True
        finally:
            os.close(fd)
    except OSError:
        ok = False
    try:
        os.unlink(path)
    except OSError:
        pass   # the probe file is only a probe: a failed delete does not make the disk unhealthy
    return ok


HEALTHZ_TTL = 20                 # seconds: a flood of probes costs one scan check and one disk write per window
_monotonic = time.monotonic      # its own name so tests can drive the clock
_healthz_lock = threading.Lock()
_healthz_cache = {}              # {"at": monotonic time, "body": dict, "status": int}


@router.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    """Public, minimal health check for outside uptime monitors. Only three keys, nothing about the machine.
    The result is cached for HEALTHZ_TTL seconds, so no outside caller can make it write to the disk on every call."""
    with _healthz_lock:
        now = _monotonic()
        if not _healthz_cache or now - _healthz_cache["at"] >= HEALTHZ_TTL:
            scan = _scan_ok(time.time()) if flag_on(os.environ, "BMA_FETCH") else None   # BMA_FETCH=0: never scans here
            disk = _disk_ok()
            ok = disk and scan is not False
            _healthz_cache.update(at=now, body={"ok": ok, "scan": scan, "disk": disk}, status=200 if ok else 503)
        return JSONResponse(_healthz_cache["body"], status_code=_healthz_cache["status"],
                            headers={"Cache-Control": "no-store"})


@router.get("/api/health")
def health():
    """One call for a watchdog: 200 + ok=true when the scanner ran recently and the detector answers.
    Returns 503 when the BMA scan is stale (> 3 cycles) so an external monitor can restart the server."""
    now = time.time()
    scan, scan_age, scan_ok = _scan_state(now)
    gpu = None
    mem = gpu_memory()      # nvidia-smi until torch has its own CUDA context: no context made for a health poll
    if mem:
        name = None
        try:
            import torch
            if torch.cuda.is_initialized():
                name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001
            pass
        gpu = {"name": name, **mem}
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
