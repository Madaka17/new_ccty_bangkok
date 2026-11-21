"""local/pipeline/backup_db.py: the nightly prune + backup, also run on the Raspberry Pi by bkk-backup.timer."""
import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest

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


def test_security_events_db_backed_up(monkeypatch, tmp_path):
    db = tmp_path / "counts.db"
    sqlite3.connect(db).close()
    sec = tmp_path / "security_events.db"
    with sqlite3.connect(sec) as c:
        c.execute("CREATE TABLE ev (x)")
        c.execute("INSERT INTO ev VALUES (7)")
    monkeypatch.setenv("BACKUP_SECURITY_DB", str(sec))
    mod = load(monkeypatch, db, tmp_path / "backup")
    assert mod.SECURITY_DB == str(sec)
    mod.backup(keep_backups=2)
    (folder,) = os.listdir(tmp_path / "backup")
    with sqlite3.connect(tmp_path / "backup" / folder / "security_events.db") as c:
        assert c.execute("SELECT x FROM ev").fetchone() == (7,)


def test_security_events_db_missing_is_skipped_silently(monkeypatch, tmp_path):
    db = tmp_path / "counts.db"
    sqlite3.connect(db).close()
    monkeypatch.setenv("BACKUP_SECURITY_DB", str(tmp_path / "nope.db"))
    mod = load(monkeypatch, db, tmp_path / "backup")
    mod.backup(keep_backups=2)
    (folder,) = os.listdir(tmp_path / "backup")
    assert "security_events.db" not in os.listdir(tmp_path / "backup" / folder)


def test_security_failure_is_reported_and_backup_still_runs(monkeypatch, tmp_path, capsys):
    db = tmp_path / "counts.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE t (x)")
        c.execute("INSERT INTO t VALUES (42)")
    sec = tmp_path / "security_events.db"
    sec.mkdir()  # a directory where the db should be: sqlite cannot open it, so the copy raises
    monkeypatch.setenv("BACKUP_SECURITY_DB", str(sec))
    mod = load(monkeypatch, db, tmp_path / "backup")
    mod.backup(keep_backups=2)
    assert "[backup] security_events.db FAILED:" in capsys.readouterr().out
    (folder,) = os.listdir(tmp_path / "backup")
    with sqlite3.connect(tmp_path / "backup" / folder / "vehicle_counts.db") as c:
        assert c.execute("SELECT x FROM t").fetchone() == (42,)


def test_backup_is_written_under_tmp_then_renamed(monkeypatch, tmp_path):
    db = tmp_path / "counts.db"
    sqlite3.connect(db).close()
    mod = load(monkeypatch, db, tmp_path / "backup")
    mod.backup(keep_backups=2)
    names = os.listdir(tmp_path / "backup")
    assert len(names) == 1
    assert names[0][:2] == "20"
    assert not any(n.startswith(".tmp-") for n in names)


def test_failed_backup_leaves_no_dated_or_tmp_folder(monkeypatch, tmp_path):
    db = tmp_path / "counts.db"
    db.write_bytes(b"not a database" * 200)
    mod = load(monkeypatch, db, tmp_path / "backup")
    with pytest.raises(sqlite3.DatabaseError):
        mod.backup(keep_backups=2)
    left = os.listdir(tmp_path / "backup") if (tmp_path / "backup").exists() else []
    assert [n for n in left if n.startswith("20") or n.startswith(".tmp-")] == []
