import os
import sys

# Make the backend package importable from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# Per-machine switches (the Pi's .env sets them). A module that calls load_dotenv() during a test would leak
# them into every later test, so each test starts without them; a test that needs one sets it with monkeypatch.
MACHINE_ENV = ("AI_WORKER_URL", "AI_WORKER_TOKEN", "YOLO_ALLOWED", "BMA_FETCH")


@pytest.fixture(autouse=True)
def _no_machine_env(monkeypatch):
    for name in MACHINE_ENV:
        monkeypatch.delenv(name, raising=False)
    yield
    for name in MACHINE_ENV:
        os.environ.pop(name, None)
