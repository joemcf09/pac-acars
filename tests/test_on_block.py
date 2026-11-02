"""Going on block with aircraft whose parking brake PAC ACARS can't read (some X-Plane 11 add-ons), the taxi-in hint,
and "File anyway": a landed flight that never went on block can still be filed, and goes to staff review.

Run from the PAC folder:   python tests/test_on_block.py
"""
import dataclasses
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)
import app as A  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


m = A.ROUTES["PAC1022"]
booking = {"mission": m, "aircraft": m["aircraft"][0], "ofp": None, "flight_number": "PAC9700", "airframe": None, "requested_at": 1.79e9}
stream = fly("KCVG", "18C", "KCLT", "18C")


def run(samples):
    r = FlightRecorder(booking)
    for s in samples:
        r.update(s)
    return r


print("Brake read normally")
r = run(stream)
check("on block as before", r.complete and r.phase == "ARRIVED", r.phase)

print("Aircraft whose parking brake never reads set")
nobrake = [dataclasses.replace(s, parking_brake=False) if not s.engines_running else s for s in stream]
last = nobrake[-1]
r = run(nobrake)
check("engines off but under a minute: still taxiing in", not r.complete and r.phase == "TAXI_IN", r.phase)
check("the hint says how to finish", "parking brake" in (r.waiting_for() or "").lower(), r.waiting_for())
more = [dataclasses.replace(last, t=last.t + 1 + i) for i in range(65)]
r2 = run(nobrake + more)
check("on block after a minute stopped with engines off", r2.complete and r2.phase == "ARRIVED", r2.phase)
check("the log says why", any("PARKING BRAKE NOT READ" in x["text"] for x in r2.messages))
moving = [dataclasses.replace(last, t=last.t + 1 + i, gs=5.0) for i in range(65)]
check("still rolling with engines off: not on block", not run(nobrake + moving).complete)

print("File anyway")
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "OnBlock-Pass-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False, "require_release_signature": False})
b = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": m["aircraft"][0], "airframe": None}).json
check("booked", "error" not in b, b)
rec = FlightRecorder(A.load_booking())
for s in nobrake:
    rec.update(s)
A.state.update(recorder=rec)
r = c.post("/api/pirep", json={})
check("normal filing still needs on block", r.status_code == 400, r.json)
r = c.post("/api/pirep", json={"force": True, "remarks": "File anyway"})
check("filed with File anyway", r.status_code == 200, r.json)
row = A.db().execute("SELECT review_status, flags FROM pireps ORDER BY id DESC LIMIT 1").fetchone()
check("goes to staff review, flagged", row and row[0] == "Pending" and "File anyway" in row[1], row)

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)
sys.exit(1 if failures else 0)
