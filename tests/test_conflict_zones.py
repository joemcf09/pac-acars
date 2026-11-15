"""Conflict zones: off by default; when on, zone flights need an acknowledgement to book, a flight to a restricted
country is rejected automatically, and a caution-area flight earns hazard pay.

Run from the PAC folder:   python tests/test_conflict_zones.py
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
import conflict_zones as Z  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Zones-Test-Pass-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False})
rw = analysis.runways(A.DATA)
apt = lambda i: A.airport_obj(i)  # noqa: E731

print("Rules on real routes")
st = {"conflict_zones_enabled": True}
check("off by default", Z.assess(apt("KCVG"), apt("VHHH"), None, {}, DATA) is None)
r = Z.assess(apt("KCVG"), apt("VHHH"), None, st, DATA)
check("Cincinnati–Hong Kong great circle crosses Russia", r and r["restricted_crossing"] and not r["restricted_airport"], r)
check("London–Moscow is not authorized", Z.assess(apt("EGLL"), apt("UUEE"), None, st, DATA)["restricted_airport"])
r = Z.assess(apt("KMIA"), apt("MTPP"), None, st, DATA)
check("Miami–Port-au-Prince is a caution flight at 15%", r and r["level"] == "caution" and r["pct"] == 15, r)
check("Cincinnati–Miami is clear", Z.assess(apt("KCVG"), apt("KMIA"), None, st, DATA) is None)
r = Z.assess(apt("KMIA"), apt("MTPP"), None, {**st, "conflict_zone_overrides": {"haiti": {"level": "off"}}}, DATA)
check("staff can switch an area off", r is None, r)

print("Switched off: nothing changes")
b = c.post("/api/booking", json={"mission_id": "PAC2097", "aircraft": "B738F", "airframe": None})
check("a Haiti flight books with no questions", b.status_code == 200 and "conflict" not in b.json, b.json)
c.delete("/api/booking")

print("Staff switch it on")
r = c.post("/api/staff/conflict-zones", json={"enabled": True, "zones": {"haiti": {"level": "caution", "pct": 15}}}).json
check("saved", r["enabled"] and any(z["id"] == "haiti" and z["pct"] == 15 for z in r["zones"]), r)
pub = c.get("/api/conflict-zones").json
check("the website gets the active areas", pub["enabled"] and any(z["id"] == "russia" for z in pub["zones"]))


def fly_route(mission, dep, arr, td=-150):
    b = c.post("/api/booking", json={"mission_id": mission, "aircraft": "B738F", "airframe": None})
    if b.status_code == 409 and b.json.get("needs_zone_ack"):
        need = b.json
        b = c.post("/api/booking", json={"mission_id": mission, "aircraft": "B738F", "airframe": None, "zone_ack": True})
    else:
        need = None
    assert b.status_code == 200, b.json
    b = b.json
    c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
    rec = FlightRecorder(b)
    for s in fly(dep, rw[dep][0][0], arr, rw[arr][0][0], td_fpm=td):
        rec.update(s)
    c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
    return need, b, c.post("/api/pirep", json={"remarks": "zones"}).json


print("A caution flight: Miami to Port-au-Prince")
need, b, p = fly_route("PAC2097", "KMIA", "MTPP")
check("booking asked for an acknowledgement first", need and need["zone"]["level"] == "caution", need)
check("the booking carries the assessment", (b.get("conflict") or {}).get("level") == "caution", b.get("conflict"))
check("hazard pay is 15% of flight pay", p.get("pay") and abs(p["pay"].get("hazard_pay", 0) - round(p["pay"]["flight_pay"] * .15, 2)) < .02, p.get("pay"))
if p.get("review_status") == "Pending":           # the scripted flight trips a review flag; staff accept it
    c.post(f"/api/staff/reviews/{p['id']}", json={"action": "accept", "note": "ok"})
with A.db() as con:
    tx = con.execute("SELECT amount FROM wallet WHERE pirep_id=? AND kind='hazard_pay'", (p["id"],)).fetchone()
    fp = con.execute("SELECT amount FROM wallet WHERE pirep_id=? AND kind='flight_pay'", (p["id"],)).fetchone()
check("hazard pay reaches the wallet with the flight pay", tx and fp and abs(tx[0] - round(fp[0] * .15, 2)) < .02, (tx and tx[0], fp and fp[0]))

print("A restricted flight: Addis Ababa to Khartoum")
need, b, p = fly_route("PAC5039", "HAAB", "HSSK")
check("booking warned it isn't authorized", need and need["zone"]["restricted_airport"], need)
check("the PIREP is rejected automatically", p.get("review_status") == "Rejected", (p.get("review_status"), p.get("flags")))
check("with no pay", not p.get("pay"), p.get("pay"))
with A.db() as con:
    row = con.execute("SELECT review_note FROM pireps WHERE id=?", (p["id"],)).fetchone()
    paid = con.execute("SELECT COUNT(*) FROM wallet WHERE pirep_id=?", (p["id"],)).fetchone()[0]
check("the pilot sees why", "restricted" in (row["review_note"] or "").lower(), row["review_note"])
check("nothing was paid", paid == 0, paid)

print("Flights booked before the switch")
st_ = A.settings(); st_["conflict_zones_since"] = __import__("time").time() + 3600; A.save_json(A.SETTINGS_PATH, st_)
need, b, p = fly_route("PAC5039", "HAAB", "HSSK")
check("a restricted flight booked before the rules started isn't rejected", p.get("review_status") != "Rejected", (p.get("review_status"), p.get("flags")))

print("restricted_airport: keeps generated work (checkrides, jobs) out of restricted airspace")
check("Lviv (Ukraine) is restricted when the feature is on", Z.restricted_airport("UKLL", {"conflict_zones_enabled": True}))
check("Tehran (Iran) is restricted when the feature is on", Z.restricted_airport("OIIE", {"conflict_zones_enabled": True}))
check("Cincinnati is never restricted", not Z.restricted_airport("KCVG", {"conflict_zones_enabled": True}))
check("a caution zone (Somalia) is flyable, not restricted", not Z.restricted_airport("HCMM", {"conflict_zones_enabled": True}))
check("nothing is restricted while the feature is off", not Z.restricted_airport("UKLL", {}))

print()
print("All conflict zone checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
