"""Status window for the wrong-way pipeline (wrongway_pipeline.bat): which step is running,
how far it is, and the training progress. Refreshes every 2 s. Ctrl+C closes only this window.

    python watch_wrongway.py

Reads local/logs/wrongway_status.json (written by collect_wrongway_dataset.py / train_wrongway_det.py)
and the tail of local/logs/train_wrongway_det.log for epoch / mAP.
"""
import json
import os
import re
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS = os.path.join(LOCAL_DIR, 'logs', 'wrongway_status.json')
TRAIN_LOG = os.path.join(LOCAL_DIR, 'logs', 'train_wrongway_det.log')
COLLECT_LOG = os.path.join(LOCAL_DIR, 'logs', 'collect_wrongway.log')

EPOCH_RE = re.compile(r'^\s*(\d+)/(\d+)\s+\S+G\s.*?(\d+)/(\d+)\s+(\S+it/s|\S+s/it)?', re.M)
MAP_RE = re.compile(r'^\s+all\s+\d+\s+\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', re.M)
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

STEPS = [('collect', '1. เก็บภาพจากกล้องทุกตัว + label ทิศรถอัตโนมัติ'),
         ('finalize', '2. สร้าง data.yaml + ภาพกลับด้าน'),
         ('train', '3. เทรน YOLO26x -> wrongway_det.pt'),
         ('done', '4. เสร็จ')]
ORDER = {'collect': 0, 'wait': 0, 'finalize': 1, 'collected': 1, 'train': 2, 'done': 3}


def tail(path, n=20000):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - n))
            return ANSI_RE.sub('', f.read().decode('utf-8', 'ignore')).replace('\r', '\n')
    except OSError:
        return ''


def bar(pct, width=40):
    n = int(width * pct / 100)
    return '[' + '#' * n + '-' * (width - n) + f'] {pct:5.1f}%'


def fmt_t(ts):
    return datetime.fromtimestamp(ts).strftime('%H:%M') if ts else '-'


def render(st):
    step = st.get('step', '?')
    cur = ORDER.get(step, -1)
    lines = ['  WRONG-WAY (ย้อนศร) PIPELINE STATUS      ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '']
    for i, (key, label) in enumerate(STEPS):
        mark = '[x]' if i < cur or step == 'done' else ('[>]' if i == cur else '[ ]')
        lines.append(f'  {mark} {label}')
    lines.append('')
    if step == 'collect':
        cams, cam = st.get('cameras', 1), st.get('camera', 0)
        pct = 100.0 * cam / max(1, cams)
        lines.append(f'  รอบ {st.get("round")}/{st.get("rounds")}  กล้อง {cam}/{cams}  {bar(pct)}')
        lines.append(f'  ภาพในชุดข้อมูล {st.get("images", 0)} (รอบนี้ +{st.get("kept_this_round", 0)})  ·  cell ที่รู้ทิศแล้ว {st.get("maps_known", 0)}')
        lines.append(f'  กล้องล่าสุด: {st.get("last_camera", "")}')
    elif step == 'wait':
        left = max(0, st.get('next_at', 0) - time.time())
        lines.append(f'  รอบ {st.get("round")}/{st.get("rounds")} เสร็จ  ·  ภาพ {st.get("images", 0)}  ·  cell ที่รู้ทิศแล้ว {st.get("maps_known", 0)}')
        lines.append(f'  รอบถัดไป {fmt_t(st.get("next_at"))} (อีก {int(left // 60)} นาที)')
    elif step in ('finalize', 'collected'):
        lines.append(f'  ภาพทั้งหมด {st.get("images", 0)}  ·  กำลังเตรียม data.yaml' if step == 'finalize' else f'  เก็บครบ {st.get("images", 0)} ภาพ  ·  รอเทรน')
    elif step == 'train':
        txt = tail(TRAIN_LOG)
        ep, mp = EPOCH_RE.findall(txt), MAP_RE.findall(txt)
        lines.append(f'  โมเดล {st.get("model")}  epochs {st.get("epochs")}  batch {st.get("batch")}  run {st.get("name")}')
        if 'Traceback' in txt or 'CUDA out of memory' in txt:
            last = [l for l in txt.strip().splitlines() if l.strip()][-3:]
            lines.append('  ERROR: ' + ' | '.join(last)[:200])
            if 'out of memory' in txt:
                lines.append('  -> GPU เต็ม: ปิด server แล้วรัน train_wrongway.bat 60 4')
        elif not ep:
            lines.append('  กำลังโหลด dataset / โมเดล ...')
        else:
            e, E, i, I, spd = ep[-1]
            e, E, i, I = int(e), int(E), int(i), int(I)
            pct = 100.0 * ((e - 1) + i / max(1, I)) / E
            lines.append(f'  epoch {e}/{E}  batch {i}/{I}  {spd or ""}')
            lines.append('  ' + bar(pct))
            if mp:
                lines.append(f'  val: precision {float(mp[-1][0]):.3f}  recall {float(mp[-1][1]):.3f}  mAP50 {float(mp[-1][2]):.3f}  mAP50-95 {float(mp[-1][3]):.3f}')
    elif step == 'done':
        lines.append(f'  เสร็จ -> {st.get("out")}' + (f'  (mAP50 {st["map50"]:.3f})' if st.get('map50') is not None else ''))
        lines.append('  รีสตาร์ต server (restart_public.bat) เพื่อให้ตรวจย้อนศรใช้โมเดลใหม่')
    else:
        lines.append('  ยังไม่เริ่ม: รัน wrongway_pipeline.bat')
    lines.append('')
    lines.append(f'  อัปเดตล่าสุด {fmt_t(st.get("ts"))}  ·  log: local\\logs\\collect_wrongway.log, train_wrongway_det.log')
    return '\n'.join(lines)


def main():
    while True:
        try:
            with open(STATUS, encoding='utf-8') as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        os.system('cls' if os.name == 'nt' else 'clear')
        print(render(st))
        if st.get('step') == 'done':
            break
        time.sleep(2)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
