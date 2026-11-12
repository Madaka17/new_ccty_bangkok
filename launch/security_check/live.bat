@echo off
cd /d "%~dp0..\.."
start "" /b .venv\Scripts\pythonw.exe -m launch.security_check.live %*
