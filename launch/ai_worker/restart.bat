@echo off
chcp 65001 >nul
title BKK AI Worker - Restart
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8100 -Folder ai_worker
ping -n 3 127.0.0.1 >nul
call "%~dp0start.bat" %*
