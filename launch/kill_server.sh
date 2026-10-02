#!/usr/bin/env bash
# macOS / Linux twin of kill_server.ps1: stop whatever listens on the port (default 8000).
# Usage: launch/kill_server.sh 8001
PORT="${1:-8000}"
PIDS=$(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null)
if [ -z "$PIDS" ]; then
    echo "[*] No server running on port $PORT."
    exit 0
fi
for PID in $PIDS; do
    kill "$PID" 2>/dev/null && echo "[*] Stopped process on port $PORT (PID $PID)"
done
# Give it a few seconds to close, then force
for _ in 1 2 3 4 5; do
    sleep 1
    lsof -ti "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1 || exit 0
done
lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null
