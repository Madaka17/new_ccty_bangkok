"""Build a vehicle-heading dataset from every camera (574 BMA snapshots + the HLS feeds) for
train_wrongway_det.py. Nobody labels anything by hand: heading comes from motion.

    python collect_wrongway_dataset.py                    # 1 sweep over all BMA cameras, ~30 min
    python collect_wrongway_dataset.py --rounds 6 --hls   # 6 sweeps (spread over the day) + the 34 HLS cameras
    python collect_wrongway_dataset.py --cams 7,12,300    # only these BMA camera ids (for a quick look)
    python collect_wrongway_dataset.py --finalize         # write data.yaml + flipped copies, no new captures

How a label is made
    For each camera a short burst of frames is grabbed (BMA: --frames snapshots, ~1/s, which is all
    the site serves; HLS: --hls-frames sampled every --hls-interval s). yolo26x follows every vehicle
    through the burst: ByteTrack on the HLS video, a nearest-neighbour matcher on the 1 fps snapshots
    (a moving car has no overlap with itself a second later, so IoU tracking splits it). A track that
    moved at least 0.6 box-heights gets a heading from its motion vector in image space:
        toward  moving down  (front of the vehicle faces the camera)
        away    moving up    (rear faces the camera)
        left / right         mostly horizontal motion (side view)
    Every box of that track in every frame of the burst is written as <group>_<heading>, group being
    car (car/bus/truck) or moto (motorcycle/bicycle).
    Stopped vehicles (queues, red lights: most of Bangkok most of the day) cannot vote with motion.
    Each camera keeps a heading map (12x9 grid, one vote per moving track, heading_maps.json): once a
    cell has seen enough agreeing traffic, a vehicle standing in that cell is labeled with the cell's
    heading - a queued vehicle faces its lane. Run several sweeps: the maps fill in over the day.
    A frame is kept only when almost every vehicle in it got a label: unlabeled vehicles would
    otherwise be learned as background, and a detector that ignores queued cars is useless here.

Classes (0-7): car_toward car_away car_left car_right moto_toward moto_away moto_left moto_right
Split: by camera (--val share of the cameras go to val), so val measures new viewpoints.
Flip augmentation is done here, not in the trainer: a mirrored image swaps left <-> right, which
Ultralytics' fliplr cannot express, so train images get a *_flip.jpg twin with swapped labels.

Output: local/dataset_wrongway/{images,labels}/{train,val}/ + data.yaml + meta.jsonl
"""
import argparse
import hashlib
import json
import math
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(LOCAL_DIR)
sys.path.insert(0, BASE_DIR)
OUT_DIR = os.path.join(LOCAL_DIR, 'dataset_wrongway')
STATUS_FILE = os.path.join(LOCAL_DIR, 'logs', 'wrongway_status.json')   # read by watch_wrongway.py

HEADINGS = ['toward', 'away', 'left', 'right']
GROUPS = ['car', 'moto']
NAMES = [f'{g}_{h}' for g in GROUPS for h in HEADINGS]
MOTO_CLASSES = {1, 3}                 # COCO bicycle, motorcycle
VEHICLE_CLASSES = [1, 2, 3, 5, 7]
FLIP_SWAP = {NAMES.index(f'{g}_left'): NAMES.index(f'{g}_right') for g in GROUPS}
FLIP_SWAP.update({v: k for k, v in FLIP_SWAP.items()})

MIN_TRACK_OBS = 3               # observations for a stopped track to take the cell's heading
MIN_MOVE_HEIGHTS = 0.6          # displacement over the burst, in mean box heights
MIN_MOVE_PX = 5.0
MIN_MOVE_2OBS = 1.0             # a track seen only twice needs a clearer step (box heights) to count
VERTICAL_MIN = 0.55             # |uy| above this = toward/away
HORIZONTAL_MAX = 0.45           # |uy| below this = left/right; in between = ambiguous, no label
MAX_UNLABELED_SHARE = 0.5       # unlabeled vehicles / labeled vehicles a kept frame may have (both >= --min-h)
STILL_MAX_HEIGHTS = 0.15        # a track that moved less than this is "stopped" (may take the cell's heading)
GRID_COLS, GRID_ROWS = 12, 9
CELL_MIN_VOTES = 10             # moving tracks a cell needs before it labels stopped vehicles
CELL_MIN_AGREE = 0.85           # share of those votes on the winning heading
FRAMES_PER_BURST_KEPT = 3
MAX_WIDTH = 704                 # HLS frames are resized down to the BMA-like scale


