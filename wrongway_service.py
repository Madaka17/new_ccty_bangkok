"""
Wrong-way (ย้อนศร) patrol over every BMA camera, from single snapshots.

The BMA site serves one frame per camera every few minutes, so direction cannot come from motion
(that is what ViolationMonitor does on the live HLS camera). Instead the trained heading detector
(wrongway_det.pt from local/pipeline/train_wrongway_det.py, YOLO26x with classes
<car|moto>_<toward|away|left|right>) reads which way each vehicle faces, and each camera learns
which heading is normal where:

    snapshot -> heading detector -> every confident box votes into a 12x9 grid cell (the cell under
    the vehicle's road contact point) of the camera's HeadingField, persisted in cache/heading/<camid>.json
    -> a cell is "known" once it has HEADING_MIN_VOTES votes with HEADING_MIN_AGREE agreement
    -> a vehicle whose heading is the exact opposite of its known cell (toward<->away, left<->right),
       not straddling a cell of its own heading, is a candidate
    -> the frame with a red box + a green arrow for the lane's normal direction goes to the vision
       agent (Gemini, else Claude): JSON {wrong_way, confidence, note_th}
    -> verdict wrong_way: frame + crop to <WRONGWAY_ARCHIVE_DIR>/<YYYY-MM-DD>/ and one row in wrongway.csv

Everything is in the `wrongway_checks` table of vehicle_counts.db and served by /api/wrongway/*.
Budget: WRONGWAY_MAX_PER_HOUR agent calls, WRONGWAY_PER_CAM candidates per camera per cycle, one
visit per camera every WRONGWAY_COOLDOWN seconds. Assistive log, not an enforcement record: a
person checks the evidence (a parked car facing the wrong way looks the same to a still image).
"""
import base64
import csv
import json
import os
import queue
import sqlite3
import threading
import time
from datetime import datetime

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
CACHE_DIR = os.path.join(DATA_DIR, "cache", "wrongway")
FIELD_DIR = os.path.join(DATA_DIR, "cache", "heading")
ARCHIVE_DIR = os.getenv("WRONGWAY_ARCHIVE_DIR", os.path.join(os.getenv("BMA_DATA_DIR", r"D:\Data"), "wrongway"))
DET_PATH = os.getenv("WRONGWAY_DET", os.path.join(BASE_DIR, "wrongway_det.pt"))
if not os.path.isabs(DET_PATH):
    DET_PATH = os.path.join(BASE_DIR, DET_PATH)
AGENT_MODEL = os.getenv("WRONGWAY_AGENT_MODEL", os.getenv("GEMINI_VISION_MODEL", "gemini-3.1-flash-lite"))
FALLBACK_MODEL = os.getenv("GEMINI_VISION_FALLBACK", "gemini-3.1-flash-lite")
AGENT_TIMEOUT_MS = 40000

HEADINGS = ["toward", "away", "left", "right"]
OPPOSITE = {0: 1, 1: 0, 2: 3, 3: 2}
HEADING_TH = {"toward": "วิ่งเข้าหากล้อง", "away": "วิ่งออกจากกล้อง", "left": "วิ่งไปทางซ้าย", "right": "วิ่งไปทางขวา"}
GRID_COLS, GRID_ROWS = 12, 9
HEADING_MIN_VOTES = int(os.getenv("WRONGWAY_MIN_VOTES", "40"))   # detections a cell needs before it judges
HEADING_MIN_AGREE = 0.85
FIELD_SAVE_EVERY = 120.0
DET_IMGSZ = 640
VOTE_CONF = 0.5                   # detections that teach the field
CAND_CONF = float(os.getenv("WRONGWAY_MIN_CONF", "0.6"))   # detections that may be flagged
MIN_BOX_H = int(os.getenv("WRONGWAY_MIN_H", "16"))
PER_CAM = int(os.getenv("WRONGWAY_PER_CAM", "2"))
COOLDOWN = float(os.getenv("WRONGWAY_COOLDOWN", "120"))
MAX_PER_HOUR = int(os.getenv("WRONGWAY_MAX_PER_HOUR", "120"))
AGENT_MIN_CONF = 0.7
WORKERS = int(os.getenv("WRONGWAY_WORKERS", "3"))
AGENT_BACKOFF_S = 600
RATE_BACKOFF_S = 60
CACHE_KEEP_H = 48
CROP_MARGIN = 0.5
CROP_MIN_SIDE = 320
VERDICT_TH = {"pending": "รอตรวจ", "wrong_way": "ขับย้อนศร", "ok": "ไม่ย้อนศร", "unclear": "มองไม่ชัด", "error": "ตรวจไม่สำเร็จ"}

