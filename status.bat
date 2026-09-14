@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: If called as child window or with --inline flag, run the monitor directly
if "%~1"=="--child" goto :RUN_MONITOR
if "%~1"=="--inline" goto :RUN_MONITOR

:: Otherwise, pop up a new standalone CMD window
echo [*] Opening Realtime Pipeline Status Pop-up Window...
start "🚦 BKK Traffic — Pipeline & AI Realtime Monitor" cmd /k ""%~f0" --child"
exit /b

:RUN_MONITOR
title 🚦 BKK Traffic — Pipeline & AI Realtime Monitor
mode con: cols=90 lines=38
color 0F

if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe pipeline_status.py --watch 1
) else (
    python pipeline_status.py --watch 1
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Notice] Monitor stopped.
)
pause
