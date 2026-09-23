@echo off
rem web\dist is not in git: build the React UI when it is missing (or always with "build_web.bat force").
rem Called by run_server.bat / run_public.bat / run_test.bat. Without npm the server falls back to local\legacy_ui.
cd /d "%~dp0"
if /i not "%~1"=="force" if exist "web\dist\index.html" exit /b 0
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [Notice] web\dist missing and npm not found - install Node.js to get the new UI. Using legacy UI.
    exit /b 0
)
echo [*] Building web UI (web\dist) ...
pushd web
if not exist "node_modules" call npm ci
call npm run build
popd
exit /b 0
