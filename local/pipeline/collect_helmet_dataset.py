"""Build a helmet / no-helmet crop dataset from the CCTV frames, labelled by the vision model.

Motorcycle boxes (rider merged with the bike) are cut out of the frames in dataset/images/ (and,
with --live, fresh frames from the cameras), upscaled, and sent one by one to Gemini / Claude
with the same question the live monitor asks. Crops the model is sure about land in

    dataset_helmet/<train|val>/<helmet|no_helmet>/<stem>_<n>.jpg

ready for `python train_helmet.py` (YOLO11 classification). "unclear" answers are skipped, so
review a sample of both folders by hand before training: the model can only be as good as
these labels, and helmets on 40 px riders are hard even for a person.

    python collect_helmet_dataset.py                    # all frames in dataset/, up to 1500 API calls
    python collect_helmet_dataset.py --max-calls 300    # small first batch to check label quality
    python collect_helmet_dataset.py --live --rounds 20 --every 60   # also grab live frames
    python collect_helmet_dataset.py --bma --rounds 60 --every 240   # BMA snapshots (574 city cams, riders bigger)
    python collect_helmet_dataset.py --min-height 48    # stricter crop size (cleaner labels, fewer crops)

Needs GEMINI_API_KEY (or ANTHROPIC_API_KEY) in .env. Resumable: crops already labelled are skipped.
"""
import argparse
import glob
import json
import os
import random
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
import cv2

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # local/ (dataset, runs, logs)
BASE_DIR = os.path.dirname(LOCAL_DIR)  # project root (server, models, cameras, .env)
sys.path.insert(0, BASE_DIR)  # import root modules
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

from violation_service import HELMET_PROMPT, CROP_MARGIN

OUT_DIR = os.path.join(LOCAL_DIR, 'dataset_helmet')
SRC_DIR = os.path.join(LOCAL_DIR, 'dataset', 'images')
# Snapshots bma_service refreshes every ~4 min while server.py runs; each file is one camera
BMA_SNAP_DIR = os.path.join(BASE_DIR, 'cache', 'bma_snapshots')
DONE_FILE = os.path.join(OUT_DIR, 'labelled.json')
VAL_SHARE = 0.15
MOTO_CLASSES = (1, 3)
PERSON = 0


def rider_boxes(model, frame, min_h):
    """Motorcycle/bicycle boxes merged with an overlapping person box (the rider), as in VehicleTracker."""
    r = model(frame, imgsz=960, conf=0.15, iou=0.45, classes=[PERSON, *MOTO_CLASSES], verbose=False)[0]
    persons, motos = [], []
    for (x1, y1, x2, y2), cf, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
        (persons if int(c) == PERSON else motos).append([int(x1), int(y1), int(x2), int(y2), cf])
    out = []
    for x1, y1, x2, y2, cf in motos:
        rider = False
        for px1, py1, px2, py2, pcf in persons:
            if not (px2 < x1 or px1 > x2 or py2 < y1 - 40 or py1 > y2 + 40):
                x1, y1, x2, y2 = min(x1, px1), min(y1, py1), max(x2, px2), max(y2, py2)
                rider = True
        # No person on the bike (parked) -> nothing to label
        if rider and y2 - y1 >= min_h:
            out.append((x1, y1, x2, y2))
    return out


