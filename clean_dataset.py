"""Automatic QA pass over the auto-labelled dataset before training.

Removes what a human labeller would reject without looking twice:
  - boxes smaller than MIN_PX pixels on either side (noise from TTA at 1280)
  - boxes that are mostly outside the frame
  - near-duplicate images from the same camera (static scene, nothing moved)
  - surplus empty frames (keeps up to EMPTY_SHARE of the set as negatives)

Prints per-class counts afterwards. Does not replace manual correction; it only trims the
obvious errors so the model does not learn them.
"""
import glob
import os
from collections import Counter

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, 'dataset')
MIN_PX = 8
MAX_OUTSIDE = 0.4       # drop a box if more than this share of its area is off-frame
DUP_DIFF = 2.5          # mean abs grey difference (0-255) under which two frames count as identical
EMPTY_SHARE = 0.10
NAMES = {0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}


def read_labels(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path):
        p = line.split()
        if len(p) == 5:
            out.append((int(p[0]), *map(float, p[1:])))
    return out


def clean_boxes(boxes, w, h):
    kept = []
    for cls, cx, cy, bw, bh in boxes:
        pw, ph = bw * w, bh * h
        if pw < MIN_PX or ph < MIN_PX:
            continue
        x1, y1, x2, y2 = cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2
        inside = max(0.0, min(1.0, x2) - max(0.0, x1)) * max(0.0, min(1.0, y2) - max(0.0, y1))
        if inside / max(1e-9, bw * bh) < 1 - MAX_OUTSIDE:
            continue
        kept.append((cls, min(1, max(0, cx)), min(1, max(0, cy)), min(1, bw), min(1, bh)))
    return kept


def thumb(img):
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 48)).astype(np.float32)


def main():
    removed_img = removed_box = 0
    counts = Counter()
    for split in ('train', 'val'):
        img_dir = os.path.join(DATASET_DIR, 'images', split)
        lab_dir = os.path.join(DATASET_DIR, 'labels', split)
        files = sorted(glob.glob(os.path.join(img_dir, '*.jpg')))
        last_by_cam = {}
        empties = []
        for path in files:
            stem = os.path.splitext(os.path.basename(path))[0]
            cam = stem.rsplit('_', 2)[0]
            img = cv2.imread(path)
            if img is None:
                os.remove(path)
                removed_img += 1
                continue
            h, w = img.shape[:2]
            t = thumb(img)
            prev = last_by_cam.get(cam)
            if prev is not None and float(np.abs(t - prev).mean()) < DUP_DIFF:
                os.remove(path)
                lp = os.path.join(lab_dir, stem + '.txt')
                if os.path.exists(lp):
                    os.remove(lp)
                removed_img += 1
                continue
            last_by_cam[cam] = t
            lp = os.path.join(lab_dir, stem + '.txt')
            boxes = read_labels(lp)
            kept = clean_boxes(boxes, w, h)
            removed_box += len(boxes) - len(kept)
            with open(lp, 'w') as f:
                f.write(''.join(f'{c} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n' for c, cx, cy, bw, bh in kept))
            if not kept:
                empties.append((path, lp))
            for c, *_ in kept:
                counts[NAMES.get(c, c)] += 1
        keep_empty = int(EMPTY_SHARE * max(1, len(files)))
        for path, lp in empties[keep_empty:]:
            os.remove(path)
            os.remove(lp)
            removed_img += 1
        print(f'[clean] {split}: {len(glob.glob(os.path.join(img_dir, "*.jpg")))} images kept')
    print(f'[clean] removed {removed_img} images, {removed_box} boxes')
    print('[clean] boxes per class:', dict(counts.most_common()))


if __name__ == '__main__':
    main()
