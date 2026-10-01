@echo off
chcp 65001 >nul
title BKK StreetSmart - Stop PRODUCTION
echo [*] Stopping production server (port 8000) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8000
echo [OK] Server stopped. bkksmartstreet.com shows a Cloudflare error page until start.bat runs again.
timeout /t 5
