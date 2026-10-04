"""
Department of Highways cameras (highwaytraffic.go.th), for the nationwide tab of the live camera page.

The DOH map lists about 210 sites on highways across the country, each with one or two HLS streams (in and
out). Two ASP.NET page methods give a site's details: GetSiteInfo (lat, lon, code, place) and GetCameraInfo
(the player HTML with the stream links). GetCameraInfo only answers inside the session the page starts.

Most links the page gives are dead (streaming3 answers 404 for about 180 sites), but the same feed is often
live on streaming1 under its older name, PhaseN/PER_N_XXX[_IN|_OUT]. So each site's links and those names are
tried, and only the ones that answer with a playlist are kept: about 90 sites, 50 of them not on Longdo's list.

The list is built once a day in a background thread (about 1,300 small requests, 3 at a time) and kept on
disk, so a restart does not ask again.
"""
import html
import http.cookiejar
import json
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from backend.core import thai_regions
from backend.core.instance import DATA_DIR

PAGE = "https://highwaytraffic.go.th/DOHWeb/Home.aspx"
STREAM1 = "https://streaming1.highwaytraffic.go.th/Phase{n}/PER_{n}_{k}{sfx}.stream/playlist.m3u8"
CACHE_FILE = os.path.join(DATA_DIR, "cache", "doh_cameras.json")
REFRESH_S = 24 * 3600
WORKERS = 3
TIMEOUT = 10
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
DIRECTION = {"_IN": "ขาเข้า", "_OUT": "ขาออก"}


def stream_key(url):
    """The DOH feed behind an HLS link, whichever host serves it: ".../Phase3/PER_3_008_IN.stream/..." and
    ".../PER-3/PER-3-008_IN.stream/..." -> "PER_3_008_IN". "" for other links."""
    m = re.search(r"/(PER[-_]\d+[-_]\d+(?:_IN|_OUT)?)\.stream/", url or "", re.I)
    return m.group(1).replace("-", "_").upper() if m else ""


def _text(fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(fragment or ""))).strip()


def _cell(info_html, label):
    """The value next to a label in GetSiteInfo's little table ("ชื่อจุดติดตั้ง", "รายละเอียด")."""
    m = re.search(re.escape(label) + r".*?</td>\s*<td[^>]*>(.*?)</td>", info_html or "", re.S)
    return _text(m.group(1)) if m else ""


class DohCameras:
    def __init__(self):
        self._items = []
        self._updated = 0.0
        self._lock = threading.Lock()
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self._items, self._updated = data.get("items") or [], float(data.get("updated") or 0)
        except (OSError, ValueError):
            pass

    def items(self):
        with self._lock:
            return list(self._items)

    def start(self):
        threading.Thread(target=self._loop, name="doh-cameras", daemon=True).start()

    def _loop(self):
        while True:
            if time.time() - self._updated > REFRESH_S:
                try:
                    self.refresh()
                except Exception as e:
                    print(f"[DOH cameras] refresh failed: {e}")
            time.sleep(3600)

    # ------------------------------------------------------------------ building the list
    def _opener(self):
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        op.addheaders = [("User-Agent", USER_AGENT)]
        return op

    def _method(self, op, name, site_id):
        req = urllib.request.Request(f"{PAGE}/{name}", data=json.dumps({"siteID": site_id}).encode(), method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8", "Referer": PAGE})
        with op.open(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())["d"]

    @staticmethod
    def _live(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status == 200 and resp.read(64).lstrip().startswith(b"#EXTM3U")
        except Exception:
            return False

    def _site(self, op, site_id):
        info = self._method(op, "GetSiteInfo", site_id)        # [lat, lon, code, place table html]
        player = self._method(op, "GetCameraInfo", site_id)
        lat, lon, code = float(info[0]), float(info[1]), str(info[2]).strip()
        name, detail = _cell(info[3], "ชื่อจุดติดตั้ง"), _cell(info[3], "รายละเอียด")
        # The page's own links (some are glued together or on plain http, which an https page cannot play),
        # then the older streaming1 names of the same feed
        links = [u for u in re.findall(r'site_code="([^"]*)"', player) if re.fullmatch(r"https://[\w.:-]+/\S+\.m3u8", u)]
        m = re.fullmatch(r"PER-(\d+)-(\d+)", code)
        if m:
            links += [STREAM1.format(n=m.group(1), k=m.group(2), sfx=s) for s in ("", "_IN", "_OUT")]
        streams = {}
        for url in links:
            key = stream_key(url)
            if key and key not in streams and self._live(url):
                streams[key] = url
        if not streams:
            return []
        province = thai_regions.find_in_text(f"{name} {detail}") or thai_regions.province_at(lat, lon)
        # "1 - อ.หนองแค จ.สระบุรี" -> "ทางหลวง 1 อ.หนองแค"
        place = re.sub(r"^(\d+)\s*-\s*", r"ทางหลวง \1 ", name) or code
        place = re.sub(r"\s*(?:จ\.|จังหวัด)\s*[฀-๿]+", "", place).strip()
        out = []
        for key, url in streams.items():
            sfx = next((s for s in DIRECTION if key.endswith(s)), "")
            way = DIRECTION.get(sfx, "")
            out.append({
                "camid": f"DOH-{code}{sfx.replace('_', '-').lower()}",
                "source": "doh", "organization": "กรมทางหลวง",
                "title": " ".join(p for p in (place, way, detail or "") if p),
                "short_title": " ".join(p for p in (place, way) if p),
                "province": province, "hls_url": url, "vdourl": "", "imgurl": "",
                "latitude": lat, "longitude": lon, "site_code": code,
            })
        return out

    def refresh(self):
        op = self._opener()
        with op.open(PAGE, timeout=30) as resp:
            page = resp.read().decode("utf-8", "replace")
        ids = sorted({int(x) for x in re.findall(r"MoveLocation2?\((\d+)\)", page)})
        if not ids:
            raise RuntimeError("no sites on the DOH page")

        def one(site_id):
            try:
                return self._site(op, site_id)
            except Exception:
                return []

        with ThreadPoolExecutor(WORKERS) as ex:
            items = [c for cams in ex.map(one, ids) for c in cams]
        seen, unique = set(), []
        for c in items:
            if c["camid"] not in seen:
                seen.add(c["camid"])
                unique.append(c)
        with self._lock:
            self._items, self._updated = unique, time.time()
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"updated": self._updated, "sites": len(ids), "items": unique}, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
        print(f"[DOH cameras] {len(unique)} live streams from {len(ids)} sites")


doh_cameras = DohCameras()
