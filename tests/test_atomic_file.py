"""write_json_atomic: a failed write leaves the old file in place and no tmp file behind."""
import json
import os
import threading

import pytest

from backend.core import atomic_file
from backend.core.atomic_file import write_json_atomic


def test_writes_and_reads_back(tmp_path):
    path = tmp_path / "state.json"
    write_json_atomic(str(path), {"a": "ถนน"}, ensure_ascii=False)
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a": "ถนน"}
    assert "ถนน" in path.read_text(encoding="utf-8")


def test_old_file_kept_when_dump_fails(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"old": 1}), encoding="utf-8")
    with pytest.raises(TypeError):
        write_json_atomic(str(path), {"x": object()})
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"old": 1}
    assert list(tmp_path.glob("*.tmp")) == []


def test_retries_replace_on_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError("locked")
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_file.os, "replace", flaky)
    monkeypatch.setattr(atomic_file.time, "sleep", lambda s: None)
    write_json_atomic(str(path), {"ok": True})
    assert calls["n"] == 3
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"ok": True}


def test_gives_up_after_retries(tmp_path, monkeypatch):
    path = tmp_path / "state.json"

    def locked(src, dst):
        raise PermissionError("locked")

    monkeypatch.setattr(atomic_file.os, "replace", locked)
    monkeypatch.setattr(atomic_file.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        write_json_atomic(str(path), {"ok": True})
    assert list(tmp_path.glob("*.tmp")) == []


def test_tmp_name_has_pid_and_thread(tmp_path, monkeypatch):
    # Two processes writing the same path must not share a tmp file, so the pid is in the name.
    path = tmp_path / "state.json"
    seen = []

    def capture(src, dst):
        seen.append(src)
        os.rename(src, dst)

    monkeypatch.setattr(atomic_file.os, "replace", capture)
    write_json_atomic(str(path), {"ok": True})
    expected = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    assert seen == [expected]
