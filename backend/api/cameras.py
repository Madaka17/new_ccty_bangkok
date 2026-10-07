"""
Camera lists for the live camera page and the map, the pictures the browser cannot fetch itself, the hidden
(down) cameras, and the cameras the background counters watch.
"""
import gzip
import json
import os
import time

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from backend.core import thai_regions
from backend.core.instance import DATA_DIR
from backend.services import bma_scanner, camera_health, cameras_data, counter, longdo_cameras, SAFE_ID, survey
from backend.vision.doh_cameras import doh_cameras, stream_key as doh_stream_key
from backend.vision.world_cameras import world_cameras

router = APIRouter()


@router.get("/api/cameras")
def get_cameras():
    return {"total": len(cameras_data), "items": cameras_data}

@router.get("/api/cameras/longdo")
def get_longdo_cameras():
    """Returns all cameras from Longdo Traffic API with disk and memory caching (services.longdo_cameras)."""
    return longdo_cameras()

@router.get("/api/cameras/health")
def get_cameras_health():
    """camid -> "online" / "offline" for the live-AI cameras, checked at most every 5 min."""
    return camera_health.get()

def _unmasked(c):
    """Longdo masks some camera addresses (camid=X.X.X.X), and parks suspended cameras on one placeholder
    stream (tempsus.m3u8): blank those links so the page does not try them."""
    hls = "" if "tempsus" in (c.get("hls_url") or "") else c.get("hls_url") or ""
    vdo = "" if "X.X.X.X" in (c.get("vdourl") or "") else c.get("vdourl") or ""
    img = "" if "X.X.X.X" in (c.get("imgurl") or "") else c.get("imgurl") or ""
    return dict(c, hls_url=hls, vdourl=vdo, imgurl=img, source="itic")

@router.get("/api/cameras/all")
def get_all_cameras(request: Request):
    """Every camera for the live camera page. Ours first (cameras_bkk.json, the ones the AI knows), then the
    rest of iTIC's list from Longdo, then the Department of Highways cameras Longdo does not list (source
    "doh"), then the BMA cameras (source "bma"), which have no video: the page shows their newest frame,
    then the rest of the country (world_cameras.py: BMA flood centre, Pattaya, city and river cameras),
    whose "media" says how the page shows each one. Left out: Longdo cameras on the "tempsus" placeholder stream (suspended, about 80 in Pattaya) and links
    with a masked address (camid=X.X.X.X). Each camera carries its province and region (ภาค) for the
    nationwide tab."""
    # A DOH feed on iTIC's relay plays from DOH's own host when DOH's list (checked daily) has it live:
    # the relay answers 404 for many of these feeds
    doh_live = {doh_stream_key(c.get("hls_url")): c["hls_url"] for c in doh_cameras.items()}
    doh_live.pop("", None)

    def _direct(c):
        url = doh_live.get(doh_stream_key(c.get("hls_url")))
        return dict(c, hls_url=url) if url else c

    items = [_direct(_unmasked(c)) for c in cameras_data]
    seen = {c.get("camid") for c in cameras_data} | {c.get("hls_url") for c in cameras_data if c.get("hls_url")}
    for c in map(_unmasked, get_longdo_cameras().get("items") or []):
        if not (c["hls_url"] or c["vdourl"]) or c.get("camid") in seen or c["hls_url"] in seen:
            continue
        seen.update(k for k in (c.get("camid"), c["hls_url"]) if k)
        items.append(c)
    # The same DOH feed reaches us through iTIC's relay as well as from DOH's own hosts
    feeds = {doh_stream_key(c.get("hls_url")) for c in items} - {""}
    for c in doh_cameras.items():
        if c.get("camid") in seen or doh_stream_key(c.get("hls_url")) in feeds:
            continue
        seen.add(c.get("camid"))
        items.append(dict(c))
    for c in bma_scanner.cameras:
        camid = str(c.get("camid") or "")
        if not SAFE_ID.fullmatch(camid):
            continue
        district = c.get("district") or ""
        place = [c.get("road") or "", f"เขต{district}" if district and district != "กรุงเทพมหานคร" else ""]
        items.append({
            "camid": f"BMA-{camid}", "bma_id": camid, "source": "bma",
            "title": " ".join(p for p in [c.get("title") or ""] + place if p),
            "short_title": c.get("short_title") or c.get("title") or camid,
            "province": "กรุงเทพมหานคร", "hls_url": "", "vdourl": "", "imgurl": f"/api/bma/snapshot/{camid}?annotate=0",
            "latitude": float(c.get("latitude") or 0), "longitude": float(c.get("longitude") or 0),
        })
    items.extend(world_cameras.items())
    for c in items:
        # Longdo's geocode beats the province in its title, which defaults to Bangkok when the title has none
        province = thai_regions.from_geocode(c.get("geocode")) or thai_regions.normalize(c.get("province"))
        c["province"] = province or c.get("province") or ""
        c["region"] = thai_regions.region_of(province)
        if not thai_regions.in_thailand(c.get("latitude"), c.get("longitude")):
            c["latitude"] = c["longitude"] = 0   # e.g. BMA-1712 has its latitude in both
    # About 430 KB of mostly Thai text: gzip takes it under 60 KB
    body = json.dumps({"total": len(items), "items": items}, ensure_ascii=False).encode("utf-8")
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(gzip.compress(body, 6), media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, media_type="application/json")

