@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - YOLO26x Training Status
cls
echo ======================================================================
echo   BKK StreetSmart - YOLO26x Training Monitor
echo   (Press Ctrl+C or close window anytime. Training continues in background)
echo ======================================================================
echo.

if exist "local\logs\wrongway_status.json" (
    echo [*] Status:
    type "local\logs\wrongway_status.json"
    echo.
    echo.
)

echo [*] Reading live training log...
echo.
.venv\Scripts\python.exe local\pipeline\watch_train.py local\logs\train_wrongway_det.log
pause
