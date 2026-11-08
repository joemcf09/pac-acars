"""The cargo folder (full air waybill, acceptance and tracking per shipment) and the after-action debrief.

Run from the PAC folder:   python tests/test_cargo_folder.py
"""
import os
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
c.post("/api/auth/setup", json={"password": "Cargo-Folder-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False})

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

print()
print("All cargo folder checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
