@echo off
chcp 65001 >nul
title BKK StreetSmart - Stop TEST server
echo [*] Stopping test server (port 8001) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8001
echo [OK] Test server stopped. Production on port 8000 is not touched.
timeout /t 5
