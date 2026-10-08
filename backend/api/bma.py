"""
BMA traffic cameras: the scanner's counts, snapshots, the live stream and the CSV / archive views.
"""
import asyncio
import io
import os
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from backend.bma.bma_service import RAW_DIR as BMA_RAW_DIR
from backend.core import stale_stamp
from backend.core.instance import DATA_DIR
from backend.services import bma_scanner, SAFE_ID

router = APIRouter()


# BMA Traffic & YOLO Vehicle Counting Endpoints
@router.get("/api/bma/cameras")
def get_bma_cameras():
    """Returns all BMA cameras with latest detection counts, road, district, and status."""
    cams = bma_scanner.db.get_all_latest()
    if not cams:
        cams = bma_scanner.cameras
    return {"total": len(bma_scanner.cameras), "items": cams}

@router.get("/api/bma/analytics")
def get_bma_analytics():
    """Returns comprehensive data analysis for BMA cameras vehicle counts."""
    return bma_scanner.get_analytics()

@router.post("/api/bma/scan")
def trigger_bma_scan():
    """Start an immediate scan of all BMA cameras."""
    return bma_scanner.start_scan()

@router.get("/api/bma/scan/status")
def get_bma_scan_status():
    """Returns current scanning progress across all BMA cameras."""
    return bma_scanner.get_status()

@router.get("/api/bma/snapshot/{camid}")
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

    if not SAFE_ID.fullmatch(camid):
        raise HTTPException(400, "bad camera id")
    # annotate=0: the plain frame, not the one the scanner keeps with its YOLO boxes drawn on
    cache_file = os.path.join(DATA_DIR, "cache", "bma_snapshots", f"{camid}.jpg")
    if not annotate:
        cache_file = os.path.join(BMA_RAW_DIR, f"{camid}.jpg")
    if os.path.exists(cache_file):
        # the scanner's last frame; while the BMA site is down it can be hours old, so it says so on the picture
        return Response(content=stale_stamp.stamp_file(cache_file), media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"})
    if not annotate:
        # No plain frame yet (the scanner keeps one on each pass). Asking BMA here would be one request per
        # tile of the camera wall, and BMA answers such a burst with 429 for everyone, the scanner included.
        return Response(status_code=404)

    try:
        raw = await loop.run_in_executor(None, lambda: bma_scanner.session.fetch_snapshot(str(camid), timeout=4.0))
        if raw:
            return Response(content=raw, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    except Exception:
        pass
    return Response(status_code=404)

@router.get("/api/bma/stream/{camid}")
async def stream_bma_camera(camid: str, fps: float = 2.0):
    """Live MJPEG video stream with real-time YOLO detection overlay for any BMA camera."""
    async def _stream():
        cam = next((c for c in bma_scanner.cameras if str(c.get('camid')) == str(camid)), None)
        if not cam:
            return
        
        # 1. Immediately yield cached snapshot so client never experiences a black screen!
        cache_file = os.path.join(DATA_DIR, "cache", "bma_snapshots", f"{camid}.jpg")
        last_frame = None
        if os.path.exists(cache_file):
            try:
                last_frame = stale_stamp.stamp_file(cache_file)
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

@router.get("/api/bma/live_analysis/{camid}")
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

@router.get("/api/bma/export/csv")
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

@router.get("/api/bma/cycle")
def get_bma_cycle():
    """Automatic count cycle: running totals since the last reset and when the next reset happens."""
    return bma_scanner.get_cycle_status()

@router.get("/api/bma/comparison")
def get_bma_comparison(period: str = Query("day", pattern="^(day|week|month)$")):
    """Returns comparative data analysis across Day, Week, and Month periods."""
    return bma_scanner.get_comparison(period=period)

@router.get("/api/bma/drive_d_status")
def get_bma_drive_d_status():
    """Folder layout under the CSV export directory (D:\\Data by default)."""
    return bma_scanner.archiver.files_status()
