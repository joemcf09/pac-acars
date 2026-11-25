"""Manual PIREP approval can complete the booked flight: deliver its cargo, move the aircraft and pilot, close the booking.
Run from the PAC folder: python tests/test_manual_complete.py"""
import os, shutil, subprocess, sys, tempfile, time, datetime as dt, base64
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-manual-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
c = A.app.test_client()
anonymous = A.app.test_client().get('/api/manual-pireps/latest-flight')
check('booking lookup requires sign-in', anonymous.status_code == 401, anonymous.json)
c.post("/api/auth/setup", json={"password": "Manual-Test-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False})
c.get("/api/cargo/overview")
with A.db() as con:
    # an order PAC flies straight to (truck freight is addressed to a nearby town no PAC route serves)
    flown = {rt["destination"]["icao"] for rt in A.ROUTES.values() if rt["origin"]["icao"] == "KCVG" and rt.get("category") == "Scheduled"}
    order = next(r for r in con.execute("SELECT * FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION' AND current_station='KCVG'")
                 if r["destination"] in flown)
route = next(rt for rt in A.ROUTES.values() if rt["origin"]["icao"] == "KCVG" and rt["destination"]["icao"] == order["destination"] and rt.get("category") == "Scheduled")
ac = next(a for a in route["aircraft"] if A.FLEET.get(a, {}).get("max_payload_lbs", 0) >= order["gross_weight_lbs"] * 2)
with A.db() as con:
    tail = con.execute("SELECT reg FROM airframes WHERE type=? LIMIT 1", (ac,)).fetchone()[0]
    con.execute("UPDATE airframes SET location='KCVG', status='Available' WHERE reg=?", (tail,))
ls = c.post("/api/plan/loadsheet", json={"mission_id": route["id"], "aircraft": ac, "cargo_transfer_ids": [order["id"]]}).json
b = c.post("/api/booking", json={"mission_id": route["id"], "aircraft": ac, "manifest_seed": ls["seed"], "cargo_transfer_ids": [order["id"]], "zone_ack": True}).json
latest = c.get('/api/manual-pireps/latest-flight')
check('latest booking fills only known flight details', latest.status_code == 200 and
      all(latest.json.get(k) == v for k, v in {'flight': route['id'], 'dep': 'KCVG',
      'arr': route['destination']['icao'], 'aircraft': ac}.items()) and
      'departed' not in latest.json and 'minutes' not in latest.json, latest.json)
dep_t = (dt.datetime.utcnow() - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
report = {"flight": route["id"], "dep": "KCVG", "arr": route["destination"]["icao"], "tail": tail, "aircraft": ac,
          "departed": dep_t, "minutes": "90", "reason": "Forgot to start ACARS, sound was muted."}
bad_image = c.post("/api/manual-pireps", json=dict(report, screenshot="data:image/webp;base64," + base64.b64encode(b"RIFFwebp").decode()))
check("unsupported screenshot explains the rejected field", bad_image.status_code == 400 and "PNG, JPEG or WebP" in bad_image.json.get("error", ""), bad_image.json)
bad_route = c.post("/api/manual-pireps", json=dict(report, dep="XXXX"))
check("unknown airport explains the rejected field", bad_route.status_code == 400 and "ICAO" in bad_route.json.get("error", ""), bad_route.json)
r = c.post("/api/manual-pireps", json=report)
check("the manual report is filed", r.status_code == 201, r.json)
rid = r.json["id"]
a = c.post(f"/api/staff/reviews/{rid}", json={"action": "accept", "note": "Screenshot checks out.", "complete_flight": True})
check("staff accept it with the complete box ticked", a.status_code == 200, a.json)
with A.db() as con:
    sh = con.execute("SELECT status, current_station FROM cargo_shipments WHERE id=?", (order["id"],)).fetchone()
    # the flight's own cargo reaches the flight's destination: delivered there, or waiting there for its next leg
    # (connecting freight, e.g. KCVG → KDFW bound for PANC, stays AT_STATION at KDFW)
    own = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE booking_key=? AND current_station=? AND (status LIKE 'DELIVERED%' OR status='AT_STATION')",
                      (f"PAC0001:{b['requested_at']}", route["destination"]["icao"])).fetchone()[0]
    frame = con.execute("SELECT location, status FROM airframes WHERE reg=?", (tail,)).fetchone()
    loc = con.execute("SELECT location FROM pilots WHERE id='PAC0001'").fetchone()[0]
    bk = con.execute("SELECT COUNT(*) FROM bookings WHERE pilot_id='PAC0001'").fetchone()[0]
    rep = con.execute("SELECT score, review_status FROM pireps WHERE id=?", (rid,)).fetchone()
dest = route["destination"]["icao"]
check("the picked-up order is delivered", sh["status"].startswith("DELIVERED") and sh["current_station"] == dest, dict(sh))
check("the flight's own cargo reaches its destination", own > 0, own)
check("the aircraft is at the arrival airport and free", frame["location"] == dest and frame["status"] == "Available", dict(frame))
check("the pilot is at the arrival airport", loc == dest, loc)
check("the booking is closed", bk == 0, bk)
check("still no score", rep["score"] is None and rep["review_status"] == "Accepted", dict(rep))
already_reported = c.get('/api/manual-pireps/latest-flight')
check('reported flight is not offered again', already_reported.status_code == 404, already_reported.json)
recovery_booking = {'mission': route, 'aircraft': ac, 'flight_number': 'PACREC1',
                    'airframe': tail, 'requested_at': time.time()}
A.save_booking(recovery_booking, notify=False)
A.clear_booking()
recovered = c.get('/api/manual-pireps/latest-flight')
check('a cleared booking remains available for manual entry', recovered.status_code == 200 and
      recovered.json['flight'] == 'PACREC1' and recovered.json['source'] == 'recent PAC booking', recovered.json)
webp = b"RIFF\x0c\x00\x00\x00WEBPVP8 "
older = (dt.datetime.utcnow() - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
with_webp = c.post("/api/manual-pireps", json=dict(report, departed=older,
    screenshot="data:application/octet-stream;base64," + base64.b64encode(webp).decode()))
check("WebP evidence is accepted even when the browser reports a generic MIME type", with_webp.status_code == 201, with_webp.json)
if with_webp.status_code == 201:
    with A.db() as con:
        evidence = con.execute("SELECT mime FROM manual_pirep_evidence WHERE pirep_id=?", (with_webp.json["id"],)).fetchone()
    check("WebP evidence uses the verified image MIME type", evidence["mime"] == "image/webp")
print(); print("All manual completion checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
