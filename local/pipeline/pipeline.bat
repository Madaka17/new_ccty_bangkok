@echo off
setlocal
cd /d "%~dp0..\.."
title BKK Traffic - Full End-to-End Pipeline

echo ======================================================================
echo   BKK Traffic - Full Pipeline (Collect -^> Relabel -^> Clean -^> Train -^> Serve)
echo ======================================================================
echo.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "TARGET_LIMIT=%~1"
if "%TARGET_LIMIT%"=="" set "TARGET_LIMIT=1000"

set "EPOCHS=%~2"
if "%EPOCHS%"=="" set "EPOCHS=60"

set "LOG=local\pipeline.log"

echo === [%DATE% %TIME%] 1/3 collect: target %TARGET_LIMIT% images === >> "%LOG%"
echo [*] [1/3] Collecting images (Target: %TARGET_LIMIT% images)...
"%PY%" local\pipeline\collect_dataset.py --rounds 1000 --every 60 --limit %TARGET_LIMIT% >> "%LOG%" 2>&1

if "%SKIP_RELABEL%"=="1" goto clean
echo === [%DATE% %TIME%] 1b/3 relabel: tiled + per-class floors === >> "%LOG%"
echo [*] [1b/3] Re-labelling older frames (tiled, low motorcycle floor; set SKIP_RELABEL=1 to skip)...
"%PY%" local\pipeline\relabel_dataset.py --keep-manual >> "%LOG%" 2>&1

:clean
echo === [%DATE% %TIME%] 2/3 clean labels === >> "%LOG%"
echo [*] [2/3] Cleaning and filtering dataset...
"%PY%" local\pipeline\clean_dataset.py >> "%LOG%" 2>&1

echo === [%DATE% %TIME%] 3/3 train: stop server, %EPOCHS% epochs === >> "%LOG%"
echo [*] [3/3] Pausing AI server for training (%EPOCHS% epochs)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'server\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 5 /nobreak >nul

"%PY%" local\pipeline\train_model.py --epochs %EPOCHS% --imgsz 960 --patience 15 >> "%LOG%" 2>&1

echo === [%DATE% %TIME%] restart server === >> "%LOG%"
echo [*] Restarting AI server...
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0..\..\.venv\Scripts\python.exe' -ArgumentList 'server.py' -WorkingDirectory '%~dp0..\..' -WindowStyle Hidden"
timeout /t 10 /nobreak >nul

echo === [%DATE% %TIME%] pipeline finished === >> "%LOG%"
echo.
echo [OK] Pipeline finished successfully!
pause
