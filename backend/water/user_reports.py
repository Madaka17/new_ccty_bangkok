"""
Flood reports from the public: province, district, a pin, water depth, an optional photo and a note
of up to 2,000 characters, sent from the Report Flood page.

POST /api/flood/user-reports (public; size and rate limited in access_guard)
    -> the photo is decoded with Pillow (at most MAX_PIXELS), turned upright, cut to MAX_SIDE and saved again
       as a plain JPEG, so nothing of the phone's EXIF (GPS, model, time) is kept
    -> the Qwen vision model behind LOCAL_LLM_* checks photo and note together: a real photo of water on a
       road or soi, nothing unfit to show -> published, else rejected (and the photo deleted)
    -> a note without a photo is checked the same way as text; a pin and a depth alone are published at once
    -> when the model does not answer the report stays pending, and a worker tries again every RETRY_SECONDS
Published reports show on the maps for SHOW_HOURS as "ประชาชนแจ้ง ยังไม่ยืนยัน". The operator can delete
one (DELETE, operator only). Rows live in the user_flood_reports table of vehicle_counts.db, photos in
cache/user_reports/<id>.jpg.
"""
import base64
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from functools import lru_cache

from PIL import Image, ImageOps

from backend.core import local_llm, thai_regions
from backend.core.instance import BASE_DIR, DATA_DIR
from backend.water.flood_feeds import hide_contacts

DB_PATH = os.path.join(DATA_DIR, "vehicle_counts.db")
PHOTO_DIR = os.path.join(DATA_DIR, "cache", "user_reports")
SHOW_HOURS = float(os.getenv("USER_REPORT_HOURS", "6"))
MAX_PIXELS = 40_000_000        # refuse bigger images before decoding them (decompression bombs)
MAX_SIDE = 1280
NOTE_MAX = 2000
RETRY_SECONDS = 60
AGENT_TIMEOUT = 45
# All of Thailand (the province flood tab counts reports from every province): a pin outside is a mistake or a test
LAT_RANGE, LNG_RANGE = (5.5, 20.5), (97.3, 105.7)
DEPTHS = {"ankle": ("ข้อเท้า", 10), "shin": ("หน้าแข้ง", 25), "chest": ("อก", 120),
          "knee": ("เข่า", 45), "thigh": ("เลยเข่า", 60)}  # retain old reports' depth codes
LEVEL_TH = {"none": "ไม่เห็นน้ำท่วม", "puddle": "น้ำขังเล็กน้อย", "flooded": "น้ำท่วมผิวจราจร", "severe": "น้ำท่วมหนัก"}
_ID = re.compile(r"[0-9a-f]{12}")
_LINK = re.compile(r"https?://|www\.|\.(com|net|org|co|th|ly|io)\b", re.I)

CHECK_PROMPT = (
    "You check what the public sends to the Bangkok flood map: a photo (maybe) and a short Thai note (maybe). "
    'Answer ONLY with JSON: {"flood": true|false, "level": "none|puddle|flooded|severe", "fit": true|false, '
    '"note_th": "<one short Thai sentence about what the photo shows>"}. '
    "flood = the photo is a real camera photo (not a screenshot, drawing, meme or photo of a screen) of water "
    "standing or flowing on a road, soi, street, footpath or car park. With no photo, flood is true. "
    "level = puddle: pools, lanes still clear; flooded: water over a lane or more; severe: deep water, up to "
    "the wheels or the knees; none: no flood water. With no photo, level is none. "
    "fit = false when the photo or the note shows or says anything unfit for a public map: nudity, violence, "
    "a person's face as the subject, ads, links, phone numbers, insults or politics. Otherwise true."
)


@lru_cache(maxsize=1)
def report_locations():
    """Province/district choices from the bundled boundaries, independent of live traffic feeds."""
    with open(os.path.join(BASE_DIR, "config", "thailand_districts.geojson"), encoding="utf-8") as f:
        features = json.load(f)["features"]
    provinces = {}
    for ft in features:
        p = ft["properties"]
        province = thai_regions.PROVINCES[str(p["pro_code"])][0]
        coords = ft["geometry"]["coordinates"]
        rings = coords if ft["geometry"]["type"] == "Polygon" else [r for poly in coords for r in poly]
        points = [point for ring in rings for point in ring]
        lng = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
        lat = (min(p[1] for p in points) + max(p[1] for p in points)) / 2
        provinces.setdefault(province, []).append({"name": p["amp_th"], "lat": round(lat, 5), "lng": round(lng, 5)})
    return {name: sorted(districts, key=lambda d: d["name"]) for name, districts in sorted(provinces.items())}


