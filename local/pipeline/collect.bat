@echo off
setlocal
cd /d "%~dp0..\.."
title BKK Traffic - CCTV Dataset Collection

echo ======================================================================
echo   BKK Traffic - CCTV Dataset Collection
echo ======================================================================
echo.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "TARGET_LIMIT=%~1"
if "%TARGET_LIMIT%"=="" set "TARGET_LIMIT=1000"

set "ROUND_INTERVAL=%~2"
if "%ROUND_INTERVAL%"=="" set "ROUND_INTERVAL=60"

echo [*] Target: %TARGET_LIMIT% images
echo [*] Interval: %ROUND_INTERVAL% seconds
echo [*] You can open status.bat to monitor progress in realtime.
echo.

"%PY%" local\pipeline\collect_dataset.py --rounds 1000 --every %ROUND_INTERVAL% --limit %TARGET_LIMIT%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Collection stopped (code: %ERRORLEVEL%)
) else (
    echo.
    echo [OK] Target reached: %TARGET_LIMIT% images collected!
)

pause
