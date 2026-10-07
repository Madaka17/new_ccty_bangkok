"""
Visitor telemetry and the operator team's Web Push alerts.
"""
import json

from fastapi import APIRouter, Body, Query

from backend.api.system import health
from backend.api.traffic import road_events
from backend.bma.bma_events import bma_feed
from backend.core.alert_service import AlertService
from backend.core.instance import DATA_DIR
from backend.core.telemetry_service import telemetry
from backend.services import flood_agent, incidents, province_flood
from backend.water import water_service
from backend.water.air_service import air
from backend.water.flood_feeds import tmd_warnings, traffy_reports
from backend.water.flood_service import flood_roads

router = APIRouter()


@router.get("/api/telemetry/online")
def telemetry_online():
    return {"ok": True, "online": telemetry.online_count()}

@router.get("/api/telemetry/stats")
def telemetry_stats():
    """Uncached visitor stats for the live visitors tab (the analytics summary is cached 60 s)."""
    return {"ready": True, **telemetry.stats()}

@router.post("/api/telemetry/view")
def telemetry_view(payload: dict = Body(...)):
    return {"ok": telemetry.view(payload.get("sid"), payload.get("view"))}

@router.post("/api/telemetry/heartbeat")
def telemetry_heartbeat(payload: dict = Body(...)):
    return {"ok": telemetry.heartbeat(payload.get("sid"), payload.get("view"))}

# POSTs here are operator-only through access_guard, so only the team can subscribe or send a test.
alerts = AlertService(DATA_DIR, {
    "agent": lambda: flood_agent.status()["report"],
    "flood": flood_roads.status, "water": water_service.get_summary, "incidents": incidents.status,
    "bma_events": lambda: bma_feed.get(hours=2, limit=60), "air": air.status,
    "traffy": traffy_reports.status, "tmd": tmd_warnings.status,
    "health": lambda: json.loads(health().body),
    "road_events": road_events, "provinces": province_flood.status,
})

@router.get("/api/alerts/status")
def alerts_status(endpoint: str = Query(None)):
    """VAPID public key, topics, subscriber count and whether this browser (endpoint) is subscribed."""
    return alerts.status(endpoint)

@router.get("/api/alerts/recent")
def alerts_recent(limit: int = Query(50, ge=1, le=200)):
    return alerts.recent(limit)

@router.post("/api/alerts/subscribe")
def alerts_subscribe(payload: dict = Body(...)):
    return alerts.subscribe(payload.get("subscription"), payload.get("topics"), payload.get("label", ""),
                            payload.get("provinces"))

@router.post("/api/alerts/unsubscribe")
def alerts_unsubscribe(payload: dict = Body(...)):
    return alerts.unsubscribe(payload.get("endpoint"))

@router.post("/api/alerts/test")
def alerts_test(payload: dict = Body(None)):
    return alerts.test((payload or {}).get("endpoint"))