class UserReports:
    def __init__(self):
        self.lock = threading.Lock()
        os.makedirs(PHOTO_DIR, exist_ok=True)
        with self._db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_flood_reports (
                    id        TEXT PRIMARY KEY,
                    ts        INTEGER NOT NULL,
                    lat       REAL NOT NULL,
                    lng       REAL NOT NULL,
                    depth     TEXT NOT NULL,        -- ankle | shin | chest (legacy: knee | thigh)
                    note      TEXT,
                    has_photo INTEGER NOT NULL,
                    status    TEXT NOT NULL,        -- pending | published | rejected | deleted
                    ai_level  TEXT,                 -- none | puddle | flooded | severe (from the photo)
                    ai_note   TEXT
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS user_flood_reports_ts ON user_flood_reports(ts)")
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(user_flood_reports)")}
            for name in ("province", "district"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE user_flood_reports ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _db(self):
        """A connection for one block: committed at the end (rolled back on error), then closed."""
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _set(self, rid, **fields):
        with self.lock, self._db() as conn:
            conn.execute(f"UPDATE user_flood_reports SET {', '.join(k + ' = ?' for k in fields)} WHERE id = ?",
                         [*fields.values(), rid])

    @staticmethod
    def photo_path(rid):
        if not _ID.fullmatch(str(rid)):
            raise ValueError("bad id")
        return os.path.join(PHOTO_DIR, f"{rid}.jpg")

    # ------------------------------------------------------------ in
    @staticmethod
    def _clean_photo(data_url):
        """JPEG bytes from a data: URL, upright, at most MAX_SIDE, without EXIF. ValueError when it is no image."""
        head, _, b64 = str(data_url).partition(",")
        if not head.startswith("data:image/") or not b64:
            raise ValueError("รูปแบบรูปไม่ถูกต้อง")
        try:
            raw = base64.b64decode(b64, validate=True)
            img = Image.open(io.BytesIO(raw))
            if img.width * img.height > MAX_PIXELS:
                raise ValueError("รูปใหญ่เกินไป")
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001 - anything Pillow cannot read
            raise ValueError("เปิดรูปนี้ไม่ได้ ลองถ่ายใหม่หรือเลือกรูป JPEG") from e
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85)   # a fresh file: no EXIF, no GPS
        return out.getvalue()

    def create(self, body):
        """Validate and store a report, check it, return {id, status, message}. ValueError = bad input (400)."""
        try:
            lat, lng = float(body.get("lat")), float(body.get("lng"))
        except (TypeError, ValueError):
            raise ValueError("ยังไม่ได้ปักหมุดตำแหน่ง") from None
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
            raise ValueError("ตำแหน่งอยู่นอกประเทศไทย")
        depth = str(body.get("depth") or "")
        if depth not in DEPTHS:
            raise ValueError("เลือกระดับน้ำก่อน")
        province = str(body.get("province") or "").strip()
        district = str(body.get("district") or "").strip()
        if province not in report_locations():
            raise ValueError("เลือกจังหวัดก่อน")
        if district not in {d["name"] for d in report_locations()[province]}:
            raise ValueError("เลือกอำเภอ/เขตให้ตรงกับจังหวัด")
        note = str(body.get("note") or "").strip()
        if len(note) > NOTE_MAX:
            raise ValueError("รายละเอียดต้องไม่เกิน 2,000 ตัวอักษร")
        if _LINK.search(note):
            raise ValueError("ข้อความใส่ลิงก์ไม่ได้")
        jpeg = self._clean_photo(body["photo"]) if body.get("photo") else None

        rid = secrets.token_hex(6)
        if jpeg:
            with open(self.photo_path(rid), "wb") as f:
                f.write(jpeg)
        status = "pending" if (jpeg or note) else "published"
        with self.lock, self._db() as conn:
            conn.execute("""INSERT INTO user_flood_reports
                         (id, ts, lat, lng, depth, note, has_photo, status, ai_level, ai_note, province, district)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (rid, int(time.time()), round(lat, 6), round(lng, 6), depth, note, int(bool(jpeg)), status,
                          None, None, province, district))
        if status == "pending":
            status = self._check(rid)
        messages = {"published": "ขึ้นแผนที่แล้ว ขอบคุณที่แจ้ง",
                    "pending": "ได้รับแล้ว กำลังรอ AI ตรวจ จะขึ้นแผนที่เมื่อผ่าน",
                    "rejected": "ไม่ขึ้นแผนที่: AI ไม่พบน้ำท่วมในรูป หรือรูป/ข้อความไม่เหมาะสม"}
        return {"id": rid, "status": status, "message": messages[status]}

    # ------------------------------------------------------------ check
    def _check(self, rid):
        """Ask the model about a pending report. Returns the new status (pending when the model did not answer)."""
        with self._db() as conn:
            row = conn.execute("SELECT * FROM user_flood_reports WHERE id = ?", (rid,)).fetchone()
        if not row or row["status"] != "pending":
            return row["status"] if row else "deleted"
        if not local_llm.default.enabled():
            return "pending"
        content = []
        if row["has_photo"]:
            with open(self.photo_path(rid), "rb") as f:
                image = "data:image/jpeg;base64," + base64.standard_b64encode(f.read()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": image}})
        content.append({"type": "text", "text": f"Photo: {'attached' if row['has_photo'] else 'none'}. Note: \"{row['note'] or ''}\""})
        messages = [{"role": "system", "content": CHECK_PROMPT}, {"role": "user", "content": content}]
        try:
            try:
                text = local_llm.default.chat(messages, max_tokens=200, temperature=0.1, timeout=AGENT_TIMEOUT)
            except Exception as e:  # noqa: BLE001
                if "429" not in str(e):
                    raise
                # the gateway allows 3 requests at once and the flood watch shares it: one more try after a moment
                time.sleep(4)
                text = local_llm.default.chat(messages, max_tokens=200, temperature=0.1, timeout=AGENT_TIMEOUT)
            start, end = text.find("{"), text.rfind("}")
            v = json.loads(text[start:end + 1])
        except Exception as e:  # noqa: BLE001 - endpoint busy or down: the worker tries again
            print(f"[UserReports] check of {rid} failed: {type(e).__name__}: {str(e)[:120]}")
            return "pending"
        level = str(v.get("level") or "none").lower()
        ok = v.get("fit") is True and (v.get("flood") is True or not row["has_photo"])
        status = "published" if ok else "rejected"
        self._set(rid, status=status, ai_level=level if level in LEVEL_TH else "none", ai_note=str(v.get("note_th") or "")[:200])
        if status == "rejected" and row["has_photo"]:
            try:
                os.remove(self.photo_path(rid))
            except OSError:
                pass
        return status

    def start(self):
        threading.Thread(target=self._retry_loop, daemon=True, name="user-reports").start()

    def _retry_loop(self):
        while True:
            time.sleep(RETRY_SECONDS)
            try:
                with self._db() as conn:
                    ids = [r[0] for r in conn.execute("SELECT id FROM user_flood_reports WHERE status = 'pending' AND ts > ?",
                                                      (int(time.time() - SHOW_HOURS * 3600),))]
                for rid in ids:
                    if self._check(rid) == "pending":
                        break   # the model is still not answering: wait for the next round
            except Exception as e:  # noqa: BLE001
                print(f"[UserReports] retry failed: {e}")

    # ------------------------------------------------------------ out
    def recent(self, hours=None):
        since = int(time.time() - (hours or SHOW_HOURS) * 3600)
        with self._db() as conn:
            rows = conn.execute("SELECT * FROM user_flood_reports WHERE status = 'published' AND ts > ? ORDER BY ts DESC",
                                (since,)).fetchall()
        items = [{"id": r["id"], "ts": r["ts"], "lat": r["lat"], "lng": r["lng"], "depth": r["depth"],
                  "depth_th": DEPTHS[r["depth"]][0], "depth_cm": DEPTHS[r["depth"]][1], "note": hide_contacts(r["note"] or ""),
                  "province": r["province"], "district": r["district"],
                  "photo": f"/api/flood/user-reports/{r['id']}/photo" if r["has_photo"] else None,
                  "ai_level": r["ai_level"], "ai_level_th": LEVEL_TH.get(r["ai_level"] or ""), "ai_note": r["ai_note"] or ""}
                 for r in rows]
        return {"hours": hours or SHOW_HOURS, "total": len(items), "items": items,
                "depths": {k: {"label": v[0], "cm": v[1]} for k, v in DEPTHS.items()}}

    def published_photo(self, rid):
        """Path of a published report's photo, or None."""
        try:
            path = self.photo_path(rid)
        except ValueError:
            return None
        with self._db() as conn:
            row = conn.execute("SELECT status FROM user_flood_reports WHERE id = ?", (rid,)).fetchone()
        return path if row and row["status"] == "published" and os.path.exists(path) else None

    def delete(self, rid):
        if not _ID.fullmatch(str(rid)):
            return False
        self._set(rid, status="deleted")
        try:
            os.remove(self.photo_path(rid))
        except OSError:
            pass
        return True
