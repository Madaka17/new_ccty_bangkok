"""Realtime Pipeline & AI Training Monitor for BKK Traffic CCTV.

    python pipeline_status.py              # Single check
    python pipeline_status.py --watch 1    # Realtime monitor (auto-refresh every 1s)

Displays real-time collection progress, camera details, training epochs, loss/mAP metrics,
GPU status, process states, and live activity log.
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
LOG_FILE = os.path.join(BASE_DIR, 'pipeline.log')
CAMERAS_FILE = os.path.join(BASE_DIR, 'cameras_bkk.json')
TASK_NAME = 'BKK_Dataset_Train'

# Load camera names once
CAMERA_NAMES = {}
if os.path.exists(CAMERAS_FILE):
    try:
        with open(CAMERAS_FILE, encoding='utf-8') as f:
            for item in json.load(f).get('items', []):
                cid = item.get('camid')
                if cid:
                    CAMERA_NAMES[cid] = item.get('short_title') or item.get('title') or cid
    except Exception:
        pass


def make_bar(current, total, width=22):
    """Generate a clean ASCII/Unicode progress bar."""
    if not total or total <= 0:
        return f"[{'░' * width}] 0.0%"
    pct = min(1.0, max(0.0, current / total))
    filled = int(round(width * pct))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct * 100:.1f}%"


def get_gpu_info():
    """Query NVIDIA GPU usage via nvidia-smi (fast, ~30ms)."""
    try:
        res = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(',')]
            if len(parts) >= 4:
                name, util, used_mb, total_mb = parts[0], parts[1], float(parts[2]), float(parts[3])
                short_name = name.replace("NVIDIA GeForce ", "").replace("NVIDIA ", "")
                return f"{short_name} · GPU: {util}% · VRAM: {used_mb/1024:.1f} / {total_mb/1024:.1f} GB"
    except Exception:
        pass
    return None


def get_processes():
    """Find running pipeline and server processes."""
    targets = ('collect_dataset', 'clean_dataset', 'train_model', 'pipeline_day', 'server.py')
    found = {}
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = ' '.join(p.info['cmdline'] or [])
                if not cmdline or 'pipeline_status' in cmdline:
                    continue
                for key in targets:
                    if key in cmdline:
                        found.setdefault(key, str(p.info['pid']))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return found
    except ImportError:
        pass

    try:
        res = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'collect_dataset|train_model|clean_dataset|pipeline_day|server\\.py' } | ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }"],
            capture_output=True, text=True, timeout=5
        )
        for line in res.stdout.strip().splitlines():
            pid, _, cmd = line.partition('|')
            if 'pipeline_status' in cmd or 'Get-CimInstance' in cmd:
                continue
            for key in targets:
                if key in cmd:
                    found.setdefault(key, pid)
    except Exception:
        pass
    return found


_task_cache = {'time': 0, 'data': None}

def get_task_info():
    """Check Windows Task Scheduler status (cached for 10s to stay fast)."""
    now = time.time()
    if now - _task_cache['time'] < 10 and _task_cache['data'] is not None:
        return _task_cache['data']

    try:
        res = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f"$t = Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue; if ($t) {{ $i = $t | Get-ScheduledTaskInfo; '{{0}}|{{1}}|{{2}}|{{3}}' -f $t.State, $i.NextRunTime, $i.LastRunTime, $i.LastTaskResult }}"],
            capture_output=True, text=True, timeout=5
        )
        out = res.stdout.strip()
        if out:
            parts = out.split('|')
            if len(parts) >= 4:
                data = {'state': parts[0], 'next': parts[1], 'last': parts[2], 'result': parts[3]}
                _task_cache['time'] = now
                _task_cache['data'] = data
                return data
    except Exception:
        pass
    return _task_cache.get('data')


def get_dataset_info():
    """Scan dataset counts and inspect the latest captured frame."""
    train_files = glob.glob(os.path.join(BASE_DIR, 'dataset', 'images', 'train', '*.jpg'))
    val_files = glob.glob(os.path.join(BASE_DIR, 'dataset', 'images', 'val', '*.jpg'))
    n_train, n_val = len(train_files), len(val_files)
    total = n_train + n_val

    latest_info = None
    all_files = train_files + val_files
    if all_files:
        latest_file = max(all_files, key=os.path.getmtime)
        fname = os.path.basename(latest_file)
        mtime = datetime.fromtimestamp(os.path.getmtime(latest_file))
        
        # Parse camid from name: CAMID_YYYYMMDD_HHMMSS.jpg
        parts = fname.rsplit('_202', 1)
        camid = parts[0] if len(parts) == 2 else fname.split('_')[0]
        title = CAMERA_NAMES.get(camid, camid)
        
        # Count boxes in corresponding label file
        split = 'train' if latest_file in train_files else 'val'
        lbl_file = os.path.join(BASE_DIR, 'dataset', 'labels', split, os.path.splitext(fname)[0] + '.txt')
        boxes_count = 0
        if os.path.exists(lbl_file):
            try:
                with open(lbl_file, 'r', encoding='utf-8') as f:
                    boxes_count = len([line for line in f if line.strip()])
            except Exception:
                pass

        latest_info = {
            'filename': fname,
            'camid': camid,
            'title': title,
            'split': split,
            'time': mtime.strftime('%H:%M:%S'),
            'boxes': boxes_count
        }

    return {'train': n_train, 'val': n_val, 'total': total, 'latest': latest_info}


def get_training_info():
    """Read Ultralytics YOLO training progress from runs/train/."""
    run_dirs = sorted(glob.glob(os.path.join(BASE_DIR, 'runs', 'train', 'bkk*')), key=os.path.getmtime)
    if not run_dirs:
        # Check if completed weights exist
        bkk_weights = glob.glob(os.path.join(BASE_DIR, '*_bkk.pt'))
        return {'status': 'idle', 'weights': [os.path.basename(w) for w in bkk_weights]}

    latest_run = run_dirs[-1]
    csv_file = os.path.join(latest_run, 'results.csv')
    best_pt = os.path.join(latest_run, 'weights', 'best.pt')
    last_pt = os.path.join(latest_run, 'weights', 'last.pt')
    has_best = os.path.exists(best_pt)

    if not os.path.exists(csv_file):
        return {
            'status': 'starting',
            'run_name': os.path.basename(latest_run),
            'has_best': has_best
        }

    try:
        with open(csv_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        if len(lines) < 2:
            return {'status': 'starting', 'run_name': os.path.basename(latest_run), 'has_best': has_best}

        headers = [h.strip() for h in lines[0].split(',')]
        last_row = [v.strip() for v in lines[-1].split(',')]
        metrics = dict(zip(headers, last_row))

        epoch = int(metrics.get('epoch', len(lines) - 2))
        map50 = float(metrics.get('metrics/mAP50(B)', 0))
        map5095 = float(metrics.get('metrics/mAP50-95(B)', 0))
        box_loss = float(metrics.get('train/box_loss', metrics.get('val/box_loss', 0)))
        cls_loss = float(metrics.get('train/cls_loss', metrics.get('val/cls_loss', 0)))
        dfl_loss = float(metrics.get('train/dfl_loss', metrics.get('val/dfl_loss', 0)))

        return {
            'status': 'training',
            'run_name': os.path.basename(latest_run),
            'epoch': epoch,
            'map50': map50,
            'map5095': map5095,
            'box_loss': box_loss,
            'cls_loss': cls_loss,
            'dfl_loss': dfl_loss,
            'has_best': has_best
        }
    except Exception:
        return {'status': 'error'}


def parse_pipeline_log():
    """Extract stage info, parameters, and clean activity log lines."""
    if not os.path.exists(LOG_FILE):
        return {'stage': None, 'target_images': None, 'until_time': None, 'epochs': None, 'logs': []}

    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()

        stage = None
        target_images = None
        until_time = None
        epochs = None
        clean_logs = []

        for l in lines:
            s = l.strip()
            if not s:
                continue
            if s.startswith('=== ['):
                stage = s
                # Parse target images
                m_target = re.search(r'target\s+(\d+)', s)
                if m_target:
                    target_images = int(m_target.group(1))
                m_until = re.search(r'until\s+([0-9:]+)', s)
                if m_until:
                    until_time = m_until.group(1)
                m_ep = re.search(r'(\d+)\s+epochs', s)
                if m_ep:
                    epochs = int(m_ep.group(1))

            # Filter out h264/ffmpeg warning noise
            if any(ign in s for ign in ('[h264', '[tls', 'co located POCs', 'illegal short term',
                                       'mmco:', 'Stream timeout', 'failed to send close', 'Unable to read')):
                continue
            clean_logs.append(s)

        return {
            'stage': stage,
            'target_images': target_images,
            'until_time': until_time,
            'epochs': epochs,
            'logs': clean_logs[-7:]
        }
    except Exception:
        return {'stage': None, 'target_images': None, 'until_time': None, 'epochs': None, 'logs': []}


def get_server_health():
    """Check AI server status via localhost API."""
    try:
        with urllib.request.urlopen('http://localhost:8000/api/ai/stats', timeout=1.5) as resp:
            data = json.load(resp)
            return {
                'online': True,
                'title': data.get('title', '-'),
                'fps': data.get('fps', 0),
                'cars': data.get('cars', 0),
                'motorcycles': data.get('motorcycles', 0),
                'total': data.get('total', 0)
            }
    except Exception:
        return {'online': False}


def render_dashboard(is_watch=False, interval=1):
    now = datetime.now()
    procs = get_processes()
    task = get_task_info()
    dataset = get_dataset_info()
    training = get_training_info()
    pipeline_meta = parse_pipeline_log()
    server = get_server_health()
    gpu = get_gpu_info()

    # Determine overall phase
    is_collecting = 'collect_dataset' in procs
    is_cleaning = 'clean_dataset' in procs
    is_training = 'train_model' in procs

    if is_training:
        phase_str = "🔥 ขั้นตอนที่ 3/3: กำลังเทรนโมเดล YOLO11 (Fine-Tuning)"
    elif is_cleaning:
        phase_str = "🧹 ขั้นตอนที่ 2/3: คลีน Label และตัดภาพซ้ำ (Cleaning Dataset)"
    elif is_collecting:
        phase_str = "📸 ขั้นตอนที่ 1/3: กำลังเก็บภาพจากกล้อง CCTV สด (Collecting Frames)"
    elif pipeline_meta['stage'] and 'finished' in pipeline_meta['stage']:
        phase_str = "✅ เสร็จสิ้นกระบวนการทั้งหมดแล้ว (Pipeline Finished)"
    elif task and task.get('state') == 'Ready':
        phase_str = f"⏳ รอเริ่มตามเวลาที่กำหนด ({task.get('next')})"
    elif task and task.get('state') == 'Running':
        phase_str = "⚡ Task Scheduler กำลังทำงาน (Processing)"
    else:
        phase_str = "⏹️ ว่าง (Idle) — เซิร์ฟเวอร์พร้อมทำงาน"

    lines = []
    lines.append("=" * 86)
    lines.append("  🚦 BKK TRAFFIC CCTV — REALTIME PIPELINE & AI TRAINING MONITOR")
    if is_watch:
        lines.append(f"  [● Live Realtime อัปเดตทุก {interval} วินาที | กด Ctrl+C เพื่อออก]")
    lines.append("=" * 86)
    lines.append(f"  ⏰ เวลา:           {now:%Y-%m-%d %H:%M:%S}")
    lines.append(f"  ⚡ สถานะหลัก:     {phase_str}")
    if gpu:
        lines.append(f"  💻 อุปกรณ์ GPU:    {gpu}")
    if task:
        lines.append(f"  🎯 ตารางเวลา:     {TASK_NAME} [{task.get('state')}] · รอบถัดไป: {task.get('next')}")

    # Section 1: Collection Progress
    lines.append("-" * 86)
    lines.append("  📸 [1/3] การเก็บภาพจากกล้อง CCTV (Dataset Collection)")
    lines.append("-" * 86)

    target = pipeline_meta.get('target_images')
    until = pipeline_meta.get('until_time')
    total_imgs = dataset['total']

    if target:
        bar = make_bar(total_imgs, target, width=24)
        lines.append(f"  ความคืบหน้า:     {bar} ({total_imgs:,} / {target:,} ภาพ)")
    elif until:
        lines.append(f"  ความคืบหน้า:     เก็บภาพตามรอบเวลาจนถึง {until} น. (เก็บได้แล้ว {total_imgs:,} ภาพ)")
    else:
        lines.append(f"  ความคืบหน้า:     มีภาพรวมทั้งสิ้น {total_imgs:,} ภาพ")

    val_pct = (dataset['val'] / total_imgs * 100) if total_imgs > 0 else 0
    lines.append(f"  การแบ่งชุดข้อมูล: Train: {dataset['train']:,} ภาพ · Val: {dataset['val']:,} ภาพ ({val_pct:.1f}%)")

    lat = dataset.get('latest')
    if lat:
        lines.append(f"  ภาพบันทึกล่าสุด:  {lat['camid']} ({lat['title']}) [{lat['split']}]")
        lines.append(f"                   เวลา {lat['time']} น. · ตรวจพบรถ {lat['boxes']} คัน")
    else:
        lines.append("  ภาพบันทึกล่าสุด:  (ยังไม่มีภาพใน dataset)")

    # Section 2: Training Progress
    lines.append("-" * 86)
    lines.append("  🔥 [3/3] การเทรนโมเดล AI (YOLO11 Training)")
    lines.append("-" * 86)

    target_epochs = pipeline_meta.get('epochs') or 60
    if training.get('status') == 'training':
        ep = training.get('epoch', 0)
        ep_bar = make_bar(ep, target_epochs, width=24)
        lines.append(f"  รอบการเทรน:      {ep_bar} (Epoch {ep} / {target_epochs})")
        lines.append(f"  คะแนนความแม่นยำ: mAP50: {training['map50']:.3f} · mAP50-95: {training['map5095']:.3f}")
        lines.append(f"  Loss ล่าสุด:     Box: {training['box_loss']:.3f} · Cls: {training['cls_loss']:.3f} · DFL: {training['dfl_loss']:.3f}")
        best_status = "✅ บันทึกแล้ว" if training.get('has_best') else "⏳ กำลังประเมิน"
        lines.append(f"  Checkpoint:      weights/best.pt ({best_status}) · โฟลเดอร์: {training.get('run_name')}")
    elif training.get('status') == 'starting':
        lines.append(f"  สถานะ:           🚀 กำลังเตรียมข้อมูลและเริ่มต้นรอบเทรน ({training.get('run_name')})...")
    else:
        bkk_models = [os.path.basename(p) for p in glob.glob(os.path.join(BASE_DIR, '*_bkk.pt'))]
        if bkk_models:
            lines.append(f"  โมเดลที่เทรนแล้ว: {', '.join(bkk_models)} (Fine-tuned พร้อมใช้งาน)")
        else:
            lines.append("  โมเดลปัจจุบัน:   ยังไม่มีโมเดล custom (*_bkk.pt) — ใช้โมเดลเริ่มต้น yolo11x.pt")

    # Section 3: Processes & Server
    lines.append("-" * 86)
    lines.append("  ⚙️ เซิร์ฟเวอร์และโปรเซส (Server & Processes)")
    lines.append("-" * 86)
    if server['online']:
        lines.append(f"  [●] AI Server:    ONLINE (PID {procs.get('server.py', '-')}) · {server['fps']} FPS · กล้อง: {server['title']}")
        lines.append(f"                    ตรวจจับสด: รถยนต์ {server['cars']} | มอเตอร์ไซค์ {server['motorcycles']} (รวม {server['total']} คัน)")
    else:
        lines.append(f"  [○] AI Server:    OFFLINE (อาจหยุดชั่วคราวเพื่อเทรนโมเดล)")

    active_procs = [f"{k} (PID {v})" for k, v in procs.items() if k != 'server.py']
    lines.append(f"  โปรเซสที่รันอยู่: {', '.join(active_procs) if active_procs else 'ไม่มีสคริปต์ pipeline ทำงานอยู่'}")
    lines.append(f"  🌐 ลิงก์ออนไลน์:  https://cctv-bangkok.tail95e28b.ts.net (Tailscale Funnel)")

    # Section 4: Live Activity Log
    if pipeline_meta['logs']:
        lines.append("-" * 86)
        lines.append("  📜 บันทึกกิจกรรมล่าสุด (Live Activity Log)")
        lines.append("-" * 86)
        for log_line in pipeline_meta['logs']:
            lines.append(f"  > {log_line[:80]}")

    lines.append("=" * 86)
    return "\n".join(lines)


def enable_vt_mode():
    """Enable Windows VT100 ANSI escape processing so in-place rendering is flicker-free."""
    if sys.platform == 'win32':
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            m = ctypes.c_ulong()
            k32.GetConsoleMode(h, ctypes.byref(m))
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            k32.SetConsoleMode(h, m.value | 0x0004)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Realtime Pipeline & AI Training Monitor")
    parser.add_argument('-w', '--watch', nargs='?', const=2, type=int, default=None,
                        help="Live realtime watch mode with interval in seconds (default: 2)")
    args = parser.parse_args()

    if args.watch is not None:
        interval = max(1, args.watch)
        enable_vt_mode()
        # Clear screen ONLY once on launch
        os.system('cls' if os.name == 'nt' else 'clear')
        # Hide blinking console cursor
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()
        try:
            while True:
                content = render_dashboard(is_watch=True, interval=interval)
                # Erase each line to end (\033[K) to avoid ghost text from shorter lines
                lines = [l + '\033[K' for l in content.splitlines()]
                # \033[H moves cursor to top-left (1,1), \033[J clears remaining screen below
                buf = '\033[H' + '\n'.join(lines) + '\n\033[J'
                sys.stdout.write(buf)
                sys.stdout.flush()
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            # Restore cursor and print exit message
            sys.stdout.write('\033[?25h\n\n[!] ปิดระบบติดตามสถานะเรียบร้อยแล้ว\n')
            sys.stdout.flush()
    else:
        print(render_dashboard(is_watch=False))


if __name__ == '__main__':
    main()

