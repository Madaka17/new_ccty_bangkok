"""Machine settings that a test can leak into os.environ (load_dotenv of the Pi's .env inside backup_db.py)
must not reach the next test: on the Pi AI_WORKER_URL made later YOLO tests use the remote worker."""
import os


def test_a_leaks_like_load_dotenv():
    os.environ["AI_WORKER_URL"] = "http://leak:8100"
    os.environ["YOLO_ALLOWED"] = "0"
    os.environ["BMA_FETCH"] = "0"


def test_b_does_not_see_the_leak():
    assert "AI_WORKER_URL" not in os.environ
    assert "YOLO_ALLOWED" not in os.environ
    assert "BMA_FETCH" not in os.environ