def _fingerprint(frame):
    small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (24, 18), interpolation=cv2.INTER_AREA)
    return small.astype(np.int16)


def frozen(frames):
    """True when the burst is one repeated picture (BMA serves a stale frame for dead cameras)."""
    if len(frames) < 2:
        return True
    a = _fingerprint(frames[0])
    return all(int(np.abs(_fingerprint(f) - a).mean()) <= 2 for f in frames[1:])


class HeadingMaps:
    """Per camera: votes per grid cell per heading, from moving tracks. Persisted next to the dataset."""

    def __init__(self, path):
        self.path = path
        self.maps = {}
        try:
            with open(path, encoding='utf-8') as f:
                self.maps = json.load(f)
        except (OSError, ValueError):
            pass

    def _cell(self, camid, x, y, w, h):
        m = self.maps.setdefault(camid, [[[0, 0, 0, 0] for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)])
        r = min(GRID_ROWS - 1, max(0, int(y * GRID_ROWS / h)))
        c = min(GRID_COLS - 1, max(0, int(x * GRID_COLS / w)))
        return m[r][c]

    def vote(self, camid, x, y, w, h, heading):
        self._cell(camid, x, y, w, h)[heading] += 1

    def known(self, camid, x, y, w, h):
        """Dominant heading of the cell, or None while it is still learning / mixed."""
        votes = self._cell(camid, x, y, w, h)
        n = sum(votes)
        if n < CELL_MIN_VOTES:
            return None
        best = max(range(4), key=votes.__getitem__)
        return best if votes[best] >= CELL_MIN_AGREE * n else None

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.maps, f)

    def summary(self):
        cams = known = 0
        for m in self.maps.values():
            cams += 1
            known += sum(1 for row in m for v in row if sum(v) >= CELL_MIN_VOTES and max(v) >= CELL_MIN_AGREE * sum(v))
        return cams, known


def _foot(track):
    """Road contact point of a track: median centre x, median bottom y."""
    xs = sorted(t[1] for t in track)
    ys = sorted(t[2] + t[3] / 2 for t in track)
    return xs[len(xs) // 2], ys[len(ys) // 2]


def moved(track):
    _, x0, y0, _ = track[0]
    _, x1, y1, _ = track[-1]
    mean_h = sum(t[3] for t in track) / len(track)
    return math.hypot(x1 - x0, y1 - y0), mean_h


def heading_of(track):
    """Heading index for a track [(frame_i, cx, cy, h), ...] or None when it did not move enough / clearly."""
    if len(track) < 2:
        return None
    _, x0, y0, _ = track[0]
    _, x1, y1, _ = track[-1]
    dx, dy = x1 - x0, y1 - y0
    dist, mean_h = moved(track)
    if dist < max(MIN_MOVE_PX, (MIN_MOVE_HEIGHTS if len(track) >= 3 else MIN_MOVE_2OBS) * mean_h):
        return None
    # the path must be roughly straight: sum of step lengths close to the end-to-end distance
    steps = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(track, track[1:]))
    if steps > 1.6 * dist:
        return None
    uy = dy / dist
    if abs(uy) >= VERTICAL_MIN:
        return 0 if uy > 0 else 1
    if abs(uy) <= HORIZONTAL_MAX:
        return 3 if dx > 0 else 2
    return None


def track_bytetrack(model, frames, imgsz, conf):
    """ByteTrack through a burst of closely spaced frames (HLS video). Returns (per_frame, tracks):
    per_frame[i] = [(tid, cls_coco, box)], tracks[tid] = [(frame_i, cx, cy, h)]."""
    per_frame, tracks = [], {}
    for i, f in enumerate(frames):
        r = model.track(f, persist=i > 0, imgsz=imgsz, conf=conf, iou=0.5, classes=VEHICLE_CLASSES,
                        tracker='bytetrack.yaml', verbose=False)[0]
        rows = []
        if r.boxes is not None and r.boxes.id is not None:
            for (x1, y1, x2, y2), c, tid in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.id.tolist()):
                tid = int(tid)
                rows.append((tid, int(c), (x1, y1, x2, y2)))
                tracks.setdefault(tid, []).append((i, (x1 + x2) / 2, (y1 + y2) / 2, max(1.0, y2 - y1)))
        elif r.boxes is not None:
            for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist()):
                rows.append((-1, int(c), (x1, y1, x2, y2)))
        per_frame.append(rows)
    return per_frame, tracks


