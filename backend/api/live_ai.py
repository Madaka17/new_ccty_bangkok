"""
The live AI camera (YOLO on one stream): stats, accuracy checks, settings, the MJPEG stream, violations,
incidents and the AI usage report.
"""
import asyncio
import time

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from backend.core import access_guard
from backend.services import cameras_data, detector, incidents, vehicle_log, violations

router = APIRouter()


@router.get("/api/ai/stats")
def get_ai_stats():
    return detector.get_stats()

@router.post("/api/ai/reset_passed")
def reset_ai_passed():
    """Restart the passed-vehicle counter of the live camera (start of a manual count)."""
    return detector.reset_passed()

@router.get("/api/ai/accuracy")
def get_ai_accuracy(limit: int = Query(50, ge=1, le=500)):
    """Manual-vs-AI checks: per-row absolute error / accuracy plus MAE and mean accuracy."""
    return vehicle_log.accuracy_checks(limit=limit)

@router.post("/api/ai/accuracy")
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

@router.delete("/api/ai/accuracy/{check_id}")
def delete_ai_accuracy(check_id: int):
    if not vehicle_log.delete_accuracy_check(check_id):
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"deleted": check_id}

@router.get("/api/ai/history")
def get_ai_history(range: str = Query("24h", pattern="^(24h|7d|30d)$"), date: str = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), camid: str = Query(None)):
    """Vehicles that passed each camera: hourly for 24h or a given date, daily for 7d/30d."""
    return vehicle_log.history(range_=range, date=date, camid=camid)

@router.post("/api/ai/switch_camera")
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

@router.post("/api/ai/set_fps")
def set_fps(fps: float = Query(5.0, ge=1.0, le=30.0)):
    detector.set_target_fps(fps)
    return {"status": "success", "target_fps": fps}

@router.post("/api/ai/set_conf")
def set_conf(conf: float = Query(0.20, ge=0.05, le=0.9)):
    detector.set_confidence(conf)
    return {"status": "success", "conf_threshold": conf}

@router.post("/api/ai/set_night_mode")
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

@router.get("/api/ai/stream")
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

@router.get("/api/ai/violations")
def ai_violations(hours: int = Query(24, ge=1, le=168), camid: str = Query(None), kind: str = Query(None, pattern="^(wrong_way|no_helmet)$"), limit: int = Query(100, ge=1, le=500)):
    """Logged violations from the live AI camera, newest first, with evidence image links."""
    return violations.recent(hours=hours, camid=camid, kind=kind, limit=limit)

@router.get("/api/ai/violations/status")
def ai_violations_status(camid: str = Query(None)):
    """How much of each camera's direction-of-travel map is learned, and whether helmet checks are on."""
    return violations.status(camid=camid)

@router.get("/api/ai/violations/{vid}/image")
def ai_violation_image(vid: str):
    p = violations.image_path(vid)
    if not p:
        return Response(status_code=404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

@router.get("/api/ai/usage")
def ai_usage(request: Request, minutes: int = Query(30, ge=1, le=1440)):
    """Requests and tokens sent to the AI model (LOCAL_LLM_*) per calling module over the last `minutes`.
    Operator only: it shows which jobs run and how often."""
    if not access_guard.is_trusted(request):
        return JSONResponse(status_code=403, content={"error": "operator only"})
    from backend.core import local_llm
    return local_llm.usage(minutes)

@router.get("/api/incidents")
def get_incidents():
    return incidents.status()

@router.get("/api/incidents/history")
def get_incident_history(hours: int = Query(24, ge=1, le=168)):
    items = vehicle_log.recent_incidents(hours) + incidents.recent_longdo(hours)
    return {"hours": hours, "items": sorted(items, key=lambda i: -i['ts'])}

@router.get("/api/incidents/{incident_id}/image")
def get_incident_image(incident_id: str):
    path = incidents.snapshot_path(incident_id)
    if not path:
        return Response(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})
