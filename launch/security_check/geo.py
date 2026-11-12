"""Offline IP -> country and world-map helpers. No IP ever leaves this machine.

Data lives in GEO_DIR (default <repo>/local/geo, override with env BKK_GEO_DIR):
  dbip-country-lite-YYYY-MM.csv.gz  (DB-IP.com, CC BY 4.0)
  land-110m.json                    (Natural Earth, TopoJSON)
  countries.json                    (mledoze/countries)
Update the IP file with: python -m launch.security_check.geo --update
"""
import bisect
import glob
import gzip
import ipaddress
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEO_DIR = os.environ.get("BKK_GEO_DIR") or os.path.join(ROOT, "local", "geo")
DBIP_URL = "https://download.db-ip.com/free/dbip-country-lite-{ym}.csv.gz"


def _dir():
    return os.environ.get("BKK_GEO_DIR") or os.path.join(ROOT, "local", "geo")


def _latest_dbip(d):
    files = sorted(glob.glob(os.path.join(d, "dbip-country-lite-*.csv.gz")))
    return files[-1] if files else None


class GeoDB:
    """Lazy-loaded range table: two sorted int lists per IP family plus country codes."""

    def __init__(self, directory=None):
        self.directory = directory or _dir()
        self._loaded = False
        self._r = {4: ([], [], []), 6: ([], [], [])}  # starts, ends, codes

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        path = _latest_dbip(self.directory)
        if not path:
            return
        try:
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                v4s, v4e, v4c = self._r[4]
                for line in fh:
                    parts = line.rstrip().split(",")
                    if len(parts) < 3:
                        continue
                    a, b, cc = parts[0].strip('"'), parts[1].strip('"'), parts[2].strip('"').upper()
                    if ":" not in a:
                        try:  # fast path for IPv4
                            p4 = a.split(".")
                            q4 = b.split(".")
                            v4s.append((int(p4[0]) << 24) | (int(p4[1]) << 16) | (int(p4[2]) << 8) | int(p4[3]))
                            v4e.append((int(q4[0]) << 24) | (int(q4[1]) << 16) | (int(q4[2]) << 8) | int(q4[3]))
                            v4c.append(cc)
                        except (ValueError, IndexError):
                            if len(v4e) < len(v4s):
                                v4s.pop()
                        continue
                    try:
                        ia = int.from_bytes(socket.inet_pton(socket.AF_INET6, a), "big")
                        ib = int.from_bytes(socket.inet_pton(socket.AF_INET6, b), "big")
                    except OSError:
                        continue
                    s6, e6, c6 = self._r[6]
                    s6.append(ia)
                    e6.append(ib)
                    c6.append(cc)
        except Exception:
            self._r = {4: ([], [], []), 6: ([], [], [])}

    @property
    def available(self):
        self._load()
        return bool(self._r[4][0] or self._r[6][0])

    def lookup(self, ip):
        try:
            a = ipaddress.ip_address(str(ip).strip())
        except ValueError:
            return None
        if a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified:
            return None
        self._load()
        s, e, c = self._r[a.version]
        n = int(a)
        i = bisect.bisect_right(s, n) - 1
        if i < 0 or n > e[i]:
            return None
        cc = c[i]
        return None if cc == "ZZ" else cc


_db = None
_countries = None


def _get_db():
    global _db
    if _db is None or _db.directory != _dir():
        _db = GeoDB()
    return _db


def lookup(ip):
    return _get_db().lookup(ip)


def available():
    return _get_db().available


def _load_countries():
    global _countries
    path = os.path.join(_dir(), "countries.json")
    if _countries is not None and _countries[0] == path:
        return _countries[1]
    data = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for c in json.load(fh):
                data[str(c.get("cca2", "")).upper()] = c
    except Exception:
        pass
    _countries = (path, data)
    return data


def country_name(cc):
    c = _load_countries().get(str(cc or "").upper())
    if c:
        return (c.get("name") or {}).get("common") or str(cc)
    return str(cc or "")


def centroid(cc):
    c = _load_countries().get(str(cc or "").upper())
    ll = (c or {}).get("latlng")
    if ll and len(ll) >= 2:
        return float(ll[0]), float(ll[1])
    return None


def project(lat, lon, width=1000, height=500):
    return (lon + 180) / 360 * width, (90 - lat) / 180 * height


def _decode_arcs(topo):
    tr = topo.get("transform")
    sx, sy = (tr["scale"] if tr else (1, 1))
    tx, ty = (tr["translate"] if tr else (0, 0))
    arcs = []
    for arc in topo.get("arcs", []):
        x = y = 0
        pts = []
        for p in arc:
            if tr:
                x += p[0]
                y += p[1]
                pts.append((x * sx + tx, y * sy + ty))
            else:
                pts.append((p[0], p[1]))
        arcs.append(pts)
    return arcs


def _ring(indices, arcs):
    pts = []
    for i in indices:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def _rings(geom):
    t = geom.get("type")
    if t == "Polygon":
        return list(geom["arcs"])
    if t == "MultiPolygon":
        return [r for poly in geom["arcs"] for r in poly]
    if t == "GeometryCollection":
        return [r for g in geom.get("geometries", []) for r in _rings(g)]
    return []


def land_path(width=1000, height=500):
    """SVG path `d` of the land outline (equirectangular). '' when the file is missing."""
    try:
        with open(os.path.join(_dir(), "land-110m.json"), encoding="utf-8") as fh:
            topo = json.load(fh)
        arcs = _decode_arcs(topo)
        d = []
        for ring in _rings(topo["objects"]["land"]):
            prev = None
            for lon, lat in _ring(ring, arcs):
                x, y = project(lat, lon, width, height)
                if prev is None or abs(x - prev) > width / 2:
                    d.append(f"M{x:.1f} {y:.1f}")
                else:
                    d.append(f"L{x:.1f} {y:.1f}")
                prev = x
        return "".join(d)
    except Exception:
        return ""


def update(out=print):
    """Download the newest DB-IP Lite country file into GEO_DIR, then delete older ones."""
    d = _dir()
    os.makedirs(d, exist_ok=True)
    today = date.today()
    prev = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    for ym in (today.strftime("%Y-%m"), prev.strftime("%Y-%m")):
        url = DBIP_URL.format(ym=ym)
        dest = os.path.join(d, f"dbip-country-lite-{ym}.csv.gz")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bkk-security-check"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as fh:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
        except urllib.error.HTTPError as e:
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
            if e.code == 404:
                continue
            out(f"download failed: HTTP {e.code}")
            return 1
        except Exception as e:
            out(f"download failed: {type(e).__name__}")
            return 1
        os.replace(dest + ".part", dest)
        for old in glob.glob(os.path.join(d, "dbip-country-lite-*.csv.gz")):
            if os.path.abspath(old) != os.path.abspath(dest):
                os.remove(old)
        out("updated:", dest)
        return 0
    out("no file found for this or last month")
    return 1


if __name__ == "__main__":
    if "--update" in sys.argv[1:]:
        sys.exit(update())
    print("usage: python -m launch.security_check.geo --update")
    sys.exit(2)
