import io
import json
import threading

from backend.core import security_stream as ss
from backend.core.security_log import SecurityLog


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def make(tmp_path):
    clock = Clock(1.78e9)
    lg = SecurityLog(str(tmp_path / "sec.db"), clock=clock)
    return lg, clock


def test_new_rows_missing_db_is_quiet(tmp_path):
    assert ss.new_rows(str(tmp_path / "nope.db"), 5.0) == ([], 5.0)


def test_new_rows_only_newer_and_ordered(tmp_path):
    lg, clock = make(tmp_path)
    lg.record("probe", "1.1.1.1", "/a")
    clock.t = 1.78e9 + 1
    lg.record("bad_path", "2.2.2.2", "/b", "POST")
    clock.t = 1.78e9 + 2
    lg.record("self_check", "3.3.3.3", "/c")
    lg.flush()
    rows, last = ss.new_rows(lg.db_path, 1.78e9)
    assert [r["ip"] for r in rows] == ["2.2.2.2", "3.3.3.3"]
    assert last == 1.78e9 + 2
    assert rows[0]["method"] == "POST"
    assert ss.new_rows(lg.db_path, last) == ([], last)


def test_new_rows_read_only_and_path_with_spaces(tmp_path):
    d = tmp_path / "a dir #1"
    d.mkdir()
    lg = SecurityLog(str(d / "sec.db"), clock=Clock(1.78e9))
    lg.record("probe", "1.1.1.1", "/a")
    lg.flush()
    rows, _ = ss.new_rows(lg.db_path, 0)
    assert len(rows) == 1
    # a read-only connection cannot write: proves mode=ro is what new_rows uses
    import sqlite3
    con = sqlite3.connect(ss._ro_uri(lg.db_path), uri=True)
    try:
        try:
            con.execute("DELETE FROM recent")
            wrote = True
        except sqlite3.OperationalError:
            wrote = False
    finally:
        con.close()
    assert not wrote


def test_format_line_and_web_event():
    line = ss.format_line({"type": "x", "t": "ไทย"})
    assert line.endswith("\n") and line.count("\n") == 1
    assert json.loads(line) == {"type": "x", "t": "ไทย"}
    ev = ss.web_event({"ts": 1.78e9, "kind": "probe", "ip": "1.1.1.1", "path": "/x", "method": "GET"})
    assert set(ev) == {"type", "ts", "kind", "ip", "path", "method"} and ev["type"] == "web"
    assert "T" in ev["ts"]


def test_emitter_sets_stop_on_broken_pipe():
    class Broken:
        def write(self, s):
            raise BrokenPipeError

        def flush(self):
            pass

    stop = threading.Event()
    em = ss.Emitter(Broken(), stop)
    assert em.emit({"type": "ping"}) is False
    assert stop.is_set()
    assert em.emit({"type": "ping"}) is False


def test_emitter_writes_one_line_each():
    buf = io.StringIO()
    em = ss.Emitter(buf, threading.Event())
    em.emit({"type": "hello"})
    em.emit({"type": "ping"})
    assert [json.loads(x)["type"] for x in buf.getvalue().splitlines()] == ["hello", "ping"]


def test_pick_journal_cmd_prefers_plain_then_sudo():
    calls = []

    def runner_plain(cmd):
        calls.append(cmd)
        return "line"
    assert ss.pick_journal_cmd(runner_plain) == ss.JOURNAL_CMD
    assert len(calls) == 1 and calls[0][0] == "journalctl"

    def runner_sudo(cmd):
        return "line" if cmd[0] == "sudo" else ""
    assert ss.pick_journal_cmd(runner_sudo) == ["sudo", "-n"] + ss.JOURNAL_CMD
    assert ss.pick_journal_cmd(lambda cmd: "") is None


def test_stop_proc_skips_finished_process():
    class P:
        pid = 1
        killed = False

        def poll(self):
            return 0

        def kill(self):
            self.killed = True
    p = P()
    ss._stop_proc(p, group=True)
    assert not p.killed


def test_stop_proc_kills_running_process_on_windows_path(monkeypatch):
    class P:
        pid = 1
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True
    monkeypatch.setattr(ss.os, "name", "nt")
    p = P()
    ss._stop_proc(p, group=True)
    assert p.killed


def test_ssh_loop_does_not_start_after_stop(monkeypatch):
    stop = threading.Event()
    stop.set()
    started = []
    monkeypatch.setattr(ss.shutil, "which", lambda n: "/bin/journalctl")
    monkeypatch.setattr(ss, "pick_journal_cmd", lambda: ss.JOURNAL_CMD)
    monkeypatch.setattr(ss.subprocess, "Popen", lambda *a, **k: started.append(1))
    ss._ssh_loop(ss.Emitter(io.StringIO(), stop), [])
    assert started == []


def test_pdeathsig_only_on_linux(monkeypatch):
    monkeypatch.setattr(ss.sys, "platform", "win32")
    assert ss._pdeathsig() is None
    monkeypatch.setattr(ss.sys, "platform", "linux")
    import ctypes
    calls = []

    class Lib:
        def prctl(self, *a):
            calls.append(a)
    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **k: Lib())
    fn = ss._pdeathsig()
    assert callable(fn)
    fn()
    assert calls and calls[0][0] == 1
    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert ss._pdeathsig() is None
