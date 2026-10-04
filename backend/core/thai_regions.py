"""
Thailand's 77 provinces and the region each belongs to, for the nationwide tab of the live camera page.

Regions are the six of the Royal Institute (the grouping schools teach): north 9, northeast 20, central 22
(with Bangkok), east 7, west 5, south 14. A province code is the first two digits of a Thai geocode
(TIS 1099), which Longdo gives with each of its cameras.

A camera with no province in its name or geocode is looked up by its position on OpenStreetMap's Nominatim
(one request per place, at most one a second as its usage policy asks), and the answer is kept on disk.
"""
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from backend.core.instance import DATA_DIR

NORTH, ISAN, CENTRAL, EAST, WEST, SOUTH = "ภาคเหนือ", "ภาคอีสาน", "ภาคกลาง", "ภาคตะวันออก", "ภาคตะวันตก", "ภาคใต้"
REGIONS = [NORTH, ISAN, CENTRAL, EAST, WEST, SOUTH]
BANGKOK = "กรุงเทพมหานคร"

PROVINCES = {
    "10": (BANGKOK, CENTRAL), "11": ("สมุทรปราการ", CENTRAL), "12": ("นนทบุรี", CENTRAL),
    "13": ("ปทุมธานี", CENTRAL), "14": ("พระนครศรีอยุธยา", CENTRAL), "15": ("อ่างทอง", CENTRAL),
    "16": ("ลพบุรี", CENTRAL), "17": ("สิงห์บุรี", CENTRAL), "18": ("ชัยนาท", CENTRAL), "19": ("สระบุรี", CENTRAL),
    "20": ("ชลบุรี", EAST), "21": ("ระยอง", EAST), "22": ("จันทบุรี", EAST), "23": ("ตราด", EAST),
    "24": ("ฉะเชิงเทรา", EAST), "25": ("ปราจีนบุรี", EAST), "26": ("นครนายก", CENTRAL), "27": ("สระแก้ว", EAST),
    "30": ("นครราชสีมา", ISAN), "31": ("บุรีรัมย์", ISAN), "32": ("สุรินทร์", ISAN), "33": ("ศรีสะเกษ", ISAN),
    "34": ("อุบลราชธานี", ISAN), "35": ("ยโสธร", ISAN), "36": ("ชัยภูมิ", ISAN), "37": ("อำนาจเจริญ", ISAN),
    "38": ("บึงกาฬ", ISAN), "39": ("หนองบัวลำภู", ISAN), "40": ("ขอนแก่น", ISAN), "41": ("อุดรธานี", ISAN),
    "42": ("เลย", ISAN), "43": ("หนองคาย", ISAN), "44": ("มหาสารคาม", ISAN), "45": ("ร้อยเอ็ด", ISAN),
    "46": ("กาฬสินธุ์", ISAN), "47": ("สกลนคร", ISAN), "48": ("นครพนม", ISAN), "49": ("มุกดาหาร", ISAN),
    "50": ("เชียงใหม่", NORTH), "51": ("ลำพูน", NORTH), "52": ("ลำปาง", NORTH), "53": ("อุตรดิตถ์", NORTH),
    "54": ("แพร่", NORTH), "55": ("น่าน", NORTH), "56": ("พะเยา", NORTH), "57": ("เชียงราย", NORTH),
    "58": ("แม่ฮ่องสอน", NORTH),
    "60": ("นครสวรรค์", CENTRAL), "61": ("อุทัยธานี", CENTRAL), "62": ("กำแพงเพชร", CENTRAL), "63": ("ตาก", WEST),
    "64": ("สุโขทัย", CENTRAL), "65": ("พิษณุโลก", CENTRAL), "66": ("พิจิตร", CENTRAL), "67": ("เพชรบูรณ์", CENTRAL),
    "70": ("ราชบุรี", WEST), "71": ("กาญจนบุรี", WEST), "72": ("สุพรรณบุรี", CENTRAL), "73": ("นครปฐม", CENTRAL),
    "74": ("สมุทรสาคร", CENTRAL), "75": ("สมุทรสงคราม", CENTRAL), "76": ("เพชรบุรี", WEST),
    "77": ("ประจวบคีรีขันธ์", WEST),
    "80": ("นครศรีธรรมราช", SOUTH), "81": ("กระบี่", SOUTH), "82": ("พังงา", SOUTH), "83": ("ภูเก็ต", SOUTH),
    "84": ("สุราษฎร์ธานี", SOUTH), "85": ("ระนอง", SOUTH), "86": ("ชุมพร", SOUTH), "90": ("สงขลา", SOUTH),
    "91": ("สตูล", SOUTH), "92": ("ตรัง", SOUTH), "93": ("พัทลุง", SOUTH), "94": ("ปัตตานี", SOUTH),
    "95": ("ยะลา", SOUTH), "96": ("นราธิวาส", SOUTH),
}
_REGION = dict(PROVINCES.values())
_ALIASES = {"กรุงเทพ": BANGKOK, "กรุงเทพฯ": BANGKOK, "กทม": BANGKOK, "กทม.": BANGKOK, "Bangkok": BANGKOK,
            "อยุธยา": "พระนครศรีอยุธยา"}
