"""
Helmet patrol over every BMA camera: capture each motorcycle, ask a vision agent whether the rider
wears a helmet, keep the evidence of every rider without one on the data drive.

Flow (per camera, once per BMA scan cycle ~4 min, or on demand via check_now):
    snapshot -> YOLO boxes (shared with BmaScanner) -> motorcycle boxes tall enough to see a head
    -> crop (+margin, upscaled) saved to cache/helmet/<id>.jpg ("captures")
    -> optional local YOLO26x helmet detector (helmet_det.pt from train_helmet_det.py):
         helmet only  -> verdict "helmet" with no API call
         no_helmet    -> the agent confirms it
         nothing seen -> the agent decides
    -> helmet agent (the Qwen vision model behind LOCAL_LLM_* by default, HELMET_AGENT=cloud for Gemini
       vision, else Claude): JSON {riders, no_helmet, confidence, note_th}
       (no provider at all: the crop is kept as 'unclear')
    -> verdict no_helmet (confidence >= HELMET_MIN_CONF): full frame with a red box + the crop are
       written to <HELMET_ARCHIVE_DIR>/<YYYY-MM-DD>/<camid>_<HHMMSS>.jpg (+ _crop.jpg) and one row
       goes to helmet.csv there.

Everything is logged in the `helmet_checks` table of vehicle_counts.db and served by /api/helmet/*.
The API budget is bounded: at most HELMET_PATROL_MAX_PER_HOUR agent calls, HELMET_PATROL_PER_CAM
crops per camera per cycle and one visit per camera every HELMET_PATROL_COOLDOWN seconds.
Assistive log, not an enforcement record: confidence and both images are kept for a person to check.
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

import local_llm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
CACHE_DIR = os.path.join(DATA_DIR, "cache", "helmet")
ARCHIVE_DIR = os.getenv("HELMET_ARCHIVE_DIR", os.path.join(os.getenv("BMA_DATA_DIR", r"D:\Data"), "helmet"))
LOCAL_DET_PATH = os.getenv("HELMET_DET", os.path.join(BASE_DIR, "helmet_det.pt"))
if not os.path.isabs(LOCAL_DET_PATH):
    LOCAL_DET_PATH = os.path.join(BASE_DIR, LOCAL_DET_PATH)
# Fast non-thinking model on purpose: a 300-px crop needs no reasoning, and the thinking models
# (gemini-3.6-flash) take 15-40 s per call and hit 504 under load. Falls back to GEMINI_VISION_MODEL.
HELMET_MODEL = os.getenv("HELMET_AGENT_MODEL", os.getenv("GEMINI_VISION_MODEL", "gemini-3.1-flash-lite"))
# qwen = the OpenAI-compatible vision model behind LOCAL_LLM_* (Qwen 3.8 27B reads images); cloud = Gemini / Claude
HELMET_AGENT = os.getenv("HELMET_AGENT", "qwen").strip().lower()
AGENT_TIMEOUT_MS = 40000

MOTO_CLASS = 3                    # COCO motorcycle
MIN_BOX_H = int(os.getenv("HELMET_PATROL_MIN_H", "26"))     # px on the 352x288 BMA frame
MIN_BOX_CONF = 0.35
CROP_MARGIN = 0.35
CROP_MIN_SIDE = 320               # upscale crops so the agent sees a head, not 6 pixels
PER_CAM = int(os.getenv("HELMET_PATROL_PER_CAM", "2"))
COOLDOWN = float(os.getenv("HELMET_PATROL_COOLDOWN", "180"))
MAX_PER_HOUR = int(os.getenv("HELMET_PATROL_MAX_PER_HOUR", "240"))
HELMET_MIN_CONF = 0.7
LOCAL_DET_CONF = 0.5
WORKERS = int(os.getenv("HELMET_PATROL_WORKERS", "4"))   # cloud calls are network-bound (10-60 s each on the free tier)
AGENT_BACKOFF_S = 600             # after a 402/401 (credits / key) from the agent: no calls for this long
RATE_BACKOFF_S = 60               # after a 429 (per-minute rate limit): short pause
FALLBACK_MODEL = os.getenv("GEMINI_VISION_FALLBACK", "gemini-3.1-flash-lite")   # used when the main model returns 503
CACHE_KEEP_H = 48
VERDICT_TH = {"pending": "รอตรวจ", "helmet": "สวมหมวก", "no_helmet": "ไม่สวมหมวกกันน็อก", "unclear": "มองไม่ชัด", "error": "ตรวจไม่สำเร็จ"}

AGENT_PROMPT = (
    "You are the helmet-compliance agent of the Bangkok traffic control room. You receive one crop "
    "from a low-resolution street CCTV camera showing one motorcycle, usually with a rider and possibly "
    "passengers. Decide for each person on the motorcycle whether they wear a motorcycle helmet. "
    "Answer ONLY with JSON: "
    '{"riders": <number of people on the motorcycle>, "no_helmet": <number of them clearly NOT wearing a helmet>, '
    '"confidence": <0..1 that your no_helmet count is right>, "note_th": "<one short Thai sentence describing what you see>"}. '
    "Rules: a cap, hood, hijab, hair or a helmet carried on the arm is NOT a worn helmet. If the heads are not "
    "clearly visible (too small, blurred, dark, cut off, or the object is not a motorcycle) set no_helmet to 0 "
    "and confidence below 0.5. Never guess."
)


def _fingerprint(frame):
    """Tiny grayscale thumbnail bytes: equal for a frozen feed, different for any real new frame."""
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


def _safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))


def _write_jpeg(path, img, q=90):
    # cv2.imwrite cannot take non-ASCII paths on Windows (the data dir has a space / Thai in places)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        return False
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return True


class HelmetPatrol:
    def __init__(self, db_path, vision=None, scanner=None):
        """vision: IncidentManager-like object with .provider/.client. scanner: BmaScanner (for check_now)."""
        self.db_path = db_path
        self.vision = vision
        self.scanner = scanner
        self.lock = threading.Lock()
        self._last_visit = {}         # camid -> ts
        self._last_frame = {}         # camid -> fingerprint of the last snapshot we captured from
        self._last_boxes = {}         # camid -> [(x1,y1,x2,y2), ...] captured last time (parked / frozen bikes)
        self._calls = []              # ts of agent calls in the last hour
        self._queue = queue.Queue()
        self.last_check = 0
        self.agent_error = None       # {"ts", "message"} after a quota/auth failure; calls pause AGENT_BACKOFF_S
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._init_db()
        self.local_det = None
        self._det_lock = threading.Lock()
        if os.path.exists(LOCAL_DET_PATH):
            try:
                from ultralytics import YOLO
                self.local_det = YOLO(LOCAL_DET_PATH)
                self.local_det(np.zeros((320, 320, 3), dtype=np.uint8), verbose=False)
                print(f"[Helmet] local detector loaded: {LOCAL_DET_PATH} {self.local_det.names}")
            except Exception as e:  # noqa: BLE001
                print(f"[Helmet] local detector failed to load: {e}")
                self.local_det = None
        for _ in range(WORKERS):
            threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        # Captures left "pending" by a restart (the in-memory queue is gone): run them again
        threading.Thread(target=self._resume_pending, daemon=True).start()
        print(f"[Helmet] agent: {self.provider() or 'off'} · archive: {ARCHIVE_DIR}")

    # ------------------------------------------------------------ storage
    def _init_db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS helmet_checks (
                id          TEXT PRIMARY KEY,
                ts          INTEGER NOT NULL,
                camid       TEXT NOT NULL,
                title       TEXT,
                district    TEXT,
                box         TEXT,               -- [x1,y1,x2,y2] on the frame
                verdict     TEXT NOT NULL,      -- pending | helmet | no_helmet | unclear | error
                source      TEXT,               -- local | gemini | claude
                riders      INTEGER,
                no_helmet   INTEGER,
                confidence  REAL,
                note        TEXT,
                archive     TEXT                -- evidence frame on the data drive when no_helmet
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS helmet_checks_ts ON helmet_checks(ts)")
        conn.commit()
        conn.close()

    def _db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _insert(self, row):
        with self.lock:
            conn = self._db()
            conn.execute("INSERT OR REPLACE INTO helmet_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            conn.commit()
            conn.close()

    def _update(self, hid, **fields):
        keys = list(fields)
        with self.lock:
            conn = self._db()
            conn.execute(f"UPDATE helmet_checks SET {', '.join(k + ' = ?' for k in keys)} WHERE id = ?",
                         [fields[k] for k in keys] + [hid])
            conn.commit()
            conn.close()

    # ------------------------------------------------------------ paths
    @staticmethod
    def crop_path(hid):
        return os.path.join(CACHE_DIR, f"{hid}.jpg")

    @staticmethod
    def frame_path(hid):
        return os.path.join(CACHE_DIR, f"{hid}_frame.jpg")

    def provider(self):
        if HELMET_AGENT == "qwen" and local_llm.default.enabled():
            return "qwen"
        v = self.vision
        return getattr(v, "provider", None) if v and getattr(v, "client", None) else None

    def enabled(self):
        return self.provider() is not None or self.local_det is not None

    # ------------------------------------------------------------ capture (called from the scanner)
    def observe(self, cam, frame, boxes, force=False):
        """Pick the motorcycles worth a look in this snapshot and queue them. Returns capture ids."""
        if not self.enabled():
            return []
        camid = str(cam.get("camid"))
        now = time.time()
        if not force and now - self._last_visit.get(camid, 0) < COOLDOWN:
            return []
        motos = [(x1, y1, x2, y2, conf) for cls_id, conf, x1, y1, x2, y2 in boxes
                 if cls_id == MOTO_CLASS and conf >= MIN_BOX_CONF and (y2 - y1) >= MIN_BOX_H]
        if not motos:
            return []
        # Frozen feed (BMA keeps serving the same frame): same picture as last time -> nothing new to check
        fp = _fingerprint(frame)
        if not force and _same_scene(fp, self._last_frame.get(camid)):
            return []
        # A bike standing in the same spot as last capture (parked, or a stuck frame) is not a new rider
        prev = self._last_boxes.get(camid, [])
        motos = [m for m in motos if not any(_iou(m[:4], pb) >= 0.6 for pb in prev)]
        if not motos:
            self._last_frame[camid] = fp
            return []
        self._last_visit[camid] = now
        self._last_frame[camid] = fp
        motos.sort(key=lambda b: -(b[3] - b[1]))
        h, w = frame.shape[:2]
        ids = []
        for n, (x1, y1, x2, y2, conf) in enumerate(motos[:PER_CAM]):
            mx, my = int((x2 - x1) * CROP_MARGIN), int((y2 - y1) * CROP_MARGIN)
            # extra room above: the head sits over the top of the motorcycle box
            cx1, cy1, cx2, cy2 = max(0, x1 - mx), max(0, y1 - my * 2), min(w, x2 + mx), min(h, y2 + my)
            crop = frame[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue
            scale = max(1.0, CROP_MIN_SIDE / max(crop.shape[:2]))
            if scale > 1.0:
                crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            hid = f"{_safe(camid)}-{int(now)}-{n}"
            _write_jpeg(self.crop_path(hid), crop)
            marked = frame.copy()
            cv2.rectangle(marked, (x1, y1), (x2, y2), (0, 0, 255), 2)
            _write_jpeg(self.frame_path(hid), marked, 85)
            self._insert((hid, int(now), camid, cam.get("title") or cam.get("short_title") or camid, cam.get("district"),
                          json.dumps([x1, y1, x2, y2]), "pending", None, None, None, None, None, None))
            self._queue.put((hid, camid, cam, crop, marked))
            ids.append(hid)
        self._last_boxes[camid] = [m[:4] for m in motos[:PER_CAM]]
        return ids

    def check_now(self, camid):
        """Fetch a fresh snapshot of one camera and run the patrol on it regardless of cooldown."""
        if not self.scanner:
            return {"ok": False, "error": "no scanner"}
        cam = next((c for c in self.scanner.cameras if str(c.get("camid")) == str(camid)), None)
        if not cam:
            return {"ok": False, "error": "unknown camera"}
        raw = self.scanner.session.fetch_snapshot(str(camid), timeout=7.0)
        if not raw:
            return {"ok": False, "error": "camera offline"}
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"ok": False, "error": "bad image"}
        with self.scanner.infer_lock:
            boxes = self.scanner._detect(img)
        motos = sum(1 for b in boxes if b[0] == MOTO_CLASS)
        usable = sum(1 for b in boxes if b[0] == MOTO_CLASS and b[1] >= MIN_BOX_CONF and (b[5] - b[3]) >= MIN_BOX_H)
        ids = self.observe(cam, img, boxes, force=True)
        if ids:
            msg = f"จับภาพมอไซ {len(ids)} คัน ส่งให้ AI ตรวจแล้ว"
        elif usable:
            msg = f"เห็นมอไซ {usable} คัน แต่เป็นคันเดิมตำแหน่งเดิม (ภาพกล้องไม่เปลี่ยน) ไม่จับซ้ำ"
        elif motos:
            msg = f"เห็นมอไซ {motos} คัน แต่เล็กเกินกว่าจะเห็นหมวก"
        else:
            msg = "ไม่พบมอไซในภาพตอนนี้"
        return {"ok": True, "camid": str(camid), "motorcycles": motos, "captures": ids, "message": msg}

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
            hid, camid, cam, crop, marked = self._queue.get()
            try:
                self._analyse(hid, camid, cam, crop, marked)
            except Exception as e:  # noqa: BLE001 - one bad crop must not kill the worker
                print(f"[Helmet] check failed {hid}: {e}")
                self._update(hid, verdict="error", note=str(e)[:200])
            finally:
                self._queue.task_done()

    def _local_verdict(self, crop):
        """(verdict, conf) from the YOLO26x helmet detector, or None when it sees no head at all."""
        if self.local_det is None:
            return None
        with self._det_lock:
            r = self.local_det(crop, imgsz=640, conf=0.25, verbose=False)[0]
        best = {}
        for c, cf in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist()):
            name = r.names[int(c)]
            best[name] = max(best.get(name, 0.0), float(cf))
        if not best:
            return None
        if best.get("no_helmet", 0) >= LOCAL_DET_CONF:
            return "no_helmet", best["no_helmet"]
        if best.get("helmet", 0) >= LOCAL_DET_CONF:
            return "helmet", best["helmet"]
        return None

    def _analyse(self, hid, camid, cam, crop, marked, agent="auto"):
        """agent: auto (cloud when budget allows) | cloud (force) | local (helmet detector only), the last two from reanalyse."""
        now = time.time()
        local = self._local_verdict(crop)
        if agent == "local":
            self._settle_local(hid, camid, cam, crop, marked, local)
            self.last_check = int(now)
            return
        if agent == "auto" and local and local[0] == "helmet":
            self._update(hid, verdict="helmet", source="local", riders=1, no_helmet=0, confidence=round(local[1], 2),
                         note=f"โมเดลในเครื่องเห็นหมวกกันน็อก ({local[1]:.0%})")
            self.last_check = int(now)
            return
        provider = self.provider()
        if not provider or (agent == "auto" and not self._budget_ok(now)):
            reason = self._agent_reason(now) if provider else "ไม่มี AI agent ตรวจ (ตั้ง LOCAL_LLM_MODEL, GEMINI_API_KEY หรือ ANTHROPIC_API_KEY)"
            self._settle_without_agent(hid, camid, cam, crop, marked, local, reason, provider or "none")
            return
        jpeg = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
        hint = f" A local detector suspects no helmet ({local[1]:.0%})." if local else ""
        context = f"Camera: {cam.get('title') or camid}, Bangkok. One motorcycle crop from a 352x288 CCTV frame.{hint}"
        self._calls.append(now)
        try:
            text = self._ask(jpeg, context)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "429" in msg or "RATE_LIMIT" in msg:
                self.agent_error = {"ts": now, "message": "ชนลิมิตต่อนาทีของ API", "for": RATE_BACKOFF_S}
                print(f"[Helmet] cloud agent rate-limited, pausing {RATE_BACKOFF_S}s")
            elif any(k in msg for k in ("402", "401", "400", "RESOURCE_EXHAUSTED", "credits", "API key")):
                short = "เครดิต/โควตา API หมด" if ("402" in msg or "credits" in msg or "RESOURCE_EXHAUSTED" in msg) else msg[:120]
                self.agent_error = {"ts": now, "message": short, "for": AGENT_BACKOFF_S}
                print(f"[Helmet] cloud agent paused {AGENT_BACKOFF_S}s: {msg[:160]}")
            else:
                print(f"[Helmet] cloud agent error: {msg[:160]}")
            self._settle_without_agent(hid, camid, cam, crop, marked, local, "AI agent ไม่ตอบ: " + msg[:100], provider)
            return
        self.agent_error = None
        self._apply_verdict(hid, camid, cam, crop, marked, text, provider)

    def _apply_verdict(self, hid, camid, cam, crop, marked, text, source):
        now = time.time()
        start, end = text.find("{"), text.rfind("}")
        v = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
        riders = int(v.get("riders", 0) or 0)
        bad = int(v.get("no_helmet", 0) or 0)
        conf = float(v.get("confidence", 0) or 0)
        note = (v.get("note_th") or "").strip()[:300]
        self.last_check = int(now)
        print(f"[Helmet] {source} · {cam.get('title') or camid}: riders {riders}, no helmet {bad}, conf {conf:.2f}")
        if bad > 0 and conf >= HELMET_MIN_CONF:
            self._finish_no_helmet(hid, camid, cam, crop, marked, riders, bad, conf, note, source)
        elif conf >= 0.5 and riders > 0:
            self._update(hid, verdict="helmet", source=source, riders=riders, no_helmet=bad, confidence=round(conf, 2), note=note)
        else:
            self._update(hid, verdict="unclear", source=source, riders=riders, no_helmet=bad, confidence=round(conf, 2), note=note)

    def _row(self, hid):
        with self.lock:
            conn = self._db()
            row = conn.execute("SELECT * FROM helmet_checks WHERE id = ?", (hid,)).fetchone()
            conn.close()
        if not row:
            return None
        r = dict(row)
        r["verdict_th"] = VERDICT_TH.get(r["verdict"], r["verdict"])
        r["box"] = json.loads(r["box"]) if r.get("box") else None
        r["crop"], r["frame"] = f"/api/helmet/{hid}/crop", f"/api/helmet/{hid}/frame"
        return r

    def reanalyse(self, hid, agent="cloud"):
        """Second opinion on a saved capture from the page. Runs inline (a few seconds) and returns the row."""
        crop_p, frame_p = self.crop_path(hid), self.frame_path(hid)
        row = self._row(hid)
        if not row:
            return {"ok": False, "error": "ไม่พบรายการ"}
        if not os.path.exists(crop_p):
            return {"ok": False, "error": "ไม่มีภาพนี้ในแคชแล้ว"}
        if agent == "local" and self.local_det is None:
            return {"ok": False, "error": "ไม่มีโมเดลในเครื่อง (helmet_det.pt)"}
        if agent != "local" and not self.provider():
            return {"ok": False, "error": "ไม่มีโมเดล AI (Qwen/Gemini/Claude)"}
        camid = row["camid"]
        cam = next((c for c in (self.scanner.cameras if self.scanner else []) if str(c.get("camid")) == camid), None) \
            or {"camid": camid, "title": row["title"], "district": row["district"]}
        crop = cv2.imdecode(np.fromfile(crop_p, np.uint8), cv2.IMREAD_COLOR)
        marked = cv2.imdecode(np.fromfile(frame_p, np.uint8), cv2.IMREAD_COLOR) if os.path.exists(frame_p) else crop
        try:
            self._analyse(hid, camid, cam, crop, marked, agent=agent)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200]}
        return {"ok": True, "item": self._row(hid)}

    def _resume_pending(self):
        time.sleep(20)   # let the cloud client / local model come up first
        with self.lock:
            conn = self._db()
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM helmet_checks WHERE verdict = 'pending' AND ts >= ? ORDER BY ts DESC LIMIT 60",
                (int(time.time() - 6 * 3600),))]
            conn.close()
        ids = [h for h in ids if os.path.exists(self.crop_path(h))]
        if ids:
            print(f"[Helmet] resuming {len(ids)} captures left pending by the restart")
        for hid in ids:
            self.reanalyse(hid, "cloud")

    def reanalyse_pending(self, agent="cloud", limit=40, hours=24):
        """Re-run captures without a firm verdict (unclear / error / pending) through the cloud agent or the local detector, sequentially."""
        verdicts = "('unclear','error','pending')"
        with self.lock:
            conn = self._db()
            ids = [r["id"] for r in conn.execute(
                f"SELECT id FROM helmet_checks WHERE ts >= ? AND verdict IN {verdicts} ORDER BY ts DESC LIMIT ?",
                (int(time.time() - hours * 3600), limit))]
            conn.close()
        ids = [h for h in ids if os.path.exists(self.crop_path(h))]

        def run():
            for hid in ids:
                self.reanalyse(hid, agent)
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "queued": len(ids), "agent": agent}

    def _settle_local(self, hid, camid, cam, crop, marked, local):
        """Verdict from the local helmet detector alone (reanalyse with agent=local): no API call at all."""
        if not local:
            self._update(hid, verdict="unclear", source="local", note="โมเดลในเครื่องไม่เห็นหัวผู้ขับขี่ชัดพอจะตัดสิน")
        elif local[0] == "no_helmet":
            self._finish_no_helmet(hid, camid, cam, crop, marked, 1, 1, local[1],
                                   f"โมเดลในเครื่องไม่เห็นหมวกกันน็อก ({local[1]:.0%})", "local")
        else:
            self._update(hid, verdict="helmet", source="local", riders=1, no_helmet=0, confidence=round(local[1], 2),
                         note=f"โมเดลในเครื่องเห็นหมวกกันน็อก ({local[1]:.0%})")

    def _settle_without_agent(self, hid, camid, cam, crop, marked, local, reason, provider):
        """Agent unavailable: trust the local detector when it flagged no helmet, else leave it unclear."""
        if local and local[0] == "no_helmet":
            self._finish_no_helmet(hid, camid, cam, crop, marked, 1, 1, local[1],
                                   f"โมเดลในเครื่องไม่เห็นหมวกกันน็อก ({local[1]:.0%}) · {reason}", "local")
        else:
            self._update(hid, verdict="unclear", source=provider, note=reason)

    def _finish_no_helmet(self, hid, camid, cam, crop, marked, riders, bad, conf, note, source):
        archived = self._archive(hid, camid, cam, crop, marked, riders, bad, conf, note)
        self._update(hid, verdict="no_helmet", source=source, riders=riders, no_helmet=bad,
                     confidence=round(conf, 2), note=note, archive=archived)
        print(f"[Helmet] NO HELMET at {cam.get('title') or camid} ({bad}/{riders}, {conf:.0%})" + (f" -> {archived}" if archived else ""))

    def _archive(self, hid, camid, cam, crop, marked, riders, bad, conf, note):
        """Evidence on the data drive: frame with the red box, the crop, one CSV row. Best effort.
        File names carry the capture time (from the id), not the time the verdict came in."""
        try:
            try:
                ts = int(hid.rsplit("-", 2)[1])
            except (IndexError, ValueError):
                ts = time.time()
            dt = datetime.fromtimestamp(ts)
            day_dir = os.path.join(ARCHIVE_DIR, dt.strftime("%Y-%m-%d"))
            os.makedirs(day_dir, exist_ok=True)
            stem = os.path.join(day_dir, f"{_safe(camid)}_{dt.strftime('%H%M%S')}_{hid[-1]}")
            frame_out, crop_out = stem + ".jpg", stem + "_crop.jpg"
            label = f"NO HELMET {bad}/{riders} {conf:.0%}  {dt.strftime('%Y-%m-%d %H:%M:%S')}"
            banner = marked.copy()
            cv2.rectangle(banner, (0, 0), (banner.shape[1], 18), (0, 0, 0), -1)
            cv2.putText(banner, label, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
            _write_jpeg(frame_out, banner, 92)
            _write_jpeg(crop_out, crop, 92)
            index = os.path.join(ARCHIVE_DIR, "helmet.csv")
            new_file = not os.path.exists(index)
            with open(index, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["id", "datetime", "camid", "camera", "district", "riders", "no_helmet", "confidence", "note", "frame", "crop"])
                w.writerow([hid, dt.strftime("%Y-%m-%d %H:%M:%S"), camid, cam.get("title") or "", cam.get("district") or "",
                            riders, bad, round(float(conf), 2), note, frame_out, crop_out])
            return frame_out
        except OSError as e:
            print(f"[Helmet] archive to {ARCHIVE_DIR} failed: {e}")
            return None

    def _ask(self, jpeg, context):
        if self.provider() == "qwen":
            image = "data:image/jpeg;base64," + base64.standard_b64encode(jpeg).decode("ascii")
            return local_llm.default.chat(
                [{"role": "system", "content": AGENT_PROMPT},
                 {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}, {"type": "text", "text": context}]}],
                max_tokens=300, temperature=0.1, timeout=AGENT_TIMEOUT_MS / 1000)
        vis = self.vision
        if vis.provider == "gemini":
            from google.genai import types as genai_types
            main = HELMET_MODEL
            for model in dict.fromkeys([main, FALLBACK_MODEL]):
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
                    # 503 = model overloaded right now: try the lite model once before giving up
                    if any(k in str(e) for k in ("503", "UNAVAILABLE", "504", "DEADLINE")):
                        print(f"[Helmet] {model} overloaded (503), trying {FALLBACK_MODEL}")
                        continue
                    raise
            raise RuntimeError("503 Gemini overloaded on every model")
        response = vis.client.messages.create(
            model=os.environ.get("CLAUDE_VISION_MODEL", "claude-opus-5-5"),
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

    # ------------------------------------------------------------ API
    def status(self):
        now = time.time()
        day0 = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        with self.lock:
            conn = self._db()
            today = {r["verdict"]: r["n"] for r in conn.execute(
                "SELECT verdict, COUNT(*) n FROM helmet_checks WHERE ts >= ? GROUP BY verdict", (day0,))}
            total_no_helmet = conn.execute("SELECT COUNT(*) FROM helmet_checks WHERE verdict = 'no_helmet'").fetchone()[0]
            conn.close()
        self._calls = [t for t in self._calls if now - t < 3600]
        return {
            "updated": int(now), "enabled": self.enabled(), "agent": self.provider() or "off",
            "agent_model": local_llm.default.model if self.provider() == "qwen"
            else HELMET_MODEL if self.provider() == "gemini"
            else (os.environ.get("CLAUDE_VISION_MODEL", "claude-opus-5-5") if self.provider() else None),
            "local_detector": os.path.basename(LOCAL_DET_PATH) if self.local_det is not None else None,
            "archive_dir": ARCHIVE_DIR, "archive_ok": os.path.isdir(os.path.dirname(ARCHIVE_DIR.rstrip("/\\"))),
            "calls_last_hour": len(self._calls), "calls_per_hour_max": MAX_PER_HOUR, "queue": self._queue.qsize(),
            "agent_error": (self.agent_error["message"] if self.agent_error and now - self.agent_error["ts"] < self.agent_error.get("for", AGENT_BACKOFF_S) else None),
            "last_check": self.last_check, "cooldown_s": COOLDOWN, "per_camera": PER_CAM, "min_box_h": MIN_BOX_H,
            "today": {"captures": sum(today.values()), "pending": today.get("pending", 0), "helmet": today.get("helmet", 0),
                      "no_helmet": today.get("no_helmet", 0),
                      "unclear": today.get("unclear", 0) + today.get("error", 0)},
            "total_no_helmet": total_no_helmet,
        }

    def recent(self, hours=24, verdict=None, camid=None, limit=200):
        q, args = "SELECT * FROM helmet_checks WHERE ts >= ?", [int(time.time() - hours * 3600)]
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
            rows = [dict(r) for r in conn.execute(q, args)]
            conn.close()
        for r in rows:
            r["verdict_th"] = VERDICT_TH.get(r["verdict"], r["verdict"])
            r["box"] = json.loads(r["box"]) if r.get("box") else None
            r["crop"] = f"/api/helmet/{r['id']}/crop"
            r["frame"] = f"/api/helmet/{r['id']}/frame"
        return {"updated": int(time.time()), "hours": hours, "items": rows}

    def cameras(self):
        """Every BMA camera with its live motorcycle count and today's patrol result."""
        day0 = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        with self.lock:
            conn = self._db()
            stats = {}
            for r in conn.execute("SELECT camid, verdict, COUNT(*) n, MAX(ts) last FROM helmet_checks WHERE ts >= ? GROUP BY camid, verdict", (day0,)):
                s = stats.setdefault(r["camid"], {"captures": 0, "no_helmet": 0, "last": 0})
                s["captures"] += r["n"]
                if r["verdict"] == "no_helmet":
                    s["no_helmet"] += r["n"]
                s["last"] = max(s["last"], r["last"] or 0)
            conn.close()
        latest = {str(c.get("camid")): c for c in (self.scanner.db.get_all_latest() if self.scanner else [])}
        items = []
        for cam in (self.scanner.cameras if self.scanner else []):
            cid = str(cam.get("camid"))
            live = latest.get(cid, {})
            s = stats.get(cid, {"captures": 0, "no_helmet": 0, "last": 0})
            items.append({"camid": cid, "title": cam.get("title") or cam.get("short_title") or cid, "district": cam.get("district"),
                          "status": live.get("status") or "unknown", "motorcycles": live.get("motorcycles") or 0,
                          "total": live.get("total") or 0, "captures": s["captures"], "no_helmet": s["no_helmet"], "last": s["last"]})
        items.sort(key=lambda c: (-c["no_helmet"], -c["captures"], -c["motorcycles"]))
        return {"updated": int(time.time()), "total": len(items), "items": items}

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
                    # keep the no-helmet log forever (evidence is on the data drive); drop stale routine checks
                    conn.execute("DELETE FROM helmet_checks WHERE ts < ? AND verdict != 'no_helmet'", (int(cutoff),))
                    conn.commit()
                    conn.close()
            except OSError:
                pass
