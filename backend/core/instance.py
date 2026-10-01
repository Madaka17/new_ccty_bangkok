"""Where this server instance listens and keeps its runtime data.

Two copies of the server run from the same code, each with its own data folder under instances/:

    instances/production/   public server, port 8000   (launch/production)
    instances/test/         test server,   port 8001   (launch/test) for trying a change first

Each folder holds cache/, vehicle_counts.db, the agents' JSON state and dist/ (the web UI build it
serves). Every module takes its cache / database paths from here so the two never write into each
other's files.

    PORT          listen port                                  (default 8000)
    INSTANCE_DIR  root for cache/, vehicle_counts.db and dist/ (default: instances/production)
    BMA_DATA_DIR  CSV archive + evidence images, read by bma_archive / helmet / wrongway
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
PRODUCTION_DIR = os.path.join(BASE_DIR, "instances", "production")
PORT = int(os.getenv("PORT", "8000"))
DATA_DIR = os.path.abspath(os.getenv("INSTANCE_DIR") or PRODUCTION_DIR)
CACHE_DIR = os.path.join(DATA_DIR, "cache")
DB_PATH = os.path.join(DATA_DIR, "vehicle_counts.db")
IS_STAGE = os.path.normcase(DATA_DIR) != os.path.normcase(PRODUCTION_DIR)
os.makedirs(CACHE_DIR, exist_ok=True)
