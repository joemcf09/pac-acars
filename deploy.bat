@echo off
title Deploy PAC to the live site
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" tools\deploy.py %*
echo.
pause
