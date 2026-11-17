"""Airframe reservation timing. An airframe must be marked 'Booked' only once the booking actually persists,
and released on cancel. A booking that fails AFTER the availability check (a dispatch/transfer error, or a
conflict-zone acknowledgement that needs a second pass) must NOT strand the tail in 'Booked' with no booking
behind it. That orphan was the bug: pilots saw a plane go 'Reserved/booked' mid-planning and couldn't book it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
R = Path(__file__).resolve().parent.parent
for f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (R / "data" / f).unlink(missing_ok=True)

import app as A  # noqa: E402

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got!r}]"))
    if not ok:
        fails.append(name)

staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Admin-Pass-123456"})
staff.post("/api/settings", json={"enforce_ranks": False, "enforce_pilot_location": False, "enforce_airframes": True})
pub = A.app.test_client()
pub.post("/api/applications", json={"name": "T", "email": "t@x.com", "country": "US", "simulator": "MSFS", "hub": "KCVG",
                                    "experience": "x", "motivation": "c", "handbook": True, "agree": True, "read_handbook": True})
aid = [a for a in staff.get("/api/staff/overview").json["applications"] if a["status"] == "Pending"][0]["id"]
pid = staff.post(f"/api/staff/applications/{aid}", json={"action": "approve"}).json["pilot_id"]
tok = staff.post(f"/api/staff/pilots/{pid}/signin-link").json["link"].split("set-password=")[1]
c = A.app.test_client()
c.post("/api/auth/accept", json={"token": tok, "password": "Pilot-Pass-123456"})

def status(reg):
    return [f["status"] for f in staff.get("/api/staff/airframes").json["airframes"] if f["reg"] == reg][0]

REG = "N738PC"                                   # a B738F at KCVG in the seeded fleet
BODY = {"mission_id": "PAC1001", "aircraft": "B738F", "airframe": REG}   # a scheduled KCVG route

check("airframe starts Available", status(REG) == "Available", status(REG))

r = c.post("/api/booking", json=BODY)
check("booking succeeds", r.status_code == 200, r.status_code)
check("airframe is Booked once the booking persists", status(REG) == "Booked", status(REG))

c.delete("/api/booking")
check("airframe is released on cancel", status(REG) == "Available", status(REG))

# A booking that fails AFTER the availability check must not strand the tail.
orig = A.build_dispatch_with_transfers
A.build_dispatch_with_transfers = lambda *a, **k: (_ for _ in ()).throw(ValueError("forced dispatch failure"))
try:
    r = c.post("/api/booking", json=BODY)
finally:
    A.build_dispatch_with_transfers = orig
check("aborted booking is refused", r.status_code >= 400, r.status_code)
check("aborted booking leaves the airframe Available (no orphan)", status(REG) == "Available", status(REG))

# and the tail is immediately bookable again, not blocked by a phantom 'Booked'
r = c.post("/api/booking", json=BODY)
check("rebooking after an abort works", r.status_code == 200, r.status_code)
check("airframe Booked again after a real booking", status(REG) == "Booked", status(REG))
c.delete("/api/booking")

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
