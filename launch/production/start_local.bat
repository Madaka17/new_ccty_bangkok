@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - PRODUCTION (localhost:8000 only)
rem Silence FFmpeg h264 decoder spam; must be set before python starts (os.environ inside python is too late on Windows)
set OPENCV_FFMPEG_LOGLEVEL=-8

rem Same production server and data as start.bat, without Tailscale Funnel: this machine and the LAN only.
set "PORT=8000"
set "INSTANCE_DIR=%CD%\instances\production"

echo ======================================================================
echo   BKK StreetSmart - PRODUCTION  http://localhost:8000  (not public)
echo   data: instances\production\
echo ======================================================================
echo.

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [!] Server is already running on port 8000. Use restart.bat to restart it.
    echo.
    pause
    exit /b 0
)

call launch\build_web.bat

echo [*] Starting server at http://localhost:8000 ...
echo.
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe server.py
) else (
    python server.py
)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Server exited with code %ERRORLEVEL%
)
pause
