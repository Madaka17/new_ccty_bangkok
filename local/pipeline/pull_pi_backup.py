"""Nightly pull of the Raspberry Pi backups to this Windows PC, so a copy lives off the Pi's SSD.

Runs on the PC (stdlib only). Read-only on the Pi: it only runs `ls` and `tar cf -` over ssh.

    python pull_pi_backup.py

Config (env, all optional):
    PI_HOST=test@192.168.1.109
    PI_KEY=%USERPROFILE%\\.ssh\\bkkpi_ed25519
    PULL_DEST=D:\\BKK-Backup\\pi
    PULL_KEEP=14                       # complete db folders kept
    PI_BACKUP_DIR=/mnt/ssd/data_smartstreet/backup

Layout under PULL_DEST:
    db\\<YYYY-MM-DD_HHMM>\\           complete copy (has a .complete marker after the quick_check passes)
    db\\.bad-<name>\\                 copy that failed quick_check (no .complete)
    files\\data_smartstreet\\         rolling mirror of helmet/ violations/ wrongway/
    files\\user_reports\\             rolling mirror of user_reports/
    pull.log, last_ok.txt
"""
import contextlib
import os
import posixpath
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

DB_NAME = 'vehicle_counts.db'
FILE_SOURCES = [
    # (remote base dir, dirs to take, local folder the archive is extracted into)
    ('/mnt/ssd/data_smartstreet', ['helmet', 'violations', 'wrongway'], 'data_smartstreet'),
    ('/mnt/ssd/new_ccty_bangkok/instances/production/cache', ['user_reports'], ''),
]


DEFAULT_PI_BACKUP_DIR = '/mnt/ssd/data_smartstreet/backup'


class UnsafeMember(Exception):
    pass


def load_config(env):
    return {
        'PI_HOST': env.get('PI_HOST', 'test@192.168.1.109'),
        'PI_KEY': env.get('PI_KEY', os.path.join(os.path.expanduser('~'), '.ssh', 'bkkpi_ed25519')),
        'PULL_DEST': env.get('PULL_DEST', r'D:\BKK-Backup\pi'),
        'PULL_KEEP': int(env.get('PULL_KEEP', '14')),
        'PI_BACKUP_DIR': env.get('PI_BACKUP_DIR', DEFAULT_PI_BACKUP_DIR),
    }


def build_ssh_args(cfg, remote_cmd):
    return [
        'ssh', '-i', cfg['PI_KEY'], '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
        cfg['PI_HOST'], remote_cmd,
    ]


def parse_latest(ls_output):
    names = []
    for line in ls_output.splitlines():
        line = line.strip().rstrip('/')
        if not line:
            continue
        name = posixpath.basename(line)
        if name.startswith('20'):
            names.append(name)
    return max(names) if names else None


def safe_member(name):
    if not name or name.startswith(('/', '\\')) or ':' in name:
        return False
    parts = name.replace('\\', '/').split('/')
    return '..' not in parts


def extract_tar(stream, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=stream, mode='r|') as tar:
        for member in tar:
            if not safe_member(member.name):
                raise UnsafeMember(member.name)
            target = dest.joinpath(*member.name.replace('\\', '/').split('/'))
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(member)
                with open(target, 'wb') as out:
                    shutil.copyfileobj(src, out)
            else:
                raise UnsafeMember(member.name)


def quick_check(path):
    path = Path(path)
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        try:
            return conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def is_complete(folder):
    return (Path(folder) / '.complete').exists()


def files_remote_cmd(base, names):
    return f"cd {base} && tar cf - --ignore-failed-read $(ls -d {' '.join(names)} 2>/dev/null)"


def _remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def run_db_step(db_root, name, open_stream, log, remote_base=DEFAULT_PI_BACKUP_DIR):
    db_root = Path(db_root)
    folder = db_root / name
    if is_complete(folder):
        log(f'db {name}: already complete, skipped')
        return True
    partial = db_root / f'.partial-{name}'
    _remove(partial)
    _remove(folder)
    with open_stream(f'tar cf - -C {remote_base} {name}') as stream:
        extract_tar(stream, partial)
    os.rename(partial / name, folder)
    _remove(partial)
    if quick_check(folder / DB_NAME):
        (folder / '.complete').write_text(datetime.now().isoformat(timespec='seconds'), encoding='utf-8')
        log(f'db {name}: copied, quick_check ok')
        return True
    bad = db_root / f'.bad-{name}'
    _remove(bad)
    os.rename(folder, bad)
    log(f'db {name}: quick_check FAILED, kept as {bad.name} (no .complete)')
    return False


def prune_db(db_root, keep, log):
    db_root = Path(db_root)
    if not db_root.is_dir():
        return []
    for p in db_root.iterdir():
        if p.name.startswith('.partial-'):
            _remove(p)
            log(f'removed stale {p.name}')
    complete = sorted(p.name for p in db_root.iterdir() if p.is_dir() and is_complete(p))
    removed = complete[:-keep] if keep > 0 else complete
    for name in removed:
        _remove(db_root / name)
        log(f'pruned db {name}')
    return removed


def run_files_step(dest_folder, base, names, open_stream, log):
    dest_folder = Path(dest_folder)
    with open_stream(files_remote_cmd(base, names)) as stream:
        extract_tar(stream, dest_folder)
    log(f'files {base} {" ".join(names)} -> {dest_folder}')
    return True


@contextlib.contextmanager
def ssh_tar_stream(cfg, remote_cmd):
    proc = subprocess.Popen(build_ssh_args(cfg, remote_cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        yield proc.stdout
        # the tar end-of-archive padding must be drained, or tar blocks and never exits
        while proc.stdout.read(1 << 20):
            pass
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    err = proc.stderr.read().decode('utf-8', 'replace')
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f'ssh tar failed rc={rc}: {err.strip()}')


def make_logger(log_path):
    def log(msg):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    return log


def main(env=None):
    cfg = load_config(os.environ if env is None else env)
    dest = Path(cfg['PULL_DEST'])
    dest.mkdir(parents=True, exist_ok=True)
    log = make_logger(dest / 'pull.log')
    opener = lambda cmd: ssh_tar_stream(cfg, cmd)
    all_ok = True
    name = None

    try:
        out = subprocess.run(build_ssh_args(cfg, f"ls -1d {cfg['PI_BACKUP_DIR']}/20*"),
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f'ls rc={out.returncode}: {out.stderr.strip()}')
        name = parse_latest(out.stdout)
        if name is None:
            raise RuntimeError('no backup folder on the Pi')
        log(f'latest Pi backup: {name}')
        db_ok = run_db_step(dest / 'db', name, opener, log, remote_base=cfg['PI_BACKUP_DIR'])
    except Exception as e:
        log(f'db step FAILED: {e}')
        db_ok = False
    all_ok &= db_ok

    try:
        removed = prune_db(dest / 'db', cfg['PULL_KEEP'], log)
        log(f'prune: {len(removed)} old db folder(s) removed, keep {cfg["PULL_KEEP"]}')
    except Exception as e:
        log(f'prune FAILED: {e}')
        all_ok = False

    for base, names, sub in FILE_SOURCES:
        try:
            run_files_step(dest / 'files' / sub, base, names, opener, log)
        except Exception as e:
            log(f'files step {base} FAILED: {e}')
            all_ok = False

    log(f'summary: db={"ok" if db_ok else "FAILED"} files={"ok" if all_ok else "see above"} dest={dest}')
    if all_ok:
        (dest / 'last_ok.txt').write_text(f"{datetime.now().isoformat(timespec='seconds')} {name}\n", encoding='utf-8')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
