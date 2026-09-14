@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BKK Traffic - Pipeline & Server Live Status

echo [*] Starting BKK Traffic Pipeline Live Status Monitor...
echo [*] Press Ctrl+C anytime to stop.
echo.

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe pipeline_status.py --watch 3
) else (
    python pipeline_status.py --watch 3
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Notice] Monitor exited.
)
pause
