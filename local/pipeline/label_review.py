"""A page on this machine for a person to label crops: one crop at a time, one key.

    python label_review.py --build-helmet     # once: the helmet crops to label -> local/labels/helmet_queue.jsonl
    python label_review.py                    # then open http://127.0.0.1:8010

Bound to 127.0.0.1 only: it is a tool for the operator at this machine, never part of the public site.
Images are served by an id (a hash of the path), never by a path from the request.

heading (front / rear of a vehicle), from the labels qwen_label.py wrote, in this order:
    test     a fixed random sample (TEST_FRAC of the crops), shown WITHOUT Qwen's answer: the honest yardstick that
             train_*.py measure the old and the new model against
    doubt    Qwen disagrees with the motion label, or is unsure (< SURE); only with REVIEW_DOUBT, since
             train_from_labels.py leaves those crops out anyway
helmet: Qwen misreads helmets on these crops (a rider in a black helmet came back "bare"), so a person labels
every crop of helmet_queue.jsonl with no AI guess shown: HELMET_LOGGED crops the patrol logged as no helmet
and HELMET_RANDOM random motorcycle crops. The TEST_FRAC sample comes first.
Answers go to local/labels/<task>_human.jsonl (append only; the last answer for a crop wins, so undo just
writes the crop again).
"""
import hashlib
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')
LABELS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'labels')
PORT = 8010
TEST_FRAC = {'heading': 0.025, 'helmet': 0.3}   # about 300 crops each
SURE = 0.7
REVIEW_DOUBT = False      # True: also ask about the heading crops Qwen doubts (thousands)
SOURCE = {'heading': 'heading_qwen.jsonl', 'helmet': 'helmet_queue.jsonl'}
HELMET_LOGGED = 500
HELMET_RANDOM = 500
SNAP = os.path.join(os.path.dirname(LABELS), 'archive', 'train_src_2026-10-01', 'helmet_cache')
HELMET_ARCHIVE = os.getenv('HELMET_ARCHIVE_DIR', os.path.join(os.getenv('BMA_DATA_DIR', r'E:\data smartstreet'), 'helmet'))
MOTION_VIEW = {'toward': 'front', 'away': 'rear'}
KEYS = {
    'heading': [('f', 'front', 'หน้ารถ'), ('r', 'rear', 'ท้ายรถ'), ('s', 'unclear', 'ด้านข้าง / ดูไม่ออก')],
    'helmet': [('h', 'helmet', 'ใส่หมวกทุกคน'), ('n', 'no_helmet', 'มีคนไม่ใส่หมวก'), ('u', 'unclear', 'ดูไม่ออก / ไม่ใช่มอไซ')],
}
_lock = threading.Lock()


def _rank(path):
    """A stable number in [0, 1) for a crop."""
    return int(hashlib.md5(path.encode('utf-8')).hexdigest()[:8], 16) / 2 ** 32


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def build_helmet_queue():
    def crops(folder, suffix):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(folder) for f in fs
                      if f.endswith(suffix) and not f.endswith(('_frame.jpg', '_box.jpg')))
    logged = sorted(crops(HELMET_ARCHIVE, '_crop.jpg'), key=lambda p: _rank('pick:' + p))[:HELMET_LOGGED]
    # a salted rank: picking by _rank itself would put every random crop in the test sample
    cache = sorted(crops(SNAP, '.jpg'), key=lambda p: _rank('pick:' + p))[:HELMET_RANDOM]
    rows = [{'path': p, 'source': 'logged_no_helmet', 'label': 'unknown'} for p in logged] + \
           [{'path': p, 'source': 'random', 'label': 'unknown'} for p in cache]
    with open(os.path.join(LABELS, SOURCE['helmet']), 'w', encoding='utf-8') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    print(f'helmet queue: {len(logged)} logged as no helmet + {len(cache)} random = {len(rows)} crops')


