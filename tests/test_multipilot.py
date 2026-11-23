"""Two pilots using PAC at the same time: separate bookings, separate tracking, separate logbooks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):   # a clean airline, before PAC opens the database
    (DATA / _f).unlink(missing_ok=True)
for _p in (DATA / "flights").glob("*.pkl"):
    _p.unlink()

import app as A  # noqa: E402
import analysis  # noqa: E402
from tracker import FlightRecorder  # noqa: E402
from flightgen import fly  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


rw = analysis.runways(A.DATA)
c1 = A.app.test_client()
c1.post("/api/auth/setup", json={"password": "Multi-Pilot-Test-1"})
c1.post("/api/settings", json={"enforce_pilot_location": False, "require_type_ratings": False, "enforce_airframes": False})
_pub = A.app.test_client()
_pub.post("/api/applications", json={"name": "Second Pilot", "email": "second@example.com", "country": "US", "simulator": "MSFS",
                                     "hub": "KCVG", "experience": "300 hours", "motivation": "cargo", "handbook": True,
                                     "agree": True, "read_handbook": True})
_aid = [a for a in c1.get("/api/staff/overview").json["applications"] if a["status"] == "Pending"][0]["id"]
PID2 = c1.post(f"/api/staff/applications/{_aid}", json={"action": "approve"}).json["pilot_id"]
_tok = c1.post(f"/api/staff/pilots/{PID2}/signin-link").json["link"].split("set-password=")[1]
c2 = A.app.test_client()
check("a second pilot can set a password and sign in", c2.post("/api/auth/accept", json={"token": _tok, "password": "Multi-Pilot-Test-2"}).status_code == 200)

b1 = c1.post("/api/booking", json={"mission_id": "PAC1022", "aircraft": "B733F", "airframe": None}).json
b2 = c2.post("/api/booking", json={"mission_id": "PAC1041", "aircraft": "B763F", "airframe": None}).json
check("both pilots can hold a booking", "flight_number" in b1 and "flight_number" in b2, (b1, b2))
check("each pilot sees only their own", (c1.get("/api/bootstrap").json["booking"] or {}).get("flight_number") == b1["flight_number"]
      and (c2.get("/api/bootstrap").json["booking"] or {}).get("flight_number") == b2["flight_number"])

def sign_release(client):
    """The captain reviews and signs the dispatch release, which ACARS needs before it starts the flight."""
    d = client.get("/api/dispatch").json
    return client.post("/api/dispatch/sign", json={"requested_at": d.get("requested_at"), "revision": d.get("revision"),
                                                   "reviewed": True, "notoc": True}).status_code


check("each captain signs their own release", sign_release(c1) == 200 and sign_release(c2) == 200)
c1.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b1["requested_at"]})
c2.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b2["requested_at"]})
r1, r2 = FlightRecorder(b1), FlightRecorder(b2)
s1 = list(fly("KCVG", rw["KCVG"][0][0], "KCLT", rw["KCLT"][0][0]))
s2 = list(fly("KORD", rw["KORD"][0][0], "KCVG", rw["KCVG"][0][0]))
for i in range(max(len(s1), len(s2))):           # interleaved, as two pilots flying at once
    if i < len(s1):
        r1.update(s1[i])
    if i < len(s2):
        r2.update(s2[i])
    if i % 500 == 0:
        c1.post("/api/acars/app/live", json={"status": {"phase": "CRUISE", "tracking": True}})
        c2.post("/api/acars/app/live", json={"status": {"phase": "CLIMB", "tracking": True}})
check("each pilot's live status is their own", c1.get("/api/acars/status").json.get("phase") == "CRUISE"
      and c2.get("/api/acars/status").json.get("phase") == "CLIMB")

c1.post("/api/acars/app/complete", json={"record": r1.export(), "requested_at": b1["requested_at"], "source": "MSFS"})
c2.post("/api/acars/app/complete", json={"record": r2.export(), "requested_at": b2["requested_at"], "source": "MSFS"})
p1 = c1.post("/api/pirep", json={"remarks": "pilot one"}).json
p2 = c2.post("/api/pirep", json={"remarks": "pilot two"}).json
check("both flights file", bool(p1.get("id")) and bool(p2.get("id")), (p1.get("error"), p2.get("error")))
with A.db() as con:
    rows = {r["flight_number"]: r["pilot_id"] for r in con.execute("SELECT flight_number, pilot_id FROM pireps")}
check("each flight is filed to the right pilot", rows.get(b1["flight_number"]) == "PAC0001" and rows.get(b2["flight_number"]) == PID2, rows)
check("bookings are cleared after filing", A.all_bookings() == [], A.all_bookings())

c1.post("/api/settings", json={"simbrief_username": "pilotone"})
c2.post("/api/settings", json={"simbrief_username": "pilottwo"})
check("each pilot keeps their own SimBrief username",
      c1.get("/api/bootstrap").json["settings"]["simbrief_username"] == "pilotone"
      and c2.get("/api/bootstrap").json["settings"]["simbrief_username"] == "pilottwo")

print("\nMULTI-PILOT TEST", "PASSED" if not failures else f"FAILED ({len(failures)})")
sys.exit(1 if failures else 0)
