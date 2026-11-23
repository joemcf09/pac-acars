"""PAC ACARS window supervision test.

The engine runs the flight; the window is a separate process. This test uses a
stand-in window (tests/fake_window.py) and checks that the engine:
  A. opens the window,
  B. replaces a frozen window while tracking carries on,
  C. keeps tracking when the window is closed mid-flight, and opens a new one on the next launch,
  D. shuts down cleanly when the window is closed with no flight.
Run from the ACARS folder:   python tests/test_acars_window.py
"""
import json, os, signal, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
LOG = Path(tempfile.gettempdir()) / "pac_fake_window.log"
ENV = {**os.environ, "PAC_ACARS_WINDOW_CMD": f"{sys.executable}|{ROOT / 'tests' / 'fake_window.py'}", "PAC_ACARS_FROZEN_S": "6", "PAC_ACARS_CLOSED_S": "3",
       "PAC_FAKE_WINDOW_LOG": str(LOG)}
failures = []


import http.cookiejar  # noqa: E402
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def sign_in_and_key():
    """Fresh test site: set the founder's password, sign in, and give the ACARS app a key (in its config)."""
    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:5050{path}", method="POST", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(OPENER.open(req, timeout=10).read())
    try:
        post("/api/auth/setup", {"password": "test-password-123"})
    except urllib.error.HTTPError:
        post("/api/auth/login", {"pilot_id": "PAC0001", "password": "test-password-123"})
    key = post("/api/auth/token", {"pilot_id": "PAC0001", "password": "test-password-123", "label": "test"})["token"]
    cfg = Path("acars_client/config.json")
    c = json.loads(cfg.read_text()) if cfg.exists() else {}
    c.update(token=key, pilot={"id": "PAC0001", "name": "Test"})
    cfg.write_text(json.dumps(c))


def check(name, cond, detail=""):
    print(f"  {'ok ' if cond else 'FAIL'} {name}{'' if cond else ' · ' + str(detail)}")
    if not cond:
        failures.append(f"{name}: {detail}")


def call(port, m, path, body=None):
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=m, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json"})
    try:
        return json.loads((OPENER.open(r, timeout=8) if port == 5050 else urllib.request.urlopen(r, timeout=8)).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def windows():
    return [int(l.split()[2]) for l in LOG.read_text().splitlines() if "opened" in l] if LOG.exists() else []


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # a finished process waiting to be cleaned up isn't alive (Linux)
        return open(f"/proc/{pid}/status").read().split("State:")[1].split()[0] not in ("Z", "X")
    except Exception:
        return True


def wait_free(port, secs=15):
    """Wait until nothing listens on the port (a previous run may still be shutting down)."""
    import socket
    for _ in range(secs * 4):
        with socket.socket() as sk:
            if sk.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.25)
    return False


def wait(port, path="/", secs=30):
    for _ in range(secs * 2):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1); return True
        except Exception:
            time.sleep(0.5)
    return False


