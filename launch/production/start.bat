@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - PRODUCTION (localhost:8000 + bkksmartstreet.com)
set OPENCV_FFMPEG_LOGLEVEL=-8

rem Production: port 8000, data in instances\production (cache, database, agent state, web UI build).
rem The test server (launch\test, port 8001) keeps its own copy in instances\test.
set "PORT=8000"
set "INSTANCE_DIR=%CD%\instances\production"

echo ======================================================================
echo   BKK StreetSmart - PRODUCTION  (Public: https://bkksmartstreet.com)
echo   data: instances\production\
echo ======================================================================
echo.

rem Already running: say so instead of starting a second copy (restart.bat replaces it)
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [!] Server is already running on port 8000. Use restart.bat to restart it.
    echo.
    pause
    exit /b 0
)

rem Public access: Cloudflare Tunnel, the cloudflared Windows service (launch\cloudflare). It starts at boot on its
rem own and sends https://bkksmartstreet.com to http://127.0.0.2:8000 (that address tells the server the visitor's
rem IP is in CF-Connecting-IP; see backend\core\access_guard.py), so this script only checks it.
sc query cloudflared 2>nul | findstr /c:"RUNNING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Public URL: https://bkksmartstreet.com  ^(Cloudflare Tunnel^)
) else (
    echo [!] Cloudflare Tunnel service ^(cloudflared^) is not running: the site is not public.
    echo     Start it as administrator: Start-Service cloudflared
)
echo [*] Local URL:  http://localhost:8000
echo [*] Close this window to stop the server.
echo.

call launch\build_web.bat

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
