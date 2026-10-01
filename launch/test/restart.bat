@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - Restart TEST server

rem Close the previous test server and its window, then start fresh in this one. Production (:8000) is not touched.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8001

rem Give the OS a moment to release the port
ping -n 3 127.0.0.1 >nul

call "%~dp0start.bat"
