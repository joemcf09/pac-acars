"""VATSIM listing readiness: flights on VATSIM under PAC's callsign, counted the way VATSIM's audit counts them.
Run from the PAC folder: python tests/test_vatsim_ready.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-vat-") as temp:
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
c.post("/api/auth/setup", json={"password": "Vat-Test-1"})
now = time.time()
with A.db() as con:
    def flight(pilot, online, days_ago=2, demo=0, review="Accepted"):
        con.execute("""INSERT INTO pireps (filed_at, flight_number, aircraft, dep, arr, pilot_id, demo, review_status, detail)
            VALUES (?, 'PAC1', 'B738F', 'KCVG', 'KJFK', ?, ?, ?, ?)""", (now - days_ago * 86400, pilot, demo, review, json.dumps({"online": online})))
    for i in range(12):
        flight(f"PAC{i:04d}", {"network": "VATSIM", "callsign": f"PGI{100+i}", "share": 0.9, "checks": 30})
    flight("PAC0001", {"network": "VATSIM", "callsign": "N738PC", "share": 0.9, "checks": 30})     # wrong callsign
    flight("PAC0001", {"network": "IVAO", "callsign": "PGI1", "share": 1, "checks": 30})           # IVAO
    flight("PAC0001", {"network": "VATSIM", "callsign": "PGI9", "share": 0.3, "checks": 30})        # mostly offline
    flight("PAC0001", {"network": "VATSIM", "callsign": "PGI9", "share": 1, "checks": 30}, days_ago=70)  # too old
    flight("PAC0001", {"network": "VATSIM", "callsign": "PGI9", "share": 1, "checks": 30}, review="Rejected")
    flight("PAC0002", None)
d = c.get("/api/staff/operations-health").get_json()["vatsim"]
check("counts VATSIM flights under PGI by different pilots", d["counts"]["VATSIM flights"] == 12 and d["counts"]["Pilots"] == 12, d)
check("a VATSIM flight under another callsign is called out", d["counts"]["Other callsigns"] == 1 and "file as PGI" in d["message"], d["message"])
check("not yet 50 flights: says how many to go", "38 flights" in d["message"] and d["level"] == "notice", d["message"])
csv = c.get("/api/staff/vatsim-flights.csv")
rows = csv.get_data(as_text=True).strip().splitlines()
check("the flight list for VATSIM: callsign, origin, destination, date, no pilot ids", rows[0] == "callsign,origin,destination,date" and len(rows) == 13
      and "PAC00" not in csv.get_data(as_text=True), rows[:3])
c.post("/api/auth/logout")
check("staff only", c.get("/api/staff/vatsim-flights.csv").status_code in (401, 403))
print("\nVATSIM READY TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
