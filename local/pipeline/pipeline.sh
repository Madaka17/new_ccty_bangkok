#!/usr/bin/env bash
# End-to-end: collect frames -> clean labels -> stop server -> fine-tune -> restart server.
# Run from Git Bash:  bash pipeline.sh [images] [epochs]
set -u
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python.exe
IMAGES=${1:-1000}
EPOCHS=${2:-60}
LOG=local/pipeline.log
exec > >(tee -a "$LOG") 2>&1

echo "=== [$(date '+%F %T')] 1/3 collect: target $IMAGES images ==="
# 1 frame per camera per round; ~34 cameras, 60 s between rounds
"$PY" local/pipeline/collect_dataset.py --rounds 60 --every 60 --limit "$IMAGES" 2>&1 | grep -v '^WARNING'

echo "=== [$(date '+%F %T')] 2/3 clean labels ==="
"$PY" local/pipeline/clean_dataset.py

echo "=== [$(date '+%F %T')] 3/3 train: stop server, $EPOCHS epochs ==="
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -match 'server\.py' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
sleep 5
"$PY" local/pipeline/train_model.py --epochs "$EPOCHS" --imgsz 960 --patience 15 2>&1 | grep -vE '^WARNING|^\s*$'
STATUS=${PIPESTATUS[0]}

echo "=== [$(date '+%F %T')] restart server (train exit $STATUS) ==="
powershell -NoProfile -Command "Start-Process -FilePath '$PWD/.venv/Scripts/python.exe' -ArgumentList 'server.py' -WorkingDirectory '$PWD' -WindowStyle Hidden"
sleep 30
curl -s -o /dev/null -w "server http %{http_code}\n" http://localhost:8000/api/ai/stats
ls -la *_bkk.pt 2>/dev/null
echo "=== [$(date '+%F %T')] pipeline finished ==="
