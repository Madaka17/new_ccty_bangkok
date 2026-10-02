"""
Cameras from the rest of Thailand, for the live camera page and the camera map, each list read straight from
the agency that runs the cameras. Every list is read once a day in a background thread and kept on disk (a
failed read keeps the last good list):

- BMA flood centre (floodbangkok.bangkok.go.th), ~876 cameras on drains and roads. Their stream hosts are
  internal, so the picture comes through the site's own /api/proxy, which answers one JPEG (~9 s).
- Pattaya (livestream.pattaya.go.th), ~600. The list is public, but the video only plays on Pattaya's site
  after a Cloudflare Turnstile check, so these cameras open Pattaya's site (media "link").
- Nakhon Si Thammarat city (nstcctv.nakhoncity.org), ~220, each with its own web player (media "iframe").
- Department of Water Resources (telemetry.dwr.go.th), ~127 river stations. Their list also carries the
  cameras' own addresses with a password in them; those are never used. The picture is the public snapshot:
  the newest file name, then a POST for the file, so it goes through image_bytes().
- Pak Kret city (thaiclouderp.com), ~53, a JPEG each.
- Koh Samui city (prj.smartsamui.com), ~24, a webm stream each (media "video").
- Hat Yai City Climate (hatyaicityclimate.org), ~25 flood cameras with a picture each. Its weather pictures
  (radar, satellite, weather map) and cameras whose newest picture is over a week old are left out.
- EGAT dams, from the national water data centre's list (api-v3.thaiwater.net), 8 with an https picture. The
  rest of that list is DWR's (read above, from DWR) or links straight into the cameras over plain http.

Each camera says how the page shows it (media): "image" (a JPEG, refreshed), "video", "iframe" or "link".
"""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from backend.core import thai_regions
from backend.core.instance import DATA_DIR

FLOOD_LIST = ("https://floodbangkok.bangkok.go.th/bkk/dds/services/api/floods/v1/items/camera_profile"
              "?limit=-1&fields=id,CameraName,LiveStream,Lat,Long,camera_description")
FLOOD_FRAME = "https://floodbangkok.bangkok.go.th/api/proxy?rtcUrl={}"
PATTAYA_LIST = "https://livestream.pattaya.go.th/kapi/live/map"
PATTAYA_PAGE = "https://livestream.pattaya.go.th/"
NAKHON_LIST = "https://nstcctv.nakhoncity.org/api/cameras/public"
NAKHON_PLAYER = "https://nstcctv.nakhoncity.org/cam/{}_sub/?controls=true&muted=true&autoplay=true&playsinline=true"
DWR_API = "https://telemetry.dwr.go.th/api"
PAKKRED_PAGE = "https://www.thaiclouderp.com/CCTV_MONITOR/web/pakkred"
PAKKRED_IMAGE = "https://www.thaiclouderp.com/src/img.php?name={}_thumb.jpg"
SAMUI_MAP = "https://prj.smartsamui.com/samui_cctv/map.php"
SAMUI_STREAM = "https://prj.smartsamui.com/samui_cctv/proxy/stream.php?id={}"
HATYAI_LIST = "https://hatyaicityclimate.org/api/flood/cams"
HATYAI_NOT_CCTV = re.compile(r"เรดาร์|ดาวเทียม|แผนที่อากาศ|เครือข่าย")
HATYAI_MAX_AGE_S = 7 * 86400
THAIWATER_LIST = "https://api-v3.thaiwater.net/api/v1/thaiwater30/analyst/cctv"
CACHE_FILE = os.path.join(DATA_DIR, "cache", "world_cameras.json")
IMAGE_DIR = os.path.join(DATA_DIR, "cache", "world_images")
REFRESH_S = 24 * 3600
IMAGE_TTL = 600   # DWR posts a new picture every 15 minutes
TIMEOUT = 30
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

# group: who runs the camera, for the map's colours (OWNERS in CameraMap.jsx)
SOURCES = {
    "floodbkk": {"group": "bma", "organization": "กทม. (ระบายน้ำ)", "province": "กรุงเทพมหานคร"},
    "pattaya": {"group": "pattaya", "organization": "เมืองพัทยา", "province": "ชลบุรี"},
    "nakhon": {"group": "city", "organization": "เทศบาลนครนครศรีธรรมราช", "province": "นครศรีธรรมราช"},
    "pakkred": {"group": "city", "organization": "เทศบาลนครปากเกร็ด", "province": "นนทบุรี"},
    "samui": {"group": "city", "organization": "เทศบาลนครเกาะสมุย", "province": "สุราษฎร์ธานี"},
    "dwr": {"group": "water", "organization": "กรมทรัพยากรน้ำ", "province": ""},
    "hatyai": {"group": "city", "organization": "Hatyai City Climate", "province": "สงขลา"},
    "egat": {"group": "water", "organization": "กฟผ. (เขื่อน)", "province": ""},
}


