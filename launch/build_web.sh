#!/usr/bin/env bash
# macOS / Linux twin of build_web.bat. The web UI build is not in git: build the React UI when it is missing
# (or always with "launch/build_web.sh force"). Called by launch/production and launch/test start.sh.
# Builds into the instance's own folder: $INSTANCE_DIR/dist, else instances/production/dist.
cd "$(dirname "$0")/.." || exit 1
OUT="${INSTANCE_DIR:-$PWD/instances/production}/dist"
if [ "$1" != "force" ] && [ -f "$OUT/index.html" ]; then exit 0; fi
if ! command -v npm >/dev/null 2>&1; then
    echo "[Notice] $OUT missing and npm not found - install Node.js, then run launch/build_web.sh. The server starts without the web UI."
    exit 0
fi
echo "[*] Building web UI ($OUT) ..."
cd web || exit 1
[ -d node_modules ] || npm ci
npm run build -- --outDir "$OUT"
