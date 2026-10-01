@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - TEST server (localhost:8001)
set OPENCV_FFMPEG_LOGLEVEL=-8

rem Second copy of the server for trying changes before restarting production (launch\production, port 8000).
rem Same code, same models, same .env keys - but its own port and its own data folder instances\test
rem (cache, database, BMA archive, web UI build), so nothing it does touches the live data.
rem Map tiles are shared (read from the production cache). Delete instances\test\ to start it clean again.
rem It runs the same background AI jobs as production on the same keys: stop it when not needed.
set "PORT=8001"
set "INSTANCE_DIR=%CD%\instances\test"
set "BMA_DATA_DIR=%CD%\instances\test\data"

echo ======================================================================
echo   BKK StreetSmart - TEST server  http://localhost:8001
echo   data: instances\test\   (production on :8000 is not touched)
echo ======================================================================
echo.

netstat -ano | findstr /r /c:":8001 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [!] Test server is already running on port 8001. Use restart.bat to restart it.
    echo.
    pause
    exit /b 0
)

if not exist "instances\test\cache" (
    echo [*] First run: seeding instances\test with the small caches and a copy of the production DB ...
    mkdir "instances\test\cache" >nul 2>&1
    for %%f in (longdo_cameras.json bma_events.json traffic_history.json twa_key.json) do if exist "instances\production\cache\%%f" copy /Y "instances\production\cache\%%f" "instances\test\cache\%%f" >nul
    if exist "instances\production\cache\rsc" robocopy "instances\production\cache\rsc" "instances\test\cache\rsc" /E /NFL /NDL /NJH /NJS >nul
    if exist "instances\production\vehicle_counts.db" copy /Y "instances\production\vehicle_counts.db" "instances\test\vehicle_counts.db" >nul
    if exist "instances\production\count_cameras.json" copy /Y "instances\production\count_cameras.json" "instances\test\count_cameras.json" >nul
)
if not exist "instances\test\data" mkdir "instances\test\data"

call launch\build_web.bat

echo [*] Starting TEST server at http://localhost:8001 ...
echo.
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe server.py
) else (
    python server.py
)
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Server exited with code %ERRORLEVEL%
)
pause
