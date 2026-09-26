@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - Restart Public Server

echo ======================================================================
echo   BKK StreetSmart - Restart server (Tailscale Funnel on port 8000)
echo ======================================================================
echo.

rem Kill whatever is listening on port 8000 (the previous server.py), then start fresh.
set "KILLED="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    if not "%%p"=="0" if not defined KILLED (
        echo [*] Stopping old server ^(PID %%p^) ...
        taskkill /F /PID %%p >nul 2>&1
        set "KILLED=%%p"
    )
)
if not defined KILLED echo [*] No server running on port 8000.

rem Give the OS a moment to release the port
ping -n 3 127.0.0.1 >nul

echo [*] Starting server with Tailscale Funnel ...
echo.
call "%~dp0start.bat"
