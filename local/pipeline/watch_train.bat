@echo off
rem Live % progress of the helmet-detector training in this window. Ctrl+C to close.
title Helmet YOLO26x training
"%~dp0..\..\.venv\Scripts\python.exe" "%~dp0watch_train.py" %*
pause
