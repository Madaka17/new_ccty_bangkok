@echo off
setlocal
cd /d "%~dp0..\.."
title Wrong-way YOLO26x training
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "EPOCHS=%~1"
if "%EPOCHS%"=="" set "EPOCHS=60"
set "BATCH=%~2"
if "%BATCH%"=="" set "BATCH=8"
if not exist local\logs mkdir local\logs
echo [*] Training yolo26x on local\dataset_wrongway (%EPOCHS% epochs, batch %BATCH%)
echo     Stop the server first if the card runs out of memory, or pass a smaller batch: train_wrongway.bat 60 4
echo     log: local\logs\train_wrongway_det.log
start "Wrong-way training progress" "%PY%" local\pipeline\watch_train.py local\logs\train_wrongway_det.log
"%PY%" local\pipeline\train_wrongway_det.py --epochs %EPOCHS% --batch %BATCH% %3 %4 %5 %6 > local\logs\train_wrongway_det.log 2>&1
type local\logs\train_wrongway_det.log | findstr /C:"done ->" /C:"Error" /C:"Traceback"
pause
