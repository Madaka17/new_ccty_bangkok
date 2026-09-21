@echo off
chcp 65001 >nul
cd /d "%~dp0"
title BKK StreetSmart CCTV + YOLO11x AI Server
rem Silence FFmpeg h264 decoder spam; must be set before python starts (os.environ inside python is too late on Windows)
set OPENCV_FFMPEG_LOGLEVEL=-8

echo ======================================================================
echo   BKK StreetSmart CCTV + YOLO11x AI Server
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


