"""Helmet and wrong-way patrols share storage, archive and cloud-vision code: same rows, files, CSV and log text."""
import csv
import os
import sqlite3
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from backend.core import local_llm
from backend.vision import helmet_service as hs
from backend.vision import wrongway_service as ws

FRAME = np.zeros((40, 60, 3), np.uint8)
CAM = {"title": "Cam A", "district": "Dusit"}


def _bare(cls, path, tmp_path):
    """A patrol without __init__ (no threads, no models): only what the storage/archive/ask methods read."""
    p = object.__new__(cls)
    p.db_path = str(tmp_path / path)
    p.lock = threading.Lock()
    if hasattr(p, "_open_store"):   # absent on the pre-refactor classes
        p._open_store()
    return p


def _helmet(tmp_path):
    return _bare(hs.HelmetPatrol, "h.db", tmp_path)


def _wrongway(tmp_path):
    return _bare(ws.WrongWayPatrol, "w.db", tmp_path)


HELMET_ROW = ("h-1700000000-1", 1700000000, "c1", "Cam A", "Dusit", "[1,2,3,4]", "pending", None, None, None, None, None, None)
WW_ROW = ("w-1700000000-1", 1700000000, "c1", "Cam A", "Dusit", "[1,2,3,4]", "toward", "away", 0.9,
          "pending", None, None, None, None)


@pytest.mark.parametrize("make,table,row", [(_helmet, "helmet_checks", HELMET_ROW), (_wrongway, "wrongway_checks", WW_ROW)])
def test_storage_roundtrip(tmp_path, make, table, row):
    p = make(tmp_path)
    p._init_db()
    p._init_db()   # idempotent
    p._insert(row)
    p._update(row[0], verdict="unclear", note="n")
    conn = p._db()
    try:
        assert conn.row_factory is sqlite3.Row
        r = conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()
    assert len(r) == 1
    assert r[0]["id"] == row[0] and r[0]["verdict"] == "unclear" and r[0]["note"] == "n"
    p._insert(row)   # INSERT OR REPLACE: back to pending, still one row
    conn = p._db()
    try:
        rows = conn.execute(f"SELECT verdict FROM {table}").fetchall()
    finally:
        conn.close()
    assert [x["verdict"] for x in rows] == ["pending"]


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def test_helmet_archive(tmp_path, monkeypatch):
    arch = str(tmp_path / "arch")
    monkeypatch.setattr(hs, "ARCHIVE_DIR", arch)
    p = _helmet(tmp_path)
    out = p._archive("h-1700000000-1", "c1", CAM, FRAME, FRAME, 2, 1, 0.876, "note")
    stem = out[:-4]
    assert out.endswith("_1.jpg") and os.path.basename(out).startswith("c1_")
    assert os.path.isfile(out) and os.path.isfile(stem + "_crop.jpg")
    rows = _read_csv(os.path.join(arch, "helmet.csv"))
    assert rows[0] == ["id", "datetime", "camid", "camera", "district", "riders", "no_helmet", "confidence", "note", "frame", "crop"]
    assert rows[1][0] == "h-1700000000-1" and rows[1][2:9] == ["c1", "Cam A", "Dusit", "2", "1", "0.88", "note"]
    assert rows[1][9] == out and rows[1][10] == stem + "_crop.jpg"
    p._archive("h-1700000000-2", "c1", CAM, FRAME, FRAME, 1, 1, 0.5, "again")
    assert len(_read_csv(os.path.join(arch, "helmet.csv"))) == 3   # header written once


def test_wrongway_archive(tmp_path, monkeypatch):
    arch = str(tmp_path / "arch")
    monkeypatch.setattr(ws, "ARCHIVE_DIR", arch)
    p = _wrongway(tmp_path)
    out = p._archive("w-1700000000-1", "c1", CAM, FRAME, FRAME, 0.876, "note")
    assert os.path.isfile(out) and os.path.isfile(out[:-4] + "_crop.jpg")
    rows = _read_csv(os.path.join(arch, "wrongway.csv"))
    assert rows[0] == ["id", "datetime", "camid", "camera", "district", "confidence", "note", "frame", "crop"]
    assert rows[1][2:7] == ["c1", "Cam A", "Dusit", "0.88", "note"] and rows[1][7] == out


