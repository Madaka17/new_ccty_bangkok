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
                  (default: D:\\Data on Windows, <INSTANCE_DIR>/data on macOS and Linux)
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # project root
PRODUCTION_DIR = os.path.join(BASE_DIR, "instances", "production")
PORT = int(os.getenv("PORT", "8000"))
DATA_DIR = os.path.abspath(os.getenv("INSTANCE_DIR") or PRODUCTION_DIR)
CACHE_DIR = os.path.join(DATA_DIR, "cache")
DB_PATH = os.path.join(DATA_DIR, "vehicle_counts.db")
IS_STAGE = os.path.normcase(DATA_DIR) != os.path.normcase(PRODUCTION_DIR)
# The modules read BMA_DATA_DIR themselves, after server.py has loaded .env; this is only the fallback
DEFAULT_BMA_DATA_DIR = r"D:\Data" if sys.platform == "win32" else os.path.join(DATA_DIR, "data")
# Thai-capable fonts for text drawn on camera frames, Windows / macOS / Linux, first one found wins
THAI_FONTS = (
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\leelawad.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma.ttf",
    "/System/Library/Fonts/Thonburi.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
)


def thai_font():
    """Path of the first Thai-capable font on this machine, or None."""
    return next((p for p in THAI_FONTS if os.path.exists(p)), None)
os.makedirs(CACHE_DIR, exist_ok=True)
