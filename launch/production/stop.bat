@echo off
chcp 65001 >nul
title BKK StreetSmart - Stop PRODUCTION
echo [*] Turning off Tailscale Funnel ...
tailscale funnel --https=443 --set-path=/ off >nul 2>&1
echo [*] Stopping production server (port 8000) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8000
echo [OK] Server stopped and public access closed. Start it again with start.bat.
timeout /t 5
