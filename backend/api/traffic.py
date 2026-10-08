"""
Traffic: the city summary, areas, road events and risk, guidance, tiles, accident statistics (RSC) and
the analytics page.
"""
import gzip
import json
import time
from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from backend.api.flood import flood_national_map
from backend.bma.bma_events import bma_feed
from backend.services import bma_scanner, cameras_data, guidance, incidents
from backend.traffic import analytics_service, area_roads, near_traffic, rsc_service
from backend.traffic.area_traffic import area_traffic
from backend.traffic.road_service import road_risk
from backend.traffic.traffic_service import get_osm_tile, get_traffic_tile, traffic

router = APIRouter()


@router.get("/api/traffic/summary")
def traffic_summary(top: int = Query(8, ge=1, le=30)):
    return traffic.get_summary(top=top)

@router.get("/api/traffic/areas")
def traffic_areas(request: Request):
    """Traffic score per province and district from Longdo's lines over the whole country (area_traffic.py)."""
    body = json.dumps(area_traffic.status(), ensure_ascii=False).encode("utf-8")
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gzip.compress(body, 6), media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, media_type="application/json")

def road_event_points():
    """Accidents, closed roads and floods on roads in every province as points: {"kind", "title", "lat", "lng"}."""
    events = []
    ev = incidents.road_events()
    for i in ev["incidents"]:
        events.append({"kind": i["kind"], "title": i["title"], "lat": i["latitude"], "lng": i["longitude"]})
    for c in ev["closures"]:
        events.append({"kind": "closed" if c["kind"] == "closed" else "diversion", "title": c["title"],
                       "lat": c["latitude"], "lng": c["longitude"]})
    for f in flood_national_map()["items"]:
        if f["kind"] == "road" and f["passable"] is not False:   # impassable ones are closures above
            events.append({"kind": "flood", "title": f["title"], "lat": f["lat"], "lng": f["lng"], "depth_cm": f["depth_cm"]})
    return events

@router.get("/api/traffic/near")
def traffic_near(lat: float = Query(..., ge=5.5, le=20.5), lng: float = Query(..., ge=97.3, le=105.7)):
    """Roads around a visitor's position (the "ใกล้ฉัน" button): traffic per named road within 3 km
    (near_traffic.py), the district, and accidents, closed roads and floods within that circle.
    The page sends the position rounded to 0.01 degree (about 1 km), and it is rounded again here."""
    lat, lng = round(lat, 2), round(lng, 2)
    out = dict(near_traffic.analyse(lat, lng))
    out["province"], out["amphoe"] = area_traffic.locate(lat, lng)
    radius = out["radius_km"]
    near = []
    for e in road_event_points():
        d = near_traffic.distance_km(lat, lng, e["lat"], e["lng"])
        if d <= radius:
            near.append({**{k: v for k, v in e.items() if k not in ("lat", "lng")}, "distance_km": round(d, 1)})
    out["events"] = sorted(near, key=lambda e: e["distance_km"])[:15]
    return out

@router.get("/api/road/events")
def road_events():
    """Accidents and closed roads in every province for the traffic map: the Longdo feed (all of Thailand) and
    the BMA traffic centre's accident / road-work reports (Bangkok), each with its province and district."""
    out = incidents.road_events()
    bma = bma_feed.get(hours=24, limit=200)["items"]
    for e in bma:
        if e.get("lat") is None or e.get("lng") is None or e.get("kind") not in ("accident", "roadwork"):
            continue
        if e["kind"] == "accident" and time.time() - (e.get("ts") or 0) > 3 * 3600:
            continue   # the BMA list has no end time: an accident older than 3 hours is taken as cleared
        item = {"id": f"bma-{e['id']}", "source": "bma", "title": e.get("title") or "", "description": e.get("desc") or "",
                "latitude": e["lat"], "longitude": e["lng"], "start": datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M:%S") if e.get("ts") else None,
                "stop": None, "contributor": "ศูนย์จราจร กทม."}
        if e["kind"] == "accident":
            out["incidents"].append({**item, "kind": "accident"})
        else:
            out["closures"].append({**item, "kind": "diversion", "reason": ""})
    for i in out["incidents"] + out["closures"]:
        i["province"], i["amphoe"] = area_traffic.locate(i["latitude"], i["longitude"])
    return out

