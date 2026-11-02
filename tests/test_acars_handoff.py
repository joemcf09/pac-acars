"""PAC ACARS window hand-off test (the 1.0.3 "Failed to fetch" bug).

Edge often hands a new app window to a copy of Edge that is already running, and the msedge.exe PAC ACARS started
exits at once. 1.0.3 took that as "the pilot closed the window" and shut its engine down while the window stayed on
screen, so the next button pressed gave "Failed to fetch". It also left that window behind, so the next start-up
handed off to it again, every time. This test checks that PAC ACARS:
  F. keeps running when the window's launcher exits at once, follows the window by its check-ins,
     and still stops once that window is really closed;
  G. finds a window left open from before and uses it instead of opening a second one;
  H. does the same with a real Chromium that hands the window to a copy already running (what Edge does).
Run from the ACARS folder:   python tests/test_acars_handoff.py
"""
import json, os, shutil, signal, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "acars_client"))
import winctl  # noqa: E402
os.chdir(ROOT)
LOG = Path(tempfile.gettempdir()) / "pac_fake_window_handoff.log"
BASE = {**os.environ, "PAC_ACARS_FROZEN_S": "6", "PAC_ACARS_CLOSED_S": "3", "PAC_FAKE_WINDOW_LOG": str(LOG)}
failures = []


def check(name, cond, detail=""):
    print(f"  {'ok ' if cond else 'FAIL'} {name}{'' if cond else ' · ' + str(detail)}")
    if not cond:
        failures.append(f"{name}: {detail}")


def ping():
    try:
        return json.loads(urllib.request.urlopen("http://127.0.0.1:5070/api/ping", timeout=3).read())
    except Exception:
        return {}


def windows():
    return [int(line.split()[2]) for line in LOG.read_text().splitlines() if "opened" in line] if LOG.exists() else []


def kill(pid, sig=signal.SIGTERM):
    for f in (os.killpg, os.kill):
        try:
            f(pid, sig)
            return
        except OSError:
            pass


def wait_free(secs=20):
    import socket
    for _ in range(secs * 4):
        with socket.socket() as sk:
            if sk.connect_ex(("127.0.0.1", 5070)) != 0:
                return True
        time.sleep(0.25)
    return False


def wait_until(cond, secs):
    t = time.time()
    while time.time() - t < secs:
        if cond():
            return True
        time.sleep(0.5)
    return cond()


def engine(env, name):
    Path("acars_client/pac-acars.pid").unlink(missing_ok=True)
    log = Path(tempfile.gettempdir()) / f"pac_engine_{name}.log"
    return subprocess.Popen([sys.executable, "acars_client/client.py"], env=env, stdout=open(log, "w"), stderr=subprocess.STDOUT), log


def scenario_f():
    print("\nF. the window's launcher exits at once (Edge hands the window on)")
    LOG.unlink(missing_ok=True)
    wait_free()
    env = {**BASE, "PAC_ACARS_WINDOW_CMD": f"{sys.executable}|{ROOT / 'tests' / 'fake_handoff.py'}"}
    eng, log = engine(env, "handoff")
    try:
        time.sleep(15)  # 1.0.3 shut down about 5 s in
        p = ping()
        check("PAC ACARS is still running 15 s later", eng.poll() is None and p.get("app") == "PAC ACARS", log.read_text()[-400:])
        check("it follows the handed-on window", p.get("window_open") and p.get("window_detached"), p)
        check("the window checks in", p.get("ui_age_s") is not None and p["ui_age_s"] < 3, p)
        check("no fresh windows were opened", p.get("window_restarts") == 0 and len(windows()) == 1, (p, windows()))
        check("the log explains the hand-off", "handed to another" in log.read_text(), log.read_text()[-400:])
        kill(windows()[-1])
        check("closing that window stops PAC ACARS (no flight)", wait_until(lambda: eng.poll() is not None, 12), log.read_text()[-300:])
    finally:
        if eng.poll() is None:
            eng.kill()
        for pid in windows():
            kill(pid, signal.SIGKILL)