def crop(frame, box):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    mx, my = int((x2 - x1) * CROP_MARGIN), int((y2 - y1) * CROP_MARGIN)
    c = frame[max(0, y1 - my * 2):min(h, y2 + my), max(0, x1 - mx):min(w, x2 + mx)]
    if c.size == 0:
        return None
    scale = max(1.0, 256.0 / max(c.shape[:2]))
    if scale > 1.0:
        c = cv2.resize(c, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return c


def make_vision():
    """Same provider order as incident_service: Gemini first, then Claude."""
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if key:
        from google import genai
        from google.genai import types as T
        client = genai.Client(api_key=key)
        model = os.environ.get('GEMINI_VISION_MODEL', 'gemini-3.6-flash')

        def ask(jpeg):
            resp = client.models.generate_content(
                model=model,
                contents=[T.Part.from_bytes(data=jpeg, mime_type='image/jpeg'), T.Part(text='Crop of one motorcycle from a Bangkok traffic camera.')],
                config=T.GenerateContentConfig(system_instruction=HELMET_PROMPT, temperature=0.1, max_output_tokens=200, response_mime_type='application/json'),
            )
            return (resp.text or '').strip()
        return 'gemini', ask
    if os.environ.get('ANTHROPIC_API_KEY'):
        import base64
        import anthropic
        client = anthropic.Anthropic()

        def ask(jpeg):
            resp = client.messages.create(
                model=os.environ.get('CLAUDE_VISION_MODEL', 'claude-opus-5-5'), max_tokens=200, system=HELMET_PROMPT,
                output_config={'effort': 'low'},
                messages=[{'role': 'user', 'content': [
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': base64.standard_b64encode(jpeg).decode('ascii')}},
                    {'type': 'text', 'text': 'Crop of one motorcycle from a Bangkok traffic camera.'}]}])
            return ''.join(b.text for b in resp.content if b.type == 'text').strip()
        return 'claude', ask
    sys.exit('no vision provider: set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env')


def label(ask, jpeg, min_conf):
    text = ask(jpeg)
    s, e = text.find('{'), text.rfind('}')
    v = json.loads(text[s:e + 1]) if s >= 0 and e > s else {}
    riders, bad, conf = int(v.get('riders', 0)), int(v.get('no_helmet', 0)), float(v.get('confidence', 0))
    if riders == 0 or conf < min_conf:
        return 'unclear', conf
    return ('no_helmet' if bad > 0 else 'helmet'), conf


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--max-calls', type=int, default=1500, help='vision API calls this run')
    ap.add_argument('--min-height', type=int, default=36, help='rider+bike box height in px before upscaling')
    ap.add_argument('--min-conf', type=float, default=0.7, help='drop labels the model is less sure about')
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo26x.pt'))
    ap.add_argument('--live', action='store_true', help='also sample fresh frames from the cameras (see collect_dataset.py)')
    ap.add_argument('--bma', action='store_true', help='also use the BMA snapshot cache (needs server.py running); one pass per round')
    ap.add_argument('--rounds', type=int, default=5)
    ap.add_argument('--every', type=int, default=60)
    ap.add_argument('--sleep', type=float, default=0.3, help='seconds between API calls')
    args = ap.parse_args()

    for split in ('train', 'val'):
        for cls in ('helmet', 'no_helmet'):
            os.makedirs(os.path.join(OUT_DIR, split, cls), exist_ok=True)
    done = set(json.load(open(DONE_FILE, encoding='utf-8'))) if os.path.exists(DONE_FILE) else set()

    from ultralytics import YOLO
    det = YOLO(args.model)
    provider, ask = make_vision()
    print(f'[helmet] labelling with {provider}; {len(done)} frames already done')

    frames = sorted(glob.glob(os.path.join(SRC_DIR, '*', '*.jpg')))
    random.seed(7)
    random.shuffle(frames)
    # (stem, path-or-frame): files are read lazily in the loop so 2,000 frames do not sit in RAM
    sources = [(os.path.splitext(os.path.basename(p))[0], p) for p in frames if os.path.basename(p) not in done]
    state = {'calls': 0, 'reported': 0, 'counts': {'helmet': 0, 'no_helmet': 0, 'unclear': 0}}

    def process(batch):
        """Label every rider crop in these (stem, path-or-frame) sources; returns False once --max-calls is hit."""
        for stem, frame in batch:
            if isinstance(frame, str):
                frame = cv2.imread(frame)
            if frame is None:
                continue
            if state['calls'] >= args.max_calls:
                print(f'[helmet] reached --max-calls {args.max_calls}')
                return False
            for n, box in enumerate(rider_boxes(det, frame, args.min_height)):
                if state['calls'] >= args.max_calls:
                    break
                c = crop(frame, box)
                if c is None:
                    continue
                jpeg = cv2.imencode('.jpg', c, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
                try:
                    cls, conf = label(ask, jpeg, args.min_conf)
                except Exception as e:  # noqa: BLE001 - one bad call must not end the run
                    print(f'  ! {stem}#{n}: {e}')
                    time.sleep(5)
                    continue
                state['calls'] += 1
                state['counts'][cls] += 1
                if cls != 'unclear':
                    split = 'val' if random.random() < VAL_SHARE else 'train'
                    with open(os.path.join(OUT_DIR, split, cls, f'{stem}_{n}.jpg'), 'wb') as f:
                        f.write(jpeg)
                time.sleep(args.sleep)
            done.add(stem + '.jpg')
            if state['calls'] // 25 > state['reported']:
                state['reported'] = state['calls'] // 25
                print(f"[helmet] {state['calls']} calls: {state['counts']}")
        return True

    def bma_sources():
        """Snapshots not labelled yet; the stem carries the file mtime so each refresh counts once."""
        out = []
        for path in glob.glob(os.path.join(BMA_SNAP_DIR, '*.jpg')):
            stem = f'bma_{os.path.splitext(os.path.basename(path))[0]}_{int(os.path.getmtime(path))}'
            if stem + '.jpg' not in done:
                out.append((stem, path))
        return out

    def save_done():
        with open(DONE_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(done), f)

    try:
        more = process(sources)
        if more and (args.live or args.bma):
            cams = []
            if args.live:
                from collect_dataset import load_cameras, grab_frame
                cams = load_cameras()
            for rnd in range(args.rounds):
                batch = []
                if args.live:
                    random.shuffle(cams)
                    for cam in cams[:60]:
                        fr = grab_frame(cam)
                        if fr is not None:
                            batch.append((f'live_{cam["camid"]}_{datetime.now():%Y%m%d_%H%M%S}', fr))
                if args.bma:
                    batch.extend(bma_sources())
                print(f'[helmet] round {rnd + 1}/{args.rounds}: {len(batch)} frames')
                if not process(batch):
                    break
                save_done()
                if rnd + 1 < args.rounds:
                    time.sleep(args.every)
    finally:
        save_done()
    total = {s: {c: len(os.listdir(os.path.join(OUT_DIR, s, c))) for c in ('helmet', 'no_helmet')} for s in ('train', 'val')}
    print(f"[helmet] done: {state['calls']} calls this run, labels {state['counts']}; dataset now {total}")


if __name__ == '__main__':
    main()
