"""local/pipeline/backup_db.py: the nightly prune + backup, also run on the Raspberry Pi by bkk-backup.timer."""
import importlib.util
import os
import sqlite3
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "local" / "pipeline" / "backup_db.py"


def load(monkeypatch, db, backup_dir):
    monkeypatch.setenv("BACKUP_DB", str(db))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    spec = importlib.util.spec_from_file_location("backup_db_under_test", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_backup_db_env_picks_the_database(monkeypatch, tmp_path):
    db = tmp_path / "counts.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE t (x)")
        c.execute("INSERT INTO t VALUES (42)")
    mod = load(monkeypatch, db, tmp_path / "backup")
    assert mod.DB == str(db)
    mod.backup(keep_backups=2)
    (folder,) = os.listdir(tmp_path / "backup")
    with sqlite3.connect(tmp_path / "backup" / folder / "vehicle_counts.db") as c:
        assert c.execute("SELECT x FROM t").fetchone() == (42,)


def test_old_backups_removed(monkeypatch, tmp_path):
    db = tmp_path / "counts.db"
    sqlite3.connect(db).close()
    for name in ("2026-01-01_0330", "2026-01-02_0330", "2026-01-03_0330"):
        (tmp_path / "backup" / name).mkdir(parents=True)
    mod = load(monkeypatch, db, tmp_path / "backup")
    mod.backup(keep_backups=2)
    assert len(os.listdir(tmp_path / "backup")) == 2