def state(task):
    """(items in review order, {path: human label}) for one task."""
    qwen = _read(os.path.join(LABELS, SOURCE[task]))
    human = {}
    for r in _read(os.path.join(LABELS, f'{task}_human.jsonl')):
        if r['label'] is None:      # undo
            human.pop(r['path'], None)
        else:
            human[r['path']] = r['label']
    # the test sample is picked by a hash of the path, so it stays the same while qwen_label.py is still adding rows
    test = sorted((r for r in qwen if _rank(r['path']) < TEST_FRAC[task]), key=lambda r: _rank(r['path']))
    test_paths = {r['path'] for r in test}

    def doubtful(r):
        if task == 'helmet':
            return True           # no AI guess: a person labels every crop
        if not REVIEW_DOUBT:
            return False          # heading: the test sample only; doubtful crops are left out of training
        if r['label'] not in ('front', 'rear'):
            return False          # side / unclear crops are left out of training anyway
        conf = (r.get('raw') or {}).get('confidence', 0) or 0
        return (r.get('motion') and MOTION_VIEW[r['motion']] != r['label']) or conf < SURE

    # helmet: logged and random crops mixed, so a short session still sees both
    doubt = sorted((r for r in qwen if r['path'] not in test_paths and doubtful(r)),
                   key=lambda r: _rank(r['path']) if task == 'helmet' else 0)
    items = [dict(r, queue='test') for r in test] + [dict(r, queue='doubt') for r in doubt]
    for r in items:
        r['id'] = hashlib.md5(r['path'].encode('utf-8')).hexdigest()[:16]   # stable while the list grows
    return items, human


PAGE = """<!doctype html><html lang="th"><head><meta charset="utf-8"><title>ตรวจป้ายภาพ</title>
<style>
body{font-family:system-ui,'Segoe UI',Tahoma,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:16px}
.wrap{max-width:900px;margin:0 auto}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button{font:inherit;padding:10px 16px;border-radius:10px;border:1px solid #334155;background:#1e293b;color:#e2e8f0;cursor:pointer}
button.on{background:#2563eb;border-color:#2563eb}button.key{min-width:180px}
#img{display:block;margin:16px auto;height:420px;max-width:100%;object-fit:contain;image-rendering:auto;background:#000;border-radius:12px}
.muted{color:#94a3b8;font-size:14px}.hint{color:#fbbf24}
</style></head><body><div class="wrap">
<div class="row"><b>ตรวจป้ายภาพ</b><button id="t-heading">ย้อนศร: หน้ารถ/ท้ายรถ</button><button id="t-helmet">หมวกกันน็อก</button>
<span class="muted" id="prog"></span></div>
<p class="muted" id="what"></p><img id="img" alt="ภาพที่ต้องตรวจ"><p class="hint" id="guess"></p>
<div class="row" id="keys"></div><p class="muted">กด Z = ย้อนกลับภาพก่อนหน้า</p></div>
<script>
const KEYS = __KEYS__;
let task = 'heading', cur = null, hist = [];
async function next() {
  const r = await (await fetch('/next?task=' + task)).json();
  cur = r.item;
  document.getElementById('prog').textContent = `ตรวจแล้ว ${r.done} / ${r.total} (ชุดทดสอบ ${r.test_done} / ${r.test_total})`;
  const img = document.getElementById('img');
  if (!cur) { img.removeAttribute('src'); document.getElementById('what').textContent = 'ตรวจครบแล้ว'; document.getElementById('guess').textContent = ''; return; }
  img.src = `/img?task=${task}&i=${cur.i}`;
  document.getElementById('what').textContent = (cur.queue === 'test' ? 'ชุดทดสอบ (ไม่บอกคำตอบของ AI)' : cur.guess ? 'AI ไม่แน่ใจ หรือขัดกับป้ายเดิม' : 'ภาพที่ต้องติดป้าย') + ' · ' + cur.name;
  document.getElementById('guess').textContent = cur.queue === 'test' || !cur.guess ? '' : `AI เดา: ${cur.guess}`;
}
async function answer(label) {
  if (!cur) return;
  await fetch('/label', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task, i: cur.i, label})});
  hist.push(cur.i); next();
}
async function undo() {
  const i = hist.pop(); if (i == null) return;
  await fetch('/label', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task, i, label: null})});
  next();
}
function setTask(t) {
  task = t; hist = [];
  for (const x of ['heading', 'helmet']) document.getElementById('t-' + x).classList.toggle('on', x === t);
  document.getElementById('keys').innerHTML = KEYS[t].map(([k, v, th]) => `<button class="key" data-v="${v}">${k.toUpperCase()} = ${th}</button>`).join('');
  document.querySelectorAll('#keys button').forEach((b) => (b.onclick = () => answer(b.dataset.v)));
  next();
}
document.getElementById('t-heading').onclick = () => setTask('heading');
document.getElementById('t-helmet').onclick = () => setTask('helmet');
document.addEventListener('keydown', (e) => {
  if (e.key.toLowerCase() === 'z') return undo();
  const k = KEYS[task].find(([key]) => key === e.key.toLowerCase());
  if (k) answer(k[1]);
});
setTask('heading');
</script></body></html>"""

