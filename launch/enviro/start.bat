@echo off
chcp 65001 >nul
cd /d "%~dp0..\..\ENVIRO"
title ENVIRO Seismic Command - Public (bkksmartstreet.com/enviro)

echo ======================================================================
echo   ENVIRO Seismic Command  (Public at https://bkksmartstreet.com/enviro/)
echo ======================================================================
echo.

rem Started again: launch\watchdog may restart it from now on (stop.bat / kill_server.ps1 left this mark)
if exist "%~dp0..\watchdog\state\stopped_5050" del "%~dp0..\watchdog\state\stopped_5050"

rem Already running: say so instead of starting a second copy (restart.bat replaces it)
netstat -ano | findstr /r /c:":5050 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [!] ENVIRO is already running on port 5050. Use restart.bat to restart it.
    echo.
    pause
    exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating ENVIRO\.venv ...
    py -3 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

rem The demo passwords and node key are public in the README: replace them before going online
.venv\Scripts\python.exe "%~dp0lock_accounts.py"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Could not replace the demo passwords. ENVIRO was not started.
    pause
    exit /b 1
)

rem Public through the Cloudflare Tunnel service (launch\cloudflare): /enviro on the same address as
rem BKK StreetSmart (launch\production), which serves "/". ENVIRO strips the /enviro prefix itself.
echo [*] Public URL: https://bkksmartstreet.com/enviro/
echo [*] Local  URL: http://localhost:5050
echo [*] Close this window to stop ENVIRO.
echo.

set PORT=5050
.venv\Scripts\python.exe main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] ENVIRO exited with code %ERRORLEVEL%
)
pause
