@echo off
cd /d "%~dp0..\.."
title BKK StreetSmart - Stop TEST server
set "KILLED="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8001 .*LISTENING"') do (
    if not "%%p"=="0" if not defined KILLED (
        echo [*] Stopping test server ^(PID %%p^) ...
        taskkill /F /PID %%p >nul 2>&1
        set "KILLED=%%p"
    )
)
if not defined KILLED echo [*] No test server running on port 8001.
pause
