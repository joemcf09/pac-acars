"""A failed line checkride is shown clearly to the pilot and staff, and staff waiving a misread penalty checks it again.

Run from the PAC folder:   python tests/test_checkride_review.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)
for _p in (DATA / "flights").glob("*.pkl"):
    _p.unlink()

import analysis  # noqa: E402
import app as A  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Checkride-Test-Pass-1"})
staff.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": True})
pub = A.app.test_client()
pub.post("/api/applications", json={"name": "New Pilot", "email": "new@example.com", "country": "US", "simulator": "MSFS", "hub": "KCVG",
                                    "experience": "100 hours", "motivation": "cargo", "handbook": True, "agree": True, "read_handbook": True})
aid = [a for a in staff.get("/api/staff/overview").json["applications"] if a["status"] == "Pending"][0]["id"]
PID = staff.post(f"/api/staff/applications/{aid}", json={"action": "approve"}).json["pilot_id"]
tok = staff.post(f"/api/staff/pilots/{PID}/signin-link").json["link"].split("set-password=")[1]
c = A.app.test_client()
c.post("/api/auth/accept", json={"token": tok, "password": "Checkride-Test-Pass-2"})
rw = analysis.runways(A.DATA)


def fly_checkride(**opts):
    b = c.post("/api/booking", json={"mission_id": "PAC001", "aircraft": "B738F", "airframe": None}).json
    assert "error" not in b, b
    c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
    rec = FlightRecorder(b)
    for s in fly("KCVG", rw["KCVG"][0][0], "KBNA", rw["KBNA"][0][0], td_fpm=-120, **opts):
        rec.update(s)
    c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
    return c.post("/api/pirep", json={"remarks": "checkride"}).json


print("A checkride with an overspeed below FL100")
p = fly_checkride(overspeed_s=40)
check("it files", bool(p.get("id")), p)
car = c.get("/api/va/career").json["career"]
check("the checkride is still to do", car["checkride"] == "Pending", car["checkride"])
check("Career says the last attempt didn't pass, and why", car["checkride_last"] and not car["checkride_last"]["passed"]
      and "overspeed or position jump" in car["checkride_last"]["reasons"], car.get("checkride_last"))
book = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": "B738F", "airframe": None}).json
check("line aircraft stay locked", "error" in book, book)
rv = [r for r in staff.get("/api/staff/overview").json["reviews"] if r["id"] == p["id"]][0]
check("staff see the checkride wasn't passed, with the reason", rv["checkride"] and not rv["checkride"]["passed"]
      and "overspeed or position jump" in rv["checkride"]["reasons"], rv.get("checkride"))

print("Staff waive the overspeed")
idx = [i for i, x in enumerate(rv["breakdown"]) if "250" in x[0] and x[1] < 0]
r = staff.post(f"/api/staff/reviews/{p['id']}/waive", json={"items": idx, "note": "gust on descent"}).json
check("the waiver goes through", r.get("ok"), r)
car = c.get("/api/va/career").json["career"]
check("the checkride now counts as passed", car["checkride"] == "Passed", car["checkride"])
check("and the pilot moves up to Second Officer", car["rank"] == "Second Officer", car["rank"])
rv = [r for r in staff.get("/api/staff/overview").json["reviews"] if r["id"] == p["id"]][0]
check("the PIREP shows it passed after review", rv["checkride"]["passed"] and rv["checkride"].get("passed_after_review"), rv["checkride"])

print("What a new Second Officer can fly")
staff.post("/api/settings", json={"require_type_ratings": True})
for ac in ("B738F", "B733F", "B732F"):
    b = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": ac, "airframe": None}).json
    check(f"the line checkride rates the {ac}", "error" not in b, b.get("error"))
    c.delete("/api/booking")
b = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": "B722F", "airframe": None}).json
check("the 727 needs its own type rating", "B727 type rating" in (b.get("error") or ""), b.get("error"))
staff.post("/api/settings", json={"require_type_ratings": False})
b = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": "B722F", "airframe": None}).json
check("with type ratings switched off (the default), the rank alone unlocks the 727", "error" not in b, b.get("error"))
c.delete("/api/booking")
check("type ratings are off on a new airline", A.DEFAULT_SETTINGS["require_type_ratings"] is False)
lic = [r["type"] for r in A.pilot_type_ratings(PID)]
check("with ratings off, the licence lists every family the rank unlocks", lic == ["B722", "B737"], lic)
staff.post("/api/settings", json={"require_type_ratings": True})
lic = [r["type"] for r in A.pilot_type_ratings(PID)]
check("with ratings required, it shows the 737 family, not just the 737-800", lic == ["B737"], lic)

print("\nCHECKRIDE REVIEW TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
