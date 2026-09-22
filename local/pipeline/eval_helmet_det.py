"""Score a helmet detector on the clean and the degraded (CCTV-like) val sets.

    python eval_helmet_det.py ..\..\helmet_det.pt
    python eval_helmet_det.py ..\..\helmet_det_blur.pt --data blur
"""
import argparse
import os
import sys

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS = {'clean': os.path.join(LOCAL_DIR, 'dataset_helmet_det', 'data.yaml'),
            'blur': os.path.join(LOCAL_DIR, 'dataset_helmet_det_blur', 'data.yaml')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('weights')
    ap.add_argument('--data', default='all', choices=['all', 'clean', 'blur'])
    args = ap.parse_args()
    from ultralytics import YOLO
    m = YOLO(args.weights)
    for key in (['clean', 'blur'] if args.data == 'all' else [args.data]):
        r = m.val(data=DATASETS[key], imgsz=640, batch=8, device=0, verbose=False, plots=False, workers=0,
                  project=os.path.join(LOCAL_DIR, 'runs', 'helmet_det'), name=f'eval_{key}', exist_ok=True)
        names = r.names
        print(f'[{key}] mAP50 {r.box.map50:.3f}  mAP50-95 {r.box.map:.3f}  P {r.box.mp:.3f}  R {r.box.mr:.3f}')
        for i, c in enumerate(r.box.ap_class_index):
            print(f'    {names[int(c)]:<10} AP50 {r.box.ap50[i]:.3f}  P {r.box.p[i]:.3f}  R {r.box.r[i]:.3f}')


if __name__ == '__main__':
    main()
