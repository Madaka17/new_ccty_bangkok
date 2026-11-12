"""Copy an SQLite database with the online backup API. The test launchers use it to seed instances/test.

    python launch/copy_db.py <src> <dst>

The production database runs in WAL mode, so recent rows can sit in the -wal file. A plain file copy
misses them, and can copy a torn file while the server writes. The backup API takes a consistent snapshot
that includes the WAL. A missing <src> is not an error. Exit 0 on success, 1 on failure.
"""
import os
import sqlite3
import sys
from contextlib import closing


def copy_db(src, dst):
    if not os.path.exists(src):
        return
    try:
        with closing(sqlite3.connect(src, timeout=30)) as s, closing(sqlite3.connect(dst)) as d:
            s.backup(d)
    except BaseException:
        for p in (dst, dst + '-wal', dst + '-shm', dst + '-journal'):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise


def main(argv):
    if len(argv) != 3:
        print('usage: copy_db.py <src> <dst>', file=sys.stderr)
        return 1
    try:
        copy_db(argv[1], argv[2])
    except (sqlite3.Error, OSError) as e:
        print(f'copy_db: failed to copy {argv[1]} to {argv[2]}: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
