"""A minor overspeed penalty does not prevent an otherwise passing line checkride.

Run from the PAC folder:   python tests/test_checkride_review.py
"""
import sys
import os
import json
import shutil
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TEST_DATA = Path(tempfile.mkdtemp())
os.environ["PAC_DATA_DIR"] = str(TEST_DATA)
shutil.copy2(Path(__file__).resolve().parent.parent / "data" / "runways.json", TEST_DATA / "runways.json")

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
    b = c.post("/api/booking", json={"training": {
        "course": "PAC001", "mode": "dedicated", "aircraft": "B738F", "origin": "KCVG"
    }}).json
    assert "error" not in b, b
    c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
    rec = FlightRecorder(b)
    dep, arr = b["mission"]["origin"]["icao"], b["mission"]["destination"]["icao"]
    for s in fly(dep, rw[dep][0][0], arr, rw[arr][0][0], td_fpm=-120, **opts):
        rec.update(s)
    c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
    return c.post("/api/pirep", json={"remarks": "checkride"}).json


print("A checkride with a minor overspeed")
p = fly_checkride(overspeed_s=40)
check("it files", bool(p.get("id")), p)
car = c.get("/api/va/career").json["career"]
check("a minor overspeed does not fail the checkride", car["checkride"] == "Passed", car["checkride"])
check("Career records the checkride as passed", car["checkride_last"] and car["checkride_last"]["passed"], car.get("checkride_last"))
check("an accepted checkride earns flight pay", p.get("pay") and p["pay"]["flight_pay"] > 0, p.get("pay"))
with A.db() as con:
    checkride_payment = con.execute("SELECT amount FROM wallet WHERE pirep_id=? AND kind='flight_pay'", (p["id"],)).fetchone()
check("accepted checkride flight pay reaches the wallet", checkride_payment and checkride_payment["amount"] > 0, checkride_payment)
book = c.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": "B738F", "airframe": None}).json
check("passing unlocks line aircraft", "error" not in book, book)
c.delete("/api/booking")
rv = [r for r in staff.get("/api/staff/overview").json["reviews"] if r["id"] == p["id"]][0]
check("staff see that the checkride passed", rv["checkride"] and rv["checkride"]["passed"], rv.get("checkride"))

print("An accepted but unsuccessful type checkride")
before = A.va.career(PID)
failed_detail = json.dumps({
    "training": {"mode": "dedicated"},
    "type_checkride": {"family": "A300", "passed": False, "reasons": ["landing too firm"]},
    "pilot_rank": before["rank"],
})
with A.db() as con:
    failed_id = con.execute(
        """INSERT INTO pireps (filed_at, mission_id, mission_title, category, flight_number, aircraft, dep, arr,
                               block_min, score, grade, status, points, demo, detail, pilot_id, review_status, profit, flags)
           VALUES (?, 'TR-A300', 'A300 type checkride', 'Type checkride', 'TR-A300', 'A306F', 'PANC', 'PAJN',
                   120, 85, 'B', 'Delivered', 0, 0, ?, ?, 'Accepted', 0, '[]')""",
        (time.time(), failed_detail, PID),
    ).lastrowid
failed_pay = A.va.pay_pirep(failed_id)
after = A.va.career(PID)
stats = A.profile_stats(PID)
check("failed accepted attempts count toward career flights and hours",
      after["flights"] == before["flights"] + 1 and after["pac_hours"] == round(before["pac_hours"] + 2, 1),
      (before["flights"], before["pac_hours"], after["flights"], after["pac_hours"]))
check("failed attempts count in aircraft flight and hour totals",
      stats["by_aircraft"]["A306F"]["flights"] == 1 and stats["by_aircraft"]["A306F"]["block_hours"] == 2.0,
      stats["by_aircraft"].get("A306F"))
check("failed accepted attempts receive standard flight pay", failed_pay and failed_pay["flight_pay"] > 0, failed_pay)
check("checkride pay is not duplicated", A.va.pay_pirep(failed_id) is None)

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
