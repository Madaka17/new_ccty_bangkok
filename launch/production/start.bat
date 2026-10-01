@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - PRODUCTION (localhost:8000 + Tailscale Funnel)
set OPENCV_FFMPEG_LOGLEVEL=-8

rem Production: port 8000, data in instances\production (cache, database, agent state, web UI build).
rem The test server (launch\test, port 8001) keeps its own copy in instances\test.
set "PORT=8000"
set "INSTANCE_DIR=%CD%\instances\production"

echo ======================================================================
echo   BKK StreetSmart - PRODUCTION  (Public via Tailscale Funnel)
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

where tailscale >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] tailscale.exe not found in PATH. Install Tailscale first, or use start_local.bat.
    pause
    exit /b 1
)

echo [*] Enabling Tailscale Funnel on port 8000 ...
rem Only this site's "/": "funnel reset" or "--https=443 off" would also close ENVIRO at /enviro (launch\enviro)
tailscale funnel --https=443 --set-path=/ off >nul 2>&1
tailscale funnel --bg 8000
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Funnel failed. Enable Funnel for this node in the admin console:
    echo         https://login.tailscale.com/admin/acls  ^(nodeAttrs: funnel^)
    echo         Falling back to tailnet-only access ...
    tailscale serve --bg 8000
)
echo.
tailscale funnel status
echo.
echo [*] Public URL: https://cctv-bangkok.tail95e28b.ts.net
echo [*] Local  URL: http://localhost:8000
echo [*] Close this window to stop the server. Funnel stays on until "tailscale funnel reset".
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
