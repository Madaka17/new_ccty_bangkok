#!/usr/bin/env bash
# camera_status: see launch/camera_status.py. Usage: bash launch/camera_status.sh [port] [--watch seconds] [--once] [--all]
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" launch/camera_status.py "$@"