def track_nn(model, frames, imgsz, conf):
    """Nearest-neighbour association for ~1 fps snapshots (BMA), where a moving vehicle has no box
    overlap with itself one frame later so IoU trackers start a new id every frame. A detection joins
    the track whose predicted position (last position + last step) is closest, within a gate of a
    few box heights and a similar size, same vehicle group. Tracks with a missed frame end."""
    per_frame, tracks = [], {}
    active = {}          # tid -> (cx, cy, h, vx, vy, has_velocity, group)
    next_id = 1
    for i, f in enumerate(frames):
        r = model.predict(f, imgsz=imgsz, conf=conf, iou=0.5, classes=VEHICLE_CLASSES, verbose=False)[0]
        dets = [(int(c), (x1, y1, x2, y2)) for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist())]
        cands = []
        for j, (c, (x1, y1, x2, y2)) in enumerate(dets):
            cx, cy, h = (x1 + x2) / 2, (y1 + y2) / 2, max(1.0, y2 - y1)
            g = 1 if c in MOTO_CLASSES else 0
            for tid, (px, py, ph, vx, vy, has_v, pg) in active.items():
                if pg != g or not 0.6 <= h / ph <= 1.7:
                    continue
                scale = max(h, ph)
                d = math.hypot(cx - (px + vx), cy - (py + vy)) / scale
                if d <= (1.5 if has_v else 2.5):
                    cands.append((d, tid, j))
        cands.sort()
        used_t, used_d, rows, nxt = set(), set(), [], {}
        for d, tid, j in cands:
            if tid in used_t or j in used_d:
                continue
            used_t.add(tid)
            used_d.add(j)
            c, (x1, y1, x2, y2) = dets[j]
            cx, cy, h = (x1 + x2) / 2, (y1 + y2) / 2, max(1.0, y2 - y1)
            px, py, _, _, _, _, g = active[tid]
            nxt[tid] = (cx, cy, h, cx - px, cy - py, True, g)
            rows.append((tid, c, (x1, y1, x2, y2)))
            tracks[tid].append((i, cx, cy, h))
        for j, (c, (x1, y1, x2, y2)) in enumerate(dets):
            if j in used_d:
                continue
            cx, cy, h = (x1 + x2) / 2, (y1 + y2) / 2, max(1.0, y2 - y1)
            tid, next_id = next_id, next_id + 1
            nxt[tid] = (cx, cy, h, 0.0, 0.0, False, 1 if c in MOTO_CLASSES else 0)
            rows.append((tid, c, (x1, y1, x2, y2)))
            tracks[tid] = [(i, cx, cy, h)]
        active = nxt
        per_frame.append(rows)
    return per_frame, tracks


def label_burst(model, frames, imgsz, conf, maps=None, camid=None, tracker='nn', min_h=12):
    """Track one burst and label it. Returns per frame: (labeled [(cls, x1,y1,x2,y2)], unlabeled count).
    Moving tracks are labeled by motion and vote into the camera's heading map; stopped tracks take
    the heading of a known cell."""
    h_img, w_img = frames[0].shape[:2]
    per_frame, tracks = (track_nn if tracker == 'nn' else track_bytetrack)(model, frames, imgsz, conf)
    head = {tid: heading_of(t) for tid, t in tracks.items()}
    if maps is not None:
        for tid, hd in head.items():
            if hd is not None:
                fx, fy = _foot(tracks[tid])
                maps.vote(camid, fx, fy, w_img, h_img, hd)
        for tid, t in tracks.items():
            if head[tid] is None and len(t) >= MIN_TRACK_OBS:
                dist, mean_h = moved(t)
                if dist <= STILL_MAX_HEIGHTS * mean_h:
                    fx, fy = _foot(t)
                    head[tid] = maps.known(camid, fx, fy, w_img, h_img)
    out = []
    for rows in per_frame:
        labeled, unlabeled = [], 0
        for tid, c, box in rows:
            h = head.get(tid)
            if h is None:
                if box[3] - box[1] >= min_h:
                    unlabeled += 1
                continue
            group = 1 if c in MOTO_CLASSES else 0
            labeled.append((group * 4 + h, *box))
        out.append((labeled, unlabeled))
    return out


