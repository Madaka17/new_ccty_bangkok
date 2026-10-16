#!/usr/bin/env bash
# gateway_status: see launch/gateway_status.py. Usage: bash launch/gateway_status.sh [--watch seconds] [--once]
cd "$(dirname "$0")/.."
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" launch/gateway_status.py "$@"
