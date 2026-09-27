@echo off
rem web\dist is not in git: build the React UI when it is missing (or always with "launch\build_web.bat force").
rem Called by launch\main_web, launch\localhost_8000 and launch\localhost_8001 start.bat. Without npm the server runs the API only and "/" answers 503 until web\dist is built.
rem WEB_DIST set (the test server: local\stage\dist) = build there instead, so the live server's web\dist is left alone.
cd /d "%~dp0.."
set "OUT=%CD%\web\dist"
if defined WEB_DIST set "OUT=%WEB_DIST%"
if /i not "%~1"=="force" if exist "%OUT%\index.html" exit /b 0
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Notice] web\dist missing and npm not found - install Node.js, then run launch\build_web.bat. The server starts without the web UI.
    exit /b 0
)
echo [*] Building web UI (%OUT%) ...
pushd web
if not exist "node_modules" call npm ci
call npm run build -- --outDir "%OUT%"
popd
exit /b 0
