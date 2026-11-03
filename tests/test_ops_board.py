"""The home page's departures and arrivals boards show every pilot's flight, not just the viewer's."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import speedup  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


now = time.time()
r = A.ROUTES["PAC1001"]
with A.db() as con:
    cols = {x[1] for x in con.execute("PRAGMA table_info(pilots)")}
    for pid, name in (("PAC0002", "Ada Lovelace"), ("PAC0003", "Ray Danuk"), ("PAC0004", "Old Booking")):
        con.execute(f"INSERT OR IGNORE INTO pilots (id, name) VALUES (?,?)", (pid, name))
    mk = lambda fn, at: json.dumps({"flight_number": fn, "aircraft": "B738F", "airframe": "N738PA", "requested_at": at, "mission": r})
    con.execute("INSERT INTO bookings (pilot_id, data, requested_at) VALUES (?,?,?)", ("PAC0002", mk("PAC1001", now - 600), now - 600))
    con.execute("INSERT INTO bookings (pilot_id, data, requested_at) VALUES (?,?,?)", ("PAC0003", mk("PAC4242", now - 300), now - 300))
    con.execute("INSERT INTO bookings (pilot_id, data, requested_at) VALUES (?,?,?)", ("PAC0004", mk("PAC5555", now - 5 * 86400), now - 5 * 86400))
    con.execute("INSERT INTO pireps (filed_at, flight_number, aircraft, dep, arr, landing_rate, grade, status, demo, pilot_id, review_status, detail) "
                "VALUES (?,?,?,?,?,?,?,?,0,?,?,?)", (now - 3600, "PAC9657", "B742F", "LIMC", "EDDM", -296, "B", "Delivered", "PAC0003", "Accepted", "{}"))
# Ray's PAC ACARS is reporting a cruise; Ada has only booked
A.SESSIONS["PAC0003"] = {"remote": {"flight": "PAC4242"}, "remote_seen": now,
                         "remote_status": {"phase": "CRUISE", "live": {"lat": 38.0, "lon": -95.0, "alt_ft": 36000, "gs": 450, "on_ground": False}}}
d = A.app.test_client().get("/api/va/board").json
deps, arrs = d["departures"], d["arrivals"]
ada = next((x for x in deps if x["flight"] == "PAC1001"), None)
check("another pilot's booked flight is on the departures board", ada and ada["status"] == "BOOKED" and ada["pilot"] == "Ada L.", deps[:3])
ray = next((x for x in arrs if x["flight"] == "PAC4242"), None)
check("a flight in the air is on the arrivals board with its level", ray and ray["status"] == "EN ROUTE" and ray["remark"] == "FL360", arrs[:3])
check("active flights come before finished ones", arrs and arrs[0]["flight"] == "PAC4242", [x["flight"] for x in arrs])
fin = next((x for x in arrs if x["flight"] == "PAC9657"), None)
check("recent PIREPs show as arrived, with the pilot", fin and fin["status"] == "ARRIVED" and fin["pilot"] == "Ray D.", fin)
check("a booking untouched for days stays off the board", not any(x["flight"] == "PAC5555" for x in deps))
check("featured routes still fill the departures board", any(x["pilot"] == "OPEN" for x in deps) and len(deps) >= 7, len(deps))
A.SESSIONS["PAC0003"]["remote_status"]["phase"] = "TAXI_OUT"
speedup._store.clear()   # the board is cached briefly for visitors
d = A.app.test_client().get("/api/va/board").json
check("a pilot taxiing out shows first on departures", d["departures"][0]["flight"] == "PAC4242" and d["departures"][0]["status"] == "TAXIING", d["departures"][:2])
A.SESSIONS["PAC0003"]["remote_seen"] = now - 600
speedup._store.clear()
d = A.app.test_client().get("/api/va/board").json
check("a flight whose ACARS went quiet falls back to booked", any(x["flight"] == "PAC4242" and x["status"] == "BOOKED" for x in d["departures"]))
print(f"\n{len(failures)} failure(s)" if failures else "\nall passed")
sys.exit(1 if failures else 0)