def pick_frames(results, min_h):
    """Indices of the frames worth keeping from one burst (spread out, well labeled)."""
    ok = []
    for i, (labeled, unlabeled) in enumerate(results):
        big = [b for b in labeled if b[4] - b[2] >= min_h]
        if not big:
            continue
        if unlabeled > max(1, MAX_UNLABELED_SHARE * len(big)):
            continue
        ok.append(i)
    if len(ok) <= FRAMES_PER_BURST_KEPT:
        return ok
    idx = np.linspace(0, len(ok) - 1, FRAMES_PER_BURST_KEPT).round().astype(int)
    return [ok[i] for i in dict.fromkeys(idx)]


def write_sample(split, stem, frame, labeled, meta_f, meta):
    h, w = frame.shape[:2]
    img_dir = os.path.join(OUT_DIR, 'images', split)
    lbl_dir = os.path.join(OUT_DIR, 'labels', split)
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        return False
    with open(os.path.join(img_dir, stem + '.jpg'), 'wb') as f:
        f.write(buf.tobytes())
    with open(os.path.join(lbl_dir, stem + '.txt'), 'w', encoding='utf-8') as f:
        for cls, x1, y1, x2, y2 in labeled:
            x1, x2 = max(0.0, x1), min(float(w), x2)
            y1, y2 = max(0.0, y1), min(float(h), y2)
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            f.write(f'{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}\n')
    meta_f.write(json.dumps(dict(meta, file=f'{split}/{stem}.jpg', boxes=len(labeled)), ensure_ascii=False) + '\n')
    return True


def write_status(**fields):
    """Progress for the status window (watch_wrongway.py). Best effort."""
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(dict(fields, ts=int(time.time())), f, ensure_ascii=False)
    except OSError:
        pass


def split_for(camid, val_share):
    return 'val' if int(hashlib.md5(str(camid).encode()).hexdigest()[:8], 16) % 1000 < val_share * 1000 else 'train'


# ------------------------------------------------------------------ frame sources
def bma_burst(session, camid, n, interval):
    frames = []
    for _ in range(n):
        t0 = time.time()
        raw = session.fetch_snapshot(str(camid), timeout=5.0)
        if raw:
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                frames.append(img)
        rest = interval - (time.time() - t0)
        if rest > 0:
            time.sleep(rest)
    return frames


def hls_burst(url, n, interval):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
    frames = []
    try:
        if not cap.isOpened():
            return frames
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        every = max(1, int(round(interval * fps)))
        i = 0
        while len(frames) < n:
            ok = cap.grab()
            if not ok:
                break
            if i % every == 0:
                ok, img = cap.retrieve()
                if ok and img is not None:
                    if img.shape[1] > MAX_WIDTH:
                        s = MAX_WIDTH / img.shape[1]
                        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                    frames.append(img)
            i += 1
    finally:
        cap.release()
    return frames


def load_cameras(ids, with_hls):
    cams = []
    with open(os.path.join(BASE_DIR, 'cameras_bma.json'), encoding='utf-8') as f:
        for c in json.load(f)['items']:
            if not ids or str(c['camid']) in ids:
                cams.append({'camid': str(c['camid']), 'title': c.get('title', ''), 'source': 'bma'})
    if with_hls:
        with open(os.path.join(BASE_DIR, 'cameras_bkk.json'), encoding='utf-8') as f:
            for c in json.load(f)['items']:
                url = c.get('hls_url') or c.get('vdourl')
                if url and (not ids or str(c['camid']) in ids):
                    cams.append({'camid': str(c['camid']), 'title': c.get('title', ''), 'source': 'hls', 'url': url})
    return cams


