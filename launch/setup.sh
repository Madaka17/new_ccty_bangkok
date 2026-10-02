#!/usr/bin/env bash
# First-time setup on macOS / Linux: Python packages in .venv and the web UI's packages.
# Usage: bash launch/setup.sh
cd "$(dirname "$0")/.." || exit 1
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
    echo "[ERROR] Python 3 not found. Install it first (macOS: brew install python)."
    exit 1
fi
[ -d .venv ] || "$PY" -m venv .venv || exit 1
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt || exit 1
if command -v npm >/dev/null 2>&1; then
    (cd web && npm ci)
else
    echo "[Notice] npm not found: install Node.js 18+ (macOS: brew install node) to build the web UI."
fi
chmod +x launch/*.sh launch/production/*.sh launch/test/*.sh
echo "[OK] Ready. Start the server: launch/production/start.sh  (test server: launch/test/start.sh)"
