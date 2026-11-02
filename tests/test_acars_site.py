"""PAC ACARS never leaves a pilot stuck on a website address that isn't running (such as 127.0.0.1:5050)."""
import os
import sys
import threading
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "acars_client"))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

# The "real" PAC website for this test runs at 127.0.0.2:5051 and is treated as public.
OFFICIAL = "http://127.0.0.2:5051"
os.environ["PAC_SITE"] = OFFICIAL
CFG = ROOT / "acars_client" / "config.json"
saved_cfg = CFG.read_bytes() if CFG.exists() else None

import app as A  # noqa: E402
import client as C  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

_real_local = C.is_local_site
C.is_local_site = lambda url: _real_local(url) and "127.0.0.2" not in str(url)

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


srv = make_server("127.0.0.2", 5051, A.app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try:
    check("the default is the airline's website", C.DEFAULTS["server"] == OFFICIAL)
    check("127.0.0.1 counts as local", _real_local("http://127.0.0.1:5050") and _real_local("localhost:5050"))
    check("pac-va.com is not local", not _real_local("https://pac-va.com"))
    check("172.217.x (public) is not local", not _real_local("http://172.217.1.1"))

    # an old copy: pointed at a test site on this PC that isn't running, with that site's sign-in key
    CFG.write_text('{"server": "http://127.0.0.1:5999", "token": "pac_old", "pilot": {"id": "PAC0001", "name": "Test"}, "source": "Demo"}')
    C.state.update(site_notice=None, thread=None)
    C.refresh_hello()
    cfg = C.load_config()
    check("switched to the airline's website", C.server_url() == OFFICIAL, C.server_url())
    check("the website answered", C.state["server_ok"], C.state.get("server_error"))
    check("the old sign-in key is dropped", "token" not in cfg and "pilot" not in cfg, cfg)
    check("asks the pilot to sign in", C.state.get("auth_needed"))
    check("tells the pilot what happened", "127.0.0.1:5999" in (C.state.get("site_notice") or ""), C.state.get("site_notice"))
    check("other settings are kept", cfg.get("source") == "Demo")
    check("the default address isn't written into the config", '"server"' not in CFG.read_text())

    # never during a tracked flight
    CFG.write_text('{"server": "http://127.0.0.1:5999", "token": "pac_old"}')

    class Alive:
        def is_alive(self):
            return True
    C.state.update(thread=Alive(), site_notice=None)
    C.refresh_hello()
    check("no switch while a flight is tracked", C.server_url() == "http://127.0.0.1:5999")
    check("clear message for a local address", "Nothing is running at that address" in (C.state.get("server_error") or ""), C.state.get("server_error"))
    check("technical reason kept separately", bool(C.state.get("server_detail")))
    C.state["thread"] = None

    # a pilot's own non-local choice is respected, even when it's down
    CFG.write_text('{"server": "https://unreachable.invalid", "token": "pac_x"}')
    C.refresh_hello()
    check("a chosen public address is never replaced", C.server_url() == "https://unreachable.invalid")
    check("its message mentions the internet connection", "internet connection" in (C.state.get("server_error") or ""))

    # the window's buttons
    ui = C.ui.test_client()
    st = ui.get("/api/state").get_json()
    check("window is told the airline's address", st.get("default_server") == OFFICIAL, st.get("default_server"))
    st = ui.post("/api/site/default").get_json()
    check("'Use pac-va.com' switches back", st["config"]["server"] == OFFICIAL and st["server_ok"], st["config"]["server"])
    check("…and drops the other site's key", "token" not in C.load_config())
    CFG.write_text('{"token": "pac_keep", "pilot": {"id": "PAC0002", "name": "B"}}')
    ui.post("/api/config", json={"server": OFFICIAL + "/", "chime": False})
    check("saving settings without changing the address keeps the sign-in", C.load_config().get("token") == "pac_keep")
    r = ui.post("/api/config", json={"server": "http://127.0.0.1:5999"}).get_json()
    check("changing the address drops the key", "token" not in C.load_config() and r["config"]["server"] == "http://127.0.0.1:5999")
    C.refresh_hello()
    check("an address typed in Settings stays, even when it isn't running", C.server_url() == "http://127.0.0.1:5999")
    check("…with the offer to use the airline's website", ui.get("/api/state").get_json()["default_server"] == OFFICIAL)
    C.state["thread"] = Alive()
    r = ui.post("/api/config", json={"server": OFFICIAL})
    check("address can't change mid-flight", r.status_code == 409)
    C.state["thread"] = None
    ui.post("/api/site/default")
    check("'Use pac-va.com' clears the typed choice", "server_chosen" not in C.load_config() and C.server_url() == OFFICIAL)
    ui.post("/api/notice/dismiss")
    check("notice can be dismissed", C.state.get("site_notice") is None)
finally:
    srv.shutdown()
    if saved_cfg is None:
        CFG.unlink(missing_ok=True)
    else:
        CFG.write_bytes(saved_cfg)

print("\n" + ("PAC ACARS SITE TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
