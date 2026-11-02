"""Deploys the local PAC folder to the live server. One command, start to finish.

    deploy.bat                      everything: check, package, upload, restart, verify
    deploy.bat --dry-run            build the package and stop, so you can see what would go up
    deploy.bat --host pac-va.com --user root

What it does, in order, stopping at the first failure:

1. Compiles every .py so a typo can't take the site down on restart.
2. Packages the program files only — no .venv, no data/, no builds, no bytecode.
   The server rebuilds the virtual environment itself from requirements.txt.
3. Uploads the package and runs deploy/update.sh on the server, which backs up
   your data first, stops PAC, rsyncs the program files, reinstalls packages and
   starts PAC and the Discord bot again.
4. Checks both services came back up, and tidies the uploaded zip away.

Your data is never in the package and never touched: logbook, roster, settings,
profile, gallery, backups and the PAC ACARS builds all live on the server.
"""
import argparse
import compileall
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What the package leaves out. This list must stay a SUBSET of update.sh's own rsync
# excludes, because that rsync runs with --delete: anything missing from the package
# that update.sh doesn't also exclude would be DELETED from the server.
#
# update.sh excludes:  data/  .venv/  acars_client/config.json  static/downloads/
#                      acars_client/build/  __pycache__/
#
# acars_client/build/ is 107 MB of PyInstaller output for the Windows app. The
# server never reads it — only your PC builds PAC ACARS — so it stays home. Your
# local copy is untouched; this script only ever reads.
SKIP_DIRS = {".venv", "data", "__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_REL = ("static/downloads/", "acars_client/config.json", "acars_client/build/")

MAX_MB = 60                              # a sane package is a few MB; refuse a silly one


def step(n, text):
    print(f"\n[{n}] {text}", flush=True)


def fail(text):
    print(f"\n  FAILED: {text}\n", flush=True)
    sys.exit(1)


def wanted(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts[:-1]):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return not rel.startswith(SKIP_REL)


def compile_check():
    ok = compileall.compile_dir(
        str(ROOT), quiet=1, force=True,
        rx=re.compile(r"[\\/](\.venv|__pycache__|\.git|build|dist)[\\/]"))
    if not ok:
        fail("a Python file has a syntax error (above). Nothing was uploaded.")
    print("  every .py compiles")


def package(zip_path: Path) -> int:
    files = [p for p in ROOT.rglob("*") if p.is_file() and wanted(p)]
    if not any(p.name == "app.py" for p in files):
        fail(f"app.py isn't in {ROOT} — is deploy.bat in the PAC folder?")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            # update.sh looks for a single top-level pac-acars/ folder in the zip
            z.write(p, Path("pac-acars") / p.relative_to(ROOT))
    mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  {len(files)} files, {mb:.1f} MB")
    if mb > MAX_MB:
        fail(f"the package is {mb:.0f} MB, over the {MAX_MB} MB guard. Something that should be "
             f"excluded got in — check for a new folder of builds or media.")
    return len(files)


def run(cmd, what):
    print("  " + " ".join(cmd[:2]) + " …", flush=True)
    if subprocess.run(cmd).returncode != 0:
        fail(f"{what}. Nothing further was run.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="pac-va.com")
    ap.add_argument("--user", default="root")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    target = f"{a.user}@{a.host}"

    step(1, "Checking every Python file compiles")
    compile_check()

    step(2, "Packaging the program files")
    tmp = Path(tempfile.gettempdir()) / "pac-acars-deploy.zip"
    package(tmp)

    if a.dry_run:
        print(f"\nDry run. The package is at {tmp} — nothing was uploaded.\n")
        return

    step(3, f"Uploading to {target}")
    run(["scp", str(tmp), f"{target}:/home/pac/pac-acars.zip"], "the upload failed")

    step(4, "Updating the server (it backs up your data first)")
    run(["ssh", target,
         "chmod +x /home/pac/pac-acars/deploy/*.sh && "
         "/home/pac/pac-acars/deploy/update.sh /home/pac/pac-acars.zip && "
         "chown -R pac:pac /home/pac/pac-acars && "
         "rm -f /home/pac/pac-acars.zip"],
        "the server update failed. Your data is safe and a backup was taken before any change. "
        "See what happened with:  ssh " + target + " \"journalctl -u pac -n 50\"")

    step(5, "Checking PAC is back up")
    run(["ssh", target, "systemctl is-active pac pac-discord"], "a service did not come back up")

    print("\nDone. PAC is updated and running.\n")


if __name__ == "__main__":
    main()
