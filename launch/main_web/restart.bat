@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - Restart Public Server

echo ======================================================================
echo   BKK StreetSmart - Restart server (Tailscale Funnel on port 8000)
echo ======================================================================
echo.

rem Close the previous server and its window, then start fresh in this one.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0kill_server.ps1" -Port 8000

rem Give the OS a moment to release the port
ping -n 3 127.0.0.1 >nul

echo [*] Starting server with Tailscale Funnel ...
echo.
call "%~dp0start.bat"
