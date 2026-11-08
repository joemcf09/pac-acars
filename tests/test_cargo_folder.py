"""The cargo folder (full air waybill, acceptance and tracking per shipment) and the after-action debrief.

Run from the PAC folder:   python tests/test_cargo_folder.py
"""
import os
import copy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-cargo-folder-") as temp:
        data = Path(temp) / "data"
        data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        env = os.environ.copy()
        env["PAC_DATA_DIR"] = str(data)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--isolated"],
                                cwd=ROOT, env=env, check=False)
        sys.exit(result.returncode)

if len(sys.argv) != 2 or sys.argv[1] != "--isolated" or not os.environ.get("PAC_DATA_DIR"):
    raise SystemExit("Run this test without arguments; it creates and removes an isolated data directory.")

isolated_data = Path(os.environ["PAC_DATA_DIR"]).resolve()
temp_root = Path(tempfile.gettempdir()).resolve()
if (isolated_data.name != "data"
        or not isolated_data.parent.name.startswith("pac-cargo-folder-")
        or isolated_data.parent.parent != temp_root):
    raise SystemExit("Refusing to run outside the temporary cargo-test data directory.")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import analysis  # noqa: E402
import app as A  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
guest_cargo = A.app.test_client().get("/api/cargo/shipments")
check("cargo inventory API requires sign-in", guest_cargo.status_code == 401)
c.post("/api/auth/setup", json={"password": "Cargo-Folder-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False})
inventory_page = c.get("/")
check("cargo inventory is linked from Operations navigation",
      inventory_page.status_code == 200 and b"Cargo inventory" in inventory_page.data
      and b'id="view-cargo"' in inventory_page.data)

print("Air waybills on the preliminary load sheet")
ls = c.post("/api/plan/loadsheet", json={"mission_id": "PAC712", "aircraft": "B77F"}).json
sh = ls.get("shipments") or []
a = (sh[0] if sh else {}).get("awb_doc") or {}
check("every shipment has a waybill", sh and all(s.get("awb_doc") for s in sh), len(sh))
check("chargeable weight is the greater of gross and volumetric", a and a["chg_kg"] >= max(a["kg"], a["vol_kg"]) - 0.01, a and (a["kg"], a["vol_kg"], a["chg_kg"]))
check("volumetric weight uses 6,000 cm3 per kg", a and abs(a["vol_kg"] - a["vol_m3"] * 1e6 / 6000) < 0.2, a and (a["vol_m3"], a["vol_kg"]))
check("pieces add up across the dimension lines", a and sum(g["n"] for g in a["dims"]) == sh[0]["pieces"])
check("vaccines carry the vaccine HS heading", a.get("hs") == "3002.41", a.get("hs"))
check("cold chain stays +2 to +8 even with dry ice aboard", "+2 C TO +8 C" in a.get("temp", ""), a.get("temp"))
check("total = weight charge + other charges", abs(a["total"] - a["freight"] - sum(o["amt"] for o in a["others"])) < 0.02)
check("acceptance checks and tracking are there", len(a["checks"]) >= 6 and [t["code"] for t in a["track"]][:2] == ["BKD", "RCS"])
check("no accents in waybill text", all(ch.isascii() for ch in a["issued_at"] + a["shipper_addr"] + a["consignee_addr"]))
again = c.post("/api/plan/loadsheet", json={"mission_id": "PAC712", "aircraft": "B77F", "seed": ls["seed"]}).json
check("the same seed gives the same waybills", again["shipments"][0]["awb_doc"]["total"] == a["total"])

print("The release keeps them")
b = c.post("/api/booking", json={"mission_id": "PAC712", "aircraft": "B77F", "airframe": None, "seed": ls["seed"], "zone_ack": True}).json
d = c.get("/api/dispatch").json
check("dispatch carries a waybill per shipment", all(s.get("awb_doc") for s in d.get("shipments") or []) and d.get("shipments"))
with A.db() as con:
    cargo_rows = con.execute("SELECT id, awb, status, current_station FROM cargo_shipments ORDER BY awb").fetchall()
check("booking creates one persistent record per shipment", len(cargo_rows) == len(d["shipments"]),
      (len(cargo_rows), len(d["shipments"])))
check("persistent AWBs match the dispatch paperwork",
      {row["awb"] for row in cargo_rows} == {s["awb"] for s in d["shipments"]})
check("booked cargo starts at the departure station",
      all(row["status"] == "BOOKED" and row["current_station"] == "EBLG" for row in cargo_rows))
original_ids = {row["id"] for row in cargo_rows}
with A.db() as con:
    A.cargo_network.register_booking(con, b, "PAC0001")
    reloaded_ids = {row["id"] for row in con.execute("SELECT id FROM cargo_shipments")}
check("re-saving a booking preserves shipment identity", original_ids == reloaded_ids)

print("After-action debrief")
rw = analysis.runways(A.DATA)
c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
rec = FlightRecorder(b)
for s in fly("EBLG", rw["EBLG"][0][0], "HKJK", rw["HKJK"][0][0], td_fpm=-720):
    rec.update(s)
c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
p = c.post("/api/pirep", json={"remarks": "cargo folder"}).json
db = p.get("debrief") or {}
check("the PIREP has a debrief", db.get("planned_actual") and db.get("dispatcher"), list(db))
check("a hard landing with pharma aboard upsets the customer", (db.get("customer") or {}).get("tone") == "bad", db.get("customer"))
check("every waybill has a delivery result", len(db.get("cargo") or []) == len(d["shipments"]) and all(x["status"].startswith("DELIVERED") for x in db["cargo"]))
row = next((r for r in db["planned_actual"] if r["what"].startswith("Payload")), None)
check("payload is compared with what the type can carry", row and row.get("ok") is True, row)
lb = c.get(f"/api/logbook/{p['id']}").json
check("the debrief is kept in the logbook", (lb.get("detail") or {}).get("debrief", {}).get("dispatcher") == db["dispatcher"])
with A.db() as con:
    cargo_rows = con.execute("SELECT id, awb, status, current_station FROM cargo_shipments ORDER BY awb").fetchall()
    movement_rows = con.execute("SELECT shipment_id, event_type, pirep_id FROM cargo_movements ORDER BY id").fetchall()
check("PIREP filing records completed cargo movement",
      all(row["status"] == "DELIVERED" and row["current_station"] == p["arr"] for row in cargo_rows))
check("each shipment has one booking and one flight movement",
      len(movement_rows) == len(cargo_rows) * 2
      and sum(row["event_type"] == "FLIGHT_ARRIVAL" and row["pirep_id"] == p["id"] for row in movement_rows) == len(cargo_rows))
with A.db() as con:
    A.cargo_network.record_flight(con, b, p, p["id"], "PAC0001")
    repeated_movements = con.execute("SELECT COUNT(*) FROM cargo_movements WHERE event_type='FLIGHT_ARRIVAL' AND pirep_id=?",
                                     (p["id"],)).fetchone()[0]
check("replaying the same PIREP does not duplicate cargo movement", repeated_movements == len(cargo_rows))
duplicate = copy.deepcopy(b)
duplicate["requested_at"] += 1
for shipment in duplicate["dispatch"]["shipments"]:
    shipment.pop("shipment_id", None)
    shipment.pop("cargo_source_awb", None)
with A.db() as con:
    A.cargo_network.register_booking(con, duplicate, "PAC0002")
    duplicate_awbs = {row["awb"] for row in con.execute(
        "SELECT awb FROM cargo_shipments WHERE booking_key LIKE 'PAC0002:%'")}
check("a separate booking receives globally unique permanent AWBs",
      len(duplicate_awbs) == len(d["shipments"]) and not duplicate_awbs.intersection({s["awb"] for s in d["shipments"]}))
inventory = c.get(f"/api/cargo/shipments?station={p['arr']}&status=DELIVERED").json
check("cargo inventory API filters by current station and status",
      inventory.get("total") == len(d["shipments"])
      and all(x["current_station"] == p["arr"] and x["status"] == "DELIVERED" for x in inventory["shipments"]), inventory)
station_list = c.get("/api/cargo/stations").json
check("cargo inventory exposes stations with shipment counts",
      any(x["icao"] == p["arr"] and x["shipments"] == len(d["shipments"]) for x in station_list), station_list)
detail_response = c.get(f"/api/cargo/shipments/{cargo_rows[0]['id']}")
detail = detail_response.json
check("shipment detail API returns its recorded flight history",
      detail_response.status_code == 200 and detail.get("shipment", {}).get("current_station") == p["arr"]
      and any(x.get("pirep_id") == p["id"] and x.get("to_station") == p["arr"] for x in detail.get("movements", [])),
      (detail_response.status_code, detail))
check("cargo inventory rejects malformed station filters",
      c.get("/api/cargo/shipments?station=INVALID!").status_code == 400)

print()
print("All cargo folder checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
