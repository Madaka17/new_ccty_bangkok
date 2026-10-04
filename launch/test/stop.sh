#!/usr/bin/env bash
# Stop the test server (port 8001). Production on port 8000 is not touched.
echo "[*] Stopping test server (port 8001) ..."
bash "$(dirname "$0")/../kill_server.sh" 8001
