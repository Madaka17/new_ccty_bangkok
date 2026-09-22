"""Fine-tune YOLO26x as a vehicle-heading detector on local/dataset_wrongway/
(from collect_wrongway_dataset.py). Wrong-way driving is then "a vehicle whose heading is the
opposite of what its camera normally sees at that spot" (see wrongway_service.py).

    python train_wrongway_det.py                       # yolo26x.pt, 60 epochs, 640 px, batch 8
    python train_wrongway_det.py --model yolo26m.pt --epochs 80
    python train_wrongway_det.py --resume              # continue an interrupted run from its last.pt
    python train_wrongway_det.py --model ../../wrongway_det.pt --name yolo26x_r2 --epochs 30 --lr0 0.002
                                                       # stage 2 after more collection rounds

Output: local/runs/wrongway_det/<name>/weights/best.pt copied to wrongway_det.pt in the project root.
Classes: car_toward car_away car_left car_right moto_toward moto_away moto_left moto_right.
fliplr is 0 on purpose: a mirror swaps left/right, the dataset already carries mirrored twins.
"""
import argparse
import os
import shutil
import sys

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(LOCAL_DIR)
DATA_YAML = os.path.join(LOCAL_DIR, 'dataset_wrongway', 'data.yaml')
STATUS_FILE = os.path.join(LOCAL_DIR, 'logs', 'wrongway_status.json')


def write_status(**fields):
    import json
    import time
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(dict(fields, ts=int(time.time())), f, ensure_ascii=False)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default=os.path.join(BASE_DIR, 'yolo26x.pt'))
    ap.add_argument('--epochs', type=int, default=60)
    ap.add_argument('--imgsz', type=int, default=640)
    ap.add_argument('--batch', type=int, default=8, help='8 fits a 10 GB card with the server stopped; use 4 while it runs')
    ap.add_argument('--name', default='yolo26x')
    ap.add_argument('--resume', action='store_true', help='continue from runs/wrongway_det/<name>/weights/last.pt')
    ap.add_argument('--lr0', type=float, default=None, help='initial LR; stage-2 fine-tunes use a smaller one (e.g. 0.002)')
    ap.add_argument('--out', default=os.path.join(BASE_DIR, 'wrongway_det.pt'))
    args = ap.parse_args()
    if not os.path.exists(DATA_YAML):
        sys.exit(f'[wrongway-det] {DATA_YAML} missing; run collect_wrongway_dataset.py first')

    from ultralytics import YOLO
    last = os.path.join(LOCAL_DIR, 'runs', 'wrongway_det', args.name, 'weights', 'last.pt')
    write_status(step='train', epochs=args.epochs, batch=args.batch, model=os.path.basename(args.model), name=args.name)
    if args.resume:
        if not os.path.exists(last):
            sys.exit(f'[wrongway-det] nothing to resume: {last} missing')
        print(f'[wrongway-det] resuming {last} (batch {args.batch})')
        results = YOLO(last).train(resume=True, batch=args.batch)
    else:
        extra = {'lr0': args.lr0} if args.lr0 else {}
        results = YOLO(args.model).train(
            data=DATA_YAML,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=0,
            project=os.path.join(LOCAL_DIR, 'runs', 'wrongway_det'),
            name=args.name,
            exist_ok=True,
            pretrained=True,
            patience=15,
            # heading lives in the vehicle's shape: no mirror (left<->right), mild geometry, strong photometric
            fliplr=0.0,
            flipud=0.0,
            degrees=0.0,
            scale=0.35,
            translate=0.1,
            hsv_h=0.015,
            hsv_s=0.6,
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
        sys.exit(f'[wrongway-det] no best.pt in {results.save_dir}')
    shutil.copy(best, args.out)
    m = getattr(results, 'box', None)
    extra = f' (mAP50 {m.map50:.3f}, mAP50-95 {m.map:.3f})' if m is not None else ''
    print(f'[wrongway-det] done -> {args.out}{extra}')
    write_status(step='done', out=args.out, map50=float(m.map50) if m is not None else None)


if __name__ == '__main__':
    main()
