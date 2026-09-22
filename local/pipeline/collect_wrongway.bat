@echo off
setlocal
cd /d "%~dp0..\.."
title Wrong-way dataset - collect from all cameras
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "ROUNDS=%~1"
if "%ROUNDS%"=="" set "ROUNDS=6"
set "EVERY=%~2"
if "%EVERY%"=="" set "EVERY=40"
if not exist local\logs mkdir local\logs
echo [*] %ROUNDS% sweeps over all BMA + HLS cameras, one every %EVERY% min (Ctrl+C stops and finalizes)
echo     log: local\logs\collect_wrongway.log
"%PY%" local\pipeline\collect_wrongway_dataset.py --rounds %ROUNDS% --every %EVERY% --hls 2>&1 | "%PY%" -c "import sys; [print(l, end='') or open('local/logs/collect_wrongway.log','a',encoding='utf-8').write(l) for l in sys.stdin]"
pause
