"""Where this server instance listens and keeps its runtime data.

Two copies of the server can run from the same code: the public one (port 8000, data in the
project root) and a test one (run_test.bat: port 8001, data under local/stage/) for trying a
change before restarting the public server. Every module takes its cache / database paths from
here so the two never write into each other's files.

    PORT          listen port                       (default 8000)
    INSTANCE_DIR  root for cache/ and vehicle_counts.db (default: project root)
    BMA_DATA_DIR  CSV archive + evidence images, read by bma_archive / helmet / wrongway
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.getenv("PORT", "8000"))
DATA_DIR = os.path.abspath(os.getenv("INSTANCE_DIR") or BASE_DIR)
CACHE_DIR = os.path.join(DATA_DIR, "cache")
DB_PATH = os.path.join(DATA_DIR, "vehicle_counts.db")
IS_STAGE = DATA_DIR != BASE_DIR
os.makedirs(CACHE_DIR, exist_ok=True)
