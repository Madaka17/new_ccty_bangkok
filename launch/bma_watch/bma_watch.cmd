@echo off
chcp 65001 >nul
title BMA Watch - cpudapp.bangkok.go.th/bmatraffic

rem Checks the BMA traffic site every 10 s and pops a Windows notification when it goes down or comes back.
rem Optional: bma_watch.cmd -IntervalSeconds 30 -RemindMinutes 15
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bma_watch.ps1" %*

echo.
echo [!] BMA Watch stopped.
pause