def scenarios(label, env):
    """A to D for one kind of window, using the engine's ping (which doesn't count as a check-in)."""
    print(f"\n=== {label}")
    for f in ("data/logbook.db", "data/booking.json", "data/flight_checkpoint.json", "acars_client/config.json",
              "acars_client/flight_state.pkl", "acars_client/pac-acars.pid"):
        Path(f).unlink(missing_ok=True)
    LOG.unlink(missing_ok=True)
    for port in (5050, 5070):
        if not wait_free(port):
            print(f"Port {port} is still in use. Close the PAC website and PAC ACARS first."); sys.exit(1)
    web = subprocess.Popen([sys.executable, "app.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    eng = None
    ping = lambda: call(5070, "GET", "/api/ping")

    def checked_in(secs=15):
        """Wait for the (new) window to start and check in: a fresh Chromium can take a few seconds to open."""
        t = time.time()
        while time.time() - t < secs:
            p = ping()
            if p.get("window_open") and p.get("ui_age_s") is not None and p["ui_age_s"] < 3:
                return p
            time.sleep(0.5)
        return ping()

    def end_group(pid, sig):
        try:
            os.killpg(pid, sig)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
    try:
        wait(5050)
        sign_in_and_key()
        eng = subprocess.Popen([sys.executable, "acars_client/client.py"], env=env, stdout=open(Path(tempfile.gettempdir()) / f"pac_engine_{label.split()[0].lower()}.log", "w"), stderr=subprocess.STDOUT)
        wait(5070, "/api/ping")
        print("A. start-up")
        p = checked_in()
        check("the engine opened a window that checks in", p["window_open"] and (p["ui_age_s"] is not None and p["ui_age_s"] < 3), p)
        call(5050, "POST", "/api/settings", {"enforce_pilot_location": False})
        call(5050, "POST", "/api/booking", {"mission_id": "PAC1022", "aircraft": "B733F", "airframe": "N010PC"})
        d = call(5050, "GET", "/api/dispatch")             # the captain signs the release before ACARS may start
        call(5050, "POST", "/api/dispatch/sign", {"requested_at": d.get("requested_at"), "revision": d.get("revision"), "reviewed": True, "notoc": True})
        call(5070, "POST", "/api/config", {"demo_speedup": 15})
        check("tracking started", call(5070, "POST", "/api/start", {"source": "Demo"}).get("ok"))
        print("B. the window freezes completely")
        frozen = p["window_pid"]
        end_group(frozen, signal.SIGSTOP)
        t = time.time()
        while ping()["window_restarts"] < 1 and time.time() - t < 45:
            time.sleep(1)
        p = checked_in()
        check("a fresh window replaced the frozen one", p["window_restarts"] == 1 and p["window_pid"] != frozen, p)
        check("the new window checks in", (p["ui_age_s"] is not None and p["ui_age_s"] < 3), p["ui_age_s"])
        check("the frozen window was ended", not alive(frozen))
        check("tracking carried on", p["tracking"])
        print("C. the window is closed mid-flight")
        end_group(p["window_pid"], signal.SIGTERM); time.sleep(5)
        p = ping()
        check("the engine keeps tracking", p["tracking"] and not p["window_open"], p)
        subprocess.run([sys.executable, "acars_client/client.py"], env=env, capture_output=True, timeout=20)
        p = checked_in()
        check("opening PAC ACARS again opens a window on the same flight", p["window_open"] and (p["ui_age_s"] is not None and p["ui_age_s"] < 3) and p["tracking"], p)
        print("D. no flight, window closed")
        call(5070, "POST", "/api/stop", {}); time.sleep(1)
        end_group(ping()["window_pid"], signal.SIGTERM); time.sleep(5)
        check("PAC ACARS shut down cleanly", eng.poll() is not None)
        print("E. reopened straight away")
        log = Path(tempfile.gettempdir()) / f"pac_engine_{label.split()[0].lower()}_reopen.log"
        eng = subprocess.Popen([sys.executable, "acars_client/client.py"], env=env, stdout=open(log, "w"), stderr=subprocess.STDOUT)
        ok = wait(5070, "/api/ping", secs=15)
        check("PAC ACARS starts again at once, with no false 'isn't responding'", ok and "isn't responding" not in log.read_text(),
              log.read_text()[-300:])
    finally:
        for proc in (eng, web):
            if proc and proc.poll() is None:
                proc.kill()
        try:
            p = call(5070, "GET", "/api/ping")
            end_group(p.get("window_pid"), signal.SIGKILL)
        except Exception:
            pass


def main():
    scenarios("Stand-in window", {**ENV})
    browser = os.environ.get("PAC_ACARS_BROWSER")
    if not browser:
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.executable_path
            pw.stop()
        except Exception:
            browser = None
    if browser and os.path.exists(browser):
        env = {k: v for k, v in os.environ.items() if k != "PAC_ACARS_WINDOW_CMD"}
        env.update(PAC_ACARS_BROWSER=browser, PAC_ACARS_FROZEN_S="6", PAC_ACARS_CLOSED_S="3", PAC_ACARS_BROWSER_ARGS="--headless=new --no-sandbox")
        scenarios("Chromium app window (what Edge uses)", env)
    else:
        print("\n(No Chromium found for the app-window scenarios: pip install playwright && playwright install chromium)")
    print("\nACARS WINDOW TEST", "PASSED" if not failures else f"FAILED ({len(failures)})")
    for f in failures:
        print(" -", f)
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()
