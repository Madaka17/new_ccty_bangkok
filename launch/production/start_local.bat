@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - PRODUCTION (localhost:8000, local start)
rem Silence FFmpeg h264 decoder spam; must be set before python starts (os.environ inside python is too late on Windows)
set OPENCV_FFMPEG_LOGLEVEL=-8

rem Same production server and data as start.bat. To keep it to this machine and the LAN, stop the Cloudflare
rem Tunnel service first (Stop-Service cloudflared, as administrator): while it runs the site stays public.
set "PORT=8000"
set "INSTANCE_DIR=%CD%\instances\production"

echo ======================================================================
echo   BKK StreetSmart - PRODUCTION  http://localhost:8000
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

sc query cloudflared 2>nul | findstr /c:"RUNNING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [!] Cloudflare Tunnel is running: the site is still public at https://bkksmartstreet.com
    echo     For this machine / LAN only, run as administrator: Stop-Service cloudflared
    echo.
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