AGENT_PROMPT = (
    "You are the wrong-way-driving agent of the Bangkok traffic control room. You receive one frame from a "
    "low-resolution street CCTV camera. One vehicle is marked with a RED box. A GREEN arrow next to it shows "
    "the normal direction of travel for that lane, learned from the vehicles this camera usually sees there. "
    "Decide whether the boxed vehicle is driving AGAINST the traffic direction of its lane (ย้อนศร). Use the "
    "vehicle's orientation (which way its front faces), the other vehicles in the same lane, road markings and "
    "arrows painted on the road. Answer ONLY with JSON: "
    '{"wrong_way": <true|false>, "confidence": <0..1>, "moving": <true|false|null>, "note_th": "<one short Thai sentence>"}. '
    "Rules: a parked vehicle, a vehicle turning or crossing at an intersection, a vehicle on the opposite "
    "carriageway of a divided road, or a motorcycle on the sidewalk are NOT wrong_way. If the image is too small, "
    "blurred or dark to tell, answer wrong_way false with confidence below 0.5. Never guess."
)


def _safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))


def _write_jpeg(path, img, q=90):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        return False
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return True


def _fingerprint(frame):
    small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (24, 18), interpolation=cv2.INTER_AREA)
    return small.tobytes()


def _same_scene(a, b, tol=6):
    if a is None or b is None or len(a) != len(b):
        return False
    return int(np.abs(np.frombuffer(a, np.uint8).astype(np.int16) - np.frombuffer(b, np.uint8).astype(np.int16)).mean()) <= tol


def _iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if not inter:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


class HeadingField:
    """Votes per grid cell per heading for one camera, persisted in cache/heading/<camid>.json."""

    def __init__(self, camid):
        self.camid = camid
        self.votes = np.zeros((GRID_ROWS, GRID_COLS, 4), dtype=np.float64)
        self.dirty = False
        self.last_save = time.time()
        self.load()

    @property
    def path(self):
        return os.path.join(FIELD_DIR, f"{_safe(self.camid)}.json")

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                v = np.array(json.load(f)["votes"], dtype=np.float64)
            if v.shape == self.votes.shape:
                self.votes = v
        except (OSError, ValueError, KeyError):
            pass

    def save(self, force=False):
        if not self.dirty or (not force and time.time() - self.last_save < FIELD_SAVE_EVERY):
            return
        os.makedirs(FIELD_DIR, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"camid": self.camid, "cols": GRID_COLS, "rows": GRID_ROWS, "votes": self.votes.tolist(),
                       "saved": int(time.time())}, f)
        self.dirty = False
        self.last_save = time.time()

    @staticmethod
    def cell(x, y, w, h):
        return min(GRID_ROWS - 1, max(0, int(y * GRID_ROWS / h))), min(GRID_COLS - 1, max(0, int(x * GRID_COLS / w)))

    def add(self, x, y, w, h, heading, weight=1.0):
        r, c = self.cell(x, y, w, h)
        self.votes[r, c, heading] += weight
        self.dirty = True

    def known(self, x, y, w, h):
        """Dominant heading of the cell under (x, y), or None while it is learning / mixed."""
        r, c = self.cell(x, y, w, h)
        v = self.votes[r, c]
        n = v.sum()
        if n < HEADING_MIN_VOTES:
            return None
        best = int(v.argmax())
        return best if v[best] >= HEADING_MIN_AGREE * n else None

    def summary(self):
        n = self.votes.sum(axis=2)
        dom = self.votes.max(axis=2)
        known = int(((n >= HEADING_MIN_VOTES) & (dom >= HEADING_MIN_AGREE * np.maximum(n, 1))).sum())
        active = int((n >= 5).sum())
        return {"cells": GRID_ROWS * GRID_COLS, "active": active, "known": known, "votes": int(n.sum())}

    def cells(self):
        """Known cells for the overlay: [{r, c, heading, n}]."""
        out = []
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                v = self.votes[r, c]
                n = v.sum()
                if n >= HEADING_MIN_VOTES and v.max() >= HEADING_MIN_AGREE * n:
                    out.append({"r": r, "c": c, "heading": HEADINGS[int(v.argmax())], "n": int(n)})
        return out


