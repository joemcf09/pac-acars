# Building PAC ACARS for Windows

This turns the ACARS app into `PAC ACARS.exe`, a portable zip and an installer,
and puts them on the PAC website for download.

## One-time setup

1. **Python 3.10 or newer** (you already have it if the PAC website runs).
2. **Inno Setup 6** for the installer (free): https://jrsoftware.org/isdl.php
   Optional: without it you still get the exe and a portable zip.

## Build

Double-click **`acars_client\build\build_acars.bat`**. It:

1. installs the build tools (PyInstaller) and the native window (pywebview) into PAC's Python environment,
2. packages the app into `acars_client\build\dist\PAC ACARS\PAC ACARS.exe`,
3. makes `static\downloads\PAC-ACARS-<version>-portable.zip`,
4. makes the installer `static\downloads\PAC-ACARS-Setup-<version>.exe` (if Inno Setup is installed).

The PAC website then shows a download card on its ACARS page, and older copies of
the app show an "update available" notice.

## A new version

Change the version number in four places, then build again:

| File | What to change |
|---|---|
| `acars_client/client.py` | `VERSION = "1.0.1"` |
| `acars_client/build/build_acars.bat` | `set "VERSION=1.0.1"` |
| `acars_client/build/installer.iss` | `#define AppVersion "1.0.1"` |
| `acars_client/build/version_info.txt` | `filevers`, `prodvers`, `FileVersion`, `ProductVersion` |

Keep the `AppId` in `installer.iss` the same forever: that's how Windows knows a new
installer upgrades the existing PAC ACARS instead of installing a second copy.

## Where things go on a pilot's PC

| What | Where |
|---|---|
| The program | `%LOCALAPPDATA%\Programs\PAC ACARS` (no administrator rights needed) |
| Settings, in-flight state, log | `%APPDATA%\PAC ACARS` (`config.json`, `flight_state.pkl`, `acars.log`) |

Uninstalling removes the program but keeps the settings, so a reinstall remembers them.

## Windows SmartScreen

A new, unsigned program shows "Windows protected your PC" the first time (More info ›
Run anyway). That goes away with a code-signing certificate, or as more people
download the same file. Worth doing before opening PAC to other pilots.

## Troubleshooting

* The app writes `%APPDATA%\PAC ACARS\acars.log`. Look there first if something doesn't work.
* PAC ACARS shows itself in a Microsoft Edge app window (Chrome if Edge is missing), else the built-in
  window, else the browser. If a window freezes, the log shows `WINDOW NOT RESPONDING` and the reason, and a
  fresh window opens on its own; tracking carries on. Settings › Window can switch to the built-in window.
