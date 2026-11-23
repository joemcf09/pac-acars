"""Runs every PAC test and reports one pass/fail line each. Use it before merging anything:

    python tools/run_tests.py                 # everything
    python tools/run_tests.py --no-ui         # skip the two ACARS app tests that open a real browser window
    python tools/run_tests.py volume flights  # only tests whose name contains one of these words

Two kinds of test live in tests/: plain scripts that print ok/FAIL lines and exit non-zero on failure, and pytest-style
files (top-level `def test_...` functions). Each test gets its own empty data folder (PAC_DATA_DIR), so tests can't see
each other's pilots, bookings or settings, and most run side by side. The ACARS app tests start the real site and
app on fixed ports and use the repository's own data folder, so they run alone, one after another, at the end."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
# start the real website on :5050 and the ACARS app on :5070, drive a real browser window, and use ROOT/data
SERIAL_UI = {"test_acars_app", "test_acars_window"}
TIMEOUT = 600


def is_pytest(path):
    return bool(re.search(r"^def test_\w+\(", path.read_text(encoding="utf-8", errors="replace"), re.M))


def run_one(path):
    name = path.stem
    started = time.time()
    with tempfile.TemporaryDirectory(prefix=f"pac-{name}-") as temp:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        if name not in SERIAL_UI:
            data = Path(temp) / "data"
            data.mkdir()
            shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
            env["PAC_DATA_DIR"] = str(data)
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(path)] if is_pytest(path) else [sys.executable, str(path)]
        try:
            p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT)
            ok, out = p.returncode == 0, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired as e:
            ok, out = False, f"timed out after {TIMEOUT} s\n" + ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
    return name, ok, round(time.time() - started, 1), out


def why(out):
    """The lines that explain a failure: FAIL checks, assertion errors and the last traceback line."""
    lines = [l for l in out.splitlines() if re.search(r"\bFAIL|Error|assert|Traceback|timed out", l)]
    return "\n".join("      " + l.strip()[:220] for l in lines[-8:]) or "      (no output; run the test on its own to see why)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="run only tests whose file name contains one of these words")
    ap.add_argument("--no-ui", action="store_true", help="skip the ACARS app tests that need a real browser")
    ap.add_argument("-j", type=int, default=max(2, min(8, os.cpu_count() or 2)), help="tests to run side by side")
    a = ap.parse_args()
    tests = sorted(TESTS.glob("test_*.py"))
    if a.only:
        tests = [t for t in tests if any(w in t.stem for w in a.only)]
    serial = [t for t in tests if t.stem in SERIAL_UI and not a.no_ui]
    parallel = [t for t in tests if t.stem not in SERIAL_UI]
    print(f"Running {len(parallel) + len(serial)} test files ({a.j} at a time, then {len(serial)} on their own)\n", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=a.j) as ex:
        for name, ok, secs, out in ex.map(run_one, parallel):
            results.append((name, ok, secs, out))
            print(f"  {'ok  ' if ok else 'FAIL'} {name} ({secs} s)" + ("" if ok else "\n" + why(out)), flush=True)
    for t in serial:
        name, ok, secs, out = run_one(t)
        results.append((name, ok, secs, out))
        print(f"  {'ok  ' if ok else 'FAIL'} {name} ({secs} s)" + ("" if ok else "\n" + why(out)), flush=True)
    failed = [r[0] for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} of {len(results)} test files passed." + (f" Failed: {', '.join(failed)}" if failed else " All green."))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
