"""Customer orders: freight waiting at stations before anyone books, loaded and delivered like transfer cargo,
withdrawn quietly when nobody takes it. Runs in a temporary data folder.

Run from the PAC folder: python tests/test_cargo_orders.py
"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-cargo-orders-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        env = dict(os.environ, PAC_DATA_DIR=str(data))
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=env).returncode)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import analysis  # noqa: E402
import app as A  # noqa: E402
import cargo_orders as O  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Orders-Test-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False})
print("Stocking")
ov = c.get("/api/cargo/overview").json
with A.db() as con:
    rows = con.execute("SELECT * FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%'").fetchall()
check("opening the cargo page stocks the stations", ov["counts"]["waiting"] > 0 and len(rows) == ov["counts"]["waiting"], ov["counts"])
hub = sum(r["current_station"] == "KCVG" for r in rows)
check("the KCVG hub is stocked to its target", hub >= O.policy(A.settings())["hub_target"], hub)
check("orders never go back where they start", all(r["origin"] != r["destination"] for r in rows))
check("every order has real parties, a deadline and loadable units",
      all(r["shipper"] and r["consignee"] and '"deadline"' in r["data"] and '"unit_details"' in r["data"] for r in rows))
with A.db() as con:
    again = O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings())
check("stocking runs at most every 30 minutes", again["created"] == 0, again)

print("A pilot flies one")
row = next(r for r in rows if r["origin"] == "KCVG")
route, ac = next((r, a) for r in A.ROUTES.values() if r["origin"]["icao"] == "KCVG" and r["destination"]["icao"] == row["destination"]
                 and r.get("category") == "Scheduled" for a in r["aircraft"] if A.FLEET.get(a, {}).get("max_payload_lbs", 0) >= row["gross_weight_lbs"])
ls = c.post("/api/plan/loadsheet", json={"mission_id": route["id"], "aircraft": ac, "cargo_transfer_ids": [row["id"]]}).json
check("the order loads onto the load sheet", any(s["awb"] == row["awb"] for s in ls.get("shipments", [])), ls.get("error"))
b = c.post("/api/booking", json={"mission_id": route["id"], "aircraft": ac, "manifest_seed": ls["seed"], "cargo_transfer_ids": [row["id"]], "zone_ack": True})
check("and books", b.status_code == 200, b.json.get("error"))
b = b.json; rw = analysis.runways(A.DATA); o, d = route["origin"]["icao"], route["destination"]["icao"]
c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
rec = FlightRecorder(b)
for s in fly(o, rw[o][0][0], d, rw[d][0][0], td_fpm=-150):
    rec.update(s)
c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
c.post("/api/pirep", json={"remarks": "order"})
with A.db() as con:
    f = con.execute("SELECT status, current_station FROM cargo_shipments WHERE id=?", (row["id"],)).fetchone()
    h = [x[0] for x in con.execute("SELECT event_type FROM cargo_movements WHERE shipment_id=? ORDER BY id", (row["id"],))]
check("filing delivers it with its history", f["status"].startswith("DELIVERED") and f["current_station"] == d
      and h == ["ORDER_RECEIVED", "TRANSFER_BOOKED", "FLIGHT_ARRIVAL"], (dict(f), h))

print("Freight for the leg you plan")
stocked = set(O.stations(list(A.ROUTES.values()), O.policy(A.settings())["stations"]))
leg = next(r for r in A.ROUTES.values() if r.get("category") == "Scheduled" and r["origin"]["icao"] not in stocked
           and r["origin"]["icao"] != r["destination"]["icao"] and any(a in A.FLEET for a in r["aircraft"]))
lac = next(a for a in leg["aircraft"] if a in A.FLEET)
ls1 = c.post("/api/plan/loadsheet", json={"mission_id": leg["id"], "aircraft": lac}).json
opts = [t for t in ls1.get("transfer_options") or ls1.get("cargo_transfers") or [] if (t.get("destination") == leg["destination"]["icao"])]
with A.db() as con:
    n1 = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE current_station=? AND destination=?", (leg["origin"]["icao"], leg["destination"]["icao"])).fetchone()[0]
check("planning a quiet leg puts customer freight on it", n1 >= 1, (leg["id"], list(ls1)[:30]))
c.post("/api/plan/loadsheet", json={"mission_id": leg["id"], "aircraft": lac})
with A.db() as con:
    n2 = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE current_station=? AND destination=?", (leg["origin"]["icao"], leg["destination"]["icao"])).fetchone()[0]
check("reopening the load sheet doesn't keep adding freight", n2 == n1, (n1, n2))

print("Freight on a booking nobody flies")
row2 = next(r for r in A.cargo_network.transfer_options if False) if False else None
with A.db() as con:
    cand = con.execute("""SELECT * FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION' AND reserved_booking_key IS NULL
        AND current_station='KCVG'""").fetchall()
pick = None
for r2 in cand:
    rt = next(((r, a) for r in A.ROUTES.values() if r["origin"]["icao"] == "KCVG" and r["destination"]["icao"] == r2["destination"]
               and r.get("category") == "Scheduled" for a in r["aircraft"] if A.FLEET.get(a, {}).get("max_payload_lbs", 0) >= r2["gross_weight_lbs"] * 2), None)
    if rt:
        pick = (r2, rt); break
r2, (route2, ac2) = pick
ls2 = c.post("/api/plan/loadsheet", json={"mission_id": route2["id"], "aircraft": ac2, "cargo_transfer_ids": [r2["id"]]}).json
b2 = c.post("/api/booking", json={"mission_id": route2["id"], "aircraft": ac2, "manifest_seed": ls2["seed"], "cargo_transfer_ids": [r2["id"]], "zone_ack": True}).json
with A.db() as con:
    held = con.execute("SELECT reserved_booking_key FROM cargo_shipments WHERE id=?", (r2["id"],)).fetchone()[0]
check("booking reserves the waiting freight", bool(held))
A.release_idle_cargo()
with A.db() as con:
    still = con.execute("SELECT reserved_booking_key FROM cargo_shipments WHERE id=?", (r2["id"],)).fetchone()[0]
check("a fresh booking keeps it", still == held)
saved = A.cargo_network.release_idle.__defaults__
A.cargo_network.release_idle.__defaults__ = ((), None, -1)       # pretend three days have passed
A.release_idle_cargo()
A.cargo_network.release_idle.__defaults__ = saved
with A.db() as con:
    f2 = con.execute("SELECT status, reserved_booking_key FROM cargo_shipments WHERE id=?", (r2["id"],)).fetchone()
    h2 = [x[0] for x in con.execute("SELECT event_type FROM cargo_movements WHERE shipment_id=? ORDER BY id", (r2["id"],))]
check("after three days idle it goes back on the shelf", f2["status"] == "AT_STATION" and f2["reserved_booking_key"] is None and h2[-1] == "TRANSFER_RELEASED", (dict(f2), h2))
o2, d2 = route2["origin"]["icao"], route2["destination"]["icao"]
c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b2["requested_at"]})
rec2 = FlightRecorder(c.get("/api/booking").json.get("booking") or b2)
for s_ in fly(o2, rw[o2][0][0], d2, rw[d2][0][0], td_fpm=-150):
    rec2.update(s_)
c.post("/api/acars/app/complete", json={"record": rec2.export(), "requested_at": b2["requested_at"], "source": "MSFS"})
fr = c.post("/api/pirep", json={"remarks": "late"})
with A.db() as con:
    f3 = con.execute("SELECT status, current_station FROM cargo_shipments WHERE id=?", (r2["id"],)).fetchone()
    own = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE booking_key=? AND status LIKE 'DELIVERED%'", (f"PAC0001:{b2['requested_at']}",)).fetchone()[0]
check("flying the old booking later still files", fr.status_code == 200 and own > 0, (fr.status_code, fr.json.get("error") if fr.is_json else None, own))
check("and the released freight stays behind for someone else", f3["status"] == "AT_STATION" and f3["current_station"] == o2, dict(f3))

print("Unclaimed orders")
with A.db() as con:
    r = O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings(), now=time.time() + 8 * 86400, force=True)
    left = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION' AND created_at<?",
                       (time.time() + 86400,)).fetchone()[0]
    delivered = con.execute("SELECT status FROM cargo_shipments WHERE id=?", (row["id"],)).fetchone()[0]
check("a day past the deadline they go to another carrier", r["withdrawn"] > 0 and left == 0, (r, left))
check("and the station is restocked", r["created"] > 0, r)
check("delivered freight is untouched", delivered.startswith("DELIVERED"), delivered)
c.post("/api/settings", json={"cargo_orders_enabled": False})
with A.db() as con:
    off = O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings(), force=True)
check("staff can switch orders off", off == {"created": 0, "withdrawn": 0}, off)
print()
print("All cargo order checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
