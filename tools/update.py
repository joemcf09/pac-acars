"""Safely updates PAC from a new package (the pac-acars.zip you download).

    update.bat  path\\to\\pac-acars.zip        (or drag the zip onto update.bat)

1. Checks the PAC website isn't running.
2. Backs up your data to data/backups/<time>-before-update/.
3. Copies in the new program files. Your data is never touched: the logbook, settings, profile and photo,
   home-page text, fleet edits and photos, gallery, backups, sign-in key, the PAC ACARS app's settings,
   and your own PAC ACARS builds.
4. Installs any new Python packages.
"""
import filecmp
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# never replaced or removed by an update
PROTECTED_FILES = {"data/logbook.db", "data/settings.json", "data/profile.json", "data/site.json", "data/fleet_custom.json",
                   "data/booking.json", "data/secret_key", "data/stand_positions.json", "data/flight_checkpoint.json", "data/flight_state.pkl",
                   "acars_client/config.json", "acars_client/flight_state.pkl", "acars_client/acars.log", "acars_client/chime.wav",
                   "acars_client/pac-acars.pid"}
PROTECTED_DIRS = ("data/backups/", "data/gallery/", "data/fleet_photos/", "data/downloads/", "data/flights/", "data/acars-builds/", ".venv/", "acars_client/build/dist/",
                  "acars_client/build/work/", "acars_client/build/Output/", "acars_client/window-profile/")
PROTECTED_PATTERNS = ("data/pilot_photo.", "static/downloads/PAC-ACARS-")


def protected(rel):
    return rel in PROTECTED_FILES or rel.startswith(PROTECTED_DIRS) or rel.startswith(PROTECTED_PATTERNS) or "__pycache__" in rel


def website_running():
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", 5050)) == 0


def backup():
    dest = DATA / "backups" / (time.strftime("%Y%m%d-%H%M%S") + "-before-update")
    dest.mkdir(parents=True, exist_ok=True)
    if (DATA / "logbook.db").exists():
        src, dst = sqlite3.connect(DATA / "logbook.db"), sqlite3.connect(dest / "logbook.db")
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    for f in ("settings.json", "profile.json", "site.json", "fleet_custom.json", "booking.json", "secret_key"):
        if (DATA / f).exists():
            shutil.copy2(DATA / f, dest / f)
    for f in DATA.glob("pilot_photo.*"):
        shutil.copy2(f, dest / f.name)
    if (DATA / "fleet_photos").exists():
        shutil.copytree(DATA / "fleet_photos", dest / "fleet_photos", dirs_exist_ok=True)
    return dest


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    package = Path(sys.argv[1].strip('"'))
    if not package.exists() or package.suffix.lower() != ".zip":
        print(f"Can't find the update package: {package}")
        return 1
    if website_running():
        print("The PAC website is running. Close its window (or press Ctrl+C in it), then run the update again.")
        return 1
    print(f"Updating PAC from {package.name}")
    dest = backup()
    print(f"  1. Your data is backed up in {dest.relative_to(ROOT)}")
    tmp = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(package) as z:
            z.extractall(tmp)
        roots = [p.parent for p in tmp.rglob("app.py") if (p.parent / "acars_client").exists()]
        if not roots:
            print("That zip doesn't look like a PAC package (no app.py found). Nothing was changed.")
            return 1
        new = roots[0]
        old_reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8") if (ROOT / "requirements.txt").exists() else ""
        changed = added = kept = 0
        for f in new.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(new).as_posix()
            if protected(rel):
                kept += 1
                continue
            target = ROOT / rel
            if target.exists() and filecmp.cmp(f, target, shallow=False):
                continue
            existed = target.exists()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            changed += existed
            added += not existed
        print(f"  2. Program files: {changed} updated, {added} new. Your data wasn't touched.")
        new_reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8") if (ROOT / "requirements.txt").exists() else ""
        venv_py = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if new_reqs != old_reqs and venv_py.exists():
            print("  3. Installing new Python packages…")
            subprocess.run([str(venv_py), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=False)
        else:
            print("  3. No new Python packages needed.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nDone. Start the website again with start.bat. If you use the installed PAC ACARS, rebuild it with "
          "acars_client\\build\\build_acars.bat when the update notes say PAC ACARS changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
