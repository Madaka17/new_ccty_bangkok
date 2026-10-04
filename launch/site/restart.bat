@echo off
chcp 65001 >nul
title BKK StreetSmart - Restart whole site
rem Restart production (port 8000) and ENVIRO (port 5050), each in its own window.
pushd "%~dp0..\.."
set "ROOT=%CD%"
popd
echo [*] Restarting production and ENVIRO ...
start "" cmd /c "%ROOT%\launch\production\restart.bat"
start "" cmd /c "%ROOT%\launch\enviro\restart.bat"
timeout /t 5
