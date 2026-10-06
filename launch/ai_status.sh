#!/usr/bin/env bash
# ai_status: see launch/ai_status.py. Usage: bash launch/ai_status.sh [port] [--watch seconds]
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" launch/ai_status.py "$@"
