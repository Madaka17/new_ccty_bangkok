"""Nightly upkeep for vehicle_counts.db: prune old rows, VACUUM, and copy the database + the helmet /
violation CSV indexes to a dated backup folder on the data drive.

    python backup_db.py                 # prune + backup to <BMA_DATA_DIR>\backup\
    python backup_db.py --keep-days 60  # keep 60 days of bma_history / samples (default 90)
    python backup_db.py --no-prune      # backup only

Safe while the server runs: pruning uses short transactions and the copy uses the SQLite online
backup API, so a half-written file is never produced. Backups older than --keep-backups (14) are
deleted. Schedule with backup_db.bat (Task Scheduler, e.g. daily 03:30).
"""
import argparse
import glob
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

LOCAL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(LOCAL_DIR)
sys.path.insert(0, BASE_DIR)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

DB = os.path.join(BASE_DIR, 'vehicle_counts.db')
DATA_DIR = os.getenv('BMA_DATA_DIR', r'D:\Data')
BACKUP_DIR = os.getenv('BACKUP_DIR', os.path.join(DATA_DIR, 'backup'))
# table -> epoch column. The no-helmet log, violations and incidents are kept forever (evidence).
PRUNE = {'bma_history': 'ts', 'samples': 'ts'}


def prune(keep_days):
    cutoff = int(time.time() - keep_days * 86400)
    conn = sqlite3.connect(DB, timeout=30)
    for table, col in PRUNE.items():
        n = conn.execute(f'DELETE FROM {table} WHERE {col} < ?', (cutoff,)).rowcount
        conn.commit()
        print(f'[backup] {table}: deleted {n} rows older than {keep_days} days')
    # routine helmet checks (helmet / unclear / error) older than 7 days; no_helmet stays
    n = conn.execute("DELETE FROM helmet_checks WHERE verdict != 'no_helmet' AND ts < ?", (int(time.time() - 7 * 86400),)).rowcount
    conn.commit()
    print(f'[backup] helmet_checks: deleted {n} routine rows older than 7 days')
    before = os.path.getsize(DB)
    conn.execute('VACUUM')
    conn.close()
    print(f'[backup] VACUUM {before / 2**20:.1f} MB -> {os.path.getsize(DB) / 2**20:.1f} MB')


def backup(keep_backups):
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    out_dir = os.path.join(BACKUP_DIR, stamp)
    os.makedirs(out_dir, exist_ok=True)
    src = sqlite3.connect(DB, timeout=30)
    dst = sqlite3.connect(os.path.join(out_dir, 'vehicle_counts.db'))
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    for name in ('helmet/helmet.csv', 'violations/violations.csv', 'roads_index.csv', 'summary_daily.csv'):
        p = os.path.join(DATA_DIR, name)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(out_dir, os.path.basename(p)))
    for cfg in ('.env', 'config/cameras_bma.json', 'config/cameras_bkk.json'):
        p = os.path.join(BASE_DIR, cfg)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(out_dir, os.path.basename(cfg)))
    print(f'[backup] written {out_dir}')
    old = sorted(glob.glob(os.path.join(BACKUP_DIR, '20*')))[:-keep_backups]
    for d in old:
        shutil.rmtree(d, ignore_errors=True)
        print(f'[backup] removed old backup {d}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--keep-days', type=int, default=90)
    ap.add_argument('--keep-backups', type=int, default=14)
    ap.add_argument('--no-prune', action='store_true')
    args = ap.parse_args()
    if not os.path.exists(DB):
        sys.exit(f'[backup] {DB} not found')
    if not args.no_prune:
        prune(args.keep_days)
    backup(args.keep_backups)


if __name__ == '__main__':
    main()
