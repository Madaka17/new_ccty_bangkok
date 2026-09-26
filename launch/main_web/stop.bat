@echo off
chcp 65001 >nul
title BKK StreetSmart - Stop Server
echo [*] Turning off Tailscale Funnel ...
tailscale funnel reset >nul 2>&1
echo [*] Stopping server ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill_server.ps1" -Port 8000
echo [OK] Server stopped and public access closed. Start it again with start.bat.
timeout /t 5