# ------------------------------------------------------------------ finalize
def finalize(flip):
    n_flip = 0
    if flip:
        img_dir = os.path.join(OUT_DIR, 'images', 'train')
        lbl_dir = os.path.join(OUT_DIR, 'labels', 'train')
        for name in sorted(os.listdir(img_dir)) if os.path.isdir(img_dir) else []:
            if not name.endswith('.jpg') or name.endswith('_flip.jpg'):
                continue
            stem = name[:-4]
            out_img = os.path.join(img_dir, stem + '_flip.jpg')
            if os.path.exists(out_img):
                continue
            lbl = os.path.join(lbl_dir, stem + '.txt')
            if not os.path.exists(lbl):
                continue
            img = cv2.imdecode(np.fromfile(os.path.join(img_dir, name), np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            rows = []
            with open(lbl, encoding='utf-8') as f:
                for line in f:
                    p = line.split()
                    if len(p) != 5:
                        continue
                    cls = int(p[0])
                    rows.append(f'{FLIP_SWAP.get(cls, cls)} {1.0 - float(p[1]):.6f} {p[2]} {p[3]} {p[4]}')
            ok, buf = cv2.imencode('.jpg', cv2.flip(img, 1), [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                continue
            with open(out_img, 'wb') as f:
                f.write(buf.tobytes())
            with open(os.path.join(lbl_dir, stem + '_flip.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(rows) + ('\n' if rows else ''))
            n_flip += 1
    counts = {}
    for split in ('train', 'val'):
        d = os.path.join(OUT_DIR, 'labels', split)
        per_cls = [0] * len(NAMES)
        n_img = 0
        if os.path.isdir(d):
            for name in os.listdir(d):
                n_img += 1
                with open(os.path.join(d, name), encoding='utf-8') as f:
                    for line in f:
                        try:
                            per_cls[int(line.split()[0])] += 1
                        except (ValueError, IndexError):
                            pass
        counts[split] = (n_img, per_cls)
    with open(os.path.join(OUT_DIR, 'data.yaml'), 'w', encoding='utf-8') as f:
        f.write(f"path: {OUT_DIR.replace(os.sep, '/')}\ntrain: images/train\nval: images/val\n")
        f.write(f'nc: {len(NAMES)}\nnames: {NAMES}\n')
    print(f'[wrongway] finalize: {n_flip} flipped twins added')
    for split, (n_img, per_cls) in counts.items():
        print(f'[wrongway] {split}: {n_img} images · ' + ', '.join(f'{n}={c}' for n, c in zip(NAMES, per_cls)))
    print(f'[wrongway] data.yaml -> {os.path.join(OUT_DIR, "data.yaml")}')


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rounds', type=int, default=1, help='sweeps over all cameras')
    ap.add_argument('--every', type=float, default=0.0, help='minutes between sweeps (0 = back to back)')
    ap.add_argument('--frames', type=int, default=10, help='snapshots per BMA burst (the site serves ~1 frame/s)')
    ap.add_argument('--interval', type=float, default=0.0, help='extra seconds between BMA snapshots (fetch alone takes ~1.1 s)')
    ap.add_argument('--workers', type=int, default=4, help='parallel camera fetches (the BMA site copes with ~4)')
    ap.add_argument('--hls', action='store_true', help='also read the HLS cameras from cameras_bkk.json')
    ap.add_argument('--hls-frames', type=int, default=24, help='frames per HLS burst (video: ByteTrack, dense sampling)')
    ap.add_argument('--hls-interval', type=float, default=0.2, help='seconds between sampled HLS frames')
    ap.add_argument('--cams', default='', help='comma-separated camera ids to restrict to')
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo26x.pt'))
    ap.add_argument('--imgsz', type=int, default=832, help='tracking resolution (352 px frames are upscaled)')
    ap.add_argument('--conf', type=float, default=0.3)
    ap.add_argument('--min-h', type=int, default=12, help='px: smaller boxes do not count towards keeping a frame')
    ap.add_argument('--val', type=float, default=0.15, help='share of cameras used for validation')
    ap.add_argument('--no-flip', action='store_true', help='skip the mirrored train copies at finalize')
    ap.add_argument('--finalize', action='store_true', help='only rebuild data.yaml (+ flips) from what is on disk')
    ap.add_argument('--limit', type=int, default=0, help='stop after this many images were written (0 = no limit)')
    args = ap.parse_args()

    if args.finalize:
        finalize(not args.no_flip)
        return

    from ultralytics import YOLO
    from bma_service import BmaSession
    model = YOLO(args.model)
    model.predict(np.zeros((288, 352, 3), dtype=np.uint8), imgsz=args.imgsz, verbose=False)   # warm up
    session = BmaSession()
    ids = {s.strip() for s in args.cams.split(',') if s.strip()}
    cams = load_cameras(ids, args.hls)
    if not cams:
        sys.exit('[wrongway] no cameras selected')
    n_val = sum(1 for c in cams if split_for(c['camid'], args.val) == 'val')
    print(f'[wrongway] {len(cams)} cameras ({n_val} val) · {args.frames} frames @ {args.interval}s · rounds {args.rounds}')
    os.makedirs(OUT_DIR, exist_ok=True)
    meta_f = open(os.path.join(OUT_DIR, 'meta.jsonl'), 'a', encoding='utf-8')
    maps = HeadingMaps(os.path.join(OUT_DIR, 'heading_maps.json'))
    print('[wrongway] heading maps: %d cameras, %d known cells' % maps.summary())
    written = 0
    stop = threading.Event()

    def fetch(cam):
        if stop.is_set():
            return cam, []
        try:
            if cam['source'] == 'hls':
                return cam, hls_burst(cam['url'], args.hls_frames, args.hls_interval)
            return cam, bma_burst(session, cam['camid'], args.frames, args.interval)
        except Exception as e:  # noqa: BLE001
            print(f'[wrongway] {cam["camid"]}: fetch failed: {e}')
            return cam, []

    try:
        for rnd in range(args.rounds):
            t0 = time.time()
            order = list(cams)
            random.shuffle(order)
            stats = {'frozen': 0, 'empty': 0, 'kept': 0, 'bursts': 0}
            # network-bound fetches in a pool; the GPU work stays on this thread (one tracker state)
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for n_cam, (cam, frames) in enumerate(pool.map(fetch, order), 1):
                    if stop.is_set():
                        break
                    write_status(step='collect', round=rnd + 1, rounds=args.rounds, camera=n_cam, cameras=len(order),
                                 images=written, kept_this_round=stats['kept'], last_camera=cam['title'][:40], maps_known=maps.summary()[1])
                    if len(frames) < MIN_TRACK_OBS:
                        stats['empty'] += 1
                        continue
                    if frozen(frames):
                        stats['frozen'] += 1
                        continue
                    stats['bursts'] += 1
                    results = label_burst(model, frames, args.imgsz, args.conf, maps, f"{cam['source']}:{cam['camid']}",
                                          tracker='bytetrack' if cam['source'] == 'hls' else 'nn', min_h=args.min_h)
                    keep = pick_frames(results, args.min_h)
                    if not keep:
                        continue
                    split = split_for(cam['camid'], args.val)
                    ts = int(time.time())
                    for i in keep:
                        stem = f"{cam['source']}_{cam['camid']}_{ts}_{i}"
                        if write_sample(split, stem, frames[i], results[i][0], meta_f,
                                        {'camid': cam['camid'], 'source': cam['source'], 'title': cam['title'], 'split': split}):
                            written += 1
                            stats['kept'] += 1
                    if args.limit and written >= args.limit:
                        stop.set()
                        break
            meta_f.flush()
            maps.save()
            print(f'[wrongway] round {rnd + 1}/{args.rounds}: {stats["bursts"]} bursts tracked, {stats["kept"]} images kept, '
                  f'{stats["frozen"]} frozen, {stats["empty"]} offline · {int(time.time() - t0)}s · total {written} · '
                  'heading maps: %d cameras, %d known cells' % maps.summary())
            if stop.is_set():
                break
            if rnd + 1 < args.rounds and args.every > 0:
                rest = args.every * 60 - (time.time() - t0)
                if rest > 0:
                    print(f'[wrongway] next sweep in {int(rest / 60)} min')
                    write_status(step='wait', round=rnd + 1, rounds=args.rounds, images=written, next_at=int(time.time() + rest),
                                 maps_known=maps.summary()[1])
                    time.sleep(rest)
    except KeyboardInterrupt:
        print('\n[wrongway] interrupted, finalizing what is on disk')
    finally:
        meta_f.close()
        maps.save()
    write_status(step='finalize', images=written)
    finalize(not args.no_flip)
    write_status(step='collected', images=written)


if __name__ == '__main__':
    main()
