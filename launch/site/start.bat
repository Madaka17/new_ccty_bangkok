@echo off
chcp 65001 >nul
title BKK StreetSmart - Start whole site
rem The whole public site in one click: production (port 8000, bkksmartstreet.com) and ENVIRO (port 5050,
rem bkksmartstreet.com/enviro). Each opens in its own window; one that is already running is skipped.
pushd "%~dp0..\.."
set "ROOT=%CD%"
popd

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Production is already running on port 8000.
) else (
    echo [*] Starting production ...
    start "" cmd /c "%ROOT%\launch\production\start.bat"
)

netstat -ano | findstr /r /c:":5050 .*LISTENING" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] ENVIRO is already running on port 5050.
) else (
    echo [*] Starting ENVIRO ...
    start "" cmd /c "%ROOT%\launch\enviro\start.bat"
)
timeout /t 5
