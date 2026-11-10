"""Public cargo network page: totals, lanes, on-time delivery and freight waiting, from filed flights and shipments.
Run from the PAC folder: python tests/test_network.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-net-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import network_stats  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Net-Test-1"})
c.post("/api/auth/logout")
now = time.time()
with A.db() as con:
    def pirep(dep, arr, lbs, ago_days, demo=0, review="Accepted", ac="B738F"):
        con.execute("""INSERT INTO pireps (filed_at, flight_number, aircraft, dep, arr, block_min, distance_nm, payload_lbs, demo,
            review_status, pilot_id) VALUES (?,?,?,?,?,?,?,?,?,?, 'PAC0001')""", (now - ago_days * 86400, "PAC1", ac, dep, arr, 120, 500, lbs, demo, review))
    pirep("KCVG", "KJFK", 30000, 2); pirep("KCVG", "KJFK", 20000, 3); pirep("KJFK", "EGLL", 90000, 4, ac="B77F")
    pirep("KCVG", "KMIA", 99999, 2, demo=1); pirep("KCVG", "KLAX", 77777, 2, review="Rejected"); pirep("KCVG", "KSEA", 55555, 40)
    def ship(sid, status, station, lbs, goods):
        con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper,
            consignee, commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status, data, created_at, updated_at)
            VALUES (?,?,?,?,'KCVG','EGLL',?,?,'S','C',?,1,?,1,'Standard','[]','SPX','{}',?,?)""",
            (sid, "901-1" + sid[:7], "k" + sid, "x" + sid, station, status, goods, lbs, now, now))
    ship("a" * 32, "DELIVERED", "EGLL", 5000, "Pharmaceuticals"); ship("b" * 32, "DELIVERED", "EGLL", 3000, "Pharmaceuticals")
    ship("c" * 32, "DELIVERED_LATE", "EGLL", 2000, "Flowers"); ship("d" * 32, "AT_STATION", "KJFK", 4000, "Machinery")
    ship("e" * 32, "AT_STATION", "KJFK", 1000, "Mail")

r = c.get("/api/public/network")
d = r.get_json() or {}
check("anyone can see it", r.status_code == 200, r.status_code)
check("only real, accepted flights in the last 30 days count", d.get("flights") == 3 and d.get("freight_lbs") == 140000, (d.get("flights"), d.get("freight_lbs")))
check("busiest lane first, flights on a lane added up", d["lanes"][0]["from"]["icao"] == "KJFK" and d["lanes"][1]["flights"] == 2
      and d["lanes"][1]["lbs"] == 50000, d.get("lanes"))
check("lanes carry coordinates for the map", d["lanes"][0]["from"]["lat"] is not None)
check("on-time share of deliveries", d.get("delivered") == 3 and d.get("on_time_pct") == 67, (d.get("delivered"), d.get("on_time_pct")))
check("freight waiting, by station", d["waiting"][0]["icao"] == "KJFK" and d["waiting"][0]["shipments"] == 2 and d["waiting"][0]["lbs"] == 5000, d.get("waiting"))
check("what we carried, by weight", d["goods"][0]["commodity"] == "Pharmaceuticals" and d["goods"][0]["lbs"] == 8000, d.get("goods"))
check("aircraft names for the types list", d.get("fleet_names", {}).get("B77F", "B77F") != "B77F")
check("no pilot ids in the public figures", "PAC0001" not in json.dumps(d))
check("the page opens for anyone", c.get("/network").status_code == 200)
with A.db() as con:
    empty = network_stats.stats(con, A.AIRPORTS, now=now + 400 * 86400)
check("a quiet month reads as zeros, not an error", empty["flights"] == 0 and empty["freight_lbs"] == 0 and empty["lanes"] == [])

print("\nNETWORK TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
