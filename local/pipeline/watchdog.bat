@echo off
rem Restart the public server when /api/health fails 3 checks in a row (~3 min).
rem Run it in its own window, or at logon:
rem   schtasks /create /tn "BKK StreetSmart watchdog" /tr "\"%~dp0watchdog.bat\"" /sc onlogon
rem Stop it (e.g. before training on the GPU) with Ctrl+C or launch\main_web\stop.bat + close the window.
title BKK StreetSmart watchdog
cd /d "%~dp0..\.."
set FAILS=0
:loop
for /f %%c in ('curl -s -o nul -w "%%{http_code}" --max-time 20 http://127.0.0.1:8000/api/health') do set CODE=%%c
if "%CODE%"=="200" (
    set FAILS=0
) else (
    set /a FAILS+=1
    echo [%date% %time%] health=%CODE% fail %FAILS%/3 >> "local\logs\watchdog.log"
    if %FAILS% GEQ 3 (
        echo [%date% %time%] restarting server >> "local\logs\watchdog.log"
        start "" cmd /c "launch\main_web\restart.bat"
        set FAILS=0
        ping -n 181 127.0.0.1 >nul
    )
)
ping -n 61 127.0.0.1 >nul
goto loop
