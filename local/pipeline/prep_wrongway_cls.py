"""Turn the wrong-way detection dataset into a heading classification dataset for train_wrongway_cls.py.

    python prep_wrongway_cls.py                 # local/dataset_wrongway -> local/dataset_wrongway_cls
    python prep_wrongway_cls.py --min-h 14      # skip smaller boxes

The detector trained on local/dataset_wrongway (wrongway_det.pt) never learned to find the vehicles
(mAP50 ~0.10): finding a car and telling which way it faces in one 8-class head is too much for noisy
motion labels. The server already finds every vehicle with yolo26x (tiled, shared with the counter),
so only the heading is left to learn: every toward/away box becomes one crop in <split>/<toward|away>/,
car and motorcycle together (motorcycles are too few on their own). toward shows the front of the
vehicle, away its rear, which a still frame can tell apart. left/right come from sideways motion and
show a front, a rear or a side depending on the camera angle, so they are left out.
"""
import argparse
import os
import shutil

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'dataset_wrongway')
DST = os.path.join(ROOT, 'dataset_wrongway_cls')
HEADINGS = ['toward', 'away', 'left', 'right']   # label class id % 4
KEEP = ('toward', 'away')
MARGIN = 0.15      # context around the box: road, shadow, lane marks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-h', type=int, default=12, help='smallest box height in px on the source frame')
    args = ap.parse_args()
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    counts = {}
    for split in ('train', 'val'):
        for h in KEEP:
            os.makedirs(os.path.join(DST, split, h), exist_ok=True)
        img_dir, lbl_dir = os.path.join(SRC, 'images', split), os.path.join(SRC, 'labels', split)
        for name in sorted(os.listdir(img_dir)):
            stem = os.path.splitext(name)[0]
            lbl = os.path.join(lbl_dir, stem + '.txt')
            if not os.path.exists(lbl):
                continue
            img = cv2.imread(os.path.join(img_dir, name))
            if img is None:
                continue
            H, W = img.shape[:2]
            with open(lbl) as f:
                rows = [ln.split() for ln in f if ln.strip()]
            for n, (c, cx, cy, bw, bh) in enumerate(rows):
                head = HEADINGS[int(c) % 4]
                cx, cy, bw, bh = float(cx) * W, float(cy) * H, float(bw) * W, float(bh) * H
                if head not in KEEP or bh < args.min_h:
                    continue
                mx, my = bw * (0.5 + MARGIN), bh * (0.5 + MARGIN)
                crop = img[max(0, int(cy - my)):min(H, int(cy + my)), max(0, int(cx - mx)):min(W, int(cx + mx))]
                if crop.size == 0:
                    continue
                cv2.imwrite(os.path.join(DST, split, head, f'{stem}_{n}.jpg'), crop)
                counts[(split, head)] = counts.get((split, head), 0) + 1
    for split in ('train', 'val'):
        print(split, {h: counts.get((split, h), 0) for h in KEEP})


if __name__ == '__main__':
    main()
