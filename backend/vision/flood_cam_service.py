"""
Flood watch over every BMA camera: is there water on the road in front of the camera right now?

Flow:
    BmaScanner hands every raw snapshot to observe() (each camera about every 4 min)
    -> the worker takes the cameras due for a check: never checked, or checked more than INTERVAL
       ago (WET_INTERVAL for the ones that had water) and holding a newer frame than that check
    -> screen: TILES frames per call, tiled in a grid with a big number on each tile, one vision
       call to the Qwen model behind LOCAL_LLM_* (9 tiles take about 5 s)
    -> confirm: every tile the screen calls puddle / flooded / severe is asked again on its own, so
       one misread tile in a grid does not put a false flood on the map; this verdict is final
    -> state per camera in cache/flood_cams.json, the frame it judged in cache/flood_cams/<camid>.jpg

Levels: none, puddle (water pooling at the kerb, lanes clear), flooded (water over part or all of a
lane), severe (road under deep water), unclear (dark, blurred, rain on the lens, no signal).

A frame that has not changed since the last check (a frozen feed) is not asked again. At start the
watch takes the scanner's last saved snapshots younger than SEED_MAX_AGE, so the map has something
while the BMA site is down. Every verdict keeps the time of its frame, and the map fades the ones
whose frame is older than STALE_MINUTES.

At most MAX_PER_HOUR vision calls. Served by /api/flood/cameras*.
"""
import base64
import json
import os
import threading
import time
from collections import deque

import cv2
import numpy as np

from backend.bma.bma_service import CACHE_DIR as SNAPSHOT_DIR   # the scanner's last annotated frame per camera
from backend.core import local_llm
from backend.core.instance import DATA_DIR   # cache root: project root, or local/stage for the test server
from backend.vision.helmet_service import _fingerprint, _same_scene

STATE_FILE = os.path.join(DATA_DIR, "cache", "flood_cams.json")
FRAME_DIR = os.path.join(DATA_DIR, "cache", "flood_cams")

INTERVAL = int(os.getenv("FLOOD_CAM_INTERVAL", "600"))           # seconds between checks of a dry camera
WET_INTERVAL = int(os.getenv("FLOOD_CAM_WET_INTERVAL", "300"))   # ... of a camera that had water, to see it drain
MAX_PER_HOUR = int(os.getenv("FLOOD_CAM_MAX_PER_HOUR", "900"))   # a full round is ~64 screen calls + confirms
GRID = 3
TILES = GRID * GRID
TILE_W, TILE_H = 352, 288      # the BMA frame size
STALE_MINUTES = 60
SEED_MAX_AGE = 12 * 3600
AGENT_TIMEOUT = 120
ERROR_BACKOFF = 60

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
    '"confidence": <0..1>, "note_th": "<one short Thai sentence about the water you see>"}]} with one entry per tile.'
)
CONFIRM_PROMPT = (
    "You are the flood-watch agent of the Bangkok traffic control room. The image is one low-resolution street "
    "CCTV snapshot. Decide whether flood water stands or flows on the road surface. " + _LEVEL_RULES + " "
    "Never guess: when unsure between two levels, pick the lower one. "
    'Answer ONLY with JSON: {"level": "none|puddle|flooded|severe|unclear", "confidence": <0..1>, '
    '"note_th": "<one short Thai sentence: where the water is and how deep it looks>"}.'
)


def _parse(text):
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]) if start >= 0 and end > start else {}


