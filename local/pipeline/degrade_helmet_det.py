"""Stage-2 dataset for the helmet detector: the same images degraded to look like BMA CCTV crops
(352x288 frames, riders 30-60 px, JPEG, blur, night). Boxes are unchanged, so the labels are copied.

    python degrade_helmet_det.py                 # local/dataset_helmet_det -> local/dataset_helmet_det_blur
    python degrade_helmet_det.py --copies 3      # degraded variants per train image (default 2)

Output: local/dataset_helmet_det_blur/{images,labels}/{train,val}/ + data.yaml
    train: originals + N degraded copies       val: originals + 1 degraded copy (so mAP reflects blurry input)
Then fine-tune:  python train_helmet_det.py --model ..\\..\\helmet_det.pt --data blur --name yolo26x_blur --epochs 40
"""
import argparse
import glob
import os
import random
import shutil
import sys

import cv2
import numpy as np

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(LOCAL_DIR, 'dataset_helmet_det')
OUT = os.path.join(LOCAL_DIR, 'dataset_helmet_det_blur')


def degrade(img, rng):
    """One random CCTV-like degradation: downscale, blur, noise, JPEG, low light."""
    h, w = img.shape[:2]
    out = img
    # 1. resolution: shrink so the whole photo is 90-220 px wide (heads become 6-15 px), then back up
    tw = rng.randint(90, 220)
    small = cv2.resize(out, (tw, max(1, int(h * tw / w))), interpolation=cv2.INTER_AREA)
    out = cv2.resize(small, (w, h), interpolation=rng.choice([cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_NEAREST]))
    # 2. motion / focus blur
    if rng.random() < 0.7:
        k = rng.choice([3, 5, 7])
        if rng.random() < 0.5:
            out = cv2.GaussianBlur(out, (k, k), 0)
        else:
            kernel = np.zeros((k, k), np.float32)
            kernel[k // 2, :] = 1.0 / k          # horizontal motion streak
            if rng.random() < 0.5:
                kernel = kernel.T
            out = cv2.filter2D(out, -1, kernel)
    # 3. night: darker + colour cast + sensor noise
    if rng.random() < 0.45:
        gain = rng.uniform(0.25, 0.6)
        out = cv2.convertScaleAbs(out, alpha=gain, beta=rng.uniform(-10, 10))
        noise = np.random.normal(0, rng.uniform(4, 14), out.shape).astype(np.float32)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    elif rng.random() < 0.5:
        noise = np.random.normal(0, rng.uniform(2, 7), out.shape).astype(np.float32)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    # 4. heavy JPEG like the BMA feed
    q = rng.randint(25, 60)
    ok, buf = cv2.imencode('.jpg', out, [cv2.IMWRITE_JPEG_QUALITY, q])
    if ok:
        out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--copies', type=int, default=2)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()
    if not os.path.isdir(SRC):
        sys.exit(f'[degrade] {SRC} missing; run prep_helmet_det.py first')
    rng = random.Random(args.seed)
    np.random.seed(args.seed)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    counts = {}
    for split, copies in (('train', args.copies), ('val', 1)):
        img_dir, lbl_dir = os.path.join(OUT, 'images', split), os.path.join(OUT, 'labels', split)
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(lbl_dir, exist_ok=True)
        n = 0
        for src in sorted(glob.glob(os.path.join(SRC, 'images', split, '*.*'))):
            stem = os.path.splitext(os.path.basename(src))[0]
            lbl = os.path.join(SRC, 'labels', split, stem + '.txt')
            img = cv2.imread(src)
            if img is None:
                continue
            variants = [(stem, img)] + [(f'{stem}_d{i}', degrade(img, rng)) for i in range(copies)]
            for name, im in variants:
                cv2.imwrite(os.path.join(img_dir, name + '.jpg'), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
                if os.path.exists(lbl):
                    shutil.copy(lbl, os.path.join(lbl_dir, name + '.txt'))
                n += 1
        counts[split] = n
    with open(os.path.join(OUT, 'data.yaml'), 'w', encoding='utf-8') as f:
        f.write(f'path: {OUT}\ntrain: images/train\nval: images/val\nnames:\n  0: helmet\n  1: no_helmet\n')
    print(f'[degrade] done {counts} -> {OUT}')


if __name__ == '__main__':
    main()