def test_archive_failure_logs_and_returns_none(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    bad = str(blocker / "sub")
    monkeypatch.setattr(hs, "ARCHIVE_DIR", bad)
    monkeypatch.setattr(ws, "ARCHIVE_DIR", bad)
    assert _helmet(tmp_path)._archive("h-1-1", "c1", CAM, FRAME, FRAME, 1, 1, 0.5, "n") is None
    assert _wrongway(tmp_path)._archive("w-1-1", "c1", CAM, FRAME, FRAME, 0.5, "n") is None
    out = capsys.readouterr().out
    assert f"[Helmet] archive to {bad} failed:" in out
    assert f"[WrongWay] archive to {bad} failed:" in out


class FakeModels:
    def __init__(self, fail_first=1):
        self.tried = []
        self.fail_first = fail_first

    def generate_content(self, model, contents, config):
        self.tried.append(model)
        if len(self.tried) <= self.fail_first:
            raise RuntimeError("503 UNAVAILABLE")
        return SimpleNamespace(text=' {"ok":1} ', usage_metadata=None, usage=None)


def _vision(models):
    return SimpleNamespace(provider="gemini", client=SimpleNamespace(models=models))


def test_helmet_ask_falls_back_and_logs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hs, "HELMET_MODEL", "main-m")
    monkeypatch.setattr(hs, "FALLBACK_MODEL", "fallback-m")
    monkeypatch.setattr(hs, "HELMET_AGENT", "cloud")
    monkeypatch.setattr(local_llm, "_usage", local_llm.deque())
    models = FakeModels()
    p = _helmet(tmp_path)
    p.vision = _vision(models)
    assert p._ask(b"jpg", "ctx") == '{"ok":1}'
    assert models.tried == ["main-m", "fallback-m"]
    assert "[Helmet] main-m overloaded (503), trying fallback-m" in capsys.readouterr().out
    assert any(c["caller"] == hs.__name__ for c in local_llm.usage(5)["callers"])


def test_wrongway_ask_falls_back_silently(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ws, "AGENT_MODEL", "main-m")
    monkeypatch.setattr(ws, "FALLBACK_MODEL", "fallback-m")
    monkeypatch.setattr(local_llm, "_usage", local_llm.deque())
    models = FakeModels()
    p = _wrongway(tmp_path)
    p.vision = _vision(models)
    assert p._ask(b"jpg", "ctx") == '{"ok":1}'
    assert models.tried == ["main-m", "fallback-m"]
    assert capsys.readouterr().out == ""
    assert any(c["caller"] == ws.__name__ for c in local_llm.usage(5)["callers"])


def test_ask_gives_up_when_every_model_is_overloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "AGENT_MODEL", "a")
    monkeypatch.setattr(ws, "FALLBACK_MODEL", "b")
    p = _wrongway(tmp_path)
    p.vision = _vision(FakeModels(fail_first=9))
    with pytest.raises(RuntimeError, match="503 Gemini overloaded on every model"):
        p._ask(b"jpg", "ctx")


def test_ask_reraises_other_errors(tmp_path):
    class Boom(FakeModels):
        def generate_content(self, **kw):
            raise ValueError("bad key")
    p = _wrongway(tmp_path)
    p.vision = _vision(Boom())
    with pytest.raises(ValueError):
        p._ask(b"jpg", "ctx")


