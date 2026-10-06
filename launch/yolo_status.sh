#!/usr/bin/env bash
# yolo_status: see launch/yolo_status.py. Usage: bash launch/yolo_status.sh [port] [--watch seconds]
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" launch/yolo_status.py "$@"
