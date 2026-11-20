@echo off
rem Desktop icon target. Starts the live Bionic usage page with pythonw (it opens the browser).
rem With --report: collect now, rebuild report.html and open that instead.
chcp 65001 >nul
cd /d "%~dp0..\.."
if /i "%~1"=="--report" goto report
start "" "%CD%\.venv\Scripts\pythonw.exe" "%~dp0live.py"
exit /b 0
:report
"%CD%\.venv\Scripts\python.exe" "%~dp0collect.py"
"%CD%\.venv\Scripts\python.exe" "%~dp0report.py" --open
