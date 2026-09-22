"""Convert the Kaggle andrewmvd/helmet-detection set (PASCAL VOC, 764 images, classes
"With Helmet" / "Without Helmet") into a YOLO detection dataset at local/dataset_helmet_det/.

    python prep_helmet_det.py            # downloads via kagglehub (anonymous, ~390 MB) and converts
    python prep_helmet_det.py --val 0.15 # validation share (default 0.15)

Output: local/dataset_helmet_det/{images,labels}/{train,val}/ + data.yaml, ready for train_helmet_det.py.
"""
import argparse
import glob
import os
import random
import shutil
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(LOCAL_DIR, 'dataset_helmet_det')
CLASSES = {'With Helmet': 0, 'Without Helmet': 1}
NAMES = ['helmet', 'no_helmet']


def convert(xml_path, img_dir):
    root = ET.parse(xml_path).getroot()
    fname = root.findtext('filename')
    img = os.path.join(img_dir, fname)
    if not os.path.exists(img):
        return None, []
    w = float(root.find('size/width').text)
    h = float(root.find('size/height').text)
    rows = []
    for obj in root.findall('object'):
        cls = CLASSES.get(obj.findtext('name'))
        if cls is None:
            continue
        b = obj.find('bndbox')
        x1, y1, x2, y2 = (float(b.findtext(k)) for k in ('xmin', 'ymin', 'xmax', 'ymax'))
        x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
        y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        rows.append(f'{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}')
    return img, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--val', type=float, default=0.15)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()

    import kagglehub
    src = kagglehub.dataset_download('andrewmvd/helmet-detection')
    xmls = sorted(glob.glob(os.path.join(src, 'annotations', '*.xml')))
    img_dir = os.path.join(src, 'images')
    print(f'[prep] {len(xmls)} annotations in {src}')

    random.Random(args.seed).shuffle(xmls)
    n_val = int(len(xmls) * args.val)
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    counts = {'train': 0, 'val': 0}
    for i, xml_path in enumerate(xmls):
        split = 'val' if i < n_val else 'train'
        img, rows = convert(xml_path, img_dir)
        if img is None:
            continue
        for sub in ('images', 'labels'):
            os.makedirs(os.path.join(OUT_DIR, sub, split), exist_ok=True)
        stem = os.path.splitext(os.path.basename(img))[0]
        shutil.copy(img, os.path.join(OUT_DIR, 'images', split, os.path.basename(img)))
        with open(os.path.join(OUT_DIR, 'labels', split, stem + '.txt'), 'w') as f:
            f.write('\n'.join(rows) + ('\n' if rows else ''))
        counts[split] += 1

    with open(os.path.join(OUT_DIR, 'data.yaml'), 'w', encoding='utf-8') as f:
        f.write(f'path: {OUT_DIR}\ntrain: images/train\nval: images/val\nnames:\n')
        for i, n in enumerate(NAMES):
            f.write(f'  {i}: {n}\n')
    print(f'[prep] done {counts} -> {OUT_DIR}')


if __name__ == '__main__':
    main()
