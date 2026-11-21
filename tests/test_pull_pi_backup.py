"""local/pipeline/pull_pi_backup.py: the Windows PC's off-SSD pull of the Pi backups. No network here:
ssh is replaced by an in-memory tar stream."""
import contextlib
import importlib.util
import io
import sqlite3
import tarfile
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "local" / "pipeline" / "pull_pi_backup.py"
spec = importlib.util.spec_from_file_location("pull_pi_backup_under_test", _PATH)
pull = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pull)


def make_tar(entries):
    """entries: list of (name, bytes) or (name, None, linkname) for a symlink."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for e in entries:
            info = tarfile.TarInfo(e[0])
            if len(e) == 3:
                info.type = tarfile.SYMTYPE
                info.linkname = e[2]
                t.addfile(info)
            else:
                info.size = len(e[1])
                t.addfile(info, io.BytesIO(e[1]))
    return buf.getvalue()


def good_db_bytes(tmp_path):
    p = tmp_path / "_src.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE t (x)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()
    c.close()
    data = p.read_bytes()
    p.unlink()
    return data


def fake_opener(payload):
    calls = []

    @contextlib.contextmanager
    def open_stream(remote_cmd):
        calls.append(remote_cmd)
        yield io.BytesIO(payload)

    open_stream.calls = calls
    return open_stream


# ---- ssh command builder ----

def test_build_ssh_args_has_key_batchmode_timeout_host_and_command():
    cfg = {"PI_HOST": "test@192.168.1.109", "PI_KEY": r"C:\Users\u\.ssh\bkkpi_ed25519"}
    args = pull.build_ssh_args(cfg, "ls -1d /x/20*")
    assert args[0] == "ssh"
    assert args[args.index("-i") + 1] == r"C:\Users\u\.ssh\bkkpi_ed25519"
    assert "BatchMode=yes" in args
    assert "ConnectTimeout=15" in args
    assert args[-2] == "test@192.168.1.109"
    assert args[-1] == "ls -1d /x/20*"


# ---- picking the newest backup ----

def test_parse_latest_picks_newest_20_name_and_ignores_others():
    out = "/mnt/x/2026-11-19_0330\n/mnt/x/2026-11-21_0330\n/mnt/x/2026-11-20_0330/\n/mnt/x/tmp\n"
    assert pull.parse_latest(out) == "2026-11-21_0330"


def test_parse_latest_none_when_empty():
    assert pull.parse_latest("") is None


# ---- path safety ----

@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd", "C:/x", "..\\x", "a/..", "\\\\srv\\x"])
def test_unsafe_names_rejected(bad):
    assert pull.safe_member(bad) is False


@pytest.mark.parametrize("good", ["a/b.db", "2026-11-21_0330/vehicle_counts.db", "x/..y/z"])
def test_safe_names_accepted(good):
    assert pull.safe_member(good) is True


def test_extract_writes_files(tmp_path):
    dest = tmp_path / "out"
    data = make_tar([("2026-11-21_0330/vehicle_counts.db", b"abc"), ("2026-11-21_0330/cfg.json", b"{}")])
    pull.extract_tar(io.BytesIO(data), dest)
    assert (dest / "2026-11-21_0330" / "vehicle_counts.db").read_bytes() == b"abc"
    assert (dest / "2026-11-21_0330" / "cfg.json").read_bytes() == b"{}"


def test_extract_overwrites_existing_file(tmp_path):
    dest = tmp_path / "out"
    (dest / "helmet").mkdir(parents=True)
    (dest / "helmet" / "a.csv").write_bytes(b"old")
    pull.extract_tar(io.BytesIO(make_tar([("helmet/a.csv", b"new")])), dest)
    assert (dest / "helmet" / "a.csv").read_bytes() == b"new"


def test_extract_rejects_parent_traversal(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(pull.UnsafeMember):
        pull.extract_tar(io.BytesIO(make_tar([("../x", b"evil")])), dest)
    assert not (tmp_path / "x").exists()


def test_extract_rejects_absolute_member(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(pull.UnsafeMember):
        pull.extract_tar(io.BytesIO(make_tar([("/tmp/evil_bkk_test", b"evil")])), dest)


def test_extract_rejects_symlink_member(tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(pull.UnsafeMember):
        pull.extract_tar(io.BytesIO(make_tar([("link", None, "/etc/passwd")])), dest)


# ---- quick_check ----

def test_quick_check_ok_on_good_db(tmp_path):
    p = tmp_path / "good.db"
    with sqlite3.connect(p) as c:
        c.execute("CREATE TABLE t (x)")
    assert pull.quick_check(p) is True


def test_quick_check_fails_on_corrupt_file(tmp_path):
    p = tmp_path / "bad.db"
    p.write_bytes(b"this is not a sqlite database" * 500)
    assert pull.quick_check(p) is False


def test_quick_check_fails_on_missing_file(tmp_path):
    assert pull.quick_check(tmp_path / "nope.db") is False


# ---- .complete skip and the DB step ----

def test_db_step_skips_when_complete(tmp_path):
    root = tmp_path / "db"
    folder = root / "2026-11-21_0330"
    folder.mkdir(parents=True)
    (folder / ".complete").write_text("x")
    opener = fake_opener(b"")
    assert pull.run_db_step(root, "2026-11-21_0330", opener, lambda m: None) is True
    assert opener.calls == []


def test_db_step_good_copy_gets_complete_marker(tmp_path):
    root = tmp_path / "db"
    payload = make_tar([("2026-11-21_0330/vehicle_counts.db", good_db_bytes(tmp_path))])
    ok = pull.run_db_step(root, "2026-11-21_0330", fake_opener(payload), lambda m: None)
    assert ok is True
    assert (root / "2026-11-21_0330" / ".complete").exists()
    assert not (root / ".partial-2026-11-21_0330").exists()


def test_db_step_corrupt_copy_marked_bad_without_complete(tmp_path):
    root = tmp_path / "db"
    payload = make_tar([("2026-11-21_0330/vehicle_counts.db", b"garbage" * 1000)])
    ok = pull.run_db_step(root, "2026-11-21_0330", fake_opener(payload), lambda m: None)
    assert ok is False
    assert not (root / "2026-11-21_0330").exists()
    assert (root / ".bad-2026-11-21_0330" / "vehicle_counts.db").exists()


# ---- keep / prune ----

def _complete(root, name):
    d = root / name
    d.mkdir(parents=True)
    (d / ".complete").write_text("x")


def test_prune_keeps_newest_complete_and_removes_stale_partials(tmp_path):
    root = tmp_path / "db"
    for n in ["2026-11-17_0330", "2026-11-18_0330", "2026-11-19_0330", "2026-11-20_0330", "2026-11-21_0330"]:
        _complete(root, n)
    (root / ".partial-2026-11-21_0330").mkdir()
    removed = pull.prune_db(root, keep=2, log=lambda m: None)
    assert sorted(removed) == ["2026-11-17_0330", "2026-11-18_0330", "2026-11-19_0330"]
    assert sorted(p.name for p in root.iterdir()) == ["2026-11-20_0330", "2026-11-21_0330"]


def test_prune_leaves_bad_folders_alone(tmp_path):
    root = tmp_path / "db"
    _complete(root, "2026-11-20_0330")
    (root / ".bad-2026-11-19_0330").mkdir()
    pull.prune_db(root, keep=1, log=lambda m: None)
    assert (root / ".bad-2026-11-19_0330").exists()


# ---- files step ----

def test_files_remote_cmd_filters_missing_dirs_and_ignores_failed_reads():
    cmd = pull.files_remote_cmd("/mnt/ssd/data_smartstreet", ["helmet", "violations", "wrongway"])
    assert cmd.startswith("cd /mnt/ssd/data_smartstreet && ")
    assert "ls -d helmet violations wrongway" in cmd
    assert "--ignore-failed-read" in cmd
    assert '"' not in cmd


def test_files_step_extracts_into_destination(tmp_path):
    files = tmp_path / "files"
    payload = make_tar([("helmet/a.csv", b"1"), ("violations/b.csv", b"2")])
    ok = pull.run_files_step(files / "data_smartstreet", "/x", ["helmet", "violations"],
                             fake_opener(payload), lambda m: None)
    assert ok is True
    assert (files / "data_smartstreet" / "helmet" / "a.csv").read_bytes() == b"1"
    assert (files / "data_smartstreet" / "violations" / "b.csv").read_bytes() == b"2"