CAMERA_STATUS_FILE = os.path.join(DATA_DIR, "camera_status.json")   # written by launch\camera_status.py every 5 minutes

CAMERA_STATUS_MAX_AGE = 20 * 60

_down_cache = {"mtime": 0, "checked_at": 0, "items": []}

@router.get("/api/cameras/down")
def get_down_cameras():
    """Cameras the newest launch\\camera_status.py round could not pull from, for the live camera page to hide until
    a later round finds them working again. Empty when that round is over 20 minutes old (the status window is
    closed), so a stopped check never hides a camera."""
    try:
        mtime = os.path.getmtime(CAMERA_STATUS_FILE)
        if mtime != _down_cache["mtime"]:
            with open(CAMERA_STATUS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            _down_cache.update(mtime=mtime, checked_at=int(data.get("checked_at") or 0),
                               items=[camid for camid, r in (data.get("cameras") or {}).items() if r.get("state") == "down"])
    except (OSError, ValueError):
        return {"checked_at": 0, "items": []}
    if time.time() - _down_cache["checked_at"] > CAMERA_STATUS_MAX_AGE:
        return {"checked_at": _down_cache["checked_at"], "items": []}
    return {"checked_at": _down_cache["checked_at"], "items": _down_cache["items"]}

@router.get("/api/cameras/image/{camid}")
def get_camera_image(camid: str):
    """Newest picture of a DWR, DDPM or Nonthaburi camera, which the browser cannot fetch itself: see world_cameras.py."""
    if not SAFE_ID.fullmatch(camid):
        raise HTTPException(400, "bad camera id")
    data = world_cameras.image_bytes(camid)
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "max-age=60"})

@router.get("/api/count/cameras")
def get_count_cameras():
    return counter.status()

@router.put("/api/count/cameras")
def set_count_cameras(payload: dict = Body(...)):
    camids = payload.get("camids") or []
    if not isinstance(camids, list) or len(camids) > counter.max_cameras:
        return JSONResponse(status_code=400, content={"error": f"camids must be a list of at most {counter.max_cameras}"})
    by_id = {c["camid"]: c for c in cameras_data}
    counter.set_cameras([by_id[c] for c in camids if c in by_id])
    return counter.status()

@router.get("/api/survey/ranking")
def get_survey_ranking():
    """Every camera with its latest measurement: continuous counters plus round-robin survey samples."""
    now = int(time.time())
    items = []
    for c in counter.status()["cameras"]:
        if c["active"]:
            items.append({"camid": c["camid"], "title": c["title"], "ts": now, "source": "count",
                          "rate_per_min": c["rate_per_min"], "visible": c["total"],
                          "moving_pct": c["moving_pct"], "level": c["level"], "error": ""})
    sv = survey.status()
    items += sv["cameras"]
    return {"cycle_seconds": sv["cycle_seconds"], "sample_seconds": sv["sample_seconds"],
            "total_cameras": len(cameras_data), "cameras": items}
