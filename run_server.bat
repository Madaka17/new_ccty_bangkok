@echo off
cd /d "%~dp0"
title BKK Traffic CCTV & YOLO11x AI Server

echo ======================================================================
echo   BKK Traffic CCTV & YOLO11x AI Server
echo ======================================================================
echo.

if exist ".venv\Scripts\python.exe" goto USE_VENV
goto USE_GLOBAL

:USE_VENV
echo [OK] Using Python Virtual Environment (.venv)
echo [*] Starting YOLO11x AI Server at http://localhost:8000 ...
echo.
.venv\Scripts\python.exe server.py
goto END

:USE_GLOBAL
echo [Notice] .venv not found, attempting with system python...
echo [*] Starting YOLO11x AI Server at http://localhost:8000 ...
echo.
python server.py
goto END

:END
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Server exited with code %ERRORLEVEL%
)
pause


