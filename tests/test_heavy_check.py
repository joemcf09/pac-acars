"""Aircraft that age: the heavy (C) check comes due, the aircraft may only be ferried to the maintenance base,
spends its weeks in the hangar there and comes back fresh. Run from the PAC folder: python tests/test_heavy_check.py"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-heavy-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, heavy_check as H  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

check("existing airframes start part-way through the cycle, the same every time", 300 <= H.seed_hours("N771PC") < 6000 and H.seed_hours("N771PC") == H.seed_hours("N771PC"))
check("nothing changes before the limit", H.after_flight(5999, "KMIA", "Available") is None)
st, note, until = H.after_flight(6001, "KMIA", "Available")
check("due away from base: wait for a ferry to KCVG", st == H.DUE and "KCVG" in note and until is None)
st, note, until = H.after_flight(6001, "KCVG", "Available", now=1000)
check("due at base: into the hangar for three weeks", st == H.IN_CHECK and until == 1000 + 21 * 86400)
check("an AOG or inspection takes priority", H.after_flight(7000, "KCVG", "Inspection") is None)
row = {"status": H.DUE}
check("a due airframe may fly the ferry to the base", H.may_book(row, {"category": "Ferry", "payload_lbs": 0, "destination": {"icao": "KCVG"}}))
check("but not a cargo flight", not H.may_book(row, {"category": "Scheduled", "payload_lbs": 40000, "destination": {"icao": "KCVG"}}))
check("nor a ferry somewhere else", not H.may_book(row, {"category": "Ferry", "payload_lbs": 0, "destination": {"icao": "KMIA"}}))
j = H.ferry_job({"reg": "N771PC", "type": "B763F", "location": "KMIA"}, A.airport_obj, A.gc_distance_nm, A.FLEET, "PAC7999", time.time() + 86400, 150)
check("the mission board gets a ferry to KCVG for it", j and j["destination"]["icao"] == "KCVG" and j["fixed_airframe"] == "N771PC" and j["payload_lbs"] == 0)
with A.db() as con:
    con.execute("INSERT OR REPLACE INTO airframes (reg, type, location, status, hours, cycles, hours_since_check, hours_since_heavy, heavy_until) VALUES ('N999HC','B763F','KCVG',?,9000,3000,400,6100,?)",
                (H.IN_CHECK, time.time() - 10))
    con.execute("INSERT OR REPLACE INTO airframes (reg, type, location, status, hours, cycles, hours_since_check, hours_since_heavy) VALUES ('N998HC','B763F','KMIA','Available',9000,3000,0,6200)")
    H.tick(con)
    a = dict(con.execute("SELECT * FROM airframes WHERE reg='N999HC'").fetchone())
    b = dict(con.execute("SELECT * FROM airframes WHERE reg='N998HC'").fetchone())
check("after its weeks in the hangar it returns fresh", a["status"] == "Available" and a["hours_since_heavy"] == 0 and a["hours_since_check"] == 0, a)
check("a due airframe that slipped back to Available is marked again", b["status"] == H.DUE, b["status"])
print("\nHEAVY CHECK TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
