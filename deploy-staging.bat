@echo off
title Deploy PAC to the test site
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" tools\deploy.py --staging %*
echo.
pause
