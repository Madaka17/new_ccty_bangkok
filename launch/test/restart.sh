#!/usr/bin/env bash
# Stop the test server, then start it again in this terminal. Production is not touched.
DIR="$(dirname "$0")"
bash "$DIR/../kill_server.sh" 8001
sleep 2
exec bash "$DIR/start.sh"
