"""
Flood watch over every BMA camera and the iTIC cameras: is there water on the road in front of the camera now?

Flow:
    BmaScanner hands every raw snapshot to observe() (each camera about every 3 min); itic_frames.py adds
    the iTIC cameras around Bangkok with add_cameras() and hands in a frame of each every 5 min
    -> WORKERS workers each take the cameras due for a check: never checked, or checked more than
       INTERVAL ago (WET_INTERVAL for the ones that had water) and holding a newer frame than that check
    -> screen: TILES frames per call, tiled in a grid with a big number on each tile, one vision
       call to the Qwen model behind LOCAL_LLM_*; it answers only a level per tile, no note, so the
       reply is short (with a Thai note per tile a grid took about 24 s)
    -> confirm: every tile the screen calls puddle / flooded / severe is asked again on its own, so
       one misread tile in a grid does not put a false flood on the map; this verdict is final
    -> the confirm call also copies the date and time printed on the frame: a frame printed more than
       STAMP_MAX_LAG before it was fetched is an old copy the BMA site still serves (seen after an
       outage: pictures two days old), so it is judged unclear, not wet
    -> state per camera in cache/flood_cams.json, the frame it judged in cache/flood_cams/<camid>.jpg

Levels: none, puddle (water pooling at the kerb, lanes clear), flooded (water over part or all of a
lane), severe (road under deep water), unclear (dark, blurred, rain on the lens, no signal).

A frame that has not changed since the last check (a frozen feed) is not asked again. SEED_DELAY
after start the watch takes the scanner's last saved snapshots younger than SEED_MAX_AGE for the
cameras that sent no frame since, so the map has something while the BMA site is down; not before,
because the text bar on a saved snapshot hides the printed time the stale check reads. Every verdict
keeps the time of its frame, and the map fades the ones whose frame is older than STALE_MINUTES.

FLOOD_CAM_RESEED (seconds, 0 = off) keeps taking those saved snapshots every that often and replaces a
held frame with a newer one. For a machine with BMA_FETCH=0 that is fed by a copy of another machine's
snapshots (launch/test/pi_frames_sync.py copies the Raspberry Pi's into instances/test).

Three guards on the verdicts (the small local model made false floods on a rainy night). Each has a switch,
read from the environment at import, default on:
    FLOOD_CAM_CORRUPT_CHECK=1   a frame with broken-stream colour blocks (_corrupt) is never sent to the model:
                                it gets level unclear, note "ภาพเสีย", source corrupt, and spends no call.
                                FLOOD_CAM_CORRUPT_SHARE (0.025) is the share of the frame in such blocks.
    FLOOD_CAM_NOTE_CHECK=1      a confirm asks for the note before the level, and a wet level whose note says
                                there is no water (_note_check) is set to none.
    FLOOD_CAM_CONFIRM_TWICE=1   flooded or severe on a confirm is first a candidate (level unclear, note
                                "รอยืนยัน"); it is published when the next confirm, on a different frame,
                                is wet too. A candidate expires after 2 x WET_INTERVAL without that look.

At most MAX_PER_HOUR vision calls. Served by /api/flood/cameras*.
"""
import base64
import copy
import json
from backend.core.atomic_file import write_json_atomic
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from backend.bma.bma_service import CACHE_DIR as SNAPSHOT_DIR   # the scanner's last annotated frame per camera
from backend.core import local_llm
from backend.core.hourly_budget import HourlyBudget
from backend.core.instance import DATA_DIR   # cache root: instances/production, or instances/test for the test server
from backend.vision.frame_utils import fingerprint, same_scene
from backend.core.log import get_logger

log = get_logger("FloodCam")

STATE_FILE = os.path.join(DATA_DIR, "cache", "flood_cams.json")
FRAME_DIR = os.path.join(DATA_DIR, "cache", "flood_cams")

