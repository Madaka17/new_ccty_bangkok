#!/usr/bin/env bash
# Stop the production server, then start it again in this terminal.
DIR="$(dirname "$0")"
bash "$DIR/../kill_server.sh" 8000
sleep 2
exec bash "$DIR/start.sh"