def _get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _post_json(url, body):
    return json.loads(_get(url, json.dumps(body).encode(), {"Content-Type": "application/json"}))


def _camera(source, key, name, lat, lng, media, province="", **extra):
    info = SOURCES[source]
    name = re.sub(r"\s+", " ", name or "").strip() or str(key)
    return {
        "camid": re.sub(r"[^A-Za-z0-9_.-]", "", f"{source}-{key}")[:80],
        "source": source, "group": info["group"], "organization": info["organization"],
        "title": name, "short_title": name, "media": media,
        "province": info["province"] or thai_regions.normalize(province) or thai_regions.province_at(lat, lng),
        "hls_url": "", "vdourl": "", "imgurl": "", "latitude": float(lat or 0), "longitude": float(lng or 0),
        **extra,
    }


def read_flood():
    out = []
    for row in json.loads(_get(FLOOD_LIST)).get("data") or []:
        if row.get("LiveStream"):
            name = " ".join(p for p in (row.get("CameraName"), row.get("camera_description")) if p)
            out.append(_camera("floodbkk", row.get("id"), name, row.get("Lat"), row.get("Long"), "image",
                               imgurl=FLOOD_FRAME.format(urllib.parse.quote(row["LiveStream"], safe=""))))
    return out


def read_pattaya():
    out = []
    for row in (json.loads(_get(PATTAYA_LIST)).get("details") or {}).get("items") or []:
        if row.get("monitorState") == "offline" or row.get("status") is False:
            continue
        name = f"{row['location']} ({row.get('name')})" if row.get("location") else row.get("name")
        out.append(_camera("pattaya", row.get("id"), name, row.get("lat"), row.get("lng"), "link", page_url=PATTAYA_PAGE))
    return out


def read_nakhon():
    return [_camera("nakhon", row["id"], row.get("name"), row.get("lat"), row.get("lng"), "iframe",
                    embed_url=NAKHON_PLAYER.format(urllib.parse.quote(row["id"])), page_url="https://nstcctv.nakhoncity.org/")
            for row in json.loads(_get(NAKHON_LIST)) if re.fullmatch(r"[\w-]{1,40}", str(row.get("id") or ""))]


def read_dwr():
    body = {"paginate": {"page": 1, "pageSize": 1000, "orders": [{"key": "MAIN_BASIN", "desc": False}]}, "search": {}}
    rows = (_post_json(f"{DWR_API}/public/reportCctv/listPaginate", body).get("value") or {}).get("results") or []

    def one(row):
        st = row.get("entity") or {}
        if not st.get("cctvOnline"):
            return None
        # The list has no position; the station's own page does
        detail = json.dumps(json.loads(_get(f"{DWR_API}/public/station/{st['id']}")))
        lat = re.search(r'"lat": ?(-?[\d.]+)', detail)
        lon = re.search(r'"lon": ?(-?[\d.]+)', detail)
        if not (lat and lon):
            return None
        return _camera("dwr", st["id"], f"{st.get('stnNameTh') or ''} ({st.get('stationCode')})", lat.group(1), lon.group(1),
                       "image", province=row.get("provinceNameTh"), station=st["id"])

    with ThreadPoolExecutor(3) as ex:
        return list(ex.map(one, rows))


def read_pakkred():
    page = _get(PAKKRED_PAGE).decode("utf-8", "replace")
    codes = dict(re.findall(r"view_cctv\(\"(CAMPK\d+)\",\s*\"(\d+)\.", page))   # CAMPK001 -> "1"
    by_number = {n: code for code, n in codes.items()}
    out = []
    for lat, lng, name, n in re.findall(r'\[\{"lat":(-?[\d.]+),"lng":(-?[\d.]+)\},"((?:[^"\\]|\\.)*)",(\d+)\]', page):
        code = by_number.get(n)
        if code:
            out.append(_camera("pakkred", code, json.loads(f'"{name}"'), lat, lng, "image", imgurl=PAKKRED_IMAGE.format(code)))
    return out