INTERVAL = int(os.getenv("FLOOD_CAM_INTERVAL", "300"))           # seconds between checks of a dry camera
WET_INTERVAL = int(os.getenv("FLOOD_CAM_WET_INTERVAL", "300"))   # ... of a camera that had water, to see it drain
WORKERS = int(os.getenv("FLOOD_CAM_WORKERS", "4"))               # grids asked at once, so a full round fits in INTERVAL
MAX_PER_HOUR = int(os.getenv("FLOOD_CAM_MAX_PER_HOUR", "1500"))  # a full round is ~70 screen calls + confirms, 12 an hour
GRID = 3
TILES = GRID * GRID
TILE_W, TILE_H = 352, 288      # the BMA frame size
CONFIRM_W = 704
# A verdict whose frame is older than this is faded and marked "ภาพเก่า": the camera sent no new frame for
# about 5 BMA scan cycles (3 min) or 3 iTIC rounds (5 min), so it no longer shows the road as it is now
STALE_MINUTES = int(os.getenv("FLOOD_CAM_STALE_MINUTES", "15"))
SEED_MAX_AGE = 12 * 3600
SEED_DELAY = 300               # about one scanner cycle: live frames first
RESEED = int(os.getenv("FLOOD_CAM_RESEED", "0"))   # seconds between re-reads of the saved snapshots; 0 = seed once
AGENT_TIMEOUT = 120
ERROR_BACKOFF = 60
STAMP_MAX_LAG = int(os.getenv("FLOOD_CAM_STAMP_MAX_LAG", "3600"))   # printed time this much older than the fetch: stale copy
# Printed time older than this: a camera clock never set (they reset to a default years back), not a stale
# copy. Was 30 days, but the BMA site served camera 1463's flood picture of 26 Sep 2026 as new on 20 Nov,
# 55 days later, so old copies outlive a month. A camera whose clock is months off now gets unclear for a
# wet call, which is the safe side.
STAMP_MAX_AGE = int(os.getenv("FLOOD_CAM_STAMP_MAX_AGE_DAYS", "365")) * 86400
# Guard 1: broken video frames. Share of the frame in flat, strongly coloured 7x7 patches (see _corrupt).
# Set by hand on ~670 frames (Pi copies and production cache): 2.5% flags the two broken copies of camera 1379
# and six good frames (about 1%); the next-highest good frame is at 2.25%. Some broken frames score lower.
CORRUPT_CHECK = int(os.getenv("FLOOD_CAM_CORRUPT_CHECK", "1"))
CORRUPT_SHARE = float(os.getenv("FLOOD_CAM_CORRUPT_SHARE", "0.025"))
CORRUPT_VERDICT = {"level": "unclear", "confidence": 1.0, "note_th": "ภาพเสีย (สัญญาณภาพแตก)"}
# Guard 2: the note must agree with the level (_note_check)
NOTE_CHECK = int(os.getenv("FLOOD_CAM_NOTE_CHECK", "1"))
# Guard 3: flooded or severe is seen on two frames before it is published (_second_look)
CONFIRM_TWICE = int(os.getenv("FLOOD_CAM_CONFIRM_TWICE", "1"))
BKK = timezone(timedelta(hours=7))
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun",
                                      "jul", "aug", "sep", "oct", "nov", "dec"), 1)}

LEVELS = ("none", "puddle", "flooded", "severe", "unclear")
WET = ("puddle", "flooded", "severe")
LEVEL_TH = {"none": "ไม่มีน้ำท่วม", "puddle": "น้ำขังเล็กน้อย", "flooded": "น้ำท่วมผิวจราจร",
            "severe": "น้ำท่วมหนัก", "unclear": "มองไม่ชัด"}
RANK = {"severe": 0, "flooded": 1, "puddle": 2, "unclear": 3, "none": 4}

