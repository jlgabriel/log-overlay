@echo off
cd /d "%~dp0"
python log_overlay.py %*
if errorlevel 1 pause
