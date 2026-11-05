# PyInstaller recipe for PAC ACARS.exe
# Built by build_acars.bat; run from this folder:  pyinstaller --noconfirm pac_acars.spec
import os
import sys
from PyInstaller.utils.hooks import collect_all

HERE = os.path.abspath(SPECPATH)
CLIENT = os.path.dirname(HERE)
ROOT = os.path.dirname(CLIENT)

datas = [
    (os.path.join(CLIENT, "ui.html"), "."),
    (os.path.join(CLIENT, "CHANGELOG.txt"), "."),   # shown once after an update ("What's new")
    (os.path.join(CLIENT, "assets"), "assets"),
    (os.path.join(ROOT, "data", "airports.json"), "data"),
]
binaries, hiddenimports = [], ["acars_core", "tracker", "sim_sources", "weather", "online", "winctl", "stations", "site_url"]
for pkg in ("SimConnect", "webview", "pystray"):  # MSFS connection (with its SimConnect.dll), the native window, the tray icon
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f"note: {pkg} not bundled ({e})")

a = Analysis(
    [os.path.join(CLIENT, "client.py")],
    pathex=[ROOT, CLIENT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "numpy.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PAC ACARS",
    icon=os.path.join(CLIENT, "assets", "pac-acars.ico"),
    version=os.path.join(HERE, "version_info.txt") if sys.platform == "win32" else None,
    console=False,          # no black console window
    upx=False,              # UPX-packed files trip antivirus scanners
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PAC ACARS")
