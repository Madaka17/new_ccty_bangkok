"""Live progress bar for an Ultralytics training log (one line, refreshed every second).

    python watch_train.py                       # local/logs/train_helmet_det.log
    python watch_train.py path\to\other.log
    python watch_train.py local\logs\train_wrongway_det.log

Reads the last progress line ("  12/80  ...  640: 45% ... 37/82 1.3it/s 0:28<0:35") and prints
overall % = (finished epochs + fraction of the current one) / total, plus latest val mAP.
"""
import os
import re
import sys
import time

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(LOCAL_DIR, 'logs', 'train_helmet_det.log')

EPOCH_RE = re.compile(r'^\s*(\d+)/(\d+)\s+\S+G\s.*?(\d+)/(\d+)\s+(\S+it/s|\S+s/it)?', re.M)
MAP_RE = re.compile(r'^\s+all\s+\d+\s+\d+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', re.M)
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def tail(path, n=20000):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - n))
            raw = f.read()
            if b'\x00' in raw[:200]:
                try:
                    txt = raw.decode('utf-16', 'ignore')
                except Exception:
                    txt = raw.replace(b'\x00', b'').decode('utf-8', 'ignore')
            else:
                txt = raw.decode('utf-8', 'ignore')
            return ANSI_RE.sub('', txt).replace('\r', '\n')
    except OSError:
        return ''


def main():
    t0 = time.time()
    while True:
        txt = tail(LOG)
        ep = EPOCH_RE.findall(txt)
        mp = MAP_RE.findall(txt)
        if 'done ->' in txt:
            print('\n[done] ' + txt[txt.rfind('done ->') - 16:].strip())
            break
        if 'Traceback' in txt or 'Error' in txt.split('Starting training')[-1]:
            tail_lines = [l for l in txt.strip().splitlines() if l.strip()][-4:]
            print('\n[error] ' + ' | '.join(tail_lines))
            break
        if not ep:
            print(f'\rwaiting for training to start ... {int(time.time() - t0)}s', end='')
            time.sleep(1)
            continue
        e, E, i, I, spd = ep[-1]
        e, E, i, I = int(e), int(E), int(i), int(I)
        pct = 100.0 * ((e - 1) + i / max(1, I)) / E
        elapsed = time.time() - t0
        bar = '#' * int(pct / 2.5) + '-' * (40 - int(pct / 2.5))
        mapping = f'  mAP50 {float(mp[-1][2]):.3f}' if mp else ''
        print(f'\r[{bar}] {pct:5.1f}%  epoch {e}/{E}  batch {i}/{I}  {spd or ""}{mapping}   ', end='')
        time.sleep(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
