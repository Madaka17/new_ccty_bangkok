@echo off
chcp 65001 >nul
title ENVIRO Seismic Command - Stop
echo [*] Stopping ENVIRO ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 5050 -Folder enviro
echo [OK] ENVIRO stopped. bkksmartstreet.com/enviro/ shows a Cloudflare error page until start.bat runs again.
timeout /t 5
