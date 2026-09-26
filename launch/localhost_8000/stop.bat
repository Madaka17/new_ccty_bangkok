@echo off
cd /d "%~dp0..\.."
title BKK StreetSmart - Stop server (localhost:8000)
rem Stops server.py on port 8000 (also the Main web one). Tailscale Funnel is left as is: launch\main_web\stop.bat closes it.
set "KILLED="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    if not "%%p"=="0" if not defined KILLED (
        echo [*] Stopping server ^(PID %%p^) ...
        taskkill /F /PID %%p >nul 2>&1
        set "KILLED=%%p"
    )
)
if not defined KILLED echo [*] No server running on port 8000.
pause