# Names found anywhere in a text: only the long ones, since short ones sit inside other words
# (ตาก in ตากสิน, เลย in "เลยแยก", แพร่ in เผยแพร่)
_LONG_NAMES = sorted((n for n in _REGION if len(n) >= 5), key=len, reverse=True)


def normalize(name):
    """The province's full name, or "" when it is not one of the 77 ("จ.ชลบุรี", "จังหวัดชลบุรี" -> "ชลบุรี")."""
    name = re.sub(r"^(จังหวัด|จ\.)\s*", "", (name or "").strip())
    name = _ALIASES.get(name, name)
    return name if name in _REGION else ""


def from_geocode(code):
    """Province of a Thai geocode ("240101" -> "ฉะเชิงเทรา"), or ""."""
    code = str(code or "").strip()
    return PROVINCES[code[:2]][0] if len(code) >= 2 and code[:2] in PROVINCES else ""


def region_of(province):
    return _REGION.get(province, "")


def in_thailand(lat, lon):
    """Inside the box around Thailand (a rough check that catches swapped or copied coordinates)."""
    try:
        return 5.5 < float(lat) < 20.5 and 97.3 < float(lon) < 105.7
    except (TypeError, ValueError):
        return False


def find_in_text(text):
    """The province a place text names: "จ.X" first, then any long province name in it, else ""."""
    text = text or ""
    for m in re.finditer(r"(?:จ\.|จังหวัด)\s*([฀-๿]+)", text):
        word = m.group(1)
        hit = next((n for n in sorted(_REGION, key=len, reverse=True) if word.startswith(n)), "")
        if hit:
            return hit
    if "กรุงเทพ" in text:
        return BANGKOK
    found = [(text.find(n), n) for n in _LONG_NAMES if n in text]
    return min(found)[1] if found else ""


# ---------------------------------------------------------------- lookup by position (Nominatim, cached)
_CACHE_FILE = os.path.join(DATA_DIR, "cache", "province_at.json")
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=8&accept-language=th&lat={lat}&lon={lon}"
_lock = threading.Lock()
_cache = None
_last_call = 0.0


def _load():
    global _cache
    if _cache is None:
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def province_at(lat, lon):
    """Province at a position, from Nominatim once and from disk after that; "" when unknown."""
    global _last_call
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return ""
    if not in_thailand(lat, lon):
        return ""
    key = f"{lat:.3f},{lon:.3f}"
    with _lock:
        cache = _load()
        if key in cache:
            return cache[key]
        time.sleep(max(0.0, 1.1 - (time.time() - _last_call)))
        _last_call = time.time()
        try:
            req = urllib.request.Request(_NOMINATIM.format(lat=lat, lon=lon),
                                         headers={"User-Agent": "BKK-StreetSmart/1.0 (bkksmartstreet.com)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                addr = json.loads(resp.read()).get("address") or {}
        except Exception:
            return ""   # not kept: asked again next time
        name = next((normalize(addr.get(k)) for k in ("state", "province", "city") if normalize(addr.get(k))), "")
        cache[key] = name
        try:
            os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
            with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        except OSError:
            pass
        return name
