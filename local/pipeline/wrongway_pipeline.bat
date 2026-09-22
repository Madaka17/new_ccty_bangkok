@echo off
setlocal
cd /d "%~dp0..\.."
title Wrong-way pipeline: collect -> train
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "ROUNDS=%~1"
if "%ROUNDS%"=="" set "ROUNDS=8"
set "EVERY=%~2"
if "%EVERY%"=="" set "EVERY=35"
set "EPOCHS=%~3"
if "%EPOCHS%"=="" set "EPOCHS=60"
set "BATCH=%~4"
if "%BATCH%"=="" set "BATCH=8"
if not exist local\logs mkdir local\logs

echo ======================================================================
echo   Wrong-way detector: collect (%ROUNDS% sweeps, every %EVERY% min) then train (%EPOCHS% epochs, batch %BATCH%)
echo   Status window opens separately (wrongway_status.bat). Logs in local\logs\
echo ======================================================================
start "Wrong-way status" "%PY%" local\pipeline\watch_wrongway.py

echo [1/2] collecting ...
"%PY%" local\pipeline\collect_wrongway_dataset.py --rounds %ROUNDS% --every %EVERY% --hls > local\logs\collect_wrongway.log 2>&1
if errorlevel 1 (
  echo collect failed, see local\logs\collect_wrongway.log
  pause
  exit /b 1
)

echo [2/2] training ...
"%PY%" local\pipeline\train_wrongway_det.py --epochs %EPOCHS% --batch %BATCH% > local\logs\train_wrongway_det.log 2>&1
type local\logs\train_wrongway_det.log | findstr /C:"done ->" /C:"Error" /C:"Traceback" /C:"out of memory"
pause
