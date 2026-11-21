"""model_path: YOLO weights are looked up in weights/ first, then the project root."""
import os

from backend.core.instance import alternate_model_rel, model_path


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")


def test_prefers_weights(tmp_path):
    _touch(str(tmp_path / "weights" / "a.pt"))
    _touch(str(tmp_path / "a.pt"))
    assert model_path("a.pt", base_dir=str(tmp_path)) == os.path.join(str(tmp_path), "weights", "a.pt")


def test_falls_back_to_root(tmp_path):
    _touch(str(tmp_path / "a.pt"))
    assert model_path("a.pt", base_dir=str(tmp_path)) == os.path.join(str(tmp_path), "a.pt")


def test_missing_gives_weights(tmp_path):
    assert model_path("a.pt", base_dir=str(tmp_path)) == os.path.join(str(tmp_path), "weights", "a.pt")


def test_absolute_unchanged(tmp_path):
    p = str(tmp_path / "x" / "m.pt")
    assert model_path(p, base_dir=str(tmp_path)) == p


def test_alternate_rel():
    assert alternate_model_rel("a.pt") == "weights/a.pt"
    assert alternate_model_rel("weights/a.pt") == "a.pt"
    assert alternate_model_rel("runs/x/best.pt") == "weights/runs/x/best.pt"
