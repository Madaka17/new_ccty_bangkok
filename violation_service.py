"""
Traffic-rule violations from the live AI camera: wrong-way driving and riders without a helmet.

Wrong way (ย้อนศร)
    Every camera is fixed, so each part of the frame has one normal direction of travel. The
    monitor learns it: the frame is split into a grid and each cell keeps a running sum of the
    unit motion vectors of vehicles that crossed it. Once a cell has seen enough traffic that
    agrees (count >= FLOW_MIN_COUNT and |mean vector| >= FLOW_MIN_AGREE) it is "known". A vehicle
    whose own path runs against the known direction of the cells it crosses (cos < -0.5) for
    WRONG_WAY_MIN_DIST box-heights and WRONG_WAY_MIN_S seconds is a wrong-way violation.
    Flow fields persist in cache/flow/<camid>.json so a camera does not relearn after a restart.

No helmet (ไม่สวมหมวกกันน็อก)
    COCO YOLO has no helmet class and the riders are 20-60 px tall on these feeds, so a crop of
    each motorcycle (rider merged with the bike by VehicleTracker) is sent once per track to the
    vision model already used for incidents (Gemini, else Claude). Only tracks at least
    HELMET_MIN_H px tall are checked, at most one crop per camera every HELMET_COOLDOWN seconds
    and HELMET_MAX_PER_HOUR per hour, so the API budget stays small. With no provider configured
    helmet checks are simply off; wrong-way detection needs no API.

Both go to the `violations` table in vehicle_counts.db with a JPEG evidence crop and are served by
/api/ai/violations. This is an assistive log, not an enforcement record: confidence values and
the evidence image are kept so every entry can be checked by a person.
"""
import base64
import json
import math
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
FLOW_DIR = os.path.join(DATA_DIR, "cache", "flow")
EVIDENCE_DIR = os.path.join(DATA_DIR, "cache", "violations")
# Long-term copy of every evidence image on the data drive (same drive as the BMA CSV archive):
#   D:/Data/violations/<YYYY-MM-DD>/<kind>/<camid>_<HHMMSS>.jpg  + violations.csv index
ARCHIVE_DIR = os.getenv("VIOLATION_ARCHIVE_DIR", os.path.join(os.getenv("BMA_DATA_DIR", r"D:\Data"), "violations"))

GRID_COLS, GRID_ROWS = 12, 9
FLOW_MIN_COUNT = 60          # motion samples a cell needs before its direction counts
FLOW_MIN_AGREE = 0.6         # |mean unit vector| (1 = every vehicle went the same way)
FLOW_SAVE_EVERY = 120.0      # seconds between flow-field saves
WRONG_WAY_COS = -0.5         # path direction vs cell direction: below this = against traffic
WRONG_WAY_MIN_DIST = 2.0     # box-heights travelled against the flow
WRONG_WAY_MIN_S = 1.5        # seconds of against-flow motion
WRONG_WAY_MIN_H = 14         # px; tiny far-away boxes jitter too much to judge
WRONG_WAY_MAX_STEP_S = 0.5   # a longer gap means ByteTrack re-attached the id (often to the car behind): restart
WRONG_WAY_MIN_FRAMES = 5     # consecutive against-flow frames before a violation counts
VIOLATION_COOLDOWN = 20.0    # seconds before the same camera logs the same kind again

HELMET_MIN_H = 36            # px rider+bike box height for a usable crop
HELMET_MIN_FRAMES = 3
HELMET_COOLDOWN = 15.0       # seconds between helmet checks on one camera
HELMET_MAX_PER_HOUR = 60
HELMET_MIN_CONF = 0.7
CROP_MARGIN = 0.35
# Local classifier from train_helmet.py. When present every rider crop is classified on the GPU
# (no API cooldown); the vision API is then only a second opinion on "no helmet" if
# HELMET_CONFIRM_API=1. Without the file, the API path above is used as before.
HELMET_CLS_PATH = os.getenv("HELMET_CLS", os.path.join(BASE_DIR, "helmet_cls.pt"))
HELMET_CLS_MIN_PROB = 0.8
HELMET_CONFIRM_API = os.getenv("HELMET_CONFIRM_API", "0") == "1"

