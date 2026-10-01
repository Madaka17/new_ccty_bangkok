@echo off
chcp 65001 >nul
title ENVIRO Seismic Command - Restart

rem Close the previous ENVIRO and its window, then start fresh in this one.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 5050 -Folder enviro

rem Give the OS a moment to release the port
ping -n 3 127.0.0.1 >nul

call "%~dp0start.bat"
