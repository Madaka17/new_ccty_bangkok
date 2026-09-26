@echo off
chcp 65001 >nul
cd /d "%~dp0..\.."
title BKK StreetSmart - TEST server (localhost:8001)
set OPENCV_FFMPEG_LOGLEVEL=-8

rem Second copy of the server for trying changes before restarting the public one (port 8000).
rem Same code, same models, same .env keys - but its own port, cache, database and data folder,
rem so nothing it does touches the live data. Map tiles are shared (read from the live cache).
rem Delete local\stage\ to start it clean again.
set "PORT=8001"
set "INSTANCE_DIR=%CD%\local\stage"
set "BMA_DATA_DIR=%CD%\local\stage\data"

echo ======================================================================
echo   BKK StreetSmart - TEST server  http://localhost:8001
echo   data: local\stage\   (public server on :8000 is not touched)
echo ======================================================================
echo.

if not exist "local\stage\cache" (
    echo [*] First run: seeding local\stage with the small caches and a copy of the DB ...
    mkdir "local\stage\cache" >nul 2>&1
    for %%f in (longdo_cameras.json bma_events.json traffic_history.json twa_key.json) do if exist "cache\%%f" copy /Y "cache\%%f" "local\stage\cache\%%f" >nul
    if exist "cache\rsc" robocopy "cache\rsc" "local\stage\cache\rsc" /E /NFL /NDL /NJH /NJS >nul
    if exist "vehicle_counts.db" copy /Y "vehicle_counts.db" "local\stage\vehicle_counts.db" >nul
    if exist "count_cameras.json" copy /Y "count_cameras.json" "local\stage\count_cameras.json" >nul
)
if not exist "local\stage\data" mkdir "local\stage\data"

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
