"""Fine-tune YOLO11 on the frames collected by collect_dataset.py.

    python train_model.py                        # yolo26x, 100 epochs, imgsz 960, auto batch
    python train_model.py --model yolo26l.pt --epochs 60 --imgsz 1280
    python train_model.py --resume               # continue the last interrupted run

Output: runs/train/bkk*/weights/best.pt, copied to yolo11x_bkk.pt (or <model>_bkk.pt).
To use it, set AI_MODEL=yolo26x_bkk.pt in .env (server.py runs stock yolo26x.pt by default) and restart the server.

Stop the server first: training needs the whole GPU (RTX 3050 8 GB fits yolo26x at 960 with
batch 4-6). Correct the auto-labels before training on a large set; the model can only be as
good as its labels.
"""
import argparse
import glob
import os
import shutil
import sys

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # local/ (dataset, runs, logs)
BASE_DIR = os.path.dirname(LOCAL_DIR)  # project root (server, models, cameras, .env)
DATA_YAML = os.path.join(LOCAL_DIR, 'dataset', 'dataset.yaml')
MIN_IMAGES = 200


def count_images(split):
    return len(glob.glob(os.path.join(LOCAL_DIR, 'dataset', 'images', split, '*.jpg')))


def write_boosted_yaml(repeat):
    """dataset_boost.yaml whose train split is a file list where every image with a motorcycle
    label appears `repeat` times. Motorcycles are ~3% of the boxes, so without this the model
    learns to skip them. Val is untouched, so metrics stay comparable."""
    import yaml
    with open(DATA_YAML, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    root = cfg.get('path', os.path.join(LOCAL_DIR, 'dataset'))
    imgs = sorted(glob.glob(os.path.join(root, 'images', 'train', '*.jpg')))
    lines, boosted = [], 0
    for img in imgs:
        lab = os.path.join(root, 'labels', 'train', os.path.splitext(os.path.basename(img))[0] + '.txt')
        has_moto = os.path.exists(lab) and any(l.split() and l.split()[0] == '3' for l in open(lab, encoding='utf-8'))
        boosted += has_moto
        lines.extend([img] * (repeat if has_moto else 1))
    list_path = os.path.join(root, 'train_boost.txt')
    with open(list_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    cfg['train'] = list_path
    out = os.path.join(root, 'dataset_boost.yaml')
    with open(out, 'w', encoding='utf-8') as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    print(f'[train] motorcycle boost x{repeat}: {boosted} of {len(imgs)} train images repeated -> {len(lines)} samples/epoch')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default='yolo26x.pt', help='starting weights')
    ap.add_argument('--epochs', type=int, default=100)
    ap.add_argument('--imgsz', type=int, default=960)
    ap.add_argument('--batch', type=int, default=-1, help='-1 = pick the largest batch that fits the GPU')
    ap.add_argument('--patience', type=int, default=25, help='stop when val mAP stops improving')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--moto-boost', type=int, default=4,
                    help='repeat each train image that contains a motorcycle this many times (class balance); 1 = off')
    ap.add_argument('--force', action='store_true', help='train even with fewer than %d images' % MIN_IMAGES)
    args = ap.parse_args()

    if not os.path.exists(DATA_YAML):
        sys.exit(f'{DATA_YAML} missing: run collect_dataset.py first')
    n_train, n_val = count_images('train'), count_images('val')
    print(f'[train] dataset: {n_train} train / {n_val} val images')
    if not args.resume and (n_train + n_val) < MIN_IMAGES and not args.force:
        sys.exit(f'[train] only {n_train + n_val} images; collect at least {MIN_IMAGES} (or pass --force)')
    if n_val == 0:
        sys.exit('[train] no val images; collect more so the 15% val split is populated')

    from ultralytics import YOLO

    batch = args.batch
    if batch == -1:
        try:
            import torch
            if torch.cuda.is_available():
                total_mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                if total_mem_gb <= 8.5:
                    batch = 1
                    print(f'[train] GPU VRAM is {total_mem_gb:.1f} GB: using safe batch size {batch} for imgsz={args.imgsz}')
        except Exception:
            pass

    data_yaml = DATA_YAML
    if not args.resume and args.moto_boost > 1:
        data_yaml = write_boosted_yaml(args.moto_boost)

    if args.resume:
        last = sorted(glob.glob(os.path.join(LOCAL_DIR, 'runs', 'train', 'bkk*', 'weights', 'last.pt')), key=os.path.getmtime)
        if not last:
            sys.exit('[train] nothing to resume')
        model = YOLO(last[-1])
        results = model.train(resume=True)
    else:
        model = YOLO(os.path.join(BASE_DIR, args.model))
        results = model.train(
            data=data_yaml,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=batch,
            patience=args.patience,
            device=0,
            project=os.path.join(LOCAL_DIR, 'runs', 'train'),
            name='bkk',
            exist_ok=False,
            # CCTV cameras are fixed: no horizontal flip (keeps left/right lane semantics), mild colour jitter for day/night
            fliplr=0.0,
            hsv_v=0.5,
            mosaic=1.0,
            close_mosaic=10,
            cos_lr=True,
            pretrained=True,
        )

    save_dir = str(results.save_dir)
    best = os.path.join(save_dir, 'weights', 'best.pt')
    if not os.path.exists(best):
        sys.exit(f'[train] no best.pt in {save_dir}')
    out = os.path.join(BASE_DIR, os.path.splitext(args.model)[0] + '_bkk.pt')
    shutil.copy(best, out)
    metrics = getattr(results, 'results_dict', {}) or {}
    print(f"[train] done. mAP50={metrics.get('metrics/mAP50(B)', float('nan')):.3f} "
          f"mAP50-95={metrics.get('metrics/mAP50-95(B)', float('nan')):.3f}")
    print(f'[train] weights -> {out}  (restart the server to use them)')


if __name__ == '__main__':
    main()