_LEVEL_RULES = (
    "Levels: "
    "none = dry, or a wet shiny road (rain drops, light reflections) with no distinct pools of water; "
    "puddle = distinct pools of standing water on part of the road or along the kerb, lanes still clear; "
    "flooded = water covers a lane or more: lane markings or the kerb hidden under water, spray or wakes behind vehicles; "
    "severe = road fully under deep water: water up to the wheels, strong wakes, stalled vehicles or people wading; "
    "unclear = too dark, blurred, rain on the lens hides the road, frozen, a placeholder or no-signal image, "
    "or the road is not visible. "
    "A broken or glitched picture (blocky smears, a pixelated mosaic, patches of wrong colour from a bad video "
    "signal) is unclear, never puddle or flooded; ordinary night grain and blur are not broken. "
    "Headlight and street-light reflections on wet asphalt (at night and in rain) look like water but are NOT flooding: "
    "call flooded only when you see a water surface (ripples, splashes, wakes, brown water) or markings hidden under it. "
    "Ignore any text bar and boxes drawn on top of the picture. A river, canal or pond beside the road is NOT flooding."
)
SCREEN_PROMPT = (
    "You are the flood-watch agent of the Bangkok traffic control room. The image is a grid of numbered tiles; "
    "each tile is a separate low-resolution street CCTV snapshot from a different place. For each tile decide "
    "whether flood water stands or flows on the road surface. " + _LEVEL_RULES + " "
    "This is a first pass: every tile you mark puddle, flooded or severe gets a closer look on its own, so mark a "
    "tile at least puddle whenever it may have standing water, and none only when the road is clearly free of it. "
    'Answer ONLY with JSON: {"tiles": [{"tile": <number>, "level": "none|puddle|flooded|severe|unclear", '
    '"confidence": <0..1>}]} with one entry per tile.'
)
CONFIRM_PROMPT = (
    "You are the flood-watch agent of the Bangkok traffic control room. The image is one low-resolution street "
    "CCTV snapshot. Decide whether flood water stands or flows on the road surface. " + _LEVEL_RULES + " "
    "Never guess: when unsure between two levels, pick the lower one. "
    "Describe what you see first (note_th), then choose the level that the description supports. "
    'Answer ONLY with JSON: {"note_th": "<one short Thai sentence: what the road looks like and where any water is, '
    'and how deep it looks; say so when there is no water>", '
    '"level": "none|puddle|flooded|severe|unclear", "confidence": <0..1>, '
    '"stamp": "<the date and time printed on the picture, copied exactly; empty when there is none>"}.'
)
# Guard 2: a note that says there is no water, against a wet level. Negations are cut out first, so
# "ไม่มีน้ำท่วม แต่มีน้ำขังเล็กน้อย" still has a positive phrase left (น้ำขัง) and stays a puddle.
_NO_WATER_TH = ("ไม่มีน้ำท่วม", "ไม่มีน้ำขัง", "ไม่มีแอ่งน้ำ", "ไม่พบน้ำท่วม", "ไม่พบน้ำขัง", "ไม่พบน้ำ", "ไม่มีน้ำ",
                "แห้ง", "no standing water", "no flooding", "not flooded", "no water", "dry")
# "not dry" is wet, so these block the downgrade before the dry words are looked for ("แห้ง" sits inside "ไม่แห้ง")
_PROTECTED_TH = ("ไม่แห้ง", "not dry")
_WATER_TH = ("น้ำขัง", "น้ำท่วม", "ท่วม", "แอ่งน้ำ", "น้ำนอง", "น้ำไหล", "น้ำลึก", "จมน้ำ", "ปกคลุม",
             "standing water", "flood", "puddle", "water")
_NO_WATER_RE = re.compile("|".join(re.escape(p) for p in sorted(_NO_WATER_TH, key=len, reverse=True)), re.I)
_PROTECTED_RE = re.compile("|".join(re.escape(p) for p in _PROTECTED_TH), re.I)
_NOTE_SUFFIX = " (ระดับปรับเป็นไม่มีน้ำ: คำบรรยายบอกว่าไม่มีน้ำ)"
_CANDIDATE_TH = "รอยืนยัน: "
_EXPIRED_TH = "ยังไม่ยืนยัน: ตรวจซ้ำไม่ทัน"


def _parse(text):
    """The JSON object in a reply. A small local model (qwen3.5-4b) sometimes answers the screen with the bare
    tile list, [{"tile": 1, ...}, ...], instead of {"tiles": [...]}; that list is taken as the tiles."""
    obj, arr = text.find("{"), text.find("[")
    if arr >= 0 and (obj < 0 or arr < obj):
        end = text.rfind("]")
        if end > arr:
            tiles = json.loads(text[arr:end + 1])
            if isinstance(tiles, list):
                return {"tiles": tiles}
    start, end = obj, text.rfind("}")
    return json.loads(text[start:end + 1]) if start >= 0 and end > start else {}


