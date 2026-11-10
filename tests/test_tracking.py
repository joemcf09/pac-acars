"""Public air waybill tracking: a shipment's recorded movements read as Cargo-IMP events, open to anyone with the number.
Run from the PAC folder: python tests/test_tracking.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-track-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import cargo_track  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Track-Test-1"})
c.post("/api/auth/logout")

print("Numbers")
check("dashes and spaces are fine", cargo_track.normalize("901 1000 0123") == "901-10000123" and cargo_track.normalize("90110000123") == "901-10000123")
check("junk is refused", cargo_track.normalize("abc") is None and cargo_track.normalize("901-123") is None)

now = time.time() - 3600
def shipment(con, sid, awb, status, station):
    con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper,
        consignee, commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status, data, created_at, updated_at)
        VALUES (?,?,?,?,'KCVG','EGLL',?,?,'Secret Shipper Ltd','Secret Consignee','Pharmaceuticals',12,4410,2000,'Priority','[]','SPX',?,?,?)""",
        (sid, awb, "k" + sid, awb, station, status, json.dumps({"shc": ["PIL", "COL"], "deadline": now + 86400}), now, now))
def move(con, sid, key, kind, t, frm, to, status, pirep=None, details=None):
    con.execute("""INSERT INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id,
        flight_number, pirep_id, status, details) VALUES (?,?,?,?,?,?,'PAC0001','PAC1234',?,?,?)""",
        (sid, key, kind, t, frm, to, pirep, status, json.dumps(details or {})))

with A.db() as con:
    shipment(con, "a" * 32, "901-10000123", "DELIVERED", "EGLL")
    move(con, "a" * 32, "b1", "BOOKED", now, None, "KCVG", "BOOKED")
    move(con, "a" * 32, "c1", "CLAIMED", now + 10, "KCVG", "KCVG", "BOOKED")
    move(con, "a" * 32, "f1", "FLIGHT_ARRIVAL", now + 30000, "KCVG", "EGLL", "DELIVERED")
    shipment(con, "b" * 32, "901-10000134", "AT_STATION", "KJFK")
    move(con, "b" * 32, "b2", "BOOKED", now, None, "KCVG", "BOOKED")
    move(con, "b" * 32, "f2", "FLIGHT_ARRIVAL", now + 9000, "KCVG", "KJFK", "AT_STATION")

print("Tracking")
r = c.get("/api/public/track/901-10000123")
j = r.get_json() or {}
codes = [e["code"] for e in j.get("events", [])]
check("anyone can track without signing in", r.status_code == 200, r.status_code)
check("delivered shipment reads RCS, BKD, DEP, ARR, DLV", codes == ["RCS", "BKD", "DEP", "ARR", "DLV"], codes)
check("status and goods shown", j.get("status_text") == "Delivered" and j.get("goods") == "Pharmaceuticals" and j.get("weight_kg") == 2000)
check("special handling codes shown", j.get("handling") == ["PIL", "COL"], j.get("handling"))
check("city names for the stations", j.get("places", {}).get("KCVG") not in (None, "KCVG"), j.get("places"))
blob = json.dumps(j)
check("no pilot ids, shipper or consignee names in public view", "PAC0001" not in blob and "Secret" not in blob)
check("holds are not shown", "CLAIMED" not in blob)
j2 = c.get("/api/public/track/90110000134").get_json() or {}
check("freight at a transfer station: RCF waiting for onward flight", [e["code"] for e in j2.get("events", [])][-1:] == ["RCF"]
      and j2.get("station") == "KJFK", j2.get("events"))
check("unknown number: 404", c.get("/api/public/track/901-99999999").status_code == 404)
check("bad number: 400", c.get("/api/public/track/hello").status_code == 400)
check("the page opens for anyone", c.get("/track/901-10000123").status_code == 200 and c.get("/track").status_code == 200)

print("\nTRACKING TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
