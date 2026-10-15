import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "launch"))
import run_hidden  # noqa: E402

PY = sys.executable


def test_run_writes_log_and_state(tmp_path):
    cmd = [PY, "-c", "import sys; print('hello'); print('ERROR boom', file=sys.stderr); sys.exit(3)"]
    code = run_hidden.run("demo", cmd, log_dir=tmp_path)
    assert code == 3
    text = (tmp_path / "demo.log").read_text(encoding="utf-8")
    assert "--- demo started (pid" in text
    assert " hello" in text and " ERROR boom" in text
    assert text.rstrip().endswith("--- demo exited with code 3 ---")
    st = json.loads((tmp_path / "demo.json").read_text(encoding="utf-8"))
    assert st["name"] == "demo" and st["exit_code"] == 3 and st["exited_at"] >= st["started_at"]
    assert isinstance(st["child_pid"], int) and isinstance(st["runner_pid"], int)


def test_stdin_is_closed_so_pause_cannot_hang(tmp_path):
    cmd = [PY, "-c", "import sys; data = sys.stdin.read(); print('read', len(data))"]
    assert run_hidden.run("stdin", cmd, log_dir=tmp_path) == 0
    assert " read 0" in (tmp_path / "stdin.log").read_text(encoding="utf-8")


def test_rotation(tmp_path):
    cmd = [PY, "-c", "for i in range(400): print('x' * 50, i)"]
    run_hidden.run("rot", cmd, log_dir=tmp_path, max_bytes=4000, backups=2)
    assert (tmp_path / "rot.log").stat().st_size <= 4000
    assert (tmp_path / "rot.log.1").exists() and (tmp_path / "rot.log.2").exists()
    assert not (tmp_path / "rot.log.3").exists()


def test_utf8_thai(tmp_path):
    cmd = [PY, "-c", "print('กล้อง ok')"]
    run_hidden.run("thai", cmd, log_dir=tmp_path)
    assert "กล้อง ok" in (tmp_path / "thai.log").read_text(encoding="utf-8")


def test_targets_and_unknown_name(tmp_path, monkeypatch):
    assert run_hidden.TARGETS["production"][-2].endswith(str(Path("launch") / "production" / "start.bat"))
    assert run_hidden.TARGETS["production"][-1] == "--child"
    assert run_hidden.TARGETS["camera"][-2:] == ["--watch", "300"]
    monkeypatch.setattr(run_hidden, "LOG_DIR", tmp_path)
    assert run_hidden.main(["nope"]) == 2
    assert run_hidden.main([]) == 2
