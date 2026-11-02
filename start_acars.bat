@echo off
title PAC ACARS
cd /d "%~dp0"
rem Runs PAC ACARS from source, in the same Python environment as the PAC website (start.bat).
if not exist .venv (
  echo First run: setting up Python environment...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
rem the native window component
.venv\Scripts\python -c "import webview, pystray" 2>nul || (
  echo Installing the PAC ACARS window and tray components...
  .venv\Scripts\python -m pip install pywebview pystray pillow
)
.venv\Scripts\python acars_client\client.py
if errorlevel 1 pause
