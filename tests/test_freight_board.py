"""Freight board and claims: hold waiting freight (website or Discord /claim), others can't take it, it's announced
when delivered. Run from the PAC folder: python tests/test_freight_board.py"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-board-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import analysis  # noqa: E402
import app as A  # noqa: E402
import botlink as B  # noqa: E402
import cargo_orders as O  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Board-Test-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False})
c.get("/api/cargo/overview")
with A.db() as con:
    con.execute("UPDATE pilots SET discord_id='12345' WHERE id='PAC0001'")
    con.execute("INSERT OR IGNORE INTO pilots (id, name, status) VALUES ('PAC0002','Alex B.','Active')")
    order = next(r for r in con.execute("SELECT * FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION' AND current_station='KCVG'"))
print("Claiming")
r = c.post(f"/api/cargo/shipments/{order['id']}/claim")
check("a pilot can hold waiting freight for 24 hours", r.status_code == 200 and r.json["until"] > time.time() + 23 * 3600, r.json)
with A.db() as con:
    try:
        A.cargo_network.claim(con, order["id"], "PAC0002"); took = True
    except ValueError:
        took = False
check("another pilot can't take held freight", not took)
route = next(rt for rt in A.ROUTES.values() if rt["origin"]["icao"] == "KCVG" and rt["destination"]["icao"] == order["destination"] and rt.get("category") == "Scheduled")
ac = next(a for a in route["aircraft"] if A.FLEET.get(a, {}).get("max_payload_lbs", 0) >= order["gross_weight_lbs"] * 2)
ls = c.post("/api/plan/loadsheet", json={"mission_id": route["id"], "aircraft": ac}).json
mine = next((t for t in ls["transfer_options"] if t["id"] == order["id"]), None)
check("it shows first on the holder's load sheet, marked held for them", mine and mine["claimed_by_me"] and ls["transfer_options"][0]["id"] == order["id"], ls["transfer_options"][:1])
with A.db() as con:
    others = A.cargo_network.transfer_options(con, "KCVG", order["destination"], A.ROUTES.values(), "PAC0002")
check("other pilots don't see it", all(t["id"] != order["id"] for t in others))
print("Discord /claim")
with A.app.test_request_context():
    pass
with A.db() as con:
    o2 = next(r for r in con.execute("SELECT * FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION' AND claimed_by IS NULL"))
    con.execute("DELETE FROM cargo_shipments WHERE id!=? AND id!=? AND booking_key LIKE 'ORDER:%' AND claimed_by IS NULL AND id IN (SELECT id FROM cargo_shipments LIMIT 0)", (order["id"], o2["id"]))
bot = A.app.test_client()          # the bot isn't signed in: it uses its secret, like the real one on the server
H = {"X-PAC-Bot": B.secret()}
r = bot.post("/api/bot/claim", json={"discord_id": "12345", "awb": o2["awb"]}, headers=H)
check("/claim with a linked Discord account holds it", r.status_code == 200 and r.json["awb"] == o2["awb"], (r.status_code, r.json))
r = bot.post("/api/bot/claim", json={"discord_id": "999", "awb": o2["awb"]}, headers=H)
check("/claim without a linked account explains how to link", r.status_code == 404 and "/link" in r.json["error"], r.json)
check("/claim without the bot's secret is refused", bot.post("/api/bot/claim", json={"discord_id": "12345", "awb": o2["awb"]}).status_code == 404)
print("Freight board")
fi = B._freight_items
with A.db() as con:
    con.execute("UPDATE cargo_shipments SET data=json_set(data,'$.season','valentines','$.season_name','Valentine''s flowers') WHERE id=?", (o2["id"],))
    items = fi(con, 0, time.time())
check("seasonal freight is posted on the board with a /claim hint", any(i["id"] == o2["awb"] and "/claim" in i["briefing"] for i in items), items[:2])
print("Delivery announcement")
c.delete("/api/booking")
ls = c.post("/api/plan/loadsheet", json={"mission_id": route["id"], "aircraft": ac, "cargo_transfer_ids": [order["id"]]}).json
b = c.post("/api/booking", json={"mission_id": route["id"], "aircraft": ac, "manifest_seed": ls["seed"], "cargo_transfer_ids": [order["id"]], "zone_ack": True}).json
rw = analysis.runways(A.DATA); o, d = route["origin"]["icao"], route["destination"]["icao"]
c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
rec = FlightRecorder(b)
for s_ in fly(o, rw[o][0][0], d, rw[d][0][0], td_fpm=-150):
    rec.update(s_)
c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
B.enabled = lambda: True
c.post("/api/pirep", json={"remarks": "claimed"})
with A.db() as con:
    st = con.execute("SELECT status, claimed_by FROM cargo_shipments WHERE id=?", (order["id"],)).fetchone()
    ev = [r[0] for r in con.execute("SELECT data FROM bot_events WHERE kind='freight_delivered'")]
check("the delivery is announced on Discord", any(order["awb"] in e and "12345" in e for e in ev), ev)
check("delivering it clears the hold", st["status"].startswith("DELIVERED") and st["claimed_by"] is None, dict(st))
print(); print("All freight board checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
