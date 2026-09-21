"""Re-label every frame already in dataset/ with the current auto-labeller (collect_dataset.auto_label).

Use after changing CLASS_CONF / tiling so old frames get the same (better) motorcycle labels as new
ones. Images are untouched; label files are rewritten. A backup of the labels folder is kept in
dataset/labels_backup_<timestamp>/ so hand-corrected labels can be restored.

    python relabel_dataset.py                 # both splits
    python relabel_dataset.py --split val     # one split
    python relabel_dataset.py --keep-manual   # skip label files edited after their image was saved
"""
import argparse
import glob
import os
import shutil
import sys
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
import cv2

from collect_dataset import DATASET_DIR, auto_label

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # local/ (dataset, runs, logs)
BASE_DIR = os.path.dirname(LOCAL_DIR)  # project root (server, models, cameras, .env)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--split', choices=['train', 'val'], help='default: both')
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo26x.pt'))
    ap.add_argument('--keep-manual', action='store_true', help='skip labels edited after the image was saved')
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.model)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(DATASET_DIR, f'labels_backup_{stamp}')
    shutil.copytree(os.path.join(DATASET_DIR, 'labels'), backup)
    print(f'[relabel] labels backed up to {backup}')

    for split in ([args.split] if args.split else ['train', 'val']):
        imgs = sorted(glob.glob(os.path.join(DATASET_DIR, 'images', split, '*.jpg')))
        before = after = moto_before = moto_after = skipped = 0
        for i, path in enumerate(imgs, 1):
            stem = os.path.splitext(os.path.basename(path))[0]
            lab = os.path.join(DATASET_DIR, 'labels', split, stem + '.txt')
            old = list(open(lab, encoding='utf-8')) if os.path.exists(lab) else []
            if args.keep_manual and os.path.exists(lab) and os.path.getmtime(lab) > os.path.getmtime(path) + 5:
                skipped += 1
                continue
            frame = cv2.imread(path)
            if frame is None:
                continue
            lines = auto_label(model, frame)
            with open(lab, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + ('\n' if lines else ''))
            before += len(old)
            after += len(lines)
            moto_before += sum(1 for l in old if l.split() and l.split()[0] == '3')
            moto_after += sum(1 for l in lines if l.split()[0] == '3')
            if i % 50 == 0 or i == len(imgs):
                print(f'[relabel] {split} {i}/{len(imgs)}: boxes {before} -> {after}, motorcycles {moto_before} -> {moto_after}, skipped {skipped}')


if __name__ == '__main__':
    main()
