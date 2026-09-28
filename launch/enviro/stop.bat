@echo off
chcp 65001 >nul
title ENVIRO Seismic Command - Stop
echo [*] Turning off Tailscale Funnel at /enviro ...
tailscale funnel --https=443 --set-path=/enviro off >nul 2>&1
echo [*] Stopping ENVIRO ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\main_web\kill_server.ps1" -Port 5050 -Folder enviro
echo [OK] ENVIRO stopped and public access closed. Start it again with start.bat.
timeout /t 5