@router.get("/api/traffic/guidance")
def traffic_guidance():
    """Live dispersal guidance per main corridor: hotspots, bypass roads with live flow, advice text."""
    return guidance.status()

@router.get("/api/traffic/guidance/area")
def traffic_guidance_area(province: str = Query(..., pattern=r"^\d{2}$"), amphoe: str = Query("", pattern=r"^(\d{4})?$")):
    """Road cards like /api/traffic/guidance for one province or district of Thailand (area_roads.py)."""
    out = area_roads.analyse(province, amphoe, road_event_points())
    if out is None:
        return JSONResponse(status_code=404, content={"error": "unknown province or district"})
    return out

@router.get("/api/roads/risk")
def roads_risk(level: str = Query(None, pattern="^(high|medium|low|none)$"), province: str = Query(None),
               q: str = Query(None), measured: bool = Query(None), limit: int = Query(200, ge=1, le=2000)):
    """Every named road with the rain, canal level and road-sensor water around it, scored and ranked."""
    return road_risk.status(level=level, province=province, q=q, measured=measured, limit=limit)

@router.get("/api/traffic/roads")
def traffic_roads(q: str = Query(None), limit: int = Query(50, ge=1, le=500)):
    return {"items": traffic.get_roads(q, limit)}

@router.get("/api/traffic/road_cameras")
def traffic_road_cameras(name: str = Query(...), max_km: float = Query(0.25, ge=0.05, le=2.0)):
    """Cameras located on / next to the named road, nearest first."""
    return {"name": name, "items": traffic.cameras_on_road(name, cameras_data, max_km)}

@router.get("/api/traffic/tile/{z}/{x}/{y}.pbf")
def traffic_tile(z: int, x: int, y: int):
    data, stale = get_traffic_tile(z, x, y)
    if not data:
        return Response(status_code=204)
    return Response(content=data, media_type="application/vnd.mapbox-vector-tile",
                    headers={"Content-Encoding": "gzip", "Cache-Control": "max-age=60",
                             "X-Stale": "1" if stale else "0"})

@router.get("/api/tiles/base/{z}/{x}/{y}.png")
def base_tile(z: int, x: int, y: int):
    try:
        data = get_osm_tile(z, x, y)
    except Exception:
        return Response(status_code=204)
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "max-age=86400"})

@router.get("/api/rsc/summary")
def rsc_summary():
    """Bangkok accident stats (today / YTD / by vehicle / by hour / by district) joined with BMA camera load."""
    try:
        return rsc_service.get_summary()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

@router.get("/api/rsc/camera_risk")
def rsc_camera_risk(limit: int = Query(None, ge=1, le=600), district: str = Query(None)):
    """BMA cameras ranked by accident points within RADIUS_M (current + previous year)."""
    return rsc_service.get_camera_risk(limit=limit, district=district)

@router.get("/api/rsc/points")
def rsc_points(camid: str = Query(None), lat: float = Query(None), lon: float = Query(None), radius: int = Query(None, ge=50, le=3000), limit: int = Query(500, ge=1, le=5000)):
    """Accident points near one camera (victim identity removed)."""
    return rsc_service.get_points(camid=camid, cameras=bma_scanner.cameras, radius_m=radius, lat=lat, lon=lon, limit=limit)

@router.get("/api/rsc/points.geojson")
def rsc_points_geojson():
    return rsc_service.get_points_geojson()

@router.post("/api/rsc/rebuild")
def rsc_rebuild(force: bool = Query(False)):
    """Re-fetch accident points from Thai RSC and rescore every camera (background)."""
    return rsc_service.build_camera_risk(bma_scanner.cameras, force=force)

@router.get("/api/analytics/summary")
def analytics_summary(refresh: bool = Query(False)):
    """Traffic overview, flood watch + 1-6 h outlook, density tiers, black spots, dashboard visitors."""
    return analytics_service.get_summary(force=refresh)

@router.get("/api/analytics/export")
def analytics_export(format: str = Query("json", pattern="^(json|csv)$"),
                     section: str = Query("traffic", pattern="^(traffic|flood|density|accidents|visitors)$")):
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    if format == "csv":
        return Response(content=analytics_service.export_csv(section), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="analytics-{section}-{stamp}.csv"'})
    body = json.dumps(analytics_service.get_summary(), ensure_ascii=False, indent=1)
    return Response(content=body, media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="analytics-{stamp}.json"'})
