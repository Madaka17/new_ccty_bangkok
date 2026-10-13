import importlib.util
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("yolo_switch_cli", ROOT / "launch" / "yolo_switch.py")
ys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ys)


def _state(enabled):
    return {"enabled": enabled, "changed_at": None, "holders": {}, "vram": None}


def test_on_state_answer_yes_posts_off(monkeypatch, capsys):
    posts = []

    def fake_call(port, method="GET", body=None, timeout=120):
        if method == "POST":
            posts.append(body)
            return _state(body["enabled"])
        return _state(True)

    monkeypatch.setattr(ys, "call", fake_call)
    rc = ys.main([], ask=lambda _prompt: "y")
    assert rc == 0
    assert posts == [{"enabled": False}]


def test_answer_no_makes_no_post(monkeypatch, capsys):
    posts = []

    def fake_call(port, method="GET", body=None, timeout=120):
        if method == "POST":
            posts.append(body)
        return _state(True)

    monkeypatch.setattr(ys, "call", fake_call)
    rc = ys.main([], ask=lambda _prompt: "n")
    assert rc == 0
    assert posts == []
    assert "ไม่เปลี่ยน" in capsys.readouterr().out


def test_flag_on_posts_true_without_asking(monkeypatch):
    posts = []

    def fake_call(port, method="GET", body=None, timeout=120):
        if method == "POST":
            posts.append(body)
            return _state(True)
        return _state(False)

    def no_ask(_prompt):
        raise AssertionError("must not ask when a flag is given")

    monkeypatch.setattr(ys, "call", fake_call)
    rc = ys.main(["--on"], ask=no_ask)
    assert rc == 0
    assert posts == [{"enabled": True}]


def test_server_down_returns_1(monkeypatch, capsys):
    def down(port, method="GET", body=None, timeout=120):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ys, "call", down)
    assert ys.main([], ask=lambda _prompt: "y") == 1
    assert "ต่อเซิร์ฟเวอร์" in capsys.readouterr().out


def test_describe_shows_off_and_gpu_memory():
    text = ys.describe({"enabled": False, "vram": {"used_mb": 3789, "total_mb": 10240}, "holders": {}})
    assert "ปิด" in text
    assert "GPU ใช้ 3.7 จาก 10.0 GB" in text
