"""
The traffic assistant (/api/chat): every live source it may cite, and the flood-aware router.
"""
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from backend.agents import chat_service
from backend.bma.bma_events import bma_feed
from backend.services import bkk_districts, bma_scanner, detector, flood_agent, flood_router, guidance, helmet, incidents, national_forecast, north_route, province_flood, violations, wrongway
from backend.traffic import analytics_service, rsc_service
from backend.traffic.area_traffic import area_traffic
from backend.traffic.road_service import road_risk
from backend.traffic.traffic_service import traffic
from backend.water import north_flow, water_service, weather_now
from backend.water.air_service import air
from backend.water.flood_feeds import tmd_warnings
from backend.water.flood_service import flood_roads

router = APIRouter()


def _user_location(v):
    """{lat, lng} the browser shared, if it is a real point in Thailand; None otherwise."""
    try:
        lat, lng = float(v["lat"]), float(v["lng"])
    except (TypeError, ValueError, KeyError):
        return None
    return {"lat": lat, "lng": lng} if 5.5 <= lat <= 20.5 and 97.3 <= lng <= 105.7 else None

@router.post("/api/chat")
def chat_endpoint(payload: dict = Body(...)):
    messages = payload.get("messages") or []
    messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")
                and isinstance(m.get("content"), str)]
    if not messages:
        return JSONResponse(status_code=400, content={"error": "messages required"})
    try:
        water = water_service.get_summary()
    except Exception:
        water = None
    extra = {}
    for key, fn in (("incidents", incidents.status), ("bma_events", lambda: bma_feed.get(hours=12, limit=20)),
                    ("bma_analytics", bma_scanner.get_analytics), ("rsc", rsc_service.get_summary),
                    ("camera_risk", lambda: rsc_service.get_camera_risk(limit=8)),
                    ("air", air.status), ("guidance", guidance.status),
                    ("road_risk", lambda: road_risk.status(limit=2000)), ("flood_report", flood_roads.report),
                    ("helmet", lambda: {"status": helmet.status(), "recent": helmet.recent(verdict="no_helmet", limit=5)["items"]}),
                    ("wrongway", lambda: {"status": wrongway.status(), "recent": wrongway.recent(verdict="wrong_way", limit=5)["items"]}),
                    ("violations", lambda: violations.recent(hours=24, limit=1)),
                    ("analytics", analytics_service.get_summary), ("north_flow", north_flow.brief),
                    ("weather_outlook", weather_now.outlook), ("tmd", tmd_warnings.status),
                    ("flood_agent", lambda: flood_agent.status()), ("bkk_districts", bkk_districts.status),
                    ("north_route", north_route.status), ("national_forecast", national_forecast.status),
                    ("areas", area_traffic.status), ("provinces", province_flood.status)):
        try:
            extra[key] = fn()
        except Exception as e:
            print(f"[Chat] {key} unavailable: {e}")
    extra["weather_at"] = weather_now.outlook   # forecast of a province the question names
    return chat_service.chat(traffic, messages, detector.get_stats(), water, extra, router=flood_router,
                             location=_user_location(payload.get("location")))
