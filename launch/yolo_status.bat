@echo off
rem yolo_status: see launch\yolo_status.py. Runs in its own window like the server and refreshes every 10 s.
rem Usage: yolo_status.bat [port] [--watch seconds] [--once]
chcp 65001 >nul
cd /d "%~dp0.."
set "PORT=8000"
for %%a in (%*) do echo %%a| findstr /r "^[0-9][0-9][0-9][0-9][0-9]*$" >nul && set "PORT=%%a"
title BKK StreetSmart - YOLO status (:%PORT%)
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
set "ARGS=%*"
rem Keeps watching unless --once or --watch is given
echo.%*| findstr /c:"--" >nul || set "ARGS=%* --watch 10"
"%PY%" launch\yolo_status.py %ARGS%
rem Opened by double-click and stopped (or --once): keep the window open to read the result
for %%x in (%cmdcmdline%) do if /i "%%~x"=="/c" pause
