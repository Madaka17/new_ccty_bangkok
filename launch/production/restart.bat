@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - Restart PRODUCTION

echo ======================================================================
echo   BKK StreetSmart - Restart PRODUCTION (port 8000, https://bkksmartstreet.com)
echo ======================================================================
echo.

rem Close the previous server and its window, then start fresh in this one.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8000

rem Give the OS a moment to release the port
ping -n 3 127.0.0.1 >nul

echo [*] Starting server ...
echo.
call "%~dp0start.bat"
