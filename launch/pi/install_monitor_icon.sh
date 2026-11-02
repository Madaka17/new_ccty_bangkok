#!/usr/bin/env bash
# Puts a "BKK Monitor" icon on the Raspberry Pi's desktop and in its menu. It opens the monitor page
# (bkk-monitor-web, 127.0.0.1:8090) in its own Chromium window. Run as the desktop user (test); safe to run again.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ICON_DIR="$HOME/.local/share/icons"
APP_DIR="$HOME/.local/share/applications"
DESK_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$ICON_DIR" "$APP_DIR" "$DESK_DIR"

# The Windows icon file holds several sizes: keep the largest as a PNG
"$ROOT/.venv/bin/python" - "$ROOT/launch/monitor/icons/monitor.ico" "$ICON_DIR/bkk-monitor.png" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1])
sizes = sorted(im.info.get("sizes") or [im.size])
im.size = sizes[-1]
im.convert("RGBA").save(sys.argv[2])
PY

cat > "$APP_DIR/bkk-monitor.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=BKK Monitor
Comment=Servers, AI and YOLO status on this Pi (view only)
Exec=chromium-browser --ozone-platform-hint=auto --password-store=basic --app=http://127.0.0.1:8090/ --class=BKKMonitor --user-data-dir=$HOME/.config/bkk-monitor-chromium
Icon=$ICON_DIR/bkk-monitor.png
Terminal=false
Categories=Utility;Monitor;
StartupWMClass=BKKMonitor
DESK
cp "$APP_DIR/bkk-monitor.desktop" "$DESK_DIR/bkk-monitor.desktop"
chmod +x "$DESK_DIR/bkk-monitor.desktop" "$APP_DIR/bkk-monitor.desktop"
# pcmanfm asks before running an untrusted launcher: mark ours as trusted
gio set "$DESK_DIR/bkk-monitor.desktop" metadata::trusted true 2>/dev/null || true
echo "[OK] icon 'BKK Monitor' on the desktop ($DESK_DIR) and in the menu"
