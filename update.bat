@echo off
title Update PAC
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag the new pac-acars.zip onto update.bat, or run:  update.bat path\to\pac-acars.zip
  pause
  exit /b 1
)
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" tools\update.py "%~1"
pause