class WrongWayPatrol:
    def __init__(self, db_path, vision=None, scanner=None):
        """vision: IncidentManager-like object with .provider/.client. scanner: BmaScanner (for check_now)."""
        self.db_path = db_path
        self.vision = vision
        self.scanner = scanner
        self.lock = threading.Lock()
        self.fields = {}
        self._last_visit = {}
        self._last_frame = {}
        self._last_boxes = {}
        self._calls = []
        self._queue = queue.Queue()
        self.last_check = 0
        self.agent_error = None
        self.frames_seen = 0
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._init_db()
        self.det = None
        self.det_names = {}
        self._det_lock = threading.Lock()
        if os.path.exists(DET_PATH):
            try:
                from ultralytics import YOLO
                self.det = YOLO(DET_PATH)
                self.det(np.zeros((288, 352, 3), dtype=np.uint8), imgsz=DET_IMGSZ, verbose=False)
                self.det_names = {int(k): v for k, v in self.det.names.items()}
                print(f"[WrongWay] heading detector loaded: {DET_PATH} {list(self.det_names.values())}")
            except Exception as e:  # noqa: BLE001
                print(f"[WrongWay] heading detector failed to load: {e}")
                self.det = None
        else:
            print(f"[WrongWay] no heading detector at {DET_PATH}: patrol off (train it with local/pipeline/wrongway_pipeline.bat)")
        for _ in range(WORKERS):
            threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        threading.Thread(target=self._resume_pending, daemon=True).start()

    # ------------------------------------------------------------ storage
    def _init_db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wrongway_checks (
                id          TEXT PRIMARY KEY,
                ts          INTEGER NOT NULL,
                camid       TEXT NOT NULL,
                title       TEXT,
                district    TEXT,
                box         TEXT,               -- [x1,y1,x2,y2] on the frame
                heading     TEXT,               -- what the detector saw
                expected    TEXT,               -- what the lane normally does
                det_conf    REAL,
                verdict     TEXT NOT NULL,      -- pending | wrong_way | ok | unclear | error
                source      TEXT,               -- local | gemini | claude
                confidence  REAL,
                note        TEXT,
                archive     TEXT
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS wrongway_checks_ts ON wrongway_checks(ts)")
        conn.commit()
        conn.close()

    def _db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _insert(self, row):
        with self.lock:
            conn = self._db()
            conn.execute("INSERT OR REPLACE INTO wrongway_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            conn.commit()
            conn.close()

    def _update(self, wid, **fields):
        keys = list(fields)
        with self.lock:
            conn = self._db()
            conn.execute(f"UPDATE wrongway_checks SET {', '.join(k + ' = ?' for k in keys)} WHERE id = ?",
                         [fields[k] for k in keys] + [wid])
            conn.commit()
            conn.close()

    @staticmethod
    def crop_path(wid):
        return os.path.join(CACHE_DIR, f"{wid}.jpg")

    @staticmethod
    def frame_path(wid):
        return os.path.join(CACHE_DIR, f"{wid}_frame.jpg")

    def provider(self):
        v = self.vision
        return getattr(v, "provider", None) if v and getattr(v, "client", None) else None

    def enabled(self):
        return self.det is not None

    # ------------------------------------------------------------ detector
    def _detect_headings(self, frame):
        """[(group, heading_idx, conf, x1, y1, x2, y2)] from the heading detector."""
        with self._det_lock:
            r = self.det(frame, imgsz=DET_IMGSZ, conf=0.25, iou=0.5, verbose=False)[0]
        out = []
        for (x1, y1, x2, y2), cf, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            name = self.det_names.get(int(c), "")
            group, _, head = name.partition("_")
            if head not in HEADINGS:
                continue
            out.append((group, HEADINGS.index(head), float(cf), int(x1), int(y1), int(x2), int(y2)))
        return out

    def field(self, camid):
        fl = self.fields.get(camid)
        if fl is None:
            fl = self.fields[camid] = HeadingField(camid)
        return fl

    # ------------------------------------------------------------ capture (called from the scanner)
    def observe(self, cam, frame, boxes=None, force=False):
        """Learn the camera's heading field from this snapshot and queue the vehicles that go against it."""
        if self.det is None:
            return []
        camid = str(cam.get("camid"))
        now = time.time()
        fp = _fingerprint(frame)
        if not force and _same_scene(fp, self._last_frame.get(camid)):
            return []          # frozen feed: same picture would vote twice and re-flag the same car
        self._last_frame[camid] = fp
        h, w = frame.shape[:2]
        dets = self._detect_headings(frame)
        self.frames_seen += 1
        fl = self.field(camid)
        cands = []
        for group, head, conf, x1, y1, x2, y2 in dets:
            bh = y2 - y1
            fx, fy = (x1 + x2) / 2.0, float(y2)
            known = fl.known(fx, fy, w, h)
            if conf >= VOTE_CONF and (known is None or known == head):
                # against-flow vehicles must not teach the field once the cell is known
                fl.add(fx, fy, w, h, head)
            if known is None or conf < CAND_CONF or bh < MIN_BOX_H or head != OPPOSITE[known]:
                continue
            # straddling a lane of its own heading (divided road, lane split at the cell edge): not a candidate
            if any(fl.known(px, fy, w, h) == head for px in (x1, x2)):
                continue
            cands.append((conf, group, head, known, (x1, y1, x2, y2)))
        fl.save()
        if not cands:
            return []
        if not force and now - self._last_visit.get(camid, 0) < COOLDOWN:
            return []
        prev = self._last_boxes.get(camid, [])
        cands = [c for c in cands if not any(_iou(c[4], pb) >= 0.5 for pb in prev)]
        if not cands:
            return []
        self._last_visit[camid] = now
        cands.sort(key=lambda c: -c[0])
        ids = []
        for n, (conf, group, head, known, box) in enumerate(cands[:PER_CAM]):
            wid = f"{_safe(camid)}-{int(now)}-{n}"
            crop, marked = self._evidence(frame, box, known)
            _write_jpeg(self.crop_path(wid), crop)
            _write_jpeg(self.frame_path(wid), marked, 88)
            self._insert((wid, int(now), camid, cam.get("title") or cam.get("short_title") or camid, cam.get("district"),
                          json.dumps(list(box)), HEADINGS[head], HEADINGS[known], round(conf, 3),
                          "pending", None, None, None, None))
            self._queue.put((wid, camid, cam, crop, marked))
            ids.append(wid)
        self._last_boxes[camid] = [c[4] for c in cands[:PER_CAM]]
        return ids

    def _evidence(self, frame, box, expected):
        """(crop upscaled, frame with red box + green arrow of the lane's normal direction)."""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box
        mx, my = int((x2 - x1) * CROP_MARGIN), int((y2 - y1) * CROP_MARGIN)
        crop = frame[max(0, y1 - my):min(h, y2 + my), max(0, x1 - mx):min(w, x2 + mx)]
        if crop.size == 0:
            crop = frame[y1:y2, x1:x2]
        scale = max(1.0, CROP_MIN_SIDE / max(1, max(crop.shape[:2])))
        if scale > 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        marked = cv2.resize(frame, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC) if max(h, w) < 500 else frame.copy()
        s = marked.shape[1] / w
        X1, Y1, X2, Y2 = int(x1 * s), int(y1 * s), int(x2 * s), int(y2 * s)
        cv2.rectangle(marked, (X1, Y1), (X2, Y2), (0, 0, 255), 2)
        # arrow: 1.2 box heights long, drawn beside the box so it hides nothing
        L = max(24, int((Y2 - Y1) * 1.2))
        dx, dy = [(0, 1), (0, -1), (-1, 0), (1, 0)][expected]
        ax = X2 + 10 if X2 + 10 + L < marked.shape[1] else X1 - 10
        ay = (Y1 + Y2) // 2
        p0 = (int(ax - dx * L / 2), int(ay - dy * L / 2))
        p1 = (int(ax + dx * L / 2), int(ay + dy * L / 2))
        cv2.arrowedLine(marked, p0, p1, (0, 220, 0), 3, tipLength=0.35)
        return crop, marked

    def check_now(self, camid):
        """Fresh snapshot of one camera, judged regardless of cooldown."""
        if not self.scanner:
            return {"ok": False, "error": "no scanner"}
        if self.det is None:
            return {"ok": False, "error": "ไม่มีโมเดล wrongway_det.pt (เทรนก่อนด้วย local\\pipeline\\wrongway_pipeline.bat)"}
        cam = next((c for c in self.scanner.cameras if str(c.get("camid")) == str(camid)), None)
        if not cam:
            return {"ok": False, "error": "unknown camera"}
        raw = self.scanner.session.fetch_snapshot(str(camid), timeout=7.0)
        if not raw:
            return {"ok": False, "error": "camera offline"}
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"ok": False, "error": "bad image"}
        ids = self.observe(cam, img, force=True)
        fl = self.field(str(camid)).summary()
        if ids:
            msg = f"พบรถที่หันสวนทาง {len(ids)} คัน ส่งให้ AI ยืนยันแล้ว"
        elif fl["known"] == 0:
            msg = f"กล้องนี้ยังเรียนรู้ทิศทางไม่พอ ({fl['votes']} โหวต, ต้องมีช่องที่รู้ทิศก่อน) รอสแกนอีกสักพัก"
        else:
            msg = f"ไม่พบรถย้อนศรในภาพตอนนี้ (รู้ทิศแล้ว {fl['known']}/{fl['active']} ช่อง)"
        return {"ok": True, "camid": str(camid), "captures": ids, "field": fl, "message": msg}

    # ------------------------------------------------------------ analysis
    def _budget_ok(self, now):
        self._calls = [t for t in self._calls if now - t < 3600]
        if self.agent_error and now - self.agent_error["ts"] < self.agent_error.get("for", AGENT_BACKOFF_S):
            return False
        return len(self._calls) < MAX_PER_HOUR

    def _agent_reason(self, now):
        if self.agent_error and now - self.agent_error["ts"] < self.agent_error.get("for", AGENT_BACKOFF_S):
            return "AI agent หยุดชั่วคราว: " + self.agent_error["message"]
        return "เกินงบเรียก AI ต่อชั่วโมง"

    def _worker(self):
        while True:
            wid, camid, cam, crop, marked = self._queue.get()
            try:
                self._analyse(wid, camid, cam, crop, marked)
            except Exception as e:  # noqa: BLE001
                print(f"[WrongWay] check failed {wid}: {e}")
                self._update(wid, verdict="error", note=str(e)[:200])
            finally:
                self._queue.task_done()

    def _row(self, wid):
        with self.lock:
            conn = self._db()
            row = conn.execute("SELECT * FROM wrongway_checks WHERE id = ?", (wid,)).fetchone()
            conn.close()
        return self._decorate(dict(row)) if row else None

    def _decorate(self, r):
        r["verdict_th"] = VERDICT_TH.get(r["verdict"], r["verdict"])
        r["heading_th"] = HEADING_TH.get(r.get("heading"), r.get("heading"))
        r["expected_th"] = HEADING_TH.get(r.get("expected"), r.get("expected"))
        r["box"] = json.loads(r["box"]) if r.get("box") else None
        r["crop"], r["frame"] = f"/api/wrongway/{r['id']}/crop", f"/api/wrongway/{r['id']}/frame"
        return r

    def _analyse(self, wid, camid, cam, crop, marked, agent="auto"):
        """agent: auto (cloud when budget allows, else local verdict) | cloud (force) | local (detector only)."""
        now = time.time()
        row = self._row(wid) or {}
        det_conf = float(row.get("det_conf") or 0)
        local_note = (f"โมเดลในเครื่องเห็นรถ{HEADING_TH.get(row.get('heading'), '')} "
                      f"แต่ช่องทางนี้ปกติ{HEADING_TH.get(row.get('expected'), '')} ({det_conf:.0%})")
        provider = self.provider()
        if agent == "local" or not provider or (agent == "auto" and not self._budget_ok(now)):
            reason = "" if agent == "local" else (" · " + (self._agent_reason(now) if provider else "ไม่มี AI agent ยืนยัน"))
            self._settle_local(wid, camid, cam, crop, marked, det_conf, local_note + reason)
            self.last_check = int(now)
            return
        jpeg = cv2.imencode(".jpg", marked, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
        context = (f"Camera: {cam.get('title') or camid}, Bangkok. The boxed vehicle faces '{row.get('heading')}' "
                   f"while this lane normally goes '{row.get('expected')}' (local detector {det_conf:.0%}). "
                   "Directions are in image space: toward = down the image towards the camera, away = up.")
        self._calls.append(now)
        try:
            text = self._ask(jpeg, context)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "429" in msg or "RATE_LIMIT" in msg:
                self.agent_error = {"ts": now, "message": "ชนลิมิตต่อนาทีของ API", "for": RATE_BACKOFF_S}
            elif any(k in msg for k in ("402", "401", "400", "RESOURCE_EXHAUSTED", "credits", "API key")):
                short = "เครดิต/โควตา API หมด" if ("402" in msg or "credits" in msg or "RESOURCE_EXHAUSTED" in msg) else msg[:120]
                self.agent_error = {"ts": now, "message": short, "for": AGENT_BACKOFF_S}
            print(f"[WrongWay] cloud agent error: {msg[:160]}")
            self._settle_local(wid, camid, cam, crop, marked, det_conf, local_note + " · AI agent ไม่ตอบ: " + msg[:100])
            return
        self.agent_error = None
        self.last_check = int(now)
        start, end = text.find("{"), text.rfind("}")
        v = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
        wrong = bool(v.get("wrong_way"))
        conf = float(v.get("confidence", 0) or 0)
        note = (v.get("note_th") or "").strip()[:300]
        print(f"[WrongWay] {provider} · {cam.get('title') or camid}: wrong_way {wrong}, conf {conf:.2f}")
        if wrong and conf >= AGENT_MIN_CONF:
            self._finish_wrong_way(wid, camid, cam, crop, marked, conf, note, provider)
        elif not wrong and conf >= 0.5:
            self._update(wid, verdict="ok", source=provider, confidence=round(conf, 2), note=note)
        else:
            self._update(wid, verdict="unclear", source=provider, confidence=round(conf, 2), note=note)

    def _settle_local(self, wid, camid, cam, crop, marked, det_conf, note):
        """Detector-only verdict: the vehicle faces against a well-learned lane. Kept as wrong_way so it lands
        in the evidence list for a person; 'unclear' when the detector itself was not sure."""
        if det_conf >= 0.75:
            self._finish_wrong_way(wid, camid, cam, crop, marked, det_conf, note, "local")
        else:
            self._update(wid, verdict="unclear", source="local", confidence=round(det_conf, 2), note=note)

    def _finish_wrong_way(self, wid, camid, cam, crop, marked, conf, note, source):
        archived = self._archive(wid, camid, cam, crop, marked, conf, note)
        self._update(wid, verdict="wrong_way", source=source, confidence=round(conf, 2), note=note, archive=archived)
        print(f"[WrongWay] WRONG WAY at {cam.get('title') or camid} ({conf:.0%}, {source})" + (f" -> {archived}" if archived else ""))

    def _archive(self, wid, camid, cam, crop, marked, conf, note):
        try:
            try:
                ts = int(wid.rsplit("-", 2)[1])
            except (IndexError, ValueError):
                ts = time.time()
            dt = datetime.fromtimestamp(ts)
            day_dir = os.path.join(ARCHIVE_DIR, dt.strftime("%Y-%m-%d"))
            os.makedirs(day_dir, exist_ok=True)
            stem = os.path.join(day_dir, f"{_safe(camid)}_{dt.strftime('%H%M%S')}_{wid[-1]}")
            frame_out, crop_out = stem + ".jpg", stem + "_crop.jpg"
            banner = marked.copy()
            label = f"WRONG WAY {conf:.0%}  {dt.strftime('%Y-%m-%d %H:%M:%S')}"
            cv2.rectangle(banner, (0, 0), (banner.shape[1], 22), (0, 0, 0), -1)
            cv2.putText(banner, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            _write_jpeg(frame_out, banner, 92)
            _write_jpeg(crop_out, crop, 92)
            index = os.path.join(ARCHIVE_DIR, "wrongway.csv")
            new_file = not os.path.exists(index)
            with open(index, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["id", "datetime", "camid", "camera", "district", "confidence", "note", "frame", "crop"])
                w.writerow([wid, dt.strftime("%Y-%m-%d %H:%M:%S"), camid, cam.get("title") or "", cam.get("district") or "",
                            round(float(conf), 2), note, frame_out, crop_out])
            return frame_out
        except OSError as e:
            print(f"[WrongWay] archive to {ARCHIVE_DIR} failed: {e}")
            return None

    def _ask(self, jpeg, context):
        vis = self.vision
        if vis.provider == "gemini":
            from google.genai import types as genai_types
            for model in dict.fromkeys([AGENT_MODEL, FALLBACK_MODEL]):
                try:
                    resp = vis.client.models.generate_content(
                        model=model,
                        contents=[genai_types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), genai_types.Part(text=context)],
                        config=genai_types.GenerateContentConfig(system_instruction=AGENT_PROMPT, temperature=0.1,
                                                                 max_output_tokens=300, response_mime_type="application/json",
                                                                 http_options=genai_types.HttpOptions(timeout=AGENT_TIMEOUT_MS)),
                    )
                    return (resp.text or "").strip()
                except Exception as e:  # noqa: BLE001
                    if any(k in str(e) for k in ("503", "UNAVAILABLE", "504", "DEADLINE")):
                        continue
                    raise
            raise RuntimeError("503 Gemini overloaded on every model")
        response = vis.client.messages.create(
            model=os.environ.get("CLAUDE_VISION_MODEL", "claude-opus-5"),
            output_config={"effort": "low"},
            max_tokens=200,
            system=AGENT_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(jpeg).decode("ascii")}},
                {"type": "text", "text": context},
            ]}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    # ------------------------------------------------------------ reanalysis
    def reanalyse(self, wid, agent="cloud"):
        crop_p, frame_p = self.crop_path(wid), self.frame_path(wid)
        row = self._row(wid)
        if not row:
            return {"ok": False, "error": "ไม่พบรายการ"}
        if not os.path.exists(frame_p):
            return {"ok": False, "error": "ไม่มีภาพนี้ในแคชแล้ว"}
        if agent != "local" and not self.provider():
            return {"ok": False, "error": "ไม่มี API key ของ Gemini/Claude"}
        camid = row["camid"]
        cam = next((c for c in (self.scanner.cameras if self.scanner else []) if str(c.get("camid")) == camid), None) \
            or {"camid": camid, "title": row["title"], "district": row["district"]}
        marked = cv2.imdecode(np.fromfile(frame_p, np.uint8), cv2.IMREAD_COLOR)
        crop = cv2.imdecode(np.fromfile(crop_p, np.uint8), cv2.IMREAD_COLOR) if os.path.exists(crop_p) else marked
        try:
            self._analyse(wid, camid, cam, crop, marked, agent=agent)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200]}
        return {"ok": True, "item": self._row(wid)}

    def _resume_pending(self):
        time.sleep(20)
        with self.lock:
            conn = self._db()
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM wrongway_checks WHERE verdict = 'pending' AND ts >= ? ORDER BY ts DESC LIMIT 60",
                (int(time.time() - 6 * 3600),))]
            conn.close()
        for wid in [w for w in ids if os.path.exists(self.frame_path(w))]:
            self.reanalyse(wid, "cloud" if self.provider() else "local")

    def reanalyse_pending(self, agent="cloud", limit=40, hours=24):
        with self.lock:
            conn = self._db()
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM wrongway_checks WHERE ts >= ? AND verdict IN ('unclear','error','pending') ORDER BY ts DESC LIMIT ?",
                (int(time.time() - hours * 3600), limit))]
            conn.close()
        ids = [w for w in ids if os.path.exists(self.frame_path(w))]

        def run():
            for wid in ids:
                self.reanalyse(wid, agent)
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "queued": len(ids), "agent": agent}

    def dismiss(self, wid):
        """A person looked and it is not a violation (parked car, turning vehicle): keep the row as 'ok'."""
        if not self._row(wid):
            return {"ok": False, "error": "ไม่พบรายการ"}
        self._update(wid, verdict="ok", source="person", note="ผู้ดูแลตรวจแล้ว ไม่ใช่การย้อนศร")
        return {"ok": True, "item": self._row(wid)}

    # ------------------------------------------------------------ API
    def status(self):
        now = time.time()
        day0 = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        with self.lock:
            conn = self._db()
            today = {r["verdict"]: r["n"] for r in conn.execute(
                "SELECT verdict, COUNT(*) n FROM wrongway_checks WHERE ts >= ? GROUP BY verdict", (day0,))}
            total = conn.execute("SELECT COUNT(*) FROM wrongway_checks WHERE verdict = 'wrong_way'").fetchone()[0]
            conn.close()
        self._calls = [t for t in self._calls if now - t < 3600]
        learned = sum(1 for f in self.fields.values() if f.summary()["known"] > 0)
        return {
            "updated": int(now), "enabled": self.enabled(), "detector": os.path.basename(DET_PATH) if self.det is not None else None,
            "detector_path": DET_PATH, "agent": self.provider() or "off",
            "agent_model": AGENT_MODEL if self.provider() == "gemini"
            else (os.environ.get("CLAUDE_VISION_MODEL", "claude-opus-5") if self.provider() else None),
            "archive_dir": ARCHIVE_DIR, "archive_ok": os.path.isdir(os.path.dirname(ARCHIVE_DIR.rstrip("/\\"))),
            "calls_last_hour": len(self._calls), "calls_per_hour_max": MAX_PER_HOUR, "queue": self._queue.qsize(),
            "agent_error": (self.agent_error["message"] if self.agent_error and now - self.agent_error["ts"] < self.agent_error.get("for", AGENT_BACKOFF_S) else None),
            "last_check": self.last_check, "cooldown_s": COOLDOWN, "per_camera": PER_CAM, "min_votes": HEADING_MIN_VOTES,
            "frames_seen": self.frames_seen, "cameras_seen": len(self.fields), "cameras_learned": learned,
            "today": {"captures": sum(today.values()), "pending": today.get("pending", 0), "wrong_way": today.get("wrong_way", 0),
                      "ok": today.get("ok", 0), "unclear": today.get("unclear", 0) + today.get("error", 0)},
            "total_wrong_way": total,
        }

    def recent(self, hours=24, verdict=None, camid=None, limit=200):
        q, args = "SELECT * FROM wrongway_checks WHERE ts >= ?", [int(time.time() - hours * 3600)]
        if verdict:
            q += " AND verdict = ?"
            args.append(verdict)
        if camid:
            q += " AND camid = ?"
            args.append(str(camid))
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            conn = self._db()
            rows = [self._decorate(dict(r)) for r in conn.execute(q, args)]
            conn.close()
        return {"updated": int(time.time()), "hours": hours, "items": rows}

    def cameras(self):
        """Every BMA camera with how much of its heading field is learned and today's results."""
        day0 = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        with self.lock:
            conn = self._db()
            stats = {}
            for r in conn.execute("SELECT camid, verdict, COUNT(*) n, MAX(ts) last FROM wrongway_checks WHERE ts >= ? GROUP BY camid, verdict", (day0,)):
                s = stats.setdefault(r["camid"], {"captures": 0, "wrong_way": 0, "last": 0})
                s["captures"] += r["n"]
                if r["verdict"] == "wrong_way":
                    s["wrong_way"] += r["n"]
                s["last"] = max(s["last"], r["last"] or 0)
            conn.close()
        latest = {str(c.get("camid")): c for c in (self.scanner.db.get_all_latest() if self.scanner else [])}
        items = []
        for cam in (self.scanner.cameras if self.scanner else []):
            cid = str(cam.get("camid"))
            live = latest.get(cid, {})
            s = stats.get(cid, {"captures": 0, "wrong_way": 0, "last": 0})
            fl = self.fields.get(cid)
            fs = fl.summary() if fl else {"known": 0, "active": 0, "votes": 0}
            items.append({"camid": cid, "title": cam.get("title") or cam.get("short_title") or cid, "district": cam.get("district"),
                          "status": live.get("status") or "unknown", "total": live.get("total") or 0,
                          "known": fs["known"], "active": fs["active"], "votes": fs["votes"],
                          "captures": s["captures"], "wrong_way": s["wrong_way"], "last": s["last"]})
        items.sort(key=lambda c: (-c["wrong_way"], -c["captures"], -c["known"], -c["total"]))
        return {"updated": int(time.time()), "total": len(items), "items": items}

    def field_cells(self, camid):
        fl = self.fields.get(str(camid))
        if fl is None and os.path.exists(os.path.join(FIELD_DIR, f"{_safe(camid)}.json")):
            fl = self.field(str(camid))
        return {"camid": str(camid), "cols": GRID_COLS, "rows": GRID_ROWS, "min_votes": HEADING_MIN_VOTES,
                "summary": fl.summary() if fl else None, "cells": fl.cells() if fl else []}

    # ------------------------------------------------------------ housekeeping
    def _cleanup_loop(self):
        while True:
            time.sleep(1800)
            cutoff = time.time() - CACHE_KEEP_H * 3600
            try:
                for name in os.listdir(CACHE_DIR):
                    p = os.path.join(CACHE_DIR, name)
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                with self.lock:
                    conn = self._db()
                    conn.execute("DELETE FROM wrongway_checks WHERE ts < ? AND verdict != 'wrong_way'", (int(cutoff),))
                    conn.commit()
                    conn.close()
                for fl in list(self.fields.values()):
                    fl.save(force=True)
            except OSError:
                pass
