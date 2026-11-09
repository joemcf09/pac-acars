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

print("Freight for a town near the destination (last leg by truck)")
O.TRUCK_SHARE = 1.0
with A.db() as con:
    con.execute("UPDATE cargo_shipments SET status='WITHDRAWN' WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION'")
    O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings(), force=True)
    tr = [r for r in con.execute("SELECT * FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION'")
          if '"truck_from"' in r["data"]]
O.TRUCK_SHARE = 0.3
check("some orders are booked to a town near a PAC destination", len(tr) > 0, len(tr))
import json as _j
tk = None
for r3 in tr:
    via = _j.loads(r3["data"])["truck_from"]
    rt3 = next(((r, a) for r in A.ROUTES.values() if r["origin"]["icao"] == r3["current_station"] and r["destination"]["icao"] == via
                and r.get("category") == "Scheduled" for a in r["aircraft"] if A.FLEET.get(a, {}).get("max_payload_lbs", 0) >= r3["gross_weight_lbs"] * 2), None)
    if rt3:
        tk = (r3, rt3); break
r3, (route3, ac3) = tk
nm = A._airport_nm(route3["destination"]["icao"], r3["destination"])
check("the truck leg is 300 nm or less and PAC doesn't fly it", nm <= 300 and not A.cargo_network.has_route(A.ROUTES.values(), route3["destination"]["icao"], r3["destination"]), nm)
ls3 = c.post("/api/plan/loadsheet", json={"mission_id": route3["id"], "aircraft": ac3}).json
opt = next((t for t in ls3["transfer_options"] if t["id"] == r3["id"]), None)
check("the load sheet offers it, marked by truck", opt and opt.get("truck_nm"), opt)
ov = c.get("/api/cargo/overview").json
grp = next((g for g in ov["waiting"] if g["destination"] == r3["destination"] and g["station"] == r3["current_station"]), None)
check("Find a flight knows which flights reach it", grp and route3["destination"]["icao"] in grp["fly_to"], grp)
c.delete("/api/booking")
ls3 = c.post("/api/plan/loadsheet", json={"mission_id": route3["id"], "aircraft": ac3, "cargo_transfer_ids": [r3["id"]]}).json
b3 = c.post("/api/booking", json={"mission_id": route3["id"], "aircraft": ac3, "manifest_seed": ls3["seed"], "cargo_transfer_ids": [r3["id"]], "zone_ack": True}).json
o3, d3 = route3["origin"]["icao"], route3["destination"]["icao"]
c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b3["requested_at"]})
rec3 = FlightRecorder(b3)
for s_ in fly(o3, rw[o3][0][0], d3, rw[d3][0][0], td_fpm=-150):
    rec3.update(s_)
c.post("/api/acars/app/complete", json={"record": rec3.export(), "requested_at": b3["requested_at"], "source": "MSFS"})
c.post("/api/pirep", json={"remarks": "truck"})
with A.db() as con:
    f4 = con.execute("SELECT status, current_station, destination FROM cargo_shipments WHERE id=?", (r3["id"],)).fetchone()
    det = con.execute("SELECT details FROM cargo_movements WHERE shipment_id=? AND event_type='FLIGHT_ARRIVAL'", (r3["id"],)).fetchone()[0]
check("flying it to the nearby airport delivers it by truck", f4["status"].startswith("DELIVERED") and f4["current_station"] == f4["destination"]
      and '"trucked_from"' in det, (dict(f4), det))

print("Cargo seasons")
import calendar as _cal
nov9 = _cal.timegm((2026, 11, 9, 12, 0, 0))
with A.db() as con:
    rs = O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings(), now=nov9, force=True)
    sea = con.execute("SELECT json_extract(data,'$.season') AS s, commodity, origin, destination FROM cargo_shipments WHERE json_extract(data,'$.season') IS NOT NULL").fetchall()
    news = con.execute("SELECT title FROM news WHERE title LIKE 'Cargo season:%'").fetchall()
ids = {r["s"] for r in sea}
check("in early November, Beaujolais Nouveau and Peruvian berries are in season", {"beaujolais", "berries"} <= ids, ids)
bj = [r for r in sea if r["s"] == "beaujolais"]
check("Beaujolais orders carry wine out of France or Frankfurt/Brussels", bj and all(r["origin"][:2] in ("LF", "ED", "EB") for r in bj)
      and any("wine" in (r["commodity"] or "").lower() for r in bj), [tuple(r) for r in bj[:3]])
check("each season is announced once", sorted(n[0] for n in news) == ["Cargo season: Beaujolais Nouveau", "Cargo season: Peruvian blueberries and asparagus"], [n[0] for n in news])
with A.db() as con:
    O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings(), now=nov9 + 3600, force=True)
    again = con.execute("SELECT COUNT(*) FROM news WHERE title LIKE 'Cargo season:%'").fetchone()[0]
check("…and not again on the next restock", again == 2, again)

print("Warehouses that fill up")
import uuid as _u
with A.db() as con:
    for i in range(20):      # someone left a lot of freight at KMIA
        sid_ = _u.uuid4().hex
        con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper, consignee,
            commodity, pieces, gross_weight_lbs, handling, data, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid_, f"901-9{i:07d}", "X", f"S{i}", "KCVG", "SKBO", "KMIA", "AT_STATION", "A", "B", "Freight", 10, 7000, "[]", "{}", time.time(), time.time()))
    before = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE current_station='KMIA' AND booking_key LIKE 'ORDER:%' AND status='AT_STATION'").fetchone()[0]
    con.execute("UPDATE cargo_shipments SET status='WITHDRAWN' WHERE current_station='KMIA' AND booking_key LIKE 'ORDER:%'")
    rk = O.tick(con, A.ROUTES.values(), A.FLEET, A.dispatch_pilot(), A.settings(), force=True)
    after = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE current_station='KMIA' AND booking_key LIKE 'ORDER:%' AND status='AT_STATION'").fetchone()[0]
    emb = A.warehouses.embargoed(con, "KMIA")
    mia_route = next(r for r in A.ROUTES.values() if r["origin"]["icao"] == "KMIA" and r.get("category") == "Scheduled")
    topped = O.ensure_route(con, mia_route, A.FLEET, A.dispatch_pilot(), mia_route["aircraft"][0], A.settings(), now=time.time() + 99999, routes=A.ROUTES.values())
check("a congested shed takes no new customer orders", emb and after == 0 and topped == 0, (rk, before, after, emb, topped))
ov = c.get("/api/cargo/overview").json
mia = next((x for x in ov["sheds"] if x["station"] == "KMIA"), None)
check("the Cargo inventory shows it as congested or full", mia and mia["level"] in ("Congested", "Full") and mia["pct"] >= 85, mia)
stk = c.get("/api/staff/cargo-stock").json
check("staff see each station's shed", next(x for x in stk["stations"] if x["icao"] == "KMIA")["shed_pct"] >= 85)
with A.db() as con:
    con.execute("DELETE FROM cargo_shipments WHERE booking_key='X'")

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
