@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK AI Worker (:8100, YOLO for the Raspberry Pi)

rem Runs YOLO on this PC's GPU for the Pi (backend\vision\ai_worker.py). Models load on first use and
rem leave VRAM after 10 minutes without calls. Only the Pi (AI_WORKER_ALLOW) with AI_WORKER_TOKEN gets answers.

rem Started again: launch\watchdog may restart it from now on (stop.bat / kill_server.ps1 left this mark)
if exist "%~dp0..\watchdog\state\stopped_8100" del "%~dp0..\watchdog\state\stopped_8100"

rem Modes: no flag = start hidden through launch\run_hidden.py (log launch\logs\ai_worker.log);
rem --child = the hidden run itself; --window = a visible console, for debugging.
set "MODE=hidden"
for %%a in (%*) do (
    if /i "%%~a"=="--child" set "MODE=child"
    if /i "%%~a"=="--window" set "MODE=window"
)
netstat -ano | findstr /r /c:":8100 .*LISTENING" >nul && (
    echo [!] AI worker is already running on port 8100. Use restart.bat to restart it.
    if "%MODE%"=="window" pause
    exit /b 0
)
if "%MODE%"=="hidden" (
    start "" /b ".venv\Scripts\pythonw.exe" "launch\run_hidden.py" ai_worker
    echo [OK] Started in the background. Log: launch\logs\ai_worker.log
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

set OPENCV_FFMPEG_LOGLEVEL=-8
.venv\Scripts\python.exe -m backend.vision.ai_worker
if %ERRORLEVEL% NEQ 0 echo [ERROR] AI worker exited with code %ERRORLEVEL%
if "%MODE%"=="window" pause
