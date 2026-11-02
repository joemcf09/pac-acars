"""Stands in for the PAC ACARS window process in tests: asks the engine for updates every second, like the real window, and logs the commands it receives."""
import sys, time, json, urllib.request, os
url = sys.argv[-1] if sys.argv[-1].startswith("http") else sys.argv[-2]
log = open(os.environ.get("PAC_FAKE_WINDOW_LOG", "fake_window.log"), "a")
log.write(f"{time.strftime('%H:%M:%S')} window {os.getpid()} opened\n"); log.flush()
last = None
while True:
    try:
        s = json.loads(urllib.request.urlopen(url + "api/state", timeout=5).read())
        c = s.get("win_cmd")
        if c and c.get("id") != last:
            last = c["id"]; log.write(f"{time.strftime('%H:%M:%S')} window {os.getpid()} command: {c}\n"); log.flush()
    except Exception:
        pass
    time.sleep(1)
