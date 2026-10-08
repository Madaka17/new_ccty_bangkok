"""
Weather and the sky: wind, air quality, NASA fires and storms, the weather here and TMD warnings.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.water import water_service, weather_now, wind_field
from backend.water.air_service import air
from backend.water.flood_feeds import tmd_warnings
from backend.water.nasa_feeds import nasa_feeds

router = APIRouter()


@router.get("/api/weather/wind")
def weather_wind():
    """Current wind / rain / cloud on a 7x7 grid over Bangkok (Open-Meteo) for the map overlay."""
    return water_service.get_wind_grid()

@router.get("/api/weather/wind_field")
def weather_wind_field():
    """Hourly 10 m wind (u, v in m/s) on a 1 degree grid over Thailand (Open-Meteo) for the moving wind lines."""
    return wind_field.get()

@router.get("/api/air/stations")
def air_stations():
    """PM2.5 / AQI per monitoring station in Bangkok + surrounding provinces (Air4Thai)."""
    return air.status()

@router.get("/api/nasa/fires")
def nasa_fires():
    """Fire hotspots in Thailand and along its borders from NASA FIRMS (VIIRS), last 24 h, with the numbers
    against the 24 h before (nasa_feeds.py). 202 until the first read."""
    data = nasa_feeds.fires()
    return data if data else JSONResponse(status_code=202, content={"ready": False})

@router.get("/api/nasa/events")
def nasa_events():
    """Open natural events NASA tracks from India to the western Pacific (EONET): storms with their track and
    distance to Thailand, floods, volcanoes (nasa_feeds.py). 202 until the first read."""
    data = nasa_feeds.events()
    return data if data else JSONResponse(status_code=202, content={"ready": False})

@router.get("/api/weather/now")
def weather_now_at(lat: float = Query(None), lng: float = Query(None)):
    """Weather this hour at the viewer's spot (MET Norway, cached ~1 km / 10 min); Bangkok centre without one."""
    try:
        return weather_now.get(lat, lng)
    except Exception as e:  # noqa: BLE001 - upstream down
        raise HTTPException(status_code=502, detail=f"weather: {str(e)[:120]}")

@router.get("/api/weather/warnings")
def weather_warnings():
    """TMD heavy-rain / storm warnings; `active` holds the ones issued in the last two days."""
    return tmd_warnings.status()
