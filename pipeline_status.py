"""Show where the dataset -> train pipeline is right now.

    python pipeline_status.py              # Single check
    python pipeline_status.py --watch      # Live monitor (auto-refresh)
    python pipeline_status.py -w 3         # Refresh every 3 seconds

Reads the scheduled task, running processes, dataset counts, pipeline.log and the server.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE_DIR, 'pipeline.log')
TASK = 'BKK_Dataset_Train'


def ps(cmd):
    try:
        return subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:
        return f'(powershell error: {e})'


def processes():
    target_keys = ('collect_dataset', 'clean_dataset', 'train_model', 'pipeline_day', 'server.py')
    found = {}
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = ' '.join(p.info['cmdline'] or [])
                if not cmdline or 'pipeline_status' in cmdline:
                    continue
                for key in target_keys:
                    if key in cmdline:
                        found.setdefault(key, str(p.info['pid']))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return found
    except ImportError:
        pass

    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'collect_dataset|train_model|clean_dataset|pipeline_day|server\\.py' } "
             "| ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }")
    for line in out.splitlines():
        pid, _, cmd = line.partition('|')
        if 'Get-CimInstance' in cmd or 'pipeline_status' in cmd:
            continue
        for key in target_keys:
            if key in cmd:
                found.setdefault(key, pid)
    return found


def task_info():
    out = ps(f"$t = Get-ScheduledTask -TaskName '{TASK}' -ErrorAction SilentlyContinue; if ($t) {{ $i = $t | Get-ScheduledTaskInfo; "
             f"'{{0}}|{{1}}|{{2}}|{{3}}' -f $t.State, $i.NextRunTime, $i.LastRunTime, $i.LastTaskResult }}")
    if not out:
        return None
    parts = out.split('|')
    if len(parts) < 4:
        return None
    state, nxt, last, result = parts
    return {'state': state, 'next': nxt, 'last': last, 'result': result}


def dataset_counts():
    c = {}
    for split in ('train', 'val'):
        c[split] = len(glob.glob(os.path.join(BASE_DIR, 'dataset', 'images', split, '*.jpg')))
    return c


def last_stage():
    if not os.path.exists(LOG):
        return None, []
    try:
        with open(LOG, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        stage = None
        for line in lines:
            if line.startswith('=== ['):
                stage = line
        tail = [l for l in lines[-40:] if not l.startswith('[h264') and l.strip()][-6:]
        return stage, tail
    except Exception:
        return None, []


def server_health():
    try:
        with urllib.request.urlopen('http://localhost:8000/api/ai/stats', timeout=2) as r:
            s = json.load(r)
        return f"online · AI camera {s.get('title', '-')} · {s.get('fps', 0)} FPS"
    except Exception:
        return 'offline'


def train_progress():
    runs = sorted(glob.glob(os.path.join(BASE_DIR, 'runs', 'train', 'bkk*', 'results.csv')), key=os.path.getmtime)
    if not runs:
        return None
    try:
        rows = open(runs[-1]).read().splitlines()
        if len(rows) < 2:
            return f'{os.path.dirname(runs[-1])}: starting'
        head = [h.strip() for h in rows[0].split(',')]
        last = [v.strip() for v in rows[-1].split(',')]
        d = dict(zip(head, last))
        return f"{os.path.basename(os.path.dirname(os.path.dirname(runs[-1])))}: epoch {d.get('epoch')} · mAP50 {float(d.get('metrics/mAP50(B)', 0)):.3f} · mAP50-95 {float(d.get('metrics/mAP50-95(B)', 0)):.3f}"
    except Exception:
        return None


def print_status(is_watch=False, interval=5):
    now = datetime.now()
    procs = processes()
    task = task_info()
    counts = dataset_counts()
    stage, tail = last_stage()
    models = [os.path.basename(p) for p in glob.glob(os.path.join(BASE_DIR, '*_bkk.pt'))]

    if 'train_model' in procs:
        phase = '🔥 3/3 กำลัง train model'
    elif 'clean_dataset' in procs:
        phase = '🧹 2/3 กำลัง clean label'
    elif 'collect_dataset' in procs:
        phase = '📸 1/3 กำลังเก็บภาพจากกล้อง'
    elif stage and 'finished' in stage:
        phase = '✅ เสร็จสิ้นสมบูรณ์'
    elif task and task['state'] == 'Ready':
        phase = f"⏳ รอเริ่มตามเวลา ({task['next']})"
    elif task and task['state'] == 'Running':
        phase = '⚡ Task กำลังรัน (กำลังดำเนินการ)'
    else:
        phase = '⏹️ ไม่ได้รันและไม่มี schedule'

    print("=" * 68)
    print("  🚦 BKK Traffic CCTV — Pipeline & Server Status Monitor")
    if is_watch:
        print(f"  [Live Auto-Refresh ทุก {interval} วินาที | กด Ctrl+C เพื่อหยุด]")
    print("=" * 68)
    print(f'เวลา          {now:%Y-%m-%d %H:%M:%S}')
    print(f'ขั้นตอน       {phase}')
    if task:
        print(f'schedule      {TASK}: {task["state"]} · next {task["next"]} · last run {task["last"]} (result {task["result"]})')
    
    proc_summary = ', '.join(f'{k} (PID {v})' for k, v in procs.items() if k != 'server.py')
    print(f'process       {proc_summary or "ไม่มี pipeline process กำลังรัน"}')
    if 'server.py' in procs:
        print(f'server.py     PID {procs["server.py"]} · {server_health()}')
    else:
        print(f'server.py     {server_health()}')

    print(f'dataset       train: {counts["train"]} · val: {counts["val"]} · รวม: {counts["train"] + counts["val"]} ภาพ')
    prog = train_progress()
    if prog:
        print(f'train         {prog}')
    print(f'model         ' + (', '.join(models) if models else 'ยังไม่มี *_bkk.pt (ใช้ yolo11x.pt เดิม)'))
    if stage:
        print(f'log ล่าสุด    {stage}')
        for l in tail:
            print(f'              {l[:100]}')
    print("=" * 68)


def main():
    parser = argparse.ArgumentParser(description="Monitor BKK Traffic Pipeline Status")
    parser.add_argument('-w', '--watch', nargs='?', const=5, type=int, default=None,
                        help="Live watch mode with interval in seconds (default: 5)")
    args = parser.parse_args()

    if args.watch is not None:
        interval = max(1, args.watch)
        try:
            while True:
                os.system('cls' if os.name == 'nt' else 'clear')
                print_status(is_watch=True, interval=interval)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[!] ปิดระบบติดตามสถานะเรียบร้อยแล้ว")
    else:
        print_status(is_watch=False)


if __name__ == '__main__':
    main()
