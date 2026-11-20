@echo off
rem Collect new Bionic usage records, rebuild the report and open it in the browser.
chcp 65001 >nul
cd /d "%~dp0..\.."
"%CD%\.venv\Scripts\python.exe" "%~dp0collect.py"
"%CD%\.venv\Scripts\python.exe" "%~dp0report.py" --open
