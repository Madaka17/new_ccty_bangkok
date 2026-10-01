@echo off
rem The web UI build is not in git: build the React UI when it is missing (or always with "launch\build_web.bat force").
rem Called by launch\production and launch\test start.bat. Without npm the server runs the API only and "/" answers 503 until it is built.
rem Builds into the instance's own folder: %INSTANCE_DIR%\dist (instances\test\dist for the test server), else instances\production\dist.
cd /d "%~dp0.."
set "OUT=%CD%\instances\production\dist"
if defined INSTANCE_DIR set "OUT=%INSTANCE_DIR%\dist"
if /i not "%~1"=="force" if exist "%OUT%\index.html" exit /b 0
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Notice] %OUT% missing and npm not found - install Node.js, then run launch\build_web.bat. The server starts without the web UI.
    exit /b 0
)
echo [*] Building web UI (%OUT%) ...
pushd web
if not exist "node_modules" call npm ci
call npm run build -- --outDir "%OUT%"
popd
exit /b 0
