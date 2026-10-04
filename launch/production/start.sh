#!/usr/bin/env bash
# macOS / Linux twin of start.bat: production server, port 8000, data in instances/production.
# Runs in this terminal; Ctrl+C (or launch/production/stop.sh) stops it.
cd "$(dirname "$0")/../.." || exit 1
export OPENCV_FFMPEG_LOGLEVEL=-8
export PORT=8000
export INSTANCE_DIR="$PWD/instances/production"

echo "======================================================================"
echo "  BKK StreetSmart - PRODUCTION  http://localhost:8000"
echo "  data: instances/production/"
echo "======================================================================"

if lsof -ti tcp:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[!] Server is already running on port 8000. Use restart.sh to restart it."
    exit 0
fi
# Public access goes through Cloudflare Tunnel (launch/cloudflare); on this machine it is only checked
if pgrep -x cloudflared >/dev/null 2>&1; then
    echo "[OK] cloudflared is running (public URL per launch/cloudflare/config.yml)"
else
    echo "[*] cloudflared is not running: the site is local only."
fi
echo "[*] Local URL: http://localhost:8000   (Ctrl+C stops the server)"

bash launch/build_web.sh
PY=.venv/bin/python
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
"$PY" server.py
