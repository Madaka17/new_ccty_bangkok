"""
Floods: road sensors, flood cameras, reports from the public, flood car parks, the flood agent, provinces,
forecasts, Bangkok districts and the national map.
"""
import asyncio
import json
import time

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from backend.core import access_guard, stale_stamp
from backend.services import bkk_districts, flood_agent, flood_cams, incidents, national_forecast, province_flood, user_reports
from backend.traffic.area_traffic import area_traffic
from backend.vision.flood_cam_service import STALE_MINUTES as FLOOD_CAM_STALE_MINUTES
from backend.water.flood_feeds import hdms_floods, js100_floods, traffy_reports
from backend.water.flood_parking import flood_parking
from backend.water.flood_service import flood_roads
from backend.water.user_reports import report_locations

router = APIRouter()


@router.get("/api/flood/status")
def flood_status(min_cm: float = Query(None, ge=0, le=200)):
    """Counts, every wet station and the per-district roll-up, for the flood layer on the map."""
    return flood_roads.status(min_cm=min_cm)

@router.get("/api/flood/stations")
def flood_stations(status: str = Query(None, pattern="^(flood|slight|normal|offline)$"),
                   district: str = Query(None), kind: str = Query(None, pattern="^(road|tunnel)$"),
                   limit: int = Query(400, ge=1, le=1000)):
    return flood_roads.stations(status=status, district=district, kind=kind, limit=limit)

@router.get("/api/flood/cameras")
def flood_cameras(all: bool = Query(False)):
    """AI flood watch on every BMA camera: counts and the cameras with water on the road (all=1: every checked camera)."""
    return flood_cams.status(include_dry=all)

@router.get("/api/flood/cameras/{camid}/image")
def flood_camera_image(camid: str):
    """The frame the AI judged for this camera."""
    p = flood_cams.frame_path(camid)
    if not p:
        raise HTTPException(404, "no image")
    # stamped "ภาพเก่า" once the frame is older than the map's own fade (the BMA site down, a dead feed)
    jpeg = stale_stamp.stamp_file(p, stale_minutes=FLOOD_CAM_STALE_MINUTES, frame_ts=flood_cams.frame_ts(camid))
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})

@router.post("/api/flood/cameras/check")
def flood_cameras_check():
    """Check every camera now instead of waiting for its turn (operator only through access_guard)."""
    return flood_cams.check_all()

@router.get("/api/flood/report-locations")
def user_report_locations():
    return {"provinces": report_locations()}

@router.get("/api/flood/user-reports")
def user_reports_recent(hours: float = Query(None, gt=0, le=48)):
    """Published flood reports from the public in the last hours (default USER_REPORT_HOURS), each with its province."""
    out = user_reports.recent(hours)
    for r in out["items"]:
        if not r.get("province"):
            r["province"] = province_flood.place(r["note"], "", r["lat"], r["lng"])
    return out

