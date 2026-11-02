"""PAC ACARS app stress test.

Runs the PAC website and the ACARS app, flies a demo flight, and presses every
button and feature in the app's window (in a real browser) while the weather
service is deliberately slow and failing. Fails if any action takes longer than
1.5 s to answer, if the window stops updating for more than 2.5 s, or if a
dispatch message doesn't get its reply.

Needs Playwright:  pip install playwright && playwright install chromium
Run from the ACARS folder:   python tests/test_acars_app.py
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
failures = []


def check(name, cond, detail=""):
    print(f"  {'ok ' if cond else 'FAIL'} {name}{'' if cond else ' · ' + str(detail)}")
    if not cond:
        failures.append(f"{name}: {detail}")


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


def call(port, method, path, body=None, timeout=10):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        with (OPENER.open(req, timeout=timeout) if port == 5050 else urllib.request.urlopen(req, timeout=timeout)) as r:
            return r.status, json.loads(r.read() or b"{}"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), time.time() - t


# the ACARS app with a weather service that takes 12 s and then fails
SLOW_APP = r'''
import sys, time
sys.path.insert(0, "acars_client"); sys.path.insert(0, ".")
import weather
def slow_metars(ids, *a, **k):
    time.sleep(12)
    raise weather.WeatherError("weather service timed out (test)")
weather.metars = slow_metars
import client
client.main()
'''


def wait_free(port, secs=15):
    """Wait until nothing listens on the port (a previous run may still be shutting down)."""
    import socket
    for _ in range(secs * 4):
        with socket.socket() as sk:
            if sk.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.25)
    return False


def wait_port(port, path="/"):
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


async def ui_test():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 470, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        # time every request the window makes, and every successful status update
        await pg.add_init_script("""
          window.__calls = []; window.__polls = [];
          const f = window.fetch;
          window.fetch = async (u, o) => { const t = performance.now(); try { const r = await f(u, o);
            const d = performance.now() - t; window.__calls.push([String(u), (o && o.method) || "GET", d, r.status]);
            if (String(u).includes('/api/state') && r.ok) window.__polls.push(Date.now()); return r; }
            catch (e) { window.__calls.push([String(u), (o && o.method) || "GET", performance.now() - t, 0]); throw e; } };
        """)
        await pg.goto("http://127.0.0.1:5070/")
        await pg.wait_for_timeout(2000)

        print("\nStarting a demo flight from the window")
        await pg.select_option("#source", "Demo")
        await pg.click("#startBtn")
        await pg.wait_for_timeout(3000)
        check("tracking started", await pg.evaluate("S.status && S.status.tracking === true"))

        print("\nEvery control, while the weather service is slow")
        await pg.click("#wxBtn")                       # the weather service takes 12 s: the button must answer at once
        await pg.wait_for_timeout(300)
        for tab, fill in (("delay", {"#f1": "20"}), ("divert", {"#f1": "KGSO"}), ("fuel", {}), ("eta", {}),
                          ("fault", {"#f2": "APU slow to start"}), ("text", {"#f1": "Request stand"})):
            await pg.click(f"[data-mt='{tab}']")
            for sel, val in fill.items():
                await pg.fill(sel, val)
            await pg.click("#mform button[type=submit]")
            await pg.wait_for_timeout(400)
        await pg.click("#wxBtn")                       # pressed again while the first request is still out
        await pg.click("#msgLight")                    # acknowledge messages
        await pg.click("#compactBtn")                  # compact strip and back
        await pg.wait_for_timeout(1500)
        check("compact mode on", await pg.evaluate("document.body.classList.contains('compact')"))
        await pg.click("#sExpand")
        await pg.wait_for_timeout(1500)
        check("compact mode off", await pg.evaluate("!document.body.classList.contains('compact')"))
        await pg.click("details.card summary")         # Settings
        await pg.click("#testChime")
        await pg.click("#cfgSave")
        await pg.evaluate("document.querySelector('#ofpCard details summary')?.click()")  # Route, if there's an OFP
        ofp = await pg.query_selector("#ofpBtn")
        if ofp:                                        # the OFP can only change before pushback: disabled once under way
            phase = await pg.evaluate("S.status.phase")
            enabled = await ofp.is_enabled()
            check("Refresh OFP disabled once the flight is under way", enabled == (phase == "PREFLIGHT"), (phase, enabled))
            if enabled:
                await ofp.click()                      # SimBrief isn't configured here: it must fail cleanly and quickly

        print("\nRapid-fire presses: 20 at once")
        t = time.time()
        res = await pg.evaluate("""Promise.all(Array.from({length: 20}, (_, i) => fetch('/api/message', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify({type: i % 2 ? 'eta' : 'fuel'})}).then(r => r.status)))""")
        check("20 simultaneous messages all answered", all(r == 200 for r in res), res)
        check("…within 3 s in total", time.time() - t < 3, f"{time.time() - t:.1f} s")

        print("\nWaiting 16 s for replies and the slow weather to come back")
        await pg.wait_for_timeout(16000)
        log = await pg.evaluate("S.status.messages.map(m => m.text)")
        for word in ("DELAY 20 MIN", "DIVERSION TO KGSO", "FOB", "ETA", "MX CONTROL", "STAND"):  # fuel reply: FOB (no OFP loaded here)
            check(f"reply in the log: {word}", any(word in m for m in log if m.startswith("PAC OCC")), [m for m in log[-8:]])
        check("slow weather reported in the log, not hanging", any("WX" in m and ("FAILED" in m or "NOT AVAILABLE" in m) for m in log), log[-6:])

        calls = await pg.evaluate("window.__calls")
        polls = await pg.evaluate("window.__polls")
        slow = [c for c in calls if c[1] == "POST" and c[2] > 1500]
        check("every action answered within 1.5 s", not slow, [(c[0].split('/api/')[-1], round(c[2])) for c in slow])
        gaps = [b_ - a for a, b_ in zip(polls, polls[1:])]
        check("the window kept updating (longest gap under 2.5 s)", gaps and max(gaps) < 2500, f"longest gap {max(gaps) if gaps else None} ms")
        check("no script errors in the window", not errs, errs)
        await b.close()


def main():
    for f in ("data/logbook.db", "data/booking.json", "data/flight_state.pkl", "data/flight_checkpoint.json",
              "acars_client/config.json", "acars_client/flight_state.pkl", "acars_client/pac-acars.pid"):
        Path(f).unlink(missing_ok=True)
    for port in (5050, 5070):
        if not wait_free(port):
            print(f"Port {port} is still in use. Close the PAC website and PAC ACARS first."); sys.exit(1)
    web = subprocess.Popen([sys.executable, "app.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app = None
    try:
        if not wait_port(5050):
            print("The website didn't start."); sys.exit(1)
        sign_in_and_key()
        call(5050, "POST", "/api/settings", {"enforce_pilot_location": False})
        code, bk, _ = call(5050, "POST", "/api/booking", {"mission_id": "PAC1022", "aircraft": "B733F", "airframe": "N010PC"})
        check("flight booked", code == 200, bk)
        import socket
        with socket.socket() as sk:
            if sk.connect_ex(("127.0.0.1", 5070)) == 0:
                print("Port 5070 is in use: close any running PAC ACARS first."); sys.exit(1)
        app = subprocess.Popen([sys.executable, "-c", SLOW_APP, "--no-browser"], stdout=open("/tmp/acars_app_test.log", "w"), stderr=subprocess.STDOUT)
        if not wait_port(5070, "/api/ping"):
            print("The ACARS app didn't start."); sys.exit(1)
        call(5070, "POST", "/api/config", {"demo_speedup": 20, "source": "Demo"})
        asyncio.run(ui_test())
    finally:
        for proc in (app, web):
            if proc:
                proc.kill()
    print("\nACARS APP TEST", "PASSED" if not failures else f"FAILED ({len(failures)})")
    for f in failures:
        print(" -", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
