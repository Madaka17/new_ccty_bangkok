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

rem Modes: no flag = start hidden through launch\run_hidden.py (output in launch\logs\enviro.log, shown in
rem BKK Monitor > Processes); --child = the hidden run itself (no pause, nobody is there to press a key);
rem --window = the old visible console, for debugging.
set "MODE=hidden"
for %%a in (%*) do (
    if /i "%%~a"=="--child" set "MODE=child"
    if /i "%%~a"=="--window" set "MODE=window"
)
if "%MODE%"=="hidden" (
    netstat -ano | findstr /r /c:":5050 .*LISTENING" >nul && (
        echo [!] ENVIRO is already running on port 5050. Use restart.bat to restart it.
        exit /b 0
    )
    start "" /b "%~dp0..\..\.venv\Scripts\pythonw.exe" "%~dp0..\run_hidden.py" enviro
    echo [OK] Started in the background. Log: launch\logs\enviro.log  ^(BKK Monitor ^> Processes^)
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

rem Already running: say so instead of starting a second copy (restart.bat replaces it)
netstat -ano | findstr /r /c:":5050 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [!] ENVIRO is already running on port 5050. Use restart.bat to restart it.
    echo.
    if not "%MODE%"=="child" pause
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
    if not "%MODE%"=="child" pause
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
if not "%MODE%"=="child" pause
