@echo off
chcp 65001 >nul
title BKK StreetSmart - Stop whole site
rem Stop production (port 8000) and ENVIRO (port 5050). bkksmartstreet.com is down until start.bat runs again.
echo [*] Stopping production (port 8000) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8000
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\camera_status_window.ps1" -Stop
echo [*] Stopping ENVIRO (port 5050) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 5050 -Folder enviro
echo [OK] Site stopped.
timeout /t 5
