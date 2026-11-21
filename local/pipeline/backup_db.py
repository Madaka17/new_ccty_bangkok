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

# the production server's database (BACKUP_DB: another one, e.g. a test copy)
DB = os.getenv('BACKUP_DB') or os.path.join(BASE_DIR, 'instances', 'production', 'vehicle_counts.db')
# the production security-event log (BACKUP_SECURITY_DB overrides; skipped when the file is missing)
SECURITY_DB = os.getenv('BACKUP_SECURITY_DB') or os.path.join(BASE_DIR, 'instances', 'production', 'security_events.db')
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


def _copy_db(src_path, dst_path):
    src = dst = None
    try:
        src = sqlite3.connect(src_path, timeout=30)
        dst = sqlite3.connect(dst_path)
        with dst:
            src.backup(dst)
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()


def _remove_tree(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def backup(keep_backups):
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    out_dir = os.path.join(BACKUP_DIR, stamp)
    # written under .tmp-<stamp> and renamed at the end, so a half-written folder never looks complete
    tmp_dir = os.path.join(BACKUP_DIR, f'.tmp-{stamp}')
    _remove_tree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        _copy_db(DB, os.path.join(tmp_dir, 'vehicle_counts.db'))
        if os.path.exists(SECURITY_DB):
            try:
                _copy_db(SECURITY_DB, os.path.join(tmp_dir, 'security_events.db'))
            except Exception as e:
                print(f'[backup] security_events.db FAILED: {e}')
        for name in ('helmet/helmet.csv', 'violations/violations.csv', 'roads_index.csv', 'summary_daily.csv'):
            p = os.path.join(DATA_DIR, name)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(tmp_dir, os.path.basename(p)))
        for cfg in ('.env', 'config/cameras_bma.json', 'config/cameras_bkk.json'):
            p = os.path.join(BASE_DIR, cfg)
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(tmp_dir, os.path.basename(cfg)))
        _remove_tree(out_dir)
        os.rename(tmp_dir, out_dir)
    except BaseException:
        _remove_tree(tmp_dir)
        raise
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
