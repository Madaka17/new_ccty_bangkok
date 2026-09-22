"""Fine-tune YOLO26x as a helmet / no_helmet head detector on local/dataset_helmet_det/
(from prep_helmet_det.py).

    python train_helmet_det.py                       # yolo26x.pt, 80 epochs, 640 px, batch 8
    python train_helmet_det.py --model yolo26m.pt --epochs 100

Output: local/runs/helmet_det/<name>/weights/best.pt copied to helmet_det.pt in the project root.
Classes: 0 helmet, 1 no_helmet. Boxes are rider heads, so run it on the rider crop (or the full
frame at high res) and count class 1 hits.
"""
import argparse
import os
import shutil
import sys

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(LOCAL_DIR)
DATA_YAML = os.path.join(LOCAL_DIR, 'dataset_helmet_det', 'data.yaml')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo26x.pt'))
    ap.add_argument('--epochs', type=int, default=80)
    ap.add_argument('--imgsz', type=int, default=640)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--name', default='yolo26x')
    args = ap.parse_args()
    if not os.path.exists(DATA_YAML):
        sys.exit(f'[helmet-det] {DATA_YAML} missing; run prep_helmet_det.py first')

    from ultralytics import YOLO
    model = YOLO(args.model)
    results = model.train(
        data=DATA_YAML,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=0,
        project=os.path.join(LOCAL_DIR, 'runs', 'helmet_det'),
        name=args.name,
        exist_ok=True,
        pretrained=True,
        patience=20,
        # source images are 400 px street photos; heads are small, so keep scale jitter modest
        scale=0.4,
        fliplr=0.5,
        hsv_v=0.5,
        mosaic=1.0,
        close_mosaic=10,
        cos_lr=True,
        amp=True,
        workers=4,
    )
    best = os.path.join(str(results.save_dir), 'weights', 'best.pt')
    if not os.path.exists(best):
        sys.exit(f'[helmet-det] no best.pt in {results.save_dir}')
    out = os.path.join(BASE_DIR, 'helmet_det.pt')
    shutil.copy(best, out)
    m = getattr(results, 'box', None)
    extra = f' (mAP50 {m.map50:.3f}, mAP50-95 {m.map:.3f})' if m is not None else ''
    print(f'[helmet-det] done -> {out}{extra}')


if __name__ == '__main__':
    main()
