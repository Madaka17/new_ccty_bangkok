#!/usr/bin/env bash
# macOS / Linux twin of start.bat: test server, port 8001, data in instances/test (production is not touched).
# Runs in this terminal; Ctrl+C (or launch/test/stop.sh) stops it.
cd "$(dirname "$0")/../.." || exit 1
export OPENCV_FFMPEG_LOGLEVEL=-8
export PORT=8001
export INSTANCE_DIR="$PWD/instances/test"
export BMA_DATA_DIR="$PWD/instances/test/data"

echo "======================================================================"
echo "  BKK StreetSmart - TEST server  http://localhost:8001"
echo "  data: instances/test/   (production on :8000 is not touched)"
echo "======================================================================"

if lsof -ti tcp:8001 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[!] Test server is already running on port 8001. Use restart.sh to restart it."
    exit 0
fi
if [ ! -d instances/test/cache ]; then
    echo "[*] First run: seeding instances/test with the small caches and a copy of the production DB ..."
    mkdir -p instances/test/cache
    for f in longdo_cameras.json bma_events.json traffic_history.json twa_key.json; do
        [ -f "instances/production/cache/$f" ] && cp "instances/production/cache/$f" "instances/test/cache/$f"
    done
    [ -d instances/production/cache/rsc ] && cp -R instances/production/cache/rsc instances/test/cache/rsc
    [ -f instances/production/vehicle_counts.db ] && cp instances/production/vehicle_counts.db instances/test/vehicle_counts.db
    [ -f instances/production/count_cameras.json ] && cp instances/production/count_cameras.json instances/test/count_cameras.json
fi
mkdir -p instances/test/data

bash launch/build_web.sh
echo "[*] Starting TEST server at http://localhost:8001 ...   (Ctrl+C stops it)"
PY=.venv/bin/python
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
"$PY" server.py
