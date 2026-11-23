"""Deploys the local PAC folder to the live server. One command, start to finish.

    deploy.bat                      everything: check, package, upload, restart, verify
    deploy.bat --dry-run            build the package and stop, so you can see what would go up
    deploy.bat --host pac-va.com --user root
    deploy.bat --staging            the same, to the test copy at staging.pac-va.com (the live site isn't touched;
                                    the first time, it sets the test copy up and asks for its login password)

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
import getpass
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What the package carries and leaves out. update.sh unpacks this into a fresh
# releases/<stamp>/ directory (it never deletes or overwrites the running code),
# so there is no --delete to keep in sync. The package carries the program files
# plus PAC's reference data (routes, airports, fleet, missions, partners,
# runways), because each release serves its own reference data; pilot data is
# never packaged and lives on the server under shared/data.
#
# acars_client/build/ is 107 MB of PyInstaller output for the Windows app. The
# server never reads it — only your PC builds PAC ACARS — so it stays home. Your
# local copy is untouched; this script only ever reads.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "releases", "shared"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
# acars_client/window-profile/ is the Edge profile the desktop client creates when it runs from source (900+ MB of
# cache); flight_state.pkl, acars.log and the pid file are that client's local state. None of it belongs on the server.
SKIP_REL = ("static/downloads/", "acars_client/config.json", "acars_client/build/", "acars_client/window-profile/",
            "acars_client/flight_state.pkl", "acars_client/acars.log", "acars_client/pac-acars.pid")
# the only files under data/ that ship with the code (PAC's public reference data)
DATA_REFERENCE = {"airports.json", "conflict_zones_shapes.json", "fleet.json",
                  "missions.json", "partners.json", "routes.json", "runways.json"}

MAX_MB = 60                              # a sane package is a few MB; refuse a silly one

PAC_DIR = "/home/pac/pac-acars"
ZIP_REMOTE = "/home/pac/pac-acars.zip"
STAGING_DIR = "/home/pac/pac-staging"
STAGING_ZIP = "/home/pac/pac-staging.zip"


def remote_update_script(update_sh=f"{PAC_DIR}/current/deploy/update.sh",
                         zip_remote=ZIP_REMOTE, pac_dir=PAC_DIR):
    """The command run over SSH. The update's exit status is captured and is what
    the whole command returns: the cleanup (chown, rm) runs afterward but can
    never change the result, so a failed update can't be masked as success."""
    return (
        # strip any Windows line endings from the live scripts first, so a release built with them can still deploy
        f"set -u; sed -i 's/\\r$//' {pac_dir}/current/deploy/*.sh || exit 1; chmod +x {pac_dir}/current/deploy/*.sh || exit 1; "
        # The updater belongs to the release already on the server. Pass the
        # restart explicitly so the first deploy of this fix also moves the bot
        # off its old release before that directory can be pruned.
        f"PAC_SVC_DISCORD_RESTART='sudo systemctl try-restart pac-discord' {update_sh} {zip_remote}; rc=$?; "
        # cleanup is best-effort and must not affect rc
        f"chown -R pac:pac {pac_dir}/releases {pac_dir}/shared {pac_dir}/current {pac_dir}/previous 2>/dev/null || true; "
        f"rm -f {zip_remote} || true; "
        f"exit $rc"
    )


def remote_staging_script(first_time):
    """The test copy's command. The first time, the setup script comes from the uploaded zip itself (there's no
    release on the server yet) and reads the login name and password from standard input. After that, the test
    copy's own update_staging.sh runs the normal update pointed at /home/pac/pac-staging and the pac-staging service."""
    if first_time:
        run_it = (f"T=$(mktemp -d) && unzip -q {STAGING_ZIP} 'pac-acars/deploy/*' -d $T && sed -i 's/\\r$//' $T/pac-acars/deploy/*.sh "
                  f"&& chmod +x $T/pac-acars/deploy/*.sh && $T/pac-acars/deploy/setup_staging.sh {STAGING_ZIP}; rc=$?; rm -rf $T; ")
    else:
        run_it = (f"sed -i 's/\\r$//' {STAGING_DIR}/current/deploy/*.sh || exit 1; chmod +x {STAGING_DIR}/current/deploy/*.sh || exit 1; "
                  f"{STAGING_DIR}/current/deploy/update_staging.sh {STAGING_ZIP}; rc=$?; ")
    return ("set -u; " + run_it
            + f"chown -R pac:pac {STAGING_DIR} 2>/dev/null || true; rm -f {STAGING_ZIP} || true; exit $rc")