def test_ask_claude_branch(tmp_path):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(model="claude-x", usage=None, content=[SimpleNamespace(type="text", text=" hi "),
                                                                        SimpleNamespace(type="tool", text="no")])
    p = _wrongway(tmp_path)
    p.vision = SimpleNamespace(provider="claude", client=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert p._ask(b"jpg", "ctx") == "hi"
    assert seen["max_tokens"] == 200 and seen["output_config"] == {"effort": "low"}


# ---------------------------------------------------------------- patrol_common itself
def _store(tmp_path):
    from backend.vision.patrol_common import PatrolStore
    schema = "CREATE TABLE IF NOT EXISTS t (id TEXT PRIMARY KEY, ts INTEGER NOT NULL, verdict TEXT, note TEXT)"
    return PatrolStore(str(tmp_path / "s.db"), "t", schema, "CREATE INDEX IF NOT EXISTS t_ts ON t(ts)", threading.Lock())


def test_store_insert_update_connect(tmp_path):
    s = _store(tmp_path)
    s.init()
    s.insert(("a", 1, "ok", None))
    s.update("a", verdict="bad", note="x")
    conn = s.connect()
    try:
        assert conn.row_factory is sqlite3.Row
        row = conn.execute("SELECT * FROM t").fetchone()
    finally:
        conn.close()
    assert (row["verdict"], row["note"]) == ("bad", "x")


def test_store_delete_older_keeps_verdict(tmp_path):
    s = _store(tmp_path)
    s.init()
    for i, v in enumerate(["ok", "keep", "ok"]):
        s.insert((f"id{i}", 10 + i, v, None))
    s.delete_older(12, "keep")   # id0 (ts 10, ok) goes; id1 kept by verdict; id2 is not older
    conn = s.connect()
    try:
        ids = sorted(r["id"] for r in conn.execute("SELECT id FROM t"))
    finally:
        conn.close()
    assert ids == ["id1", "id2"]


def test_clean_cache_dir_removes_old_and_survives_errors(tmp_path, monkeypatch):
    from backend.vision import patrol_common as pc
    old, new, locked = tmp_path / "old.jpg", tmp_path / "new.jpg", tmp_path / "locked.jpg"
    for f in (old, new, locked):
        f.write_text("x")
    os.utime(old, (100, 100))
    os.utime(locked, (100, 100))
    real_remove = os.remove

    def remove(p):
        if p.endswith("locked.jpg"):
            raise PermissionError("in use")
        real_remove(p)
    monkeypatch.setattr(pc.os, "remove", remove)
    pc.clean_cache_dir(str(tmp_path), 1000)
    assert not old.exists() and new.exists() and locked.exists()


def test_archive_evidence_writes_files_and_csv(tmp_path):
    from backend.vision.patrol_common import archive_evidence
    out = archive_evidence(str(tmp_path / "a"), "x.csv", "i-1700000000-3", "c/1", CAM, FRAME, FRAME,
                           "LABEL {datetime}", 22, 16, 0.5, ["id", "datetime", "camid", "camera", "district", "v", "frame", "crop"],
                           [7], "Tag")
    assert out.endswith("_3.jpg") and os.path.isfile(out) and os.path.isfile(out[:-4] + "_crop.jpg")
    rows = _read_csv(str(tmp_path / "a" / "x.csv"))
    assert rows[1][2:6] == ["c/1", "Cam A", "Dusit", "7"] and rows[1][6] == out


def test_archive_evidence_failure(tmp_path, capsys):
    from backend.vision.patrol_common import archive_evidence
    blocker = tmp_path / "f"
    blocker.write_text("x")
    assert archive_evidence(str(blocker / "d"), "x.csv", "i-1-1", "c", CAM, FRAME, FRAME, "L {datetime}", 18, 13, 0.4,
                            ["id"], [], "Tag") is None
    assert "[Tag] archive to" in capsys.readouterr().out


def test_ask_cloud_vision_log_tag_optional(monkeypatch, capsys):
    from backend.vision.patrol_common import ask_cloud_vision
    m = FakeModels()
    assert ask_cloud_vision(_vision(m), "sys", b"j", "ctx", ["a", "b"], 1000) == '{"ok":1}'
    assert m.tried == ["a", "b"] and capsys.readouterr().out == ""
    m = FakeModels()
    ask_cloud_vision(_vision(m), "sys", b"j", "ctx", ["a", "b"], 1000, log_tag="T")
    assert "[T] a overloaded (503), trying b" in capsys.readouterr().out


def test_ask_cloud_vision_counts_usage_under_caller(monkeypatch):
    from backend.vision.patrol_common import ask_cloud_vision
    monkeypatch.setattr(local_llm, "_usage", local_llm.deque())
    ask_cloud_vision(_vision(FakeModels(fail_first=0)), "sys", b"j", "ctx", ["a"], 1000, caller="my.module")
    assert any(c["caller"] == "my.module" for c in local_llm.usage(5)["callers"])
