"""Split-load recovery stays loadable, traceable, and idempotent.
Run from the PAC folder: python tests/test_volume_recovery.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-volume-recovery-") as temp:
        data = Path(temp) / "data"
        data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT,
                                env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import cargo_network
import economics
import volume

mission = volume.booking_mission(A.ROUTES["PAC2020"], "B752F", A.FLEET, {"volumetric_loading": True})
assert mission.get("volume_cap")
booking = {"mission": mission, "aircraft": "B752F", "ofp": None, "flight_number": "PAC2020",
           "airframe": None, "requested_at": 1_789_990_000, "manifest_seed": "RECOVERY-TEST"}
booking["dispatch"] = A.build_dispatch_with_transfers(booking, [])
carried = sum(s["weight_lbs"] for s in booking["dispatch"]["shipments"])
assert carried == mission["payload_lbs"]

with A.db() as con:
    cargo_network.register_booking(con, booking, "PAC0001")
    p = {"status": "Delivered", "review_status": "Accepted", "demo": False}
    awbs = cargo_network.create_volume_recovery(con, booking, p, 19, "PAC0001", A.FLEET, A.dispatch_pilot())
    again = cargo_network.create_volume_recovery(con, booking, p, 19, "PAC0001", A.FLEET, A.dispatch_pilot())
    rows = con.execute("SELECT * FROM cargo_shipments WHERE booking_key=?",
                       (f"RECOVERY:PAC0001:{booking['requested_at']}",)).fetchall()
    assert awbs and awbs == again and len(rows) == len(awbs)
    assert sum(round(r["gross_weight_lbs"]) for r in rows) == mission["volume_cap"]["from_lbs"] - carried
    assert all(r["status"] == "AT_STATION" and r["current_station"] == mission["origin"]["icao"]
               and json.loads(r["data"])["unit_details"] for r in rows)
    assert all([e["code"] for e in json.loads(r["data"])["awb_doc"]["track"]] == ["BKD", "RCS"]
               and json.loads(r["data"])["awb_doc"]["total"] == 0 for r in rows)
    cargo_network.set_flight_outcome(con, 19, accepted=False)
    assert all(con.execute("SELECT status FROM cargo_shipments WHERE id=?", (r["id"],)).fetchone()[0] == "WITHDRAWN"
               for r in rows)
    cargo_network.set_flight_outcome(con, 19, accepted=True)
    assert all(con.execute("SELECT status FROM cargo_shipments WHERE id=?", (r["id"],)).fetchone()[0] == "AT_STATION"
               for r in rows)
    options = cargo_network.transfer_options(con, mission["origin"]["icao"],
                                             mission["destination"]["icao"], A.ROUTES.values(), "PAC0001")
    selected = [x for x in options if x["awb"] == awbs[0]]
    assert selected and selected[0]["data"]["recovery_for"] == "PAC2020"
    assert selected[0]["data"]["recovery_source_awbs"]
    source = con.execute("SELECT data FROM cargo_shipments WHERE booking_key=? LIMIT 1",
                         (f"PAC0001:{booking['requested_at']}",)).fetchone()
    assert json.loads(source["data"])["recovery_awbs"] == awbs

next_booking = {"mission": A.ROUTES["PAC2020"], "aircraft": "B752F", "ofp": None,
                "flight_number": "PAC2021", "requested_at": 1_789_990_100, "manifest_seed": "RECOVERY-NEXT",
                "cargo_transfer_weight_lbs": selected[0]["gross_weight_lbs"]}
next_booking["dispatch"] = A.build_dispatch_with_transfers(next_booking, selected)
recovered = [s for s in next_booking["dispatch"]["shipments"] if s.get("transfer")]
assert len(recovered) == 1 and recovered[0]["awb"] == awbs[0]
assert recovered[0]["recovery_prepaid_lbs"] == recovered[0]["weight_lbs"]
p2 = {"payload_lbs": next_booking["dispatch"]["totals"]["weight_lbs"], "block_min": 60,
      "fuel_used_lbs": 9000, "status": "Delivered", "landing_rate": -200}
actual = economics.flight_economics(p2, next_booking, A.FLEET, {}, 1000)
without_recovery = dict(next_booking, dispatch={"shipments": []})
full = economics.flight_economics(p2, without_recovery, A.FLEET, {}, 1000)
assert actual["revenue"] < full["revenue"]
with A.db() as con:
    cargo_network.register_booking(con, next_booking, "PAC0001")
    cargo_network.record_flight(con, next_booking, {"arr": mission["destination"]["icao"],
                                                "status": "Delivered", "cargo_care": []}, 20, "PAC0001")
    delivered = con.execute("SELECT status, current_station, data FROM cargo_shipments WHERE id=?",
                            (selected[0]["id"],)).fetchone()
    assert delivered["status"] == "DELIVERED" and delivered["current_station"] == mission["destination"]["icao"]
    assert json.loads(delivered["data"])["recovery_prepaid_lbs"] == selected[0]["gross_weight_lbs"]

over_ofp = dict(booking, ofp={"payload_lbs": mission["volume_cap"]["from_lbs"]})
over_manifest = A.build_dispatch_with_transfers(over_ofp, [])
assert over_manifest["totals"]["weight_lbs"] == mission["payload_lbs"]
errors, _ = A.validate_ofp({"origin": mission["origin"], "destination": mission["destination"],
                             "payload_lbs": mission["volume_cap"]["from_lbs"]}, mission, "B752F")
assert any("fills" in error for error in errors)
print("VOLUME RECOVERY TESTS PASSED")