@router.post("/api/flood/user-reports")
async def user_reports_create(request: Request):
    """Own flood report: {province, district, lat, lng, depth, note?, photo? (data: URL)}. Size/rate limited."""
    body = bytearray()
    async for chunk in request.stream():   # counted here too: a chunked upload has no content-length to check
        body += chunk
        if len(body) > access_guard.USER_REPORT_MAX_BODY:
            raise HTTPException(413, "รูปใหญ่เกินไป")
    try:
        data = json.loads(body)
    except ValueError:
        raise HTTPException(400, "ข้อมูลไม่ถูกต้อง") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "ข้อมูลไม่ถูกต้อง")
    try:
        return await asyncio.get_running_loop().run_in_executor(None, user_reports.create, data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None

@router.get("/api/flood/user-reports/{rid}/photo")
def user_report_photo(rid: str):
    p = user_reports.published_photo(rid)
    if not p:
        raise HTTPException(404, "no photo")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

@router.delete("/api/flood/user-reports/{rid}")
def user_report_delete(rid: str):
    """Take a report off the maps (operator only through access_guard)."""
    if not user_reports.delete(rid):
        raise HTTPException(400, "bad id")
    return {"deleted": rid}

@router.get("/api/flood/parking")
def flood_parking_list():
    """Announced flood car parks (config/flood_parking.json) with the public's recent "full" reports."""
    return flood_parking.status()

@router.post("/api/flood/parking/{spot_id}/full")
def flood_parking_full(spot_id: str, request: Request):
    """A "เต็มแล้ว" press from the public (rate limited in access_guard). Shows for PARKING_FULL_MINUTES."""
    try:
        return {"id": spot_id, "user_full": flood_parking.report_full(spot_id, access_guard.client_ip(request))}
    except KeyError:
        raise HTTPException(404, "no such spot") from None

@router.get("/api/flood/analysis")
def flood_analysis():
    """AI read of the current flooding: severity, what is happening, spots to watch, what to do."""
    return flood_roads.report()

@router.get("/api/flood/notices")
def flood_notices():
    """Plain-Thai notice per flooded road: what, where, when, what to do (VEHICLE_RULES), source and time."""
    return flood_roads.notices()

@router.get("/api/flood/roads")
def flood_roads_list(limit: int = Query(60, ge=1, le=300)):
    """Worst station per road, so the page can list which roads have standing water."""
    return flood_roads.roads(limit=limit)

@router.get("/api/flood/longdo")
def flood_longdo(hours: int = Query(None, ge=1, le=48), national: bool = False):
    """Flooded-road reports from the Longdo Traffic event feed (type 6; iTIC / FM91 relays), newest first.
    national=1: every province instead of the Bangkok area, each with its province."""
    out = incidents.floods(hours=hours, national=national)
    if national:
        for f in out["items"]:
            f["province"] = province_flood.place(f["title"], f["description"], f["lat"], f["lng"])
    return out

@router.get("/api/flood/agent")
def flood_agent_status():
    """Latest agent situation report, the level history and whether a run is in progress."""
    return flood_agent.status()

@router.post("/api/flood/agent/run")
def flood_agent_run(payload: dict = Body(None)):
    """Run the agent now (operator only through access_guard); an optional question is answered in `answer`."""
    return flood_agent.run(question=(payload or {}).get("question"), force=True)

@router.get("/api/flood/reports")
def flood_reports():
    """Flood complaints from Traffy Fondue in the last few hours, newest first."""
    return traffy_reports.status()

@router.get("/api/flood/provinces")
def flood_provinces():
    """Flood situation in every province (Thai Water gauges and rain, DOH flooded highways) with the AI's
    analysis: see province_flood.py."""
    return province_flood.status()

@router.get("/api/flood/forecast")
def flood_forecast():
    """7-day outlook for the whole country: large dams' storage projection, medium reservoirs, each province's
    flood risk, flooded and at-risk main roads, and the AI's outlook and summary: see national_forecast.py."""
    return national_forecast.status()

@router.get("/api/flood/bkk-districts")
def flood_bkk_districts():
    """Flood risk in each of Bangkok's 50 districts (canals, main gauges, road water, rain, Traffy reports) with
    the AI's overview and a line per district: see bkk_districts.py."""
    return bkk_districts.status()

@router.get("/api/flood/hdms")
def flood_hdms(national: bool = False):
    """Flooded highways in Bangkok and vicinity from the Department of Highways HDMS dashboard, newest first.
    national=1: every province (without photos)."""
    if national:
        st = hdms_floods.status()
        items = hdms_floods.national()
        return {"updated_at": st["updated_at"], "error": st["error"], "total": len(items), "items": items}
    return hdms_floods.status()

@router.get("/api/flood/national-map")
def flood_national_map():
    """Where it is flooded now in every province, for the traffic map: flooded roads from the Longdo feed (the
    Department of Highways' reports and people's), with the water depth from HDMS where the two match (HDMS
    tickets are the same floods), HDMS tickets Longdo lacks, and river gauges over the bank (Thai Water)."""
    items = []
    for f in incidents.floods(national=True)["items"]:
        if not f["active"]:
            continue
        title = f["title"]
        passable = False if "ผ่านไม่ได้" in title else True if "ผ่านได้" in title else None
        items.append({"id": f["id"], "kind": "road", "title": title, "description": f["description"],
                      "lat": f["lat"], "lng": f["lng"], "ts": f["ts"], "passable": passable, "depth_cm": None,
                      "source": "กรมทางหลวง" if f["contributor"] == "DOH Admin" else "ข่าวจราจร"})
    roads = list(items)
    for h in hdms_floods.national():
        if not h["active"] or not h["lat"] or not h["lng"]:
            continue
        same = next((r for r in roads if abs(r["lat"] - h["lat"]) < 0.003 and abs(r["lng"] - h["lng"]) < 0.003), None)
        if same:
            same["depth_cm"] = same["depth_cm"] or h["depth_cm"]
            continue
        items.append({"id": h["id"], "kind": "road", "title": f"น้ำท่วม {h['place'] or h['title']}",
                      "description": " · ".join(x for x in (h["cause"], h["relief"]) if x), "lat": h["lat"], "lng": h["lng"],
                      "ts": h["ts"], "passable": None, "depth_cm": h["depth_cm"], "source": "กรมทางหลวง"})
    for p in province_flood.status()["provinces"]:
        for g in p["gauges"]:
            if g["level"] >= 5 and g["lat"] and g["lng"]:
                items.append({"id": f"gauge-{g['lat']}-{g['lng']}", "kind": "river",
                              "title": f"{g['river'] or 'น้ำ'}ล้นตลิ่ง ที่ {g['name']}" if g["river"] != g["name"] else f"{g['name']} ล้นตลิ่ง",
                              "description": f"ระดับน้ำ {round(g['pct'] or 0)}% ของตลิ่ง", "lat": g["lat"], "lng": g["lng"],
                              "ts": g["ts"], "passable": None, "depth_cm": None, "source": "คลังข้อมูลน้ำแห่งชาติ"})
    for i in items:
        i["province"], i["amphoe"] = area_traffic.locate(i["lat"], i["lng"])
    return {"updated_at": int(time.time()), "items": items,
            "counts": {"road": sum(i["kind"] == "road" for i in items), "river": sum(i["kind"] == "river" for i in items)}}

@router.get("/api/flood/js100")
def flood_js100():
    """Flooded-road items from the JS100 radio traffic news in the last 48 h, newest first (text only)."""
    return js100_floods.status()
