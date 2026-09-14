"""Collect training frames from the CCTV cameras and auto-label them with the current model.

Frames go to dataset/images/<split>/, YOLO-format labels to dataset/labels/<split>/ (same stem).
Labels come from yolo11x at a high resolution with test-time augmentation, so they are a
starting point to correct by hand (Label Studio / CVAT / Roboflow), not ground truth.

Usage:
    python collect_dataset.py                       # one pass over every camera, 1 frame each
    python collect_dataset.py --rounds 12 --every 300   # 12 passes, 5 min apart (about 1 hour)
    python collect_dataset.py --cameras ITICM_BMAMI0188 PER-3-008_2 --rounds 30 --every 120
    python collect_dataset.py --limit 2000          # stop once dataset holds 2000 images
    python collect_dataset.py --every 900 --until 20:00   # one pass every 15 min until 20:00

Run it in a separate terminal while the server is up; both share the GPU, so it uses one
inference per frame only. Run at different times of day (morning / rush hour / night / rain)
so the dataset covers the conditions the live model will see.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime

import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, 'dataset')
CAMERAS_FILE = os.path.join(BASE_DIR, 'cameras_bkk.json')

# Dataset classes (index = YOLO class id). Ids are kept identical to COCO so a fine-tuned model
# drops into the live detector (TARGET_CLASSES / CLASS_CONFIG in yolo_detector.py) unchanged;
# the two placeholder ids are never labelled. Add Thai-specific classes (tuk-tuk, songthaew)
# at id 8+ here and in dataset.yaml when you start correcting labels by hand.
CLASSES = ['person', 'bicycle', 'car', 'motorcycle', 'unused_4', 'bus', 'unused_6', 'truck']
COCO_TO_DATASET = {0: 0, 1: 1, 2: 2, 3: 3, 5: 5, 7: 7}
VAL_SHARE = 0.15


def load_cameras(only=None):
    with open(CAMERAS_FILE, encoding='utf-8') as f:
        cams = json.load(f)['items']
    cams = [c for c in cams if c.get('hls_url') or c.get('vdourl')]
    if only:
        wanted = set(only)
        cams = [c for c in cams if c['camid'] in wanted]
    return cams


def grab_frame(cam, timeout_ms=8000):
    """One frame from the camera (HLS first, MJPEG fallback). Returns BGR array or None."""
    for url in (cam.get('hls_url'), cam.get('vdourl')):
        if not url:
            continue
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms, cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms])
        try:
            if not cap.isOpened():
                continue
            # Skip the first few frames: HLS often starts on a stale keyframe
            frame = None
            for _ in range(5):
                ok, f = cap.read()
                if ok and f is not None and f.size:
                    frame = f
            if frame is not None:
                return frame
        finally:
            cap.release()
    return None


def auto_label(model, frame, conf):
    """Run the model with TTA at high resolution; returns YOLO label lines (normalized xywh)."""
    r = model(frame, imgsz=1280, conf=conf, iou=0.5, augment=True, classes=list(COCO_TO_DATASET), verbose=False)[0]
    h, w = frame.shape[:2]
    lines = []
    for box in r.boxes:
        cls = COCO_TO_DATASET[int(box.cls[0])]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cx, cy, bw, bh = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h
        lines.append(f'{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}')
    return lines


def dataset_size():
    n = 0
    for split in ('train', 'val'):
        d = os.path.join(DATASET_DIR, 'images', split)
        n += len(os.listdir(d)) if os.path.isdir(d) else 0
    return n


def write_yaml():
    path = os.path.join(DATASET_DIR, 'dataset.yaml')
    if os.path.exists(path):
        return
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'path: {DATASET_DIR}\n')
        f.write('train: images/train\nval: images/val\n\n')
        f.write('names:\n')
        for i, name in enumerate(CLASSES):
            f.write(f'  {i}: {name}\n')
    print(f'[dataset] wrote {path}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cameras', nargs='*', help='camids to sample (default: every camera with a stream)')
    ap.add_argument('--rounds', type=int, default=1, help='passes over the camera list')
    ap.add_argument('--every', type=int, default=300, help='seconds between passes')
    ap.add_argument('--limit', type=int, default=0, help='stop when the dataset reaches this many images (0 = no limit)')
    ap.add_argument('--until', help='HH:MM local time to stop at (overrides --rounds when reached first)')
    ap.add_argument('--conf', type=float, default=0.25, help='auto-label confidence floor')
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo11x.pt'))
    args = ap.parse_args()
    stop_at = None
    if args.until:
        hh, mm = map(int, args.until.split(':'))
        stop_at = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
        if stop_at <= datetime.now():
            sys.exit(f'--until {args.until} is already past')
        args.rounds = 10 ** 6

    cams = load_cameras(args.cameras)
    if not cams:
        sys.exit('no cameras matched')
    for split in ('train', 'val'):
        os.makedirs(os.path.join(DATASET_DIR, 'images', split), exist_ok=True)
        os.makedirs(os.path.join(DATASET_DIR, 'labels', split), exist_ok=True)
    write_yaml()

    from ultralytics import YOLO
    model = YOLO(args.model)
    print(f'[dataset] {len(cams)} cameras, {args.rounds} round(s), have {dataset_size()} images')

    for rnd in range(args.rounds):
        random.shuffle(cams)
        saved = 0
        for cam in cams:
            if args.limit and dataset_size() >= args.limit:
                print(f'[dataset] limit {args.limit} reached')
                return
            if stop_at and datetime.now() >= stop_at:
                print(f'[dataset] reached {args.until}, total {dataset_size()}')
                return
            frame = grab_frame(cam)
            if frame is None:
                print(f'  - {cam["camid"]}: no frame')
                continue
            lines = auto_label(model, frame, args.conf)
            split = 'val' if random.random() < VAL_SHARE else 'train'
            stem = f'{cam["camid"]}_{datetime.now():%Y%m%d_%H%M%S}'
            cv2.imwrite(os.path.join(DATASET_DIR, 'images', split, stem + '.jpg'), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
            with open(os.path.join(DATASET_DIR, 'labels', split, stem + '.txt'), 'w') as f:
                f.write('\n'.join(lines) + ('\n' if lines else ''))
            saved += 1
            print(f'  + {stem} [{split}] {len(lines)} boxes')
        print(f'[dataset] round {rnd + 1}/{args.rounds}: saved {saved}, total {dataset_size()}')
        if stop_at and datetime.now() >= stop_at:
            print(f'[dataset] reached {args.until}, total {dataset_size()}')
            return
        if rnd + 1 < args.rounds:
            time.sleep(args.every)


if __name__ == '__main__':
    main()
