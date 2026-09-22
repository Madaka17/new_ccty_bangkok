@echo off
rem Live status of the wrong-way pipeline (collect / train). Ctrl+C or close to exit.
title Wrong-way status
"%~dp0..\..\.venv\Scripts\python.exe" "%~dp0watch_wrongway.py"
pause
