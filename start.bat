@echo off
title Pagani Air Cargo ACARS
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up Python environment...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
start "" http://localhost:5050
.venv\Scripts\python app.py
pause
