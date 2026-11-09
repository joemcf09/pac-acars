"""Lane reputation: on-time careful deliveries raise a lane, late or damaging ones lower it, and demand follows.
Run from the PAC folder: python tests/test_lanes.py"""
import json, os, random, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-lanes-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import lanes as L  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
c = A.app.test_client(); c.post("/api/auth/setup", json={"password": "Lane-Test-1"})
now = time.time()
def flight(dep, arr, status, care=None, days_ago=1, review="Accepted", demo=0):
    with A.db() as con:
        con.execute("INSERT INTO pireps (filed_at, pilot_id, dep, arr, status, review_status, demo) VALUES (?,?,?,?,?,?,?)",
                    (now - days_ago * 86400, "PAC0001", dep, arr, "Delivered", review, demo))
        pid = con.execute("SELECT MAX(id) FROM pireps").fetchone()[0]
        con.execute("""INSERT INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, pirep_id, status, details)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""", (f"s{pid}", f"k{pid}", "FLIGHT_ARRIVAL", now - days_ago * 86400, dep, arr, "PAC0001", pid, status,
                                                      json.dumps({"care": care} if care else {})))
with A.db() as con:
    A.cargo_network.ensure_schema(con) if hasattr(A.cargo_network, "ensure_schema") else None
for _ in range(5):
    flight("KCVG", "KMIA", "DELIVERED")
flight("KCVG", "KJFK", "DELIVERED_LATE"); flight("KCVG", "KJFK", "DELIVERED", care={"status": "excursion"}); flight("KCVG", "KJFK", "EXCEPTION")
flight("KCVG", "KLAX", "DELIVERED_LATE", review="Rejected"); flight("KCVG", "KLAX", "DELIVERED_LATE", demo=1)
flight("KCVG", "KORD", "DELIVERED", days_ago=60)
with A.db() as con:
    reps = L.compute(con, now)
mia, jfk = reps.get(("KCVG", "KMIA")), reps.get(("KCVG", "KJFK"))
check("five recent on-time flights make a Preferred lane", mia and mia["tier"] == "Preferred" and mia["score"] == 100, mia)
check("late, damaged and failed flights put a lane at risk", jfk and jfk["tier"] == "At risk" and (jfk["late"], jfk["care_issues"], jfk["failed"]) == (1, 1, 1), jfk)
check("rejected and demo flights don't count", ("KCVG", "KLAX") not in reps, reps.get(("KCVG", "KLAX")))
check("older flights count half", reps[("KCVG", "KORD")]["score"] == 74, reps.get(("KCVG", "KORD")))
check("demand follows: preferred lanes weigh 5× an at-risk one", L.weight(reps, "KCVG", "KMIA") / L.weight(reps, "KCVG", "KJFK") == 5.0)
api = c.get("/api/lanes").json
check("the lanes page lists them, strongest first", api["lanes"][0]["origin"] == "KCVG" and api["lanes"][0]["destination"] == "KMIA", api["lanes"][:2])
check("visitors can't see it", A.app.test_client().get("/api/lanes").status_code == 401)
print(); print("All lane reputation checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
