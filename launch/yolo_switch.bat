@echo off
rem yolo_switch: see launch\yolo_switch.py. Desktop "BKK YOLO On-Off" icon opens this in its own window.
rem Usage: yolo_switch.bat [port] [--on | --off]   (no flag: asks Y/N)
chcp 65001 >nul
cd /d "%~dp0.."
title BKK StreetSmart - YOLO On-Off
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8
"%PY%" launch\yolo_switch.py %*
rem Keep the window open so the result can be read
pause
