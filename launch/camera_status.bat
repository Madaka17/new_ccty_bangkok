@echo off
rem camera_status: see launch\camera_status.py. Runs in its own window like the server, a new round every 5 minutes.
rem Usage: camera_status.bat [port] [--watch seconds] [--once] [--all]
chcp 65001 >nul
cd /d "%~dp0.."
set "PORT=8000"
for %%a in (%*) do echo %%a| findstr /r "^[0-9][0-9][0-9][0-9][0-9]*$" >nul && set "PORT=%%a"
title BKK StreetSmart - camera status (:%PORT%)
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
set "ARGS=%*"
rem Keeps watching unless --once, --all or --watch is given
echo.%*| findstr /c:"--" >nul || set "ARGS=%* --watch 300"
"%PY%" launch\camera_status.py %ARGS%
rem Opened by double-click and stopped (or --once): keep the window open to read the result
for %%x in (%cmdcmdline%) do if /i "%%~x"=="/c" pause