GUESS_TH = {'front': 'หน้ารถ', 'rear': 'ท้ายรถ', 'side': 'ด้านข้าง', 'unclear': 'ดูไม่ออก',
            'helmet': 'ใส่หมวก', 'no_helmet': 'ไม่ใส่หมวก'}


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        task = q.get('task')
        if u.path == '/':
            body = PAGE.replace('__KEYS__', json.dumps(KEYS, ensure_ascii=False)).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)
            return
        if task not in KEYS:
            return self._json({'error': 'bad task'}, 400)
        items, human = state(task)
        if u.path == '/next':
            todo = next((r for r in items if r['path'] not in human), None)
            test = [r for r in items if r['queue'] == 'test']
            item = None
            if todo:
                r = todo
                item = {'i': r['id'], 'queue': r['queue'], 'name': os.path.basename(r['path']),
                        'guess': None if r['label'] == 'unknown' else
                        GUESS_TH.get(r['label'], r['label']) + (f" (ป้ายเดิม: {GUESS_TH[MOTION_VIEW[r['motion']]]})" if r.get('motion') else '')}
            return self._json({'item': item, 'done': sum(1 for r in items if r['path'] in human), 'total': len(items),
                               'test_done': sum(1 for r in test if r['path'] in human), 'test_total': len(test)})
        if u.path == '/img':
            try:
                path = next(r['path'] for r in items if r['id'] == q.get('i'))
                with open(path, 'rb') as f:
                    data = f.read()
            except (StopIteration, OSError):
                return self._json({'error': 'not found'}, 404)
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json({'error': 'not found'}, 404)

    def do_POST(self):
        if urlparse(self.path).path != '/label':
            return self._json({'error': 'not found'}, 404)
        try:
            d = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)))
            task = d['task']
            items, _ = state(task)
            r = next(r for r in items if r['id'] == d['i'])
            label = d.get('label')
            if label is not None and label not in [v for _, v, _ in KEYS[task]]:
                raise ValueError('bad label')
        except (ValueError, KeyError, StopIteration, TypeError):
            return self._json({'error': 'bad request'}, 400)
        row = {'path': r['path'], 'label': label, 'queue': r['queue'], 'qwen': r['label'], 'motion': r.get('motion'),
               'ts': int(time.time())}
        with _lock, open(os.path.join(LABELS, f'{task}_human.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
        self._json({'ok': True})


if __name__ == '__main__':
    os.makedirs(LABELS, exist_ok=True)
    if '--build-helmet' in sys.argv:
        build_helmet_queue()
        sys.exit(0)
    print(f'open http://127.0.0.1:{PORT}  (Ctrl+C to stop)')
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