KIND_TH = {"wrong_way": "ขับย้อนศร", "no_helmet": "ไม่สวมหมวกกันน็อก"}

HELMET_PROMPT = (
    "You check motorcycle riders in a traffic-camera crop from Bangkok. The crop shows one motorcycle "
    "(possibly with a rider and passengers). Answer ONLY with JSON: "
    '{"riders": <number of people on the motorcycle>, "no_helmet": <number of them clearly NOT wearing a helmet>, '
    '"confidence": <0..1 that your no_helmet count is right>, "note_th": "<one short Thai sentence>"}. '
    "If the image is too small, blurry or dark to see heads clearly, set no_helmet to 0 and confidence below 0.5. "
    "A cap, hood or hair is not a helmet."
)


_SAFE_ID = re.compile(r"[\w.-]{1,120}")   # \w as in _safe(): letters, digits, _


def _safe_id(s):
    """An id from a URL, usable in a file name: never a path (no separators, no drive, no ..)."""
    s = str(s)
    if not _SAFE_ID.fullmatch(s) or ".." in s:
        raise ValueError("bad id")
    return s


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-6 else (0.0, 0.0)


class FlowField:
    """Learned direction of travel per grid cell of one camera."""

    def __init__(self, camid):
        self.camid = camid
        self.sum = np.zeros((GRID_ROWS, GRID_COLS, 2), dtype=np.float64)
        self.count = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.float64)
        self.dirty = False
        self.last_save = time.time()
        self.load()

    @property
    def path(self):
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(self.camid))
        return os.path.join(FLOW_DIR, f"{safe}.json")

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            s, c = np.array(d["sum"]), np.array(d["count"])
            if s.shape == self.sum.shape and c.shape == self.count.shape:
                self.sum, self.count = s, c
        except (OSError, ValueError, KeyError):
            pass

    def save(self, force=False):
        if not self.dirty or (not force and time.time() - self.last_save < FLOW_SAVE_EVERY):
            return
        os.makedirs(FLOW_DIR, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"camid": self.camid, "sum": self.sum.tolist(), "count": self.count.tolist(),
                       "cols": GRID_COLS, "rows": GRID_ROWS, "saved": int(time.time())}, f)
        self.dirty = False
        self.last_save = time.time()

    def cell(self, x, y, w, h):
        return min(GRID_ROWS - 1, max(0, int(y * GRID_ROWS / h))), min(GRID_COLS - 1, max(0, int(x * GRID_COLS / w)))

    def add(self, x, y, w, h, ux, uy, weight=1.0):
        r, c = self.cell(x, y, w, h)
        self.sum[r, c] += (ux * weight, uy * weight)
        self.count[r, c] += weight
        self.dirty = True

    def direction(self, x, y, w, h):
        """(ux, uy) of the known flow at this point, or None while the cell is still learning."""
        r, c = self.cell(x, y, w, h)
        n = self.count[r, c]
        if n < FLOW_MIN_COUNT:
            return None
        mx, my = self.sum[r, c] / n
        agree = math.hypot(mx, my)
        if agree < FLOW_MIN_AGREE:
            return None
        return mx / agree, my / agree

    def summary(self):
        known = int(((self.count >= FLOW_MIN_COUNT) & (np.linalg.norm(self.sum, axis=2) / np.maximum(self.count, 1) >= FLOW_MIN_AGREE)).sum())
        # "active": cells vehicles actually cross; sky / pillars / verges never get there, so
        # known / active is the learning progress over the drivable area
        active = int((self.count >= 5).sum())
        return {"cells": GRID_ROWS * GRID_COLS, "active": active, "known": known, "samples": int(self.count.sum())}


