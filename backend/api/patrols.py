"""
Helmet and wrong-way patrols over the BMA cameras: status, findings, evidence pictures and re-checks.
"""
import asyncio
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.services import helmet, wrongway

router = APIRouter()


@router.get("/api/helmet/status")
def helmet_status():
    return helmet.status()

@router.get("/api/helmet/recent")
def helmet_recent(hours: int = Query(24, ge=1, le=720), verdict: str = Query(None, pattern="^(pending|helmet|no_helmet|suspect|unclear|error)$"),
                  camid: str = Query(None), limit: int = Query(200, ge=1, le=1000)):
    return helmet.recent(hours=hours, verdict=verdict, camid=camid, limit=limit)

@router.get("/api/helmet/cameras")
def helmet_cameras():
    return helmet.cameras()

@router.post("/api/helmet/check/{camid}")
async def helmet_check(camid: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: helmet.check_now(camid))

@router.post("/api/helmet/reanalyse_pending")
async def helmet_reanalyse_pending(agent: str = Query("cloud", pattern="^(cloud|local)$"), limit: int = Query(40, ge=1, le=300), hours: int = Query(24, ge=1, le=168)):
    """Send every unclear / failed capture of the last hours through the chosen agent again."""
    return helmet.reanalyse_pending(agent=agent, limit=limit, hours=hours)

@router.post("/api/helmet/{hid}/reanalyse")
async def helmet_reanalyse(hid: str, agent: str = Query("cloud", pattern="^(cloud|local)$")):
    """Run one capture through the cloud agent (Gemini/Claude) again."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: helmet.reanalyse(hid, agent))

@router.get("/api/helmet/{hid}/crop")
def helmet_crop(hid: str):
    p = helmet.crop_path(hid)
    if not os.path.exists(p):
        raise HTTPException(404, "no image")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

@router.get("/api/helmet/{hid}/frame")
def helmet_frame(hid: str):
    p = helmet.frame_path(hid)
    if not os.path.exists(p):
        raise HTTPException(404, "no image")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

@router.get("/api/wrongway/status")
def wrongway_status():
    return wrongway.status()

@router.get("/api/wrongway/recent")
def wrongway_recent(hours: int = Query(24, ge=1, le=720), verdict: str = Query(None, pattern="^(pending|wrong_way|ok|unclear|error)$"),
                    camid: str = Query(None), limit: int = Query(200, ge=1, le=1000)):
    return wrongway.recent(hours=hours, verdict=verdict, camid=camid, limit=limit)

@router.get("/api/wrongway/cameras")
def wrongway_cameras():
    return wrongway.cameras()

@router.get("/api/wrongway/field/{camid}")
def wrongway_field(camid: str):
    """Learned lane directions of one camera (known grid cells) for the overlay."""
    return wrongway.field_cells(camid)

@router.post("/api/wrongway/check/{camid}")
async def wrongway_check(camid: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: wrongway.check_now(camid))

@router.post("/api/wrongway/reanalyse_pending")
async def wrongway_reanalyse_pending(agent: str = Query("cloud", pattern="^(cloud|local)$"), limit: int = Query(40, ge=1, le=300), hours: int = Query(24, ge=1, le=168)):
    return wrongway.reanalyse_pending(agent=agent, limit=limit, hours=hours)

@router.post("/api/wrongway/{wid}/reanalyse")
async def wrongway_reanalyse(wid: str, agent: str = Query("cloud", pattern="^(cloud|local)$")):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: wrongway.reanalyse(wid, agent))

@router.post("/api/wrongway/{wid}/dismiss")
def wrongway_dismiss(wid: str):
    """A person checked the evidence: not a violation."""
    return wrongway.dismiss(wid)

@router.get("/api/wrongway/{wid}/crop")
def wrongway_crop(wid: str):
    p = wrongway.crop_path(wid)
    if not os.path.exists(p):
        raise HTTPException(404, "no image")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

@router.get("/api/wrongway/{wid}/frame")
def wrongway_frame(wid: str):
    p = wrongway.frame_path(wid)
    if not os.path.exists(p):
        raise HTTPException(404, "no image")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})
