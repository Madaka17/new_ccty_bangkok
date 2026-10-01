"""Train the heading classifier (wrong-way) or a helmet classifier from the checked labels, and measure the
new model and the one in use on the crops a person labeled as the test sample.

    python train_from_labels.py heading           # local/labels/heading_*.jsonl -> local/dataset_heading_v2
    python train_from_labels.py helmet            # local/labels/helmet_*.jsonl  -> local/dataset_helmet_v2
    python train_from_labels.py heading --eval-only

Labels, best first: a person's answer (label_review.py); for heading also Qwen's answer (qwen_label.py) when it
is sure and, on the crops that have one, agrees with the motion label. Crops the person answered in the test
queue never go into training. Nothing is copied over the model in use: the result is
local/runs/<task>_v2/<name>/weights/best.pt, and the numbers say whether it is worth deploying.

Crop framing must match what the server feeds the model. Heading: the server crops the box with 15% context
(wrongway_service CLS_MARGIN); the patrol's evidence crops have 50% (CROP_MARGIN), so their centre 65% is used.
Helmet: the patrol's own crops (helmet_service), as they are.
"""
import argparse
import json
import os
import shutil
import sys

import cv2

LOCAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(LOCAL)
LABELS = os.path.join(LOCAL, 'labels')
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

CLASSES = {'heading': {'front': 'toward', 'rear': 'away'},        # the class names wrongway_service expects
           'helmet': {'helmet': 'helmet', 'no_helmet': 'no_helmet'}}
QWEN_SURE = 0.6
EVIDENCE_CENTRE = (1 + 2 * 0.15) / (1 + 2 * 0.5)      # 15% margin inside a 50%-margin crop
OLD = {'heading': os.path.join(ROOT, 'wrongway_cls.pt'),
       'helmet': os.path.join(ROOT, os.getenv('HELMET_DET', 'helmet_det_blur.pt'))}


def _read(name):
    path = os.path.join(LABELS, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def human_labels(task):
    """{path: (label, queue)}, the last answer per crop."""
    out = {}
    for r in _read(f'{task}_human.jsonl'):
        if r['label'] is None:
            out.pop(r['path'], None)
        else:
            out[r['path']] = (r['label'], r.get('queue'))
    return out


def labeled_set(task):
    """(train [(path, class)], test [(path, class)])"""
    human = human_labels(task)
    train, test = [], []
    for path, (label, queue) in human.items():
        if label in CLASSES[task]:
            (test if queue == 'test' else train).append((path, CLASSES[task][label]))
    if task == 'heading':
        for r in _read('heading_qwen.jsonl'):
            if r['path'] in human or r['label'] not in CLASSES[task]:
                continue
            if (r.get('raw') or {}).get('confidence', 0) < QWEN_SURE:
                continue
            if r.get('motion') and CLASSES[task][r['label']] != r['motion']:
                continue      # Qwen and the motion label disagree and nobody checked it: leave it out
            train.append((r['path'], CLASSES[task][r['label']]))
    return train, test


def load(task, path):
    img = cv2.imread(path)
    if img is not None and task == 'heading' and 'dataset_wrongway_cls' not in path:   # evidence crops only
        h, w = img.shape[:2]
        ch, cw = int(h * EVIDENCE_CENTRE), int(w * EVIDENCE_CENTRE)
        img = img[(h - ch) // 2:(h - ch) // 2 + ch, (w - cw) // 2:(w - cw) // 2 + cw]
    return img


def build(task, train, test, val_frac):
    out = os.path.join(LOCAL, f'dataset_{task}_v2')
    if os.path.isdir(out):
        shutil.rmtree(out)
    train = sorted(train)
    n_val = int(len(train) * val_frac)
    split = {'val': train[::max(1, len(train) // max(1, n_val))][:n_val]}
    val_paths = {p for p, _ in split['val']}
    split['train'] = [it for it in train if it[0] not in val_paths]
    split['test'] = sorted(test)
    counts = {}
    for name, items in split.items():
        for cls in set(CLASSES[task].values()):
            os.makedirs(os.path.join(out, name, cls), exist_ok=True)
        for i, (path, cls) in enumerate(items):
            img = load(task, path)
            if img is None:
                continue
            cv2.imwrite(os.path.join(out, name, cls, f'{i:06d}_{os.path.basename(path)}'), img)
            counts[(name, cls)] = counts.get((name, cls), 0) + 1
    print(f'[{task}] dataset {out}: ' + ', '.join(f'{n}/{c} {k}' for (n, c), k in sorted(counts.items())))
    return out


def evaluate(task, weights, data, imgsz):
    """Accuracy per class on the test split; the helmet detector in use is scored the way helmet_service reads it."""
    from ultralytics import YOLO
    m = YOLO(weights)
    detector = m.task == 'detect'
    right, total, per = 0, 0, {}
    for cls in sorted(os.listdir(os.path.join(data, 'test'))):
        files = [os.path.join(data, 'test', cls, f) for f in os.listdir(os.path.join(data, 'test', cls))]
        for i in range(0, len(files), 128):
            for r in m(files[i:i + 128], imgsz=640 if detector else imgsz, verbose=False):
                if detector:      # helmet_service._local_verdict: no_helmet first, then helmet, at conf >= 0.5
                    best = {}
                    for c, cf in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist()):
                        best[r.names[int(c)]] = max(best.get(r.names[int(c)], 0.0), float(cf))
                    guess = 'no_helmet' if best.get('no_helmet', 0) >= 0.5 else 'helmet' if best.get('helmet', 0) >= 0.5 else None
                else:
                    guess = r.names[int(r.probs.top1)]
                ok = guess == cls
                right += ok
                total += 1
                p = per.setdefault(cls, [0, 0])
                p[0] += ok
                p[1] += 1
    acc = right / total if total else 0
    print(f'[{task}] {os.path.basename(weights)}: {acc:.1%} right on {total} test crops · ' +
          ' · '.join(f'{c} {a}/{n}' for c, (a, n) in sorted(per.items())))
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('task', choices=('heading', 'helmet'))
    ap.add_argument('--model', default='yolo26s-cls.pt')
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--imgsz', type=int, default=None, help='default 128 for heading, 224 for helmet')
    ap.add_argument('--batch', type=int, default=64)
    ap.add_argument('--val', type=float, default=0.1)
    ap.add_argument('--name', default='r1')
    ap.add_argument('--eval-only', action='store_true')
    args = ap.parse_args()
    imgsz = args.imgsz or (128 if args.task == 'heading' else 224)

    train, test = labeled_set(args.task)
    print(f'[{args.task}] {len(train)} crops to learn from, {len(test)} test crops checked by a person')
    if len(test) < 50:
        print('  too few test crops: label more of the test queue in label_review.py first')
    data = build(args.task, train, test, args.val)
    if os.path.exists(OLD[args.task]):
        evaluate(args.task, OLD[args.task], data, imgsz)
    if args.eval_only:
        return
    from ultralytics import YOLO
    runs = os.path.join(LOCAL, 'runs', f'{args.task}_v2')
    YOLO(args.model).train(data=data, epochs=args.epochs, imgsz=imgsz, batch=args.batch, project=runs, name=args.name,
                           exist_ok=True, patience=10, workers=4, fliplr=0.5, hsv_v=0.4, erasing=0.2, plots=False)
    evaluate(args.task, os.path.join(runs, args.name, 'weights', 'best.pt'), data, imgsz)


if __name__ == '__main__':
    main()
