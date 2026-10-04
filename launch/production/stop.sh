#!/usr/bin/env bash
# Stop the production server (port 8000).
echo "[*] Stopping production server (port 8000) ..."
bash "$(dirname "$0")/../kill_server.sh" 8000