def scenario_g():
    print("\nG. a window left open from before")
    LOG.unlink(missing_ok=True)
    wait_free()
    env = {**BASE, "PAC_ACARS_WINDOW_CMD": f"{sys.executable}|{ROOT / 'tests' / 'fake_window.py'}"}
    orphan = subprocess.Popen([sys.executable, "tests/fake_window.py", "http://127.0.0.1:5070/"], env=env, start_new_session=True)
    time.sleep(1)
    eng, log = engine(env, "adopt")
    try:
        time.sleep(8)
        p = ping()
        check("PAC ACARS uses the window that was already open", windows() == [orphan.pid] and p.get("window_detached"), (windows(), p))
        check("and says so in the log", "still open from before" in log.read_text(), log.read_text()[-400:])
        check("it is still running", eng.poll() is None)
        orphan.terminate()
        check("closing it stops PAC ACARS (no flight)", wait_until(lambda: eng.poll() is not None, 12), log.read_text()[-300:])
    finally:
        for proc in (eng, orphan):
            if proc.poll() is None:
                proc.kill()


def find_chromium():
    b = os.environ.get("PAC_ACARS_BROWSER")
    if b:
        return b
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        b = pw.chromium.executable_path
        pw.stop()
        return b if os.path.exists(b) else None
    except Exception:
        return None


def scenario_h(browser):
    print("\nH. a real Chromium still running on PAC ACARS's window profile (Edge lingering in the background)")
    wait_free()
    profile = ROOT / "acars_client" / "window-profile"
    shutil.rmtree(profile, ignore_errors=True)
    flags = ["--headless=new", "--no-sandbox"]
    lingering = subprocess.Popen([browser, f"--user-data-dir={profile}", "--no-first-run"] + flags + ["about:blank"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(4)
    env = {k: v for k, v in BASE.items() if k != "PAC_ACARS_WINDOW_CMD"}
    env.update(PAC_ACARS_BROWSER=browser, PAC_ACARS_BROWSER_ARGS=" ".join(flags))
    eng, log = engine(env, "chromium_lingering")
    try:
        time.sleep(12)
        text = log.read_text()
        p = ping()
        check("the lingering copy was closed first", "leftover Edge/Chrome" in text and lingering.poll() is not None, text[-400:])
        check("the window opened in its own process, not handed on", "handed to another" not in text and not p.get("window_detached"), p)
        check("the window checks in", p.get("ui_age_s") is not None and p["ui_age_s"] < 3, p)
        check("PAC ACARS is still running", eng.poll() is None)
        kill(p.get("window_pid") or 0)
        check("closing the window stops PAC ACARS (no flight)", wait_until(lambda: eng.poll() is not None, 15), log.read_text()[-300:])
    finally:
        if eng.poll() is None:
            eng.kill()
        if lingering.poll() is None:
            kill(lingering.pid, signal.SIGKILL)
        for pid in winctl.pids_with_arg(f"--user-data-dir={profile}", os.path.basename(browser)):
            kill(pid, signal.SIGKILL)
        shutil.rmtree(profile, ignore_errors=True)


def clear_strays():
    """Windows left behind by an earlier interrupted run would be (correctly) adopted and spoil the checks."""
    browser = find_chromium()
    strays = winctl.pids_with_arg("tests/fake_window.py", os.path.basename(sys.executable))
    if browser:
        strays += winctl.pids_with_arg("--user-data-dir=" + str(ROOT / "acars_client" / "window-profile"), os.path.basename(browser))
    for pid in strays:
        kill(pid, signal.SIGKILL)
    time.sleep(1)


def main():
    clear_strays()
    scenario_f()
    scenario_g()
    browser = find_chromium()
    if browser:
        scenario_h(browser)
    else:
        print("\n(No Chromium found for scenario H: pip install playwright && playwright install chromium)")
    print("\nACARS HAND-OFF TEST", "PASSED" if not failures else f"FAILED ({len(failures)})")
    for f in failures:
        print(" -", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