class ViolationMonitor:
    def __init__(self, db_path, vision=None, cameras_by_id=lambda: {}):
        """vision: object with .provider/.client and _ask_* like IncidentManager (or None)."""
        self.db_path = db_path
        self.vision = vision
        self.cameras_by_id = cameras_by_id
        self.lock = threading.Lock()
        self.flows = {}
        # per camera: track_id -> state
        self._tracks = defaultdict(dict)
        self._last_logged = {}          # (camid, kind) -> ts
        self._helmet_last = {}          # camid -> ts
        self._helmet_calls = []
        self.flagged = defaultdict(dict)   # camid -> {track_id: kind} for the overlay
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        self._init_db()
        self.helmet_cls = None
        self._cls_lock = threading.Lock()
        if os.path.exists(HELMET_CLS_PATH):
            try:
                from ultralytics import YOLO
                self.helmet_cls = YOLO(HELMET_CLS_PATH)
                self.helmet_cls(np.zeros((160, 160, 3), dtype=np.uint8), verbose=False)  # warm up
                print(f"[Violation] helmet classifier loaded: {HELMET_CLS_PATH} {self.helmet_cls.names}")
            except Exception as e:  # noqa: BLE001
                print(f"[Violation] helmet classifier failed to load: {e}")
                self.helmet_cls = None

    # ------------------------------------------------------------ storage
    def _init_db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id          TEXT PRIMARY KEY,
                ts          INTEGER NOT NULL,
                camid       TEXT NOT NULL,
                title       TEXT,
                kind        TEXT NOT NULL,      -- wrong_way | no_helmet
                confidence  REAL,
                description TEXT,
                track_id    INTEGER,
                latitude    REAL,
                longitude   REAL,
                image       TEXT,
                archive     TEXT               -- copy on the data drive (D:/Data/violations), if written
            )""")
        try:
            conn.execute("ALTER TABLE violations ADD COLUMN archive TEXT")
        except sqlite3.OperationalError:
            pass  # column already there
        conn.execute("CREATE INDEX IF NOT EXISTS violations_ts ON violations(ts)")
        conn.commit()
        conn.close()

    def _archive(self, vid, ts, camid, title, kind, confidence, description, image_bgr):
        """Copy the evidence to the data drive and append one CSV row. Best effort: a missing
        drive must never stop detection."""
        try:
            import csv
            from datetime import datetime
            dt = datetime.fromtimestamp(ts)
            day_dir = os.path.join(ARCHIVE_DIR, dt.strftime("%Y-%m-%d"), kind)
            os.makedirs(day_dir, exist_ok=True)
            safe_cam = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(camid))
            out = os.path.join(day_dir, f"{safe_cam}_{dt.strftime('%H%M%S')}.jpg")
            # cv2.imwrite cannot take non-ASCII paths on Windows; encode then write bytes
            ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                return None
            with open(out, "wb") as f:
                f.write(buf.tobytes())
            index = os.path.join(ARCHIVE_DIR, "violations.csv")
            new_file = not os.path.exists(index)
            with open(index, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["id", "datetime", "camid", "camera", "kind", "kind_th", "confidence", "description", "image"])
                w.writerow([vid, dt.strftime("%Y-%m-%d %H:%M:%S"), camid, title, kind, KIND_TH.get(kind, kind),
                            round(float(confidence), 2), description, out])
            return out
        except OSError as e:
            print(f"[Violation] archive to {ARCHIVE_DIR} failed: {e}")
            return None

    def _log(self, camid, title, kind, confidence, description, track_id, image_bgr):
        now = time.time()
        key = (camid, kind)
        if now - self._last_logged.get(key, 0) < VIOLATION_COOLDOWN:
            return None
        self._last_logged[key] = now
        vid = f"{camid}-{kind}-{int(now)}"
        img_path = os.path.join(EVIDENCE_DIR, f"{vid}.jpg")
        cv2.imwrite(img_path, image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        archived = self._archive(vid, now, camid, title, kind, confidence, description, image_bgr)
        cam = self.cameras_by_id().get(camid, {})
        row = (vid, int(now), camid, title, kind, round(float(confidence), 2), description, int(track_id),
               cam.get("latitude"), cam.get("longitude"), f"/api/ai/violations/{vid}/image", archived)
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("INSERT OR REPLACE INTO violations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", row)
            conn.commit()
            conn.close()
        print(f"[Violation] {KIND_TH.get(kind, kind)} at {title} (conf {confidence:.2f}): {description}"
              + (f" -> {archived}" if archived else ""))
        return vid

    def recent(self, hours=24, camid=None, kind=None, limit=200):
        q = "SELECT * FROM violations WHERE ts >= ?"
        args = [int(time.time() - hours * 3600)]
        if camid:
            q += " AND camid = ?"
            args.append(camid)
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute(q, args)]
            counts = {k: n for k, n in conn.execute(
                "SELECT kind, COUNT(*) FROM violations WHERE ts >= ? GROUP BY kind", (args[0],))}
            conn.close()
        for r in rows:
            r["kind_th"] = KIND_TH.get(r["kind"], r["kind"])
        return {"updated": int(time.time()), "hours": hours, "counts": counts, "items": rows,
                "helmet_checks": self.helmet_enabled(), "helmet_mode": self.helmet_mode(),
                "archive_dir": ARCHIVE_DIR, "archive_ok": os.path.isdir(ARCHIVE_DIR)}

    def image_path(self, vid):
        p = os.path.join(EVIDENCE_DIR, f"{_safe_id(vid)}.jpg")
        return p if os.path.exists(p) else None

    def status(self, camid=None):
        out = {"helmet_checks": self.helmet_enabled(), "helmet_mode": self.helmet_mode(), "archive_dir": ARCHIVE_DIR,
               "archive_ok": os.path.isdir(os.path.dirname(ARCHIVE_DIR.rstrip("/\\"))), "cameras": {}}
        for cid, fl in self.flows.items():
            if camid and cid != camid:
                continue
            out["cameras"][cid] = fl.summary()
        return out

    # ------------------------------------------------------------ per-frame hook
    def observe(self, camid, title, tracker, frame, dets, now):
        """Call once per analysed frame with the tracker output. Returns {track_id: kind} to overlay."""
        h, w = frame.shape[:2]
        flow = self.flows.get(camid)
        if flow is None:
            flow = self.flows[camid] = FlowField(camid)
        states = self._tracks[camid]
        flagged = {}
        seen = set()

        for cls_id, conf, x1, y1, x2, y2, tid in dets:
            if tid < 0:
                continue
            seen.add(tid)
            tr = tracker._tracks.get(tid)
            if not tr:
                continue
            cx, cy, bh = (x1 + x2) / 2.0, (y1 + y2) / 2.0, max(1.0, y2 - y1)
            st = states.get(tid)
            if st is None:
                st = states[tid] = {"cls": cls_id, "prev": (now, cx, cy), "against_s": 0.0, "against_d": 0.0, "against_n": 0,
                                    "frames": 0, "helmet_done": False, "kind": None, "t": now}
            st["t"] = now
            st["frames"] += 1
            pt, px, py = st["prev"]
            dt = now - pt
            if dt <= 0:
                continue
            dx, dy = cx - px, cy - py
            step = math.hypot(dx, dy)
            st["prev"] = (now, cx, cy)
            if dt > WRONG_WAY_MAX_STEP_S:
                # Track was lost and re-found: the jump is an id hand-over, not motion
                st["against_s"] = st["against_d"] = 0.0
                st["against_n"] = 0
                continue
            speed = tr.get("speed")
            moving = speed is not None and speed >= tracker.MOVING_SPEED and step >= 2.0

            # Learn the flow from vehicles that are clearly moving, then judge this step against it
            if moving and bh >= WRONG_WAY_MIN_H:
                ux, uy = _unit(dx, dy)
                known = flow.direction(cx, cy, w, h)
                if known is not None:
                    cos = ux * known[0] + uy * known[1]
                    if cos < WRONG_WAY_COS:
                        st["against_s"] += dt
                        st["against_d"] += step / bh
                        st["against_n"] = st.get("against_n", 0) + 1
                    else:
                        st["against_s"] = max(0.0, st["against_s"] - dt)
                        st["against_d"] = max(0.0, st["against_d"] - step / bh)
                        st["against_n"] = 0
                    # against-flow motion must not teach the field
                    if cos > 0:
                        flow.add(cx, cy, w, h, ux, uy)
                else:
                    flow.add(cx, cy, w, h, ux, uy)
                if (st["kind"] is None and st["against_s"] >= WRONG_WAY_MIN_S and st["against_d"] >= WRONG_WAY_MIN_DIST
                        and st.get("against_n", 0) >= WRONG_WAY_MIN_FRAMES):
                    st["kind"] = "wrong_way"
                    ev = frame.copy()
                    cv2.rectangle(ev, (x1, y1), (x2, y2), (60, 60, 230), 3)
                    self._log(camid, title, "wrong_way", min(0.95, 0.6 + 0.1 * st["against_d"]),
                              f"วิ่งสวนทิศทางจราจร {st['against_d']:.1f} ช่วงตัวรถ นาน {st['against_s']:.1f} วินาที",
                              tid, ev)
            if st["kind"]:
                flagged[tid] = st["kind"]

            # Helmet: one vision check per motorcycle track that is big enough and has a rider on it
            # (parked bikes with nobody on board would only burn the per-camera cooldown)
            if (cls_id in (1, 3) and not st["helmet_done"] and st["frames"] >= HELMET_MIN_FRAMES and bh >= HELMET_MIN_H
                    and tid in getattr(tracker, "riders", ())):
                st["helmet_done"] = True
                self._maybe_check_helmet(camid, title, tid, frame, (x1, y1, x2, y2), now)

        # Forget tracks that left
        for tid in [t for t, s in states.items() if now - s["t"] > 10.0]:
            del states[tid]
        with self.lock:
            self.flagged[camid] = dict(flagged, **{t: k for t, k in self.flagged.get(camid, {}).items() if t in seen and t not in flagged})
        flow.save()
        return flagged

    # ------------------------------------------------------------ helmet check
    def helmet_enabled(self):
        return self.helmet_cls is not None or bool(self.vision and getattr(self.vision, "client", None))

    def helmet_mode(self):
        if self.helmet_cls is not None:
            return "classifier+api" if HELMET_CONFIRM_API and self.vision and getattr(self.vision, "client", None) else "classifier"
        return "api" if self.helmet_enabled() else "off"

    def _helmet_budget_ok(self, camid, now):
        if self.helmet_cls is not None:
            return True   # local model: every rider, no cooldown
        if not self.helmet_enabled():
            return False
        if now - self._helmet_last.get(camid, 0) < HELMET_COOLDOWN:
            return False
        self._helmet_calls = [t for t in self._helmet_calls if now - t < 3600]
        return len(self._helmet_calls) < HELMET_MAX_PER_HOUR

    def _maybe_check_helmet(self, camid, title, tid, frame, box, now):
        if not self._helmet_budget_ok(camid, now):
            return
        if self.helmet_cls is None:
            self._helmet_last[camid] = now
            self._helmet_calls.append(now)
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box
        mx, my = int((x2 - x1) * CROP_MARGIN), int((y2 - y1) * CROP_MARGIN)
        cx1, cy1, cx2, cy2 = max(0, x1 - mx), max(0, y1 - my * 2), min(w, x2 + mx), min(h, y2 + my)
        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return
        # Upscale small crops so the model gets something to look at
        scale = max(1.0, 256.0 / max(crop.shape[:2]))
        if scale > 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        if self.helmet_cls is not None:
            self._helmet_classify(camid, title, tid, crop, now)
            return
        jpeg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
        threading.Thread(target=self._helmet_verdict, args=(camid, title, tid, jpeg, crop), daemon=True).start()

    def _helmet_classify(self, camid, title, tid, crop, now):
        """Local classifier on the rider crop; optional API confirmation of a no-helmet verdict."""
        try:
            with self._cls_lock:
                r = self.helmet_cls(crop, imgsz=160, verbose=False)[0]
            names = r.names
            probs = r.probs
            top = int(probs.top1)
            p = float(probs.top1conf)
            if names[top] != "no_helmet" or p < HELMET_CLS_MIN_PROB:
                return
            if HELMET_CONFIRM_API and self.vision and getattr(self.vision, "client", None)                     and now - self._helmet_last.get(camid, 0) >= HELMET_COOLDOWN:
                self._helmet_last[camid] = now
                self._helmet_calls.append(now)
                jpeg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
                threading.Thread(target=self._helmet_verdict, args=(camid, title, tid, jpeg, crop), daemon=True).start()
                return
            self._log(camid, title, "no_helmet", p, f"ผู้ขับขี่ไม่สวมหมวกกันน็อก (โมเดลจำแนก {p:.0%})", tid, crop)
            with self.lock:
                st = self._tracks[camid].get(tid)
                if st:
                    st["kind"] = st["kind"] or "no_helmet"
                self.flagged[camid][tid] = self.flagged[camid].get(tid) or "no_helmet"
        except Exception as e:  # noqa: BLE001
            print(f"[Violation] helmet classifier failed at {title}: {e}")

    def _helmet_verdict(self, camid, title, tid, jpeg, crop):
        try:
            text = self._ask(jpeg, f"Camera: {title}. Crop of one motorcycle from the live feed.")
            start, end = text.find("{"), text.rfind("}")
            v = json.loads(text[start:end + 1]) if start >= 0 and end > start else None
            if not v:
                return
            riders, bad, conf = int(v.get("riders", 0)), int(v.get("no_helmet", 0)), float(v.get("confidence", 0))
            print(f"[Violation] helmet check {title} track {tid}: riders {riders}, no helmet {bad}, conf {conf:.2f}")
            if bad > 0 and conf >= HELMET_MIN_CONF:
                desc = v.get("note_th") or f"ผู้ขับขี่/ซ้อน {bad} จาก {riders} คน ไม่สวมหมวกกันน็อก"
                self._log(camid, title, "no_helmet", conf, desc, tid, crop)
                with self.lock:
                    st = self._tracks[camid].get(tid)
                    if st:
                        st["kind"] = st["kind"] or "no_helmet"
                    self.flagged[camid][tid] = self.flagged[camid].get(tid) or "no_helmet"
        except Exception as e:  # noqa: BLE001 - vision call is best effort
            print(f"[Violation] helmet check failed at {title}: {e}")

    def _ask(self, jpeg, context):
        vis = self.vision
        if vis.provider == "gemini":
            from google.genai import types as genai_types
            resp = vis.client.models.generate_content(
                model=os.environ.get("GEMINI_VISION_MODEL", "gemini-3.6-flash"),
                contents=[genai_types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), genai_types.Part(text=context)],
                config=genai_types.GenerateContentConfig(system_instruction=HELMET_PROMPT, temperature=0.1,
                                                         max_output_tokens=300, response_mime_type="application/json"),
            )
            return (resp.text or "").strip()
        response = vis.client.messages.create(
            model=os.environ.get("CLAUDE_VISION_MODEL", "claude-opus-5-5"),
            output_config={"effort": "low"},
            max_tokens=200,
            system=HELMET_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(jpeg).decode("ascii")}},
                {"type": "text", "text": context},
            ]}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()
