"""Fine-tune YOLO26x as a helmet / no_helmet head detector on local/dataset_helmet_det/
(from prep_helmet_det.py).

    python train_helmet_det.py                       # yolo26x.pt, 80 epochs, 640 px, batch 8
    python train_helmet_det.py --model yolo26m.pt --epochs 100
    python train_helmet_det.py --resume                  # continue an interrupted run from its last.pt
    python train_helmet_det.py --model ../../helmet_det.pt --data blur --name yolo26x_blur --epochs 40
                                                         # stage 2: fine-tune on CCTV-like degraded images

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
DATASETS = {'clean': os.path.join(LOCAL_DIR, 'dataset_helmet_det', 'data.yaml'),
            'blur': os.path.join(LOCAL_DIR, 'dataset_helmet_det_blur', 'data.yaml')}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo26x.pt'))
    ap.add_argument('--epochs', type=int, default=80)
    ap.add_argument('--imgsz', type=int, default=640)
    ap.add_argument('--batch', type=int, default=8)
    ap.add_argument('--name', default='yolo26x')
    ap.add_argument('--resume', action='store_true', help='continue from runs/helmet_det/<name>/weights/last.pt')
    ap.add_argument('--data', default='clean', choices=sorted(DATASETS), help='clean (Kaggle photos) or blur (degraded, see degrade_helmet_det.py)')
    ap.add_argument('--lr0', type=float, default=None, help='initial LR; stage-2 fine-tunes use a smaller one (e.g. 0.002)')
    args = ap.parse_args()
    data_yaml = DATASETS[args.data]
    if not os.path.exists(data_yaml):
        sys.exit(f'[helmet-det] {data_yaml} missing; run prep_helmet_det.py / degrade_helmet_det.py first')

    from ultralytics import YOLO
    last = os.path.join(LOCAL_DIR, 'runs', 'helmet_det', args.name, 'weights', 'last.pt')
    if args.resume:
        if not os.path.exists(last):
            sys.exit(f'[helmet-det] nothing to resume: {last} missing')
        print(f'[helmet-det] resuming {last} (batch {args.batch})')
        # batch may be lowered on resume when VRAM got tight (e.g. desktop apps took a share)
        results = YOLO(last).train(resume=True, batch=args.batch)
    else:
        extra = {'lr0': args.lr0} if args.lr0 else {}
        results = YOLO(args.model).train(
            data=data_yaml,
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
            **extra,
        )
    best = os.path.join(str(results.save_dir), 'weights', 'best.pt')
    if not os.path.exists(best):
        sys.exit(f'[helmet-det] no best.pt in {results.save_dir}')
    out = os.path.join(BASE_DIR, 'helmet_det.pt' if args.data == 'clean' else 'helmet_det_blur.pt')
    shutil.copy(best, out)
    m = getattr(results, 'box', None)
    extra = f' (mAP50 {m.map50:.3f}, mAP50-95 {m.map:.3f})' if m is not None else ''
    print(f'[helmet-det] done -> {out}{extra}')


if __name__ == '__main__':
    main()
