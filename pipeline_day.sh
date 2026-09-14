#!/usr/bin/env bash
# Scheduled run: collect frames all day, clean, then fine-tune and restart the server.
# Usage: bash pipeline_day.sh [until HH:MM] [every seconds] [epochs]
set -u
cd "$(dirname "$0")"
PY=.venv/Scripts/python.exe
UNTIL=${1:-20:00}
EVERY=${2:-900}
EPOCHS=${3:-50}
LOG=pipeline.log
exec >> "$LOG" 2>&1

echo "=== [$(date '+%F %T')] 1/3 collect until $UNTIL, one pass every $EVERY s ==="
"$PY" collect_dataset.py --every "$EVERY" --until "$UNTIL" 2>&1 | grep -v '^WARNING'

echo "=== [$(date '+%F %T')] 2/3 clean labels ==="
"$PY" clean_dataset.py

echo "=== [$(date '+%F %T')] 3/3 train: stop server, $EPOCHS epochs ==="
# The .venv python is a launcher that shares its PID with the real interpreter: match on server.py only
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'server\.py' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
sleep 5
"$PY" train_model.py --epochs "$EPOCHS" --imgsz 960 --patience 12 2>&1 | grep -vE '^WARNING|^\s*$'
STATUS=${PIPESTATUS[0]}

echo "=== [$(date '+%F %T')] restart server (train exit $STATUS) ==="
powershell -NoProfile -Command "Start-Process -FilePath '$PWD/.venv/Scripts/python.exe' -ArgumentList 'server.py' -WorkingDirectory '$PWD' -WindowStyle Hidden"
sleep 30
curl -s -o /dev/null -w "server http %{http_code}\n" http://localhost:8000/api/ai/stats
ls -la *_bkk.pt 2>/dev/null
echo "=== [$(date '+%F %T')] pipeline finished ==="
