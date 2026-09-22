@echo off
rem Nightly DB prune + backup. Register once (run as the same user that runs the server):
rem   schtasks /create /tn "BKK StreetSmart backup" /tr "\"%~dp0backup_db.bat\"" /sc daily /st 03:30
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" "local\pipeline\backup_db.py" >> "local\logs\backup.log" 2>&1
