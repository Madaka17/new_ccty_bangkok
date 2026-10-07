"""
Water levels: the summary, the water map, river forecasts, the northern water route and BMA water news.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.bma.bma_events import bma_feed
from backend.services import incidents, north_route, province_flood, user_reports
from backend.traffic.area_traffic import area_traffic
from backend.traffic.traffic_service import traffic
from backend.water import north_flow, river_roads, water_service
from backend.water.flood_feeds import hdms_floods, js100_floods, traffy_reports
from backend.water.flood_service import flood_roads

router = APIRouter()


@router.get("/api/water/summary")
def water_summary():
    try:
        return water_service.get_summary()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e), "api_key": water_service.key_status()})

@router.get("/api/water/map")
def water_map():
    """Map points of the water map, all of Thailand: river / canal gauges, rain gauges and the 35 large dams
    (metro ones from water_service, the rest from Thai Water's national snapshot read by province_flood every
    30 minutes), and flooded roads (BMA road sensors, Longdo flood reports and Department of Highways HDMS
    tickets in every province)."""
    try:
        out = water_service.get_map()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    # Thai Water situation_level: 5 over the bank, 4 high, 3 normal, 1-2 low, 0 no reading
    status = {5: "overflow", 4: "high", 3: "normal", 2: "low", 1: "low"}
    near = [(p["lat"], p["lng"]) for p in out["water"]]
    for g in province_flood.gauges():
        if any(abs(g["lat"] - a) < 0.001 and abs(g["lng"] - b) < 0.001 for a, b in near):
            continue
        msl, bank = g.get("msl"), g.get("bank")
        out["water"].append({
            "id": f"river-th-{g.get('station_id') or g['name']}", "kind": "river", "name": g["name"],
            "district": g["amphoe"], "province": g["province"], "lat": g["lat"], "lng": g["lng"], "ts": g["ts"],
            "status": status.get(g["level"], "offline"), "msl": msl, "bank": bank,
            "diff_bank": round(bank - msl, 2) if msl is not None and bank is not None else None,
            # No station_id: the snapshot's station ids are not the ones the graph API (the trend chart) takes
            "storage_pct": g["pct"], "river": g["river"],
        })
    roads = []
    for s in flood_roads.stations(limit=1000)["items"]:
        if s.get("lat") and s.get("lng"):
            roads.append({"id": f"sensor-{s['id']}", "kind": "sensor", "name": s.get("short_name") or s.get("name"),
                          "road": s.get("road"), "district": s.get("district") or "", "province": "กรุงเทพมหานคร",
                          "lat": s["lat"], "lng": s["lng"], "ts": s.get("ts"), "status": s.get("status"),
                          "depth_cm": s.get("level_cm"), "max_cm": s.get("max_cm"), "trend": s.get("trend_th"),
                          "sensor_kind": s.get("kind")})
    # Department of Highways tickets in every province (the Bangkok-area list adds their photos)
    hdms = {h["id"]: h for h in hdms_floods.national()}
    hdms.update({h["id"]: h for h in hdms_floods.status()["items"]})
    hdms = [h for h in hdms.values() if h["lat"] and h["lng"]]
    # Longdo flood reports in every province; the Department's own reports there repeat its HDMS tickets
    for f in incidents.floods(national=True)["items"]:
        if any(abs(f["lat"] - h["lat"]) < 0.003 and abs(f["lng"] - h["lng"]) < 0.003 for h in hdms):
            continue
        province, amphoe = area_traffic.locate(f["lat"], f["lng"])
        roads.append({"id": f["id"], "kind": "report", "name": f["place"], "district": amphoe, "province": province,
                      "lat": f["lat"], "lng": f["lng"], "ts": f["ts"],
                      "status": "report" if f["active"] else "report_ended",
                      "description": f["description"], "credit": f["credit"] or f.get("contributor") or "Longdo Traffic"})
    for h in hdms:
        if h["lat"] and h["lng"]:
            roads.append({"id": h["id"], "kind": "hdms", "name": h["place"] or h["title"], "district": h["amphoe"] or "",
                          "province": h["province"], "lat": h["lat"], "lng": h["lng"], "ts": h["ts"],
                          "status": "hdms" if h["active"] else "hdms_ended", "depth_cm": h["depth_cm"],
                          "description": " · ".join(x for x in (h["title"], h["closure"], h["relief"]) if x),
                          "credit": h["depot"]})
    # What people report (not verified): Traffy Fondue in Bangkok, this site's report form, the BMA traffic
    # centre's flood reports; JS100 radio news has no position, so it comes as text beside the map
    for t in traffy_reports.status()["items"]:
        try:
            lat, lng = float(t["lat"]), float(t["lng"])
        except (TypeError, ValueError, KeyError):
            continue
        roads.append({"id": f"traffy-{t['id']}", "kind": "traffy", "name": t.get("address") or f"เขต{t.get('district') or ''}",
                      "district": t.get("district") or "", "province": "กรุงเทพมหานคร", "lat": lat, "lng": lng,
                      "ts": int(t["ts"]) if t.get("ts") else None, "status": "people", "description": t.get("text") or "",
                      "depth_text": t.get("depth") or "", "photo": t.get("photo"), "url": t.get("url"),
                      "state": t.get("state") or "", "credit": "Traffy Fondue"})
    for r in user_reports.recent()["items"]:
        province, amphoe = area_traffic.locate(r["lat"], r["lng"])
        roads.append({"id": f"user-{r['id']}", "kind": "user", "name": r["note"] or "คนแจ้งน้ำท่วม",
                      "district": amphoe, "province": province, "lat": r["lat"], "lng": r["lng"], "ts": r["ts"],
                      "status": "people", "description": r["ai_note"], "depth_text": r["depth_th"],
                      "photo": r["photo"], "state": r["ai_level_th"] or "", "credit": "แจ้งผ่านเว็บนี้"})
    for e in bma_feed.get(kind="flood", hours=6, limit=100)["items"]:
        if e.get("lat") is not None and e.get("lng") is not None:
            roads.append({"id": f"bma-{e['id']}", "kind": "bma", "name": e.get("title") or "น้ำท่วม",
                          "district": "", "province": "กรุงเทพมหานคร", "lat": e["lat"], "lng": e["lng"], "ts": e.get("ts"),
                          "status": "people", "description": e.get("desc") or "", "credit": "ศูนย์จราจร กทม."})
    out["roads_text"] = [{"text": j["text"], "ts": int(j["ts"]) if j.get("ts") else None, "source": "JS100"}
                         for j in js100_floods.status()["items"][:20]]
    # Rain gauges and large dams in every province (Thai Water snapshot, via province_flood)
    near = [(p["lat"], p["lng"]) for p in out["rain"]]
    for r in province_flood.rain_points():
        if any(abs(r["lat"] - a) < 0.001 and abs(r["lng"] - b) < 0.001 for a, b in near):
            continue
        out["rain"].append({"id": f"rain-th-{r['lat']}-{r['lng']}", "kind": "rain", "name": r["name"], "district": r["amphoe"],
                            "province": r["province"], "lat": r["lat"], "lng": r["lng"], "ts": r["ts"],
                            "status": water_service._rain_level(r["rain_24h"]), "rain_24h": r["rain_24h"], "rain_1h": r["rain_1h"]})
    dams = province_flood.dams()
    if dams:
        out["dams"] = []
        for d in dams:
            pct = d["storage_pct"] or 0
            province, _ = area_traffic.locate(d["lat"], d["lng"])
            out["dams"].append({"id": f"dam-{d['name']}", "kind": "dam", "name": d["name"], "district": "", "province": province,
                                "lat": d["lat"], "lng": d["lng"], "ts": None,
                                "status": "high" if pct >= 90 else "normal" if pct >= 50 else "low",
                                **{k: d[k] for k in ("storage_pct", "storage", "max_storage", "inflow", "released", "date")}})
    return {**out, "roads": roads}

@router.get("/api/water/forecast")
def water_forecast(station: int = Query(..., ge=1)):
    """Observed + official (HII) or local tidal-harmonic outlook for one telemetry station."""
    try:
        return water_service.get_forecast(station)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

@router.get("/api/water/north")
def water_north():
    """Northern rivers to the Central Plain: RID gauges' discharge now, the routed 4-day outlook down to
    Ayutthaya, upstream dams and the warnings they add up to."""
    try:
        return north_flow.get_outlook()
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

@router.get("/api/water/north/route")
def water_north_route():
    """เส้นทางน้ำเหนือ tab: each gauge's and province's water for today and the next 7 days (routed, then a
    trend), the river course between the gauges for the 3D map, and the AI's read: see north_route.py."""
    return north_route.status()

@router.get("/api/water/north/nonthaburi")
def water_north_nonthaburi():
    """Nonthaburi roads beside the Chao Phraya and the chance the river tops its bank next to them in 7 days."""
    try:
        return river_roads.get(traffic)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})

@router.get("/api/water/bma_events")
def water_bma_events(kind: str = Query(None), hours: int = Query(24, ge=1, le=168), limit: int = Query(60, ge=1, le=200)):
    """Live BMA traffic-centre reports (flooded roads, accidents, closures), polled every minute."""
    return bma_feed.get(kind=kind, hours=hours, limit=limit)