def ask_staging_login():
    print("\n  First time: setting up the test copy at staging.pac-va.com.")
    print("  Choose the login for it (your browser asks for this before showing the test site).")
    name = input("  Login name [pac]: ").strip() or "pac"
    while True:
        pw = getpass.getpass("  Password (hidden as you type): ")
        if len(pw) < 10:
            print("  Use at least 10 characters.")
            continue
        if getpass.getpass("  Same password again: ") == pw:
            return name, pw
        print("  Those didn't match, try again.")


def step(n, text):
    print(f"\n[{n}] {text}", flush=True)


def fail(text):
    print(f"\n  FAILED: {text}\n", flush=True)
    sys.exit(1)


def wanted(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    parts = path.relative_to(ROOT).parts
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    # under data/: ship only PAC's reference data, never pilot data
    if parts[0] == "data":
        return path.name in DATA_REFERENCE
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
            arc = Path("pac-acars") / p.relative_to(ROOT)
            if p.suffix == ".sh":
                # Windows checkouts turn line endings into CRLF, and Linux then can't run the script
                # ("bash\r: No such file or directory"). Always ship shell scripts with LF endings.
                z.writestr(str(arc).replace("\\", "/"), p.read_bytes().replace(b"\r\n", b"\n"))
            else:
                z.write(p, arc)
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
    ap.add_argument("--staging", action="store_true", help="deploy to the test copy (staging.pac-va.com) instead of the live site")
    a = ap.parse_args()
    target = f"{a.user}@{a.host}"
    if a.staging and not a.dry_run:
        return deploy_staging(target)

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

    step(4, "Updating the server (versioned release, auto-rollback on failure)")
    # The live release's update.sh unpacks the new code into a fresh releases/<stamp>/,
    # builds its venv, flips the 'current' symlink, health-checks /up, and rolls back
    # automatically if the new release does not come up. It exits non-zero on failure;
    # remote_update_script() preserves that exit code past the cleanup, so a failed
    # deploy is reported here and the previous version stays live.
    run(["ssh", target, remote_update_script()],
        "the server update failed and was rolled back to the previous version. Your data is "
        "untouched and a backup was taken first. See:  ssh " + target + " \"journalctl -u pac -n 50\"")

    step(5, "Confirming PAC is healthy")
    run(["ssh", target, "systemctl is-active pac pac-discord"], "a service did not come back up")

    print("\nDone. PAC is updated and running.\n")


def deploy_staging(target):
    print("Deploying to the TEST COPY (staging.pac-va.com). The live site is not touched.")
    step(1, "Checking every Python file compiles")
    compile_check()
    step(2, "Packaging the program files")
    tmp = Path(tempfile.gettempdir()) / "pac-staging-deploy.zip"
    package(tmp)
    probe = subprocess.run(["ssh", target, f"test -e {STAGING_DIR}/current && echo ready || echo new"], capture_output=True, text=True)
    if probe.returncode != 0:
        fail("couldn't reach the server over SSH: " + (probe.stderr or "").strip())
    first_time = probe.stdout.strip() != "ready"
    login = ask_staging_login() if first_time else None
    step(3, f"Uploading to {target}")
    run(["scp", str(tmp), f"{target}:{STAGING_ZIP}"], "the upload failed")
    step(4, "Setting up the test copy" if first_time else "Updating the test copy (versioned release, auto-rollback on failure)")
    print("  ssh …", flush=True)
    # bytes, not text: on Windows, text mode would turn each \n into \r\n and the server would read "name\r"
    stdin = f"{login[0]}\n{login[1]}\n".encode() if login else b""
    if subprocess.run(["ssh", target, remote_staging_script(first_time)], input=stdin).returncode != 0:
        fail("the test copy didn't update (see above). The live site was not touched. Logs:  ssh " + target + " \"journalctl -u pac-staging -n 50\"")
    step(5, "Confirming the test copy is healthy")
    run(["ssh", target, "systemctl is-active pac-staging"], "the test copy did not come up")
    print("\nDone. The test copy is updated: https://staging.pac-va.com\n")


if __name__ == "__main__":
    main()
