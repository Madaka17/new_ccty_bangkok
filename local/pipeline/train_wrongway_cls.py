"""Train the vehicle heading classifier (front toward the camera / rear toward the camera) for wrongway_service.py.

    python prep_wrongway_cls.py                  # build local/dataset_wrongway_cls first
    python train_wrongway_cls.py                 # yolo26s-cls, 40 epochs, 128 px
    python train_wrongway_cls.py --clean         # then drop train crops the model is sure are mislabeled and train again

The labels come from motion (see collect_wrongway_dataset.py) and a share of them is wrong: a bad
nearest-neighbour match on 1 fps snapshots gives a car the heading of its neighbour. --clean scores
every train crop with the first model and moves the ones it rejects with >= --clean-conf into
local/dataset_wrongway_cls/rejected/, then trains a second model on what is left.
Small crops and a small model: this runs next to the live server (about 1-2 GB of GPU memory).

Result: local/runs/wrongway_cls/<name>/weights/best.pt, copied to ../../wrongway_cls.pt.
"""
import argparse
import os
import shutil

from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'dataset_wrongway_cls')
RUNS = os.path.join(ROOT, 'runs', 'wrongway_cls')
OUT = os.path.join(os.path.dirname(ROOT), 'wrongway_cls.pt')


def train(model, name, args):
    YOLO(model).train(data=DATA, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, project=RUNS, name=name,
                      exist_ok=True, patience=args.patience, workers=4, fliplr=0.5, hsv_v=0.4, erasing=0.2,
                      plots=False)
    return os.path.join(RUNS, name, 'weights', 'best.pt')


def clean(weights, args):
    """Move the train crops the model contradicts with >= clean_conf to rejected/."""
    m = YOLO(weights)
    moved = 0
    for head in os.listdir(os.path.join(DATA, 'train')):
        src = os.path.join(DATA, 'train', head)
        files = [os.path.join(src, f) for f in os.listdir(src)]
        dst = os.path.join(DATA, 'rejected', head)
        os.makedirs(dst, exist_ok=True)
        for i in range(0, len(files), 256):
            for path, r in zip(files[i:i + 256], m(files[i:i + 256], imgsz=args.imgsz, verbose=False)):
                top = r.names[int(r.probs.top1)]
                if top != head and float(r.probs.top1conf) >= args.clean_conf:
                    shutil.move(path, os.path.join(dst, os.path.basename(path)))
                    moved += 1
    print(f'[wrongway-cls] moved {moved} train crops to rejected/')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='yolo26s-cls.pt')
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--imgsz', type=int, default=128)
    ap.add_argument('--batch', type=int, default=128)
    ap.add_argument('--patience', type=int, default=10)
    ap.add_argument('--clean', action='store_true', help='drop crops the first model rejects, then train again')
    ap.add_argument('--clean-conf', type=float, default=0.9)
    args = ap.parse_args()
    best = train(args.model, 'r1', args)
    if args.clean:
        clean(best, args)
        best = train(args.model, 'r2', args)
    shutil.copy(best, OUT)
    print(f'[wrongway-cls] {best} -> {OUT}')


if __name__ == '__main__':
    main()
