#!/usr/bin/env bash
# Raspberry Pi 4 (Debian 12 aarch64) setup for BKK StreetSmart and ENVIRO. Run from anywhere; safe to run again.
# torch comes from the CPU backend: the Pi has no GPU and YOLO stays off there (YOLO_ALLOWED=0),
# and the default aarch64 wheels would pull about 20 nvidia-* CUDA packages.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$HOME/.local/bin:$PATH"

echo "[1/4] System packages (OpenCV needs libGL and glib; ffmpeg for camera streams)"
sudo apt-get update -q >/dev/null
sudo apt-get install -y -q libgl1 libglib2.0-0 ffmpeg sqlite3 >/dev/null

echo "[2/4] uv"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/0.13.6/install.sh | sh

echo "[3/4] Server venv (.venv, Python 3.14, CPU torch)"
[ -x .venv/bin/python ] || uv venv -q --python 3.14 .venv
uv pip install -q -p .venv -r requirements.txt --torch-backend cpu

echo "[4/4] ENVIRO venv (ENVIRO/.venv)"
[ -x ENVIRO/.venv/bin/python ] || uv venv -q --python 3.14 ENVIRO/.venv
uv pip install -q -p ENVIRO/.venv -r ENVIRO/requirements.txt

# .env holds API keys: only the owner may read it
[ -f .env ] && chmod 600 .env

echo "Check:"
.venv/bin/python -c "import torch, cv2, ultralytics, fastapi; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'opencv', cv2.__version__)"
echo "CUDA packages (want 0): $(uv pip list -p .venv 2>/dev/null | grep -ciE "^nvidia-(cu|cublas|cudnn|nccl)" || true)"
[ -f .env ] && echo ".env mode (want 600): $(stat -c %a .env)"