def _verdict(v):
    level = str(v.get("level", "")).strip().lower()
    try:
        conf = min(1.0, max(0.0, float(v.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {"level": level if level in LEVELS else "unclear", "confidence": round(conf, 2),
            "note_th": str(v.get("note_th") or "")[:200]}


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
    """The single frame at twice its size: the model sees the kerb and the water line, not a few pixels."""
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jpeg
    img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


class FloodCamWatch:
    def __init__(self, cameras):
        self._cams = {str(c["camid"]): c for c in cameras}
        self._frames = {}      # camid -> (jpeg, frame ts, fingerprint), newest from the scanner
        self._state = {}       # camid -> verdict dict (see _record)
        self._judged = {}      # camid -> fingerprint of the frame behind the current verdict
        self._force = set()    # camids to check now whatever their turn (check_all)
        self._calls = deque()
        self._lock = threading.Lock()
        self.last_error = None
        os.makedirs(FRAME_DIR, exist_ok=True)
        self._load()

    def enabled(self):
        return local_llm.default.enabled()

    def _load(self):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                self._state = {k: v for k, v in json.load(f).items() if k in self._cams}
        except (OSError, ValueError):
            self._state = {}

    def _save(self):
        with self._lock:
            data = json.dumps(self._state, ensure_ascii=False)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, STATE_FILE)

    # ------------------------------------------------------------ frames in
    def observe(self, cam, frame):
        """Keep the newest raw frame of this camera (called by BmaScanner for every snapshot)."""
        camid = str(cam.get("camid"))
        if camid not in self._cams:
            return
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ok:
            with self._lock:
                self._frames[camid] = (buf.tobytes(), time.time(), _fingerprint(frame))

    def _seed(self):
        """The scanner's saved snapshots, so a restart while the BMA site is down still has frames to check."""
        now = time.time()
        for camid in self._cams:
            path = os.path.join(SNAPSHOT_DIR, f"{camid}.jpg")
            try:
                ts = os.path.getmtime(path)
                if now - ts > SEED_MAX_AGE:
                    continue
                with open(path, "rb") as f:
                    jpeg = f.read()
            except OSError:
                continue
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            with self._lock:
                self._frames.setdefault(camid, (jpeg, ts, _fingerprint(img)))

    # ------------------------------------------------------------ worker
    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="flood-cam-watch").start()

    def _loop(self):
        time.sleep(20)   # let the server finish starting
        self._seed()
        while True:
            try:
                batch = self._due()[:TILES] if self.enabled() else []
                if not batch or not self._budget_ok():
                    time.sleep(20)
                    continue
                try:
                    self._screen(batch)
                finally:
                    self._save()
                self.last_error = None
            except Exception as e:  # noqa: BLE001 - the model endpoint may be down; try again later
                self.last_error = f"{type(e).__name__}: {str(e)[:160]}"
                print(f"[FloodCam] check failed: {self.last_error}")
                time.sleep(ERROR_BACKOFF)

    def _due(self):
        """Cameras holding a frame worth a look, wet ones first, then never checked, then the oldest check."""
        now = time.time()
        out = []
        with self._lock:
            for camid, (jpeg, ts, fp) in self._frames.items():
                st = self._state.get(camid)
                if st and camid not in self._force:
                    wait = WET_INTERVAL if st["level"] in WET else INTERVAL
                    if ts <= st["frame_ts"] or now - st["checked_at"] < wait:
                        continue
                    if _same_scene(fp, self._judged.get(camid)):
                        continue   # frozen feed: same picture as the one already judged
                out.append((0 if st and st["level"] in WET else 1 if not st else 2, st["checked_at"] if st else 0, camid))
        return [camid for _, _, camid in sorted(out)]

    def _budget_ok(self):
        now = time.time()
        while self._calls and now - self._calls[0] > 3600:
            self._calls.popleft()
        return len(self._calls) < MAX_PER_HOUR

    def _ask(self, jpeg, prompt, text, max_tokens):
        self._calls.append(time.time())
        image = "data:image/jpeg;base64," + base64.standard_b64encode(jpeg).decode("ascii")
        return local_llm.default.chat(
            [{"role": "system", "content": prompt},
             {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}, {"type": "text", "text": text}]}],
            max_tokens=max_tokens, temperature=0.1, timeout=AGENT_TIMEOUT)

    def _screen(self, camids):
        with self._lock:
            frames = [(camid, *self._frames[camid]) for camid in camids]
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
            v, source = _verdict(by_tile[n]), "screen"
            if v["level"] in WET:
                # water goes on the map only after a closer look at the frame alone; until then the camera stays due
                if not self._budget_ok():
                    continue
                try:
                    v, source = _verdict(_parse(self._ask(_enlarge(jpeg), CONFIRM_PROMPT, "One camera.", 300))), "confirm"
                except Exception as e:  # noqa: BLE001 - the loop backs off after this grid
                    failed = failed or e
                    continue
            self._record(camid, jpeg, ts, fp, v, source)
        if failed:
            raise failed

    def _record(self, camid, jpeg, ts, fp, v, source):
        with open(os.path.join(FRAME_DIR, f"{camid}.jpg"), "wb") as f:
            f.write(jpeg)
        prev = self._state.get(camid) or {}
        # when the water was first seen, kept while the camera stays wet
        wet_since = (prev.get("wet_since") or ts) if v["level"] in WET else None
        with self._lock:
            self._state[camid] = {**v, "checked_at": int(time.time()), "frame_ts": int(ts), "source": source,
                                  "wet_since": int(wet_since) if wet_since else None}
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

    def status(self, include_dry=False):
        now = time.time()
        counts = {level: 0 for level in LEVELS}
        stale_wet = 0
        items = []
        with self._lock:
            state = dict(self._state)
            waiting = len(self._frames)
        for camid, st in state.items():
            cam = self._cams[camid]
            stale = now - st["frame_ts"] > STALE_MINUTES * 60
            counts[st["level"]] += 1
            if stale and st["level"] in WET:
                stale_wet += 1
            if st["level"] in WET or include_dry:
                items.append({"camid": camid, "title": cam.get("title") or cam.get("short_title") or camid,
                              "road": cam.get("road") or "", "district": cam.get("district") or "",
                              "lat": cam.get("latitude"), "lng": cam.get("longitude"),
                              "level_th": LEVEL_TH[st["level"]], "stale": stale, **st})
        items.sort(key=lambda i: (i["stale"], RANK[i["level"]], -i["confidence"]))
        self._budget_ok()
        return {"enabled": self.enabled(), "model": local_llm.default.model, "total": len(self._cams),
                "checked": len(state), "with_frame": waiting, "counts": counts, "stale_wet": stale_wet,
                "last_check": max((st["checked_at"] for st in state.values()), default=None),
                "calls_last_hour": len(self._calls), "max_per_hour": MAX_PER_HOUR, "stale_minutes": STALE_MINUTES,
                "error": self.last_error, "items": items}
