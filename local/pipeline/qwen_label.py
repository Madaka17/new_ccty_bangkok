"""Label vehicle crops with the Qwen vision model (LOCAL_LLM_* in .env), for retraining the heading classifier
(wrong-way) and a helmet classifier on real BMA CCTV crops.

    python qwen_label.py heading                  # every heading crop not labeled yet
    python qwen_label.py helmet --limit 10000     # a fixed random sample of the helmet crops
    python qwen_label.py heading --dry-run        # count the crops, call nothing

Sources (crops only, never the full frames):
    heading  local/dataset_wrongway_cls/{train,val}/{toward,away}/   motion labels from collect_wrongway_dataset.py
             local/archive/train_src_2026-10-01/wrongway_cache/       vehicles the patrol flagged (last 48 h)
             <WRONGWAY_ARCHIVE_DIR>/<date>/*_crop.jpg                 vehicles it logged as wrong-way
    helmet   local/archive/train_src_2026-10-01/helmet_cache/         every motorcycle crop of the last 48 h
             <HELMET_ARCHIVE_DIR>/<date>/*_crop.jpg                   riders it logged without a helmet

The prompts give no hint of what the patrol thought: with a hint the cloud agent agreed with it 602 times out
of 603. Answers go to local/labels/<task>_qwen.jsonl, one line per crop; a rerun skips crops already there,
so the job can be stopped and started again. label_review.py shows the doubtful ones to a person.
"""
import argparse
import base64
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, '.env'))
from backend.core import local_llm  # noqa: E402

LOCAL = os.path.join(ROOT, 'local')
SNAP = os.path.join(LOCAL, 'archive', 'train_src_2026-10-01')
LABELS = os.path.join(LOCAL, 'labels')
DATA_DIR = os.getenv('BMA_DATA_DIR', r'D:\Data')
MIN_SIDE = 224
ARCHIVE = {'heading': os.getenv('WRONGWAY_ARCHIVE_DIR', os.path.join(DATA_DIR, 'wrongway')),
           'helmet': os.getenv('HELMET_ARCHIVE_DIR', os.path.join(DATA_DIR, 'helmet'))}

PROMPTS = {
    'heading': (
        "You see a crop of ONE vehicle from a low-resolution Bangkok street CCTV camera. Say which side of the "
        "vehicle faces the camera. front: the headlights, windscreen, grille or front number plate face the camera. "
        "rear: the tail lights, rear window, back door or rear number plate face the camera. side: you see mostly "
        "its side. unclear: too small, blurred, dark or hidden to tell. Judge only the vehicle in the middle of the "
        "crop. Never guess: say unclear when you are not sure."),
    'helmet': (
        "You see a crop of ONE motorcycle from a low-resolution Bangkok street CCTV camera. Count the people riding "
        "it and how many of them have NO helmet on their head. A helmet is a hard rounded shell over the whole top "
        "of the head; a cap, a hood or bare hair is no helmet. clear is false when the heads are too small, blurred, "
        "dark or hidden to tell. Never guess: when you are not sure, clear is false."),
}
SCHEMAS = {
    'heading': {"type": "object", "additionalProperties": False, "required": ["view", "confidence"],
                "properties": {"view": {"type": "string", "enum": ["front", "rear", "side", "unclear"]},
                               "confidence": {"type": "number"}}},
    'helmet': {"type": "object", "additionalProperties": False, "required": ["riders", "no_helmet", "clear", "confidence"],
               "properties": {"riders": {"type": "integer"}, "no_helmet": {"type": "integer"},
                              "clear": {"type": "boolean"}, "confidence": {"type": "number"}}},
}


def _jpgs(folder, crops_only=False):
    if not os.path.isdir(folder):
        return []
    out = []
    for dirpath, _, files in os.walk(folder):
        for f in files:
            if not f.lower().endswith('.jpg') or f.endswith(('_frame.jpg', '_box.jpg')):
                continue
            if crops_only and not f.endswith('_crop.jpg'):
                continue
            out.append(os.path.join(dirpath, f))
    return sorted(out)


