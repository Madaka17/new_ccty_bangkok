"""Hospitals in Bangkok and the surrounding provinces from OpenStreetMap, for the emergency button.

One Overpass query for amenity=hospital (nodes, ways and relations; ways/relations reduced to their centre)
over the metropolitan area, slimmed into web/public/riskbkk/hospital.geojson the same way as shelter.geojson:
a title and a phone number per point. The page sorts them by distance in the browser.

    python local/pipeline/build_hospitals.py
"""
import json
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'web', 'public', 'riskbkk', 'hospital.geojson')
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
BBOX = (13.45, 100.25, 14.15, 100.95)   # south, west, north, east: Bangkok, Nonthaburi, Pathum Thani, Samut Prakan
QUERY = f'[out:json][timeout:120];nwr["amenity"="hospital"]{BBOX};out center tags;'


def fetch():
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    for url in OVERPASS:   # the main server often answers 504 when busy: try the next one
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "bkksmartstreet.com hospital list"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["elements"]
        except Exception as e:  # noqa: BLE001
            print(f"overpass {url.split('/')[2]}: {e}")
    raise SystemExit("no Overpass server answered")


def main():
    features = []
    for el in fetch():
        t = el.get("tags", {})
        name = (t.get("name:th") or t.get("name") or "").strip()
        lat, lng = el.get("lat") or el.get("center", {}).get("lat"), el.get("lon") or el.get("center", {}).get("lon")
        if not name or lat is None:
            continue
        phone = t.get("phone") or t.get("contact:phone") or ""
        props = {"title": name}
        tels = [p.strip() for p in phone.replace(",", ";").split(";") if p.strip()]
        if tels:
            props["tel"] = tels[:2]
        if t.get("emergency") in ("yes", "no"):
            props["emergency"] = t["emergency"] == "yes"
        features.append({"type": "Feature", "properties": props,
                         "geometry": {"type": "Point", "coordinates": [round(lng, 5), round(lat, 5)]}})
    features.sort(key=lambda f: f["properties"]["title"])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(features)} hospitals -> {OUT}")


if __name__ == "__main__":
    main()
