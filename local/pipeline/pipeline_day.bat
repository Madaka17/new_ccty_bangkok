@echo off
setlocal
cd /d "%~dp0..\.."
title BKK Traffic - Daytime Pipeline (Collect until 20:00 -> Train)

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

set "UNTIL=%~1"
if "%UNTIL%"=="" set "UNTIL=20:00"

set "EVERY=%~2"
if "%EVERY%"=="" set "EVERY=900"

set "EPOCHS=%~3"
if "%EPOCHS%"=="" set "EPOCHS=60"

set "LOG=local\pipeline.log"

echo === [%DATE% %TIME%] 1/3 collect until %UNTIL%, one pass every %EVERY% s === >> "%LOG%"
echo [*] [1/3] Collecting frames until %UNTIL% (every %EVERY% s, no limit)...
"%PY%" local\pipeline\collect_dataset.py --every %EVERY% --until %UNTIL% >> "%LOG%" 2>&1

echo === [%DATE% %TIME%] 2/3 clean labels === >> "%LOG%"
echo [*] [2/3] Cleaning and filtering dataset...
"%PY%" local\pipeline\clean_dataset.py >> "%LOG%" 2>&1

echo === [%DATE% %TIME%] 3/3 train: stop server, %EPOCHS% epochs === >> "%LOG%"
echo [*] [3/3] Pausing server for training (%EPOCHS% epochs)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'server\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 5 /nobreak >nul

"%PY%" local\pipeline\train_model.py --epochs %EPOCHS% --imgsz 960 --patience 12 >> "%LOG%" 2>&1

echo === [%DATE% %TIME%] restart server === >> "%LOG%"
echo [*] Restarting server...
powershell -NoProfile -Command "Start-Process -FilePath '%~dp0..\..\.venv\Scripts\python.exe' -ArgumentList 'server.py' -WorkingDirectory '%~dp0..\..' -WindowStyle Hidden"
timeout /t 10 /nobreak >nul

echo === [%DATE% %TIME%] pipeline finished === >> "%LOG%"
echo.
echo [OK] Daytime pipeline completed successfully!
pause
