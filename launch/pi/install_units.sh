#!/usr/bin/env bash
# Copy the named units from launch/pi to /etc/systemd/system and reload systemd. Never enables or starts anything.
# Usage: bash launch/pi/install_units.sh bkk-test.service [bkk-production.service ...]
set -euo pipefail
cd "$(dirname "$0")"
[ $# -gt 0 ] || { echo "usage: $0 UNIT.service..." >&2; exit 2; }
for unit in "$@"; do
    [ -f "$unit" ] || { echo "no such unit here: $unit" >&2; exit 1; }
    sudo install -m 644 "$unit" "/etc/systemd/system/$unit"
    echo "installed $unit"
done
sudo systemctl daemon-reload
echo "Not enabled. Start with: sudo systemctl start <unit>"
