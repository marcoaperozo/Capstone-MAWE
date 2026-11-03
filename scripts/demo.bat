@echo off
REM Double-click to run the MAWE demo.
cd /d "%~dp0.."
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0demo.ps1" %*
pause
