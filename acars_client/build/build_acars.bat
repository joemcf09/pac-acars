@echo off
title Build PAC ACARS
cd /d "%~dp0"
set "ROOT=%~dp0..\.."
set "VERSION=1.1.0"

rem The airline's website, baked into the build so pilots don't have to type it.
rem Change this to your own address before building (and after moving PAC to a server).
if "%PAC_SITE%"=="" set "PAC_SITE=https://pac-va.com"
echo Pilots' copies will point at: %PAC_SITE%
> "%ROOT%\acars_client\site_url.py" echo SITE = "%PAC_SITE%"

echo === PAC ACARS %VERSION% build ===
if not exist "%ROOT%\.venv" (
  echo Setting up the Python environment...
  py -3 -m venv "%ROOT%\.venv" || python -m venv "%ROOT%\.venv"
)
set "PY=%ROOT%\.venv\Scripts\python.exe"
"%PY%" -m pip install --upgrade pip >nul
"%PY%" -m pip install -r "%ROOT%\requirements.txt" pyinstaller pywebview pystray pillow || goto :fail

echo.
echo === Packaging PAC ACARS.exe ===
"%PY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath work pac_acars.spec || goto :fail
echo Built: %~dp0dist\PAC ACARS\PAC ACARS.exe
copy /y "%ROOT%\acars_client\CHANGELOG.txt" "dist\PAC ACARS\" >nul

if not exist "%ROOT%\static\downloads" mkdir "%ROOT%\static\downloads"
copy /y "%ROOT%\acars_client\CHANGELOG.txt" "%ROOT%\static\downloads\PAC-ACARS-CHANGELOG.txt" >nul

echo.
echo === Portable zip ===
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\PAC ACARS\*' -DestinationPath '%ROOT%\static\downloads\PAC-ACARS-%VERSION%-portable.zip'" && echo Saved static\downloads\PAC-ACARS-%VERSION%-portable.zip

echo.
echo === Installer ===
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC (
  "%ISCC%" /Q installer.iss || goto :fail
  copy /y "Output\PAC-ACARS-Setup-%VERSION%.exe" "%ROOT%\static\downloads\" >nul
  echo Saved static\downloads\PAC-ACARS-Setup-%VERSION%.exe
) else (
  echo Inno Setup 6 isn't installed, so no installer was made. The portable zip works on its own.
  echo For the installer, get Inno Setup from https://jrsoftware.org/isdl.php and run this again.
)

echo.
echo Done. The PAC website now offers the download on its ACARS page and in the handbook.
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the error.
pause
exit /b 1