def _verdict(v):
    level = str(v.get("level", "")).strip().lower()
    try:
        conf = min(1.0, max(0.0, float(v.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {"level": level if level in LEVELS else "unclear", "confidence": round(conf, 2),
            "note_th": str(v.get("note_th") or "")[:200]}


def _stamp_time(text):
    """Epoch of a date and time printed on a frame ("28-09-2026 19:53:57", "2026/09/28 18:35:06",
    "28 Sep 2026 20:01:54", "28.09.2026 19:55:58"; Bangkok time), or None when it does not read as one."""
    text = str(text or "").strip().lower()
    t = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not t:
        return None
    if m := re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    elif m := re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text):
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if mo > 12:
            d, mo = mo, d   # month first
    elif m := re.search(r"(\d{1,2})\s*([a-z]{3})[a-z]*\.?,?\s*(\d{4})", text):
        d, mo, y = int(m[1]), MONTHS.get(m[2]), int(m[3])
    elif m := re.search(r"([a-z]{3})[a-z]*\.?\s*(\d{1,2}),?\s*(\d{4})", text):
        mo, d, y = MONTHS.get(m[1]), int(m[2]), int(m[3])
    else:
        return None
    if y > 2400:
        y -= 543   # Buddhist era
    try:
        return datetime(y, mo, d, int(t[1]), int(t[2]), int(t[3] or 0), tzinfo=BKK).timestamp()
    except (TypeError, ValueError):
        return None


def _stale_copy(v, stamp, frame_ts):
    """The confirm verdict, or unclear when the time printed on the frame shows an old copy served as new."""
    at = _stamp_time(stamp)
    lag = frame_ts - at if at is not None else 0
    if not STAMP_MAX_LAG < lag < STAMP_MAX_AGE:
        return v
    age = f"{lag / 86400:.0f} วัน" if lag >= 2 * 86400 else f"{lag / 3600:.0f} ชม."
    return {**v, "level": "unclear",
            "note_th": f"ภาพค้าง: เวลาบนภาพ {str(stamp)[:40]} เก่ากว่าเวลาดึงภาพ {age}"}


def _corrupt(frame):
    """True when the frame is a broken video stream: a large share of it is flat 7x7 patches with strong colour
    (H.264 macroblock smear, wrong-colour blocks). Accepts JPEG bytes or an image. The text bar on top is skipped.
    Colour alone is not enough: a warm sodium-lit street is saturated too, so only big flat patches count."""
    img = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR) if isinstance(frame, (bytes, bytearray)) else frame
    if img is None:
        return False
    img = img[int(img.shape[0] * 0.10):]
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    luma = lab[:, :, 0]
    chroma = np.sqrt((lab[:, :, 1] - 128.0) ** 2 + (lab[:, :, 2] - 128.0) ** 2)
    mean = cv2.blur(luma, (7, 7))
    spread = np.sqrt(np.maximum(cv2.blur(luma * luma, (7, 7)) - mean * mean, 0))   # local luma std
    colour = cv2.blur(chroma, (7, 7))
    share = float(((spread < 2.5) & (colour > 35)).mean())
    return share >= CORRUPT_SHARE


def _note_check(v):
    """A wet level whose note says there is no water is set to none (the note is the model's own description,
    written before the level). Only the note is read: the level is not second-guessed when the note is silent."""
    note = str(v.get("note_th") or "")
    if v.get("level") not in WET or not note or _PROTECTED_RE.search(note) or not _NO_WATER_RE.search(note):
        return v   # "not dry" is wet: a protected phrase is never a reason to downgrade
    rest = _NO_WATER_RE.sub(" ", note).lower()
    if any(p in rest for p in _WATER_TH):
        return v   # some water is still described after the negations: keep the level
    return {**v, "level": "none", "note_th": note + _NOTE_SUFFIX}


def _earlier_wet(prev, ts, now):
    """The flooded or severe level of the previous look at this camera, when that look still counts: a candidate
    not older than 2 x WET_INTERVAL, or a published confirm. The new look must be on a newer frame time; the
    picture itself may be the same (a quiet road is still a second model judgement). None otherwise."""
    if not prev or prev.get("frame_ts") is None or not int(ts) > prev["frame_ts"]:
        return None
    if prev.get("candidate"):
        return prev["candidate"] if now - prev.get("checked_at", 0) <= 2 * WET_INTERVAL else None
    if prev.get("source") == "confirm" and prev.get("level") in ("flooded", "severe"):
        return prev["level"]
    return None


def _second_look(prev, v, ts, now):
    """The confirm verdict to publish, and the state fields to keep with it (candidate, when held back).
    flooded or severe is published only when the previous wet look was on an older frame; the first one is held
    as a candidate (level unclear). When both agree the more cautious level is published (flooded if either was)."""
    if not CONFIRM_TWICE or v["level"] not in ("flooded", "severe"):
        return v, {}
    earlier = _earlier_wet(prev, ts, now)
    if earlier:
        return {**v, "level": "flooded" if "flooded" in (earlier, v["level"]) else "severe"}, {}
    return {**v, "level": "unclear", "note_th": _CANDIDATE_TH + v["note_th"]}, {"candidate": v["level"]}


def _tile(jpeg, n):
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    img = cv2.resize(img, (TILE_W, TILE_H)) if img is not None else np.zeros((TILE_H, TILE_W, 3), np.uint8)
    cv2.rectangle(img, (0, 0), (44, 40), (0, 0, 0), -1)
    cv2.putText(img, str(n), (8, 32), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
    return img


def _mosaic(jpegs):
    tiles = [_tile(j, n + 1) for n, j in enumerate(jpegs)]
    tiles += [np.zeros((TILE_H, TILE_W, 3), np.uint8)] * (-len(tiles) % GRID)
    grid = cv2.vconcat([cv2.hconcat(tiles[i:i + GRID]) for i in range(0, len(tiles), GRID)])
    return cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


def _enlarge(jpeg):
    """The single frame CONFIRM_W wide (a BMA frame at twice its size): the model sees the kerb and the water line."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jpeg
    scale = CONFIRM_W / img.shape[1]
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


class FloodCamWatch:
    def __init__(self, cameras):
        self._cams = {str(c["camid"]): c for c in cameras}   # replaced whole, never changed in place
        self._frames = {}      # camid -> (jpeg, frame ts, fingerprint), newest from the scanner
        self._state = {}       # camid -> verdict dict (see _record)
        self._judged = {}      # camid -> fingerprint of the frame behind the current verdict
        self._force = set()    # camids to check now whatever their turn (check_all)
        self._inflight = set() # camids a worker is checking now, so no other worker takes them too
        self._budget = HourlyBudget(MAX_PER_HOUR)   # vision calls in the last hour
        self._save_lock = threading.Lock()
        self._lock = threading.Lock()
        self.last_error = None
        os.makedirs(FRAME_DIR, exist_ok=True)
        self._load()

    def enabled(self):
        return local_llm.default.enabled()

    def _load(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                # kept whole: the iTIC cameras are added a little after start
                self._state = json.load(f)
        except (OSError, ValueError):
            self._state = {}

    def _save(self):
        with self._save_lock:   # the workers save in turn: one .tmp file, and never an older state over a newer one
            with self._lock:   # copy only: the frame and API paths take this lock, so not the disk write
                snapshot = copy.deepcopy(self._state)
            write_json_atomic(STATE_FILE, snapshot, ensure_ascii=False)

    # ------------------------------------------------------------ frames in
    def add_cameras(self, cameras):
        """More cameras to watch (the iTIC ones); their frames come in through observe()."""
        self._cams = {**self._cams, **{str(c["camid"]): c for c in cameras}}

    def observe(self, cam, frame):
        """Keep the newest raw frame of this camera (BmaScanner: every snapshot; IticFrames: one per round)."""
        camid = str(cam.get("camid"))
        if camid not in self._cams:
            return
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ok:
            with self._lock:
                self._frames[camid] = (buf.tobytes(), time.time(), fingerprint(frame))

    def _seed(self, refresh=False):
        """The scanner's saved snapshots, so a restart while the BMA site is down still has frames to check.
        refresh=True (FLOOD_CAM_RESEED): a snapshot newer than the frame held replaces it."""
        now = time.time()
        for camid in list(self._cams):
            path = os.path.join(SNAPSHOT_DIR, f"{camid}.jpg")
            try:
                ts = os.path.getmtime(path)
                if now - ts > SEED_MAX_AGE:
                    continue
                if refresh:
                    with self._lock:
                        held = self._frames.get(camid)
                    if held and ts <= held[1]:
                        continue   # not newer than the frame held: not read again
                with open(path, "rb") as f:
                    jpeg = f.read()
            except OSError:
                continue
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            with self._lock:
                if refresh:
                    self._frames[camid] = (jpeg, ts, fingerprint(img))
                else:
                    self._frames.setdefault(camid, (jpeg, ts, fingerprint(img)))

    def _reseed_forever(self, every):
        """Re-read the saved snapshots every `every` seconds; a failure is logged and the loop goes on."""
        while True:
            time.sleep(every)
            try:
                self._seed(refresh=True)
            except Exception as e:  # noqa: BLE001 - one bad file or a read error must not stop the reseed
                log.warning(f"reseed failed: {type(e).__name__}: {str(e)[:160]}")

    # ------------------------------------------------------------ worker
    def start(self):
        threading.Thread(target=self._run, daemon=True, name="flood-cam-watch").start()

    def _run(self):
        time.sleep(20)   # let the server finish starting
        for n in range(WORKERS):
            threading.Thread(target=self._loop, daemon=True, name=f"flood-cam-watch-{n}").start()
        time.sleep(SEED_DELAY)
        self._seed()
        if RESEED > 0:
            self._reseed_forever(RESEED)

    def _loop(self):
        while True:
            try:
                batch = self._take() if self.enabled() and self._budget_ok() else []
                if not batch:
                    time.sleep(20)
                    continue
                try:
                    self._screen(batch)
                finally:
                    with self._lock:
                        self._inflight.difference_update(batch)
                    self._save()
                self.last_error = None
            except Exception as e:  # noqa: BLE001 - the model endpoint may be down; try again later
                self.last_error = f"{type(e).__name__}: {str(e)[:160]}"
                log.warning(f"check failed: {self.last_error}")
                time.sleep(ERROR_BACKOFF)

    def _take(self):
        """The next grid of due cameras, marked in flight for this worker. A camera waiting for its second look
        (a candidate) is taken alone, so it goes straight to the single-frame confirm."""
        with self._lock:
            self._expire_candidates(time.time())
            due = self._due()
            cands = [c for c in due if (self._state.get(c) or {}).get("candidate")]
            batch = cands[:1] or due[:TILES]
            self._inflight.update(batch)
        return batch

    def _expire_candidates(self, now):
        """A candidate with no second look within 2 x WET_INTERVAL is dropped; its level stays unclear and its note
        says the look did not come in time. A camera a worker is checking now is left alone. The caller holds the lock."""
        for camid, st in self._state.items():
            if camid in self._inflight:
                continue
            if st.get("candidate") and now - st.get("checked_at", 0) > 2 * WET_INTERVAL:
                st.pop("candidate", None)
                st["note_th"] = _EXPIRED_TH

    def _due(self):
        """Cameras holding a frame worth a look, wet ones and candidates first, then never checked, then the oldest
        check. The caller holds the lock."""
        now = time.time()
        out = []
        for camid, (jpeg, ts, fp) in self._frames.items():
            if camid in self._inflight:
                continue
            st = self._state.get(camid)
            held = bool(st and st.get("candidate"))   # waiting for its second look
            wet = bool(st and (st["level"] in WET or held))
            if st and camid not in self._force:
                wait = WET_INTERVAL if wet else INTERVAL
                if ts <= st["frame_ts"] or now - st["checked_at"] < wait:
                    continue
                if not held and same_scene(fp, self._judged.get(camid)):
                    continue   # frozen feed: same picture as the one already judged (a candidate gets its second look anyway)
            out.append((0 if wet else 1 if not st else 2, st["checked_at"] if st else 0, camid))
        return [camid for _, _, camid in sorted(out)]

    def _budget_ok(self):
        return self._budget.allows()

    def _ask(self, jpeg, prompt, text, max_tokens):
        self._budget.spend()
        image = "data:image/jpeg;base64," + base64.standard_b64encode(jpeg).decode("ascii")
        return local_llm.default.chat(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}, {"type": "text", "text": text}]}],
            max_tokens=max_tokens, temperature=0.1, timeout=AGENT_TIMEOUT)

    def _screen(self, camids):
        with self._lock:
            frames = [(camid, *self._frames[camid]) for camid in camids]
            held = len(camids) == 1 and bool((self._state.get(camids[0]) or {}).get("candidate"))
        clean = []
        for camid, jpeg, ts, fp in frames:
            if CORRUPT_CHECK and _corrupt(jpeg):
                # a broken stream: no call to the model, no budget spent, shown as unclear
                self._record(camid, jpeg, ts, fp, CORRUPT_VERDICT, "corrupt")
            else:
                clean.append((camid, jpeg, ts, fp))
        frames = clean
        if not frames:
            return
        if held:
            # a candidate goes straight to the single-frame confirm; the grid is not needed for one camera
            if self._budget_ok():
                camid, jpeg, ts, fp = frames[0]
                v, extra = self._confirm(camid, jpeg, ts)
                self._record(camid, jpeg, ts, fp, v, "confirm", extra)
            return
        reply = _parse(self._ask(_mosaic([f[1] for f in frames]), SCREEN_PROMPT, f"{len(frames)} tiles.", 120 * len(frames)))
        by_tile = {}
        for t in reply.get("tiles") or []:
            try:
                by_tile[int(t.get("tile"))] = t
            except (TypeError, ValueError):
                continue
        failed = None
        for n, (camid, jpeg, ts, fp) in enumerate(frames, 1):
            if n not in by_tile:
                continue   # the model skipped this tile: it stays due and goes in the next grid
            v, source, extra = _verdict(by_tile[n]), "screen", None
            if v["level"] in WET:
                # water goes on the map only after a closer look at the frame alone; until then the camera stays due
                if not self._budget_ok():
                    continue
                try:
                    v, extra = self._confirm(camid, jpeg, ts)
                    source = "confirm"
                except Exception as e:  # noqa: BLE001 - the loop backs off after this grid
                    failed = failed or e
                    continue
            self._record(camid, jpeg, ts, fp, v, source, extra)
        if failed:
            raise failed

    def _confirm(self, camid, jpeg, ts):
        """One frame asked alone: the verdict to publish and the state fields to keep with it. The previous state is
        read before the model call, so a candidate that expires while the model thinks still counts."""
        with self._lock:
            prev = dict(self._state.get(camid) or {})
        answer = _parse(self._ask(_enlarge(jpeg), CONFIRM_PROMPT, "One camera.", 300))
        v = _verdict(answer)
        if NOTE_CHECK:
            v = _note_check(v)
        v = _stale_copy(v, answer.get("stamp"), ts)
        return _second_look(prev, v, ts, time.time())

    def _record(self, camid, jpeg, ts, fp, v, source, extra=None):
        with open(os.path.join(FRAME_DIR, f"{camid}.jpg"), "wb") as f:
            f.write(jpeg)
        prev = self._state.get(camid) or {}
        # when the water was first seen, kept while the camera stays wet. A candidate is unclear, so wet_since
        # starts at the second look, the one that is published.
        wet_since = (prev.get("wet_since") or ts) if v["level"] in WET else None
        with self._lock:
            self._state[camid] = {**v, "checked_at": int(time.time()), "frame_ts": int(ts), "source": source,
                                  "wet_since": int(wet_since) if wet_since else None, **(extra or {})}
            self._judged[camid] = fp
            self._force.discard(camid)

    # ------------------------------------------------------------ API
    def check_all(self):
        """Make every camera due now, instead of waiting for its turn."""
        with self._lock:
            self._force = set(self._frames)
        return {"queued": len(self._force)}

    def frame_path(self, camid):
        """The frame behind this camera's verdict, or None. camid must be a known camera (it becomes a path)."""
        if str(camid) not in self._cams:
            return None
        path = os.path.join(FRAME_DIR, f"{camid}.jpg")
        return path if os.path.exists(path) else None

    def frame_ts(self, camid):
        """When the frame behind this camera's verdict was taken (not when it was judged), or None."""
        return (self._state.get(str(camid)) or {}).get("frame_ts")

    def status(self, include_dry=False):
        now = time.time()
        counts = {level: 0 for level in LEVELS}
        stale_wet = 0
        items = []
        cams = self._cams
        with self._lock:
            state = {k: v for k, v in self._state.items() if k in cams}
            waiting = len(self._frames)
        for camid, st in state.items():
            cam = cams[camid]
            stale = now - st["frame_ts"] > STALE_MINUTES * 60
            counts[st["level"]] += 1
            if stale and st["level"] in WET:
                stale_wet += 1
            if st["level"] in WET or include_dry:
                items.append({"camid": camid, "title": cam.get("short_title") or cam.get("title") or camid,
                              "kind": cam.get("kind", "bma"), "organization": cam.get("organization") or "",
                              "road": cam.get("road") or "", "district": cam.get("district") or "",
                              "province": cam.get("province") or "",
                              "lat": cam.get("latitude"), "lng": cam.get("longitude"),
                              "level_th": LEVEL_TH[st["level"]], "stale": stale,
                              **st})
        items.sort(key=lambda i: (i["stale"], RANK[i["level"]], -i["confidence"]))
        return {"enabled": self.enabled(), "model": local_llm.default.model, "total": len(cams),
                "checked": len(state), "with_frame": waiting, "counts": counts, "stale_wet": stale_wet,
                "last_check": max((st["checked_at"] for st in state.values()), default=None),
                "calls_last_hour": self._budget.used(), "max_per_hour": MAX_PER_HOUR, "stale_minutes": STALE_MINUTES,
                "error": self.last_error, "items": items}
