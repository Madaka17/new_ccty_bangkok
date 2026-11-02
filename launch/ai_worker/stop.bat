@echo off
chcp 65001 >nul
title BKK AI Worker - Stop
echo [*] Stopping the AI worker ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\kill_server.ps1" -Port 8100 -Folder ai_worker
echo [OK] AI worker stopped. The Pi runs with YOLO off until start.bat runs again.
timeout /t 5