def read_samui():
    page = _get(SAMUI_MAP).decode("utf-8", "replace")
    m = re.search(r"const cameras = (\[.*?\]);", page, re.S)
    rows = json.loads(m.group(1)) if m else []
    return [_camera("samui", row["id"], f"{row.get('name') or ''} {row.get('location') or ''}", row.get("lat"), row.get("lng"),
                    "video", video_url=SAMUI_STREAM.format(int(row["id"])))
            for row in rows if str(row.get("id") or "").isdigit()]


def read_hatyai():
    out = []
    for row in json.loads(_get(HATYAI_LIST)).get("items") or []:
        loc = row.get("location") or {}
        try:
            age = time.time() - time.mktime(time.strptime(row.get("atDate") or "", "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            continue
        if (not row.get("enable") or HATYAI_NOT_CCTV.search(row.get("title") or "") or age > HATYAI_MAX_AGE_S
                or not str(row.get("photo") or "").startswith("https://") or not re.fullmatch(r"\w{1,40}", str(row.get("name") or ""))):
            continue
        out.append(_camera("hatyai", row["name"], row.get("title"), loc.get("latitude"), loc.get("longitude"), "image", imgurl=row["photo"]))
    return out


def read_thaiwater():
    out = []
    for row in json.loads(_get(THAIWATER_LIST)).get("data") or []:
        url = row.get("cctv_url") or ""
        agency = ((row.get("agency") or {}).get("agency_shortname") or {}).get("en")
        if agency != "EGAT" or not row.get("is_active") or not url.startswith("https://"):
            continue
        province = (((row.get("geocode") or {}).get("province_name")) or {}).get("th")
        out.append(_camera("egat", row.get("id"), row.get("title"), row.get("lat"), row.get("long"), "image",
                           province=province, imgurl=url))
    return out


READERS = {"flood": read_flood, "pattaya": read_pattaya, "nakhon": read_nakhon, "dwr": read_dwr,
           "pakkred": read_pakkred, "samui": read_samui, "hatyai": read_hatyai, "thaiwater": read_thaiwater}


class WorldCameras:
    def __init__(self):
        self._lists = {}       # reader name -> cameras
        self._updated = {}     # reader name -> when read
        self._lock = threading.Lock()
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self._lists, self._updated = data.get("lists") or {}, data.get("updated") or {}
        except (OSError, ValueError):
            pass
        self._by_id = {c["camid"]: c for cams in self._lists.values() for c in cams}

    def items(self):
        """Copies of every camera; DWR's point at /api/cameras/image instead of their source."""
        with self._lock:
            cams = [c for cams in self._lists.values() for c in cams]
        out = []
        for c in cams:
            c = dict(c)
            if c.pop("station", None):
                c["imgurl"] = f"/api/cameras/image/{c['camid']}"
            out.append(c)
        return out

    def start(self):
        threading.Thread(target=self._loop, name="world-cameras", daemon=True).start()

    def _loop(self):
        while True:
            for name in READERS:
                if time.time() - float(self._updated.get(name) or 0) >= REFRESH_S:
                    self.refresh(name)
            time.sleep(3600)

    def refresh(self, name):
        try:
            cams = [c for c in READERS[name]() if c]
        except Exception as e:
            print(f"[World cameras] {name} failed: {e}")
            return
        if not cams:
            return
        with self._lock:
            self._lists[name], self._updated[name] = cams, time.time()
            self._by_id = {c["camid"]: c for cs in self._lists.values() for c in cs}
            data = {"updated": self._updated, "lists": self._lists}
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        print(f"[World cameras] {name}: {len(cams)} cameras")

    def image_bytes(self, camid):
        """Newest DWR picture of a camera on our list, kept on disk for IMAGE_TTL; None when unknown or none."""
        cam = self._by_id.get(camid)
        if not cam or not cam.get("station"):
            return None
        path = os.path.join(IMAGE_DIR, f"{camid}.jpg")
        try:
            if time.time() - os.path.getmtime(path) < IMAGE_TTL:
                with open(path, "rb") as f:
                    return f.read()
        except OSError:
            pass
        try:
            name = (json.loads(_get(f"{DWR_API}/public/reportCctv/snapshot/{cam['station']}")).get("value") or "").strip()
            data = _get(f"{DWR_API}/file/image/cctv", json.dumps({"path": name}).encode(),
                        {"Content-Type": "application/json"}) if name else b""
        except Exception:
            data = b""
        if not data.startswith(b"\xff\xd8"):
            return None
        os.makedirs(IMAGE_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return data


world_cameras = WorldCameras()