def sources(task, limit, seed):
    """[(path, source, motion_label or None)]"""
    items = []
    if task == 'heading':
        for split in ('train', 'val'):
            for head in ('toward', 'away'):
                items += [(p, f'motion_{split}', head) for p in _jpgs(os.path.join(LOCAL, 'dataset_wrongway_cls', split, head))]
        items += [(p, 'flagged_cache', None) for p in _jpgs(os.path.join(SNAP, 'wrongway_cache'))]
        items += [(p, 'flagged_archive', None) for p in _jpgs(ARCHIVE['heading'], crops_only=True)]
    else:
        cache = _jpgs(os.path.join(SNAP, 'helmet_cache'))
        random.Random(seed).shuffle(cache)
        archive = _jpgs(ARCHIVE['helmet'], crops_only=True)
        items += [(p, 'flagged_archive', None) for p in archive]
        items += [(p, 'cache', None) for p in cache[:max(0, limit - len(archive))]]
    return items


def label_of(task, v):
    if task == 'heading':
        return v.get('view') if v.get('view') in ('front', 'rear', 'side') and v.get('confidence', 0) >= 0.5 else 'unclear'
    if not v.get('clear') or v.get('confidence', 0) < 0.5 or (v.get('riders') or 0) < 1:
        return 'unclear'
    return 'no_helmet' if (v.get('no_helmet') or 0) > 0 else 'helmet'


def ask(task, path):
    img = cv2.imread(path)
    # heading crops are 20-40 px: Qwen calls most of them unclear unless they are enlarged first
    s = MIN_SIDE / min(img.shape[:2])
    if s > 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    image = 'data:image/jpeg;base64,' + base64.standard_b64encode(jpeg).decode('ascii')
    text = local_llm.default.chat(
        [{"role": "system", "content": PROMPTS[task]},
         {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}},
                                      {"type": "text", "text": "Answer with JSON only."}]}],
        max_tokens=120, temperature=0.0, json_schema=SCHEMAS[task], timeout=60)
    return json.loads(text[text.find('{'):text.rfind('}') + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('task', choices=('heading', 'helmet'))
    ap.add_argument('--limit', type=int, default=10000, help='helmet: crops to label in all (archive first, then a random sample)')
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--seed', type=int, default=17)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    os.makedirs(LABELS, exist_ok=True)
    out = os.path.join(LABELS, f'{args.task}_qwen.jsonl')
    done = set()
    if os.path.exists(out):
        with open(out, encoding='utf-8') as f:
            done = {json.loads(line)['path'] for line in f if line.strip()}
    items = [it for it in sources(args.task, args.limit, args.seed) if it[0] not in done]
    print(f'{args.task}: {len(items)} crops to label, {len(done)} already labeled -> {out}')
    if args.dry_run or not items:
        return

    lock, stats, t0 = threading.Lock(), {'ok': 0, 'fail': 0}, time.time()

    def one(it):
        path, src, motion = it
        for attempt in range(4):
            try:
                v = ask(args.task, path)
                break
            except Exception as e:  # noqa: BLE001 - gateway busy or a bad answer: back off and try again
                if attempt == 3:
                    with lock:
                        stats['fail'] += 1
                    print(f'  failed {os.path.basename(path)}: {str(e)[:120]}')
                    return
                time.sleep(5 * 2 ** attempt)
        row = {'path': path, 'source': src, 'motion': motion, 'label': label_of(args.task, v), 'raw': v,
               'model': local_llm.default.model, 'ts': int(time.time())}
        with lock:
            with open(out, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            stats['ok'] += 1
            n = stats['ok'] + stats['fail']
            if n % 100 == 0:
                rate = n / (time.time() - t0)
                print(f'  {n}/{len(items)} · {rate:.1f}/s · about {(len(items) - n) / rate / 60:.0f} min left · failed {stats["fail"]}')

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(one, items))
    print(f'done: {stats["ok"]} labeled, {stats["fail"]} failed, {(time.time() - t0) / 60:.0f} min')


if __name__ == '__main__':
    main()
