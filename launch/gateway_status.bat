@echo off
rem gateway_status: see launch\gateway_status.py. Runs in its own window and checks every 5 minutes.
rem Usage: gateway_status.bat [--watch seconds] [--once]
chcp 65001 >nul
cd /d "%~dp0.."
title BKK StreetSmart - AI gateway status
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
set "ARGS=%*"
rem Keeps watching unless --once or --watch is given
echo.%*| findstr /c:"--" >nul || set "ARGS=%* --watch 300"
"%PY%" launch\gateway_status.py %ARGS%
rem Opened by double-click and stopped (or --once): keep the window open to read the result
for %%x in (%cmdcmdline%) do if /i "%%~x"=="/c" pause
