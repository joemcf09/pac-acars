"""Navigraph Charts: the SimBrief plan's request id reaches the dispatch release, so pilots can open it in Navigraph."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)
import app as A  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Founder-Pass-123"})
m = next(x for x in A.MISSIONS.values() if x["origin"]["icao"] == "KCVG")
A.save_booking({"mission": m, "aircraft": m["aircraft"][0], "flight_number": "PAC1234", "requested_at": time.time(),
                "ofp": {"request_id": "188722114", "route": "DCT", "route_points": []}}, "PAC0001")
d = c.get("/api/dispatch").get_json()
check("the dispatch release carries the SimBrief plan id", d.get("simbrief_request_id") == "188722114", d.get("simbrief_request_id"))
A.save_booking({"mission": m, "aircraft": m["aircraft"][0], "flight_number": "PAC1235", "requested_at": time.time(), "ofp": None}, "PAC0001")
check("…and is blank without a plan", c.get("/api/dispatch").get_json().get("simbrief_request_id") == "")
js = __import__("app_bundle").plain_source()   # the site script, from its pieces in static/app/
check("the page builds Navigraph's SimBrief import link", "charts.navigraph.com/flights/simbrief-instant-import?requestId=" in js)
for page in ("dispatch.html", "dispatch-classic.html"):
    html = (Path(__file__).resolve().parent.parent / "static" / page).read_text(encoding="utf-8")
    check(f"{page} has a Navigraph Charts button", 'id="navigraph"' in html and "simbrief-instant-import" in html)
print("\n" + ("NAVIGRAPH TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
