"""Train the helmet / no-helmet crop classifier on dataset_helmet/ (from collect_helmet_dataset.py).

    python train_helmet.py                      # yolo11n-cls, 40 epochs, 160 px
    python train_helmet.py --model yolo11s-cls.pt --epochs 60

Output: runs/helmet/<name>/weights/best.pt copied to helmet_cls.pt. violation_service.py loads
helmet_cls.pt automatically and then classifies every rider crop locally (no API call per rider);
the vision API is only used to double-check a "no helmet" verdict when HELMET_CONFIRM_API=1.

Small model on purpose: crops are 40-120 px riders, so a nano classifier at 160 px is enough and
runs in ~2 ms next to the detector. Needs at least ~150 crops per class to mean anything.
"""
import argparse
import glob
import os
import shutil
import sys

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # local/ (dataset, runs, logs)
BASE_DIR = os.path.dirname(LOCAL_DIR)  # project root (server, models, cameras, .env)
DATA_DIR = os.path.join(LOCAL_DIR, 'dataset_helmet')
MIN_PER_CLASS = 150


def count(split, cls):
    return len(glob.glob(os.path.join(DATA_DIR, split, cls, '*.jpg')))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default='yolo11n-cls.pt')
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--imgsz', type=int, default=160)
    ap.add_argument('--batch', type=int, default=64)
    ap.add_argument('--force', action='store_true', help='train even with fewer than %d crops per class' % MIN_PER_CLASS)
    args = ap.parse_args()

    n = {c: count('train', c) for c in ('helmet', 'no_helmet')}
    v = {c: count('val', c) for c in ('helmet', 'no_helmet')}
    print(f'[helmet] train {n} / val {v}')
    if min(n.values()) < MIN_PER_CLASS and not args.force:
        sys.exit(f'[helmet] fewer than {MIN_PER_CLASS} crops in a class; run collect_helmet_dataset.py longer (or --force)')
    if min(v.values()) == 0:
        sys.exit('[helmet] val split has an empty class; collect more')

    from ultralytics import YOLO
    model = YOLO(args.model)
    results = model.train(
        data=DATA_DIR,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=0,
        project=os.path.join(LOCAL_DIR, 'runs', 'helmet'),
        name='cls',
        exist_ok=False,
        # riders face any way in a top-down view, so flips are fine here; strong colour jitter for night
        fliplr=0.5,
        hsv_v=0.6,
        erasing=0.2,
        patience=12,
        pretrained=True,
    )
    best = os.path.join(str(results.save_dir), 'weights', 'best.pt')
    if not os.path.exists(best):
        sys.exit(f'[helmet] no best.pt in {results.save_dir}')
    out = os.path.join(BASE_DIR, 'helmet_cls.pt')
    shutil.copy(best, out)
    top1 = getattr(results, 'top1', None)
    print(f'[helmet] done -> {out}' + (f' (val top-1 {top1:.3f})' if top1 else ''))


if __name__ == '__main__':
    main()
