@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BKK StreetSmart - Public (Tailscale Funnel)
set OPENCV_FFMPEG_LOGLEVEL=-8

echo ======================================================================
echo   BKK StreetSmart CCTV + YOLO26x AI Server  (Public via Tailscale)
echo ======================================================================
echo.

where tailscale >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] tailscale.exe not found in PATH. Install Tailscale first.
    pause
    exit /b 1
)

echo [*] Enabling Tailscale Funnel on port 8000 ...
tailscale funnel reset >nul 2>&1
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

call build_web.bat

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
