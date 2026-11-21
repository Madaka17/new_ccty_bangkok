"""Where the pipeline scripts read and write YOLO weights: weights/ in the project root.

Uses the server's resolver (backend/core/instance.py, stdlib only), so a script finds a model in
weights/ or, for files from before the move, in the project root.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.core.instance import MODELS_DIR, model_path  # noqa: E402,F401


def model_out(name):
    """Path in weights/ for a newly trained model (creates weights/ when needed)."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    return os.path.join(MODELS_DIR, name)
