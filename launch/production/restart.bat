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

rem The camera watcher is not in the server's process tree, so a restart would leave the old one running
rem (and a windowed one never becomes hidden). start.bat starts a fresh one. No race with the watchdog:
rem it starts camera status only while :8000 answers, and the server is down here.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\camera_status_window.ps1" -Stop

rem Give the OS a moment to release the port
ping -n 3 127.0.0.1 >nul

echo [*] Starting server ...
echo.
call "%~dp0start.bat" %*
