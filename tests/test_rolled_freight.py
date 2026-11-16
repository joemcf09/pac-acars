"""Rolled freight: waiting orders that sit past deadline are withdrawn to another carrier, PAC forfeits the
revenue to the company ledger (never the pilots), and a digest news post is written."""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cargo_orders
import company

con = sqlite3.connect(":memory:")
con.row_factory = sqlite3.Row
con.execute("""CREATE TABLE cargo_shipments (id TEXT, awb TEXT, booking_key TEXT, source_awb TEXT, origin TEXT, destination TEXT,
    current_station TEXT, status TEXT, shipper TEXT, consignee TEXT, commodity TEXT, pieces INT, gross_weight_lbs REAL,
    chargeable_weight_kg REAL, priority TEXT, handling TEXT, security_status TEXT, reserved_booking_key TEXT,
    reserved_previous_status TEXT, data TEXT, created_at REAL, updated_at REAL)""")
con.execute("""CREATE TABLE cargo_movements (shipment_id TEXT, event_key TEXT UNIQUE, event_type TEXT, event_time REAL,
    from_station TEXT, to_station TEXT, pilot_id TEXT, flight_number TEXT, status TEXT, details TEXT)""")
con.execute("CREATE TABLE news (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, kind TEXT, title TEXT, body TEXT, important INT, expires REAL, author TEXT)")

now = time.time()
fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got}]"))
    if not ok:
        fails.append(name)

def add_order(sid, service, chg_kg, deadline):
    data = {"deadline": deadline, "service": service, "agent": "Kuehne+Nagel"}
    con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, origin, destination, current_station, status,
        gross_weight_lbs, chargeable_weight_kg, priority, reserved_booking_key, data, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, "123-"+sid, f"ORDER:{sid}", "VHHH", "ELLX", "VHHH", "AT_STATION", chg_kg*2.20462, chg_kg, service, None,
         json.dumps(data), now, now))

# one shipment fresh (not past deadline), one well past deadline+1day
add_order("fresh", "EXPRESS", 1000, now + 10 * 3600)
add_order("stale", "EXPRESS", 2000, now - 2 * 86400)

gone = cargo_orders.withdraw_stale(con, now)
check("only the stale order is rolled", gone == 1, gone)

statuses = {r["id"]: r["status"] for r in con.execute("SELECT id, status FROM cargo_shipments")}
check("stale order is WITHDRAWN", statuses["stale"] == "WITHDRAWN", statuses)
check("fresh order is untouched", statuses["fresh"] == "AT_STATION", statuses)

# EXPRESS rate midpoint is (5.5+8.5)/2 = 7.0 per chargeable kg; 2000 kg -> ~14,000
ledger = con.execute("SELECT kind, amount, description FROM company_ledger").fetchall()
check("one rolled_freight ledger line", len(ledger) == 1 and ledger[0]["kind"] == "rolled_freight", [dict(r) for r in ledger])
check("the loss is negative (company pays, ~ -14000)", ledger and ledger[0]["amount"] < 0 and abs(ledger[0]["amount"] + 14000) < 1, ledger and ledger[0]["amount"])
check("ledger total matches the forfeit", round(company.ledger_total(con)) == round(ledger[0]["amount"]), company.ledger_total(con))

mv = con.execute("SELECT details FROM cargo_movements WHERE shipment_id='stale'").fetchone()
det = json.loads(mv["details"]) if mv else {}
check("movement names a carrier and the forfeit", det.get("carrier") in cargo_orders.CARRIERS and det.get("forfeited") > 0, det)

news = con.execute("SELECT title, body FROM news").fetchall()
check("a digest news post is written", len(news) == 1 and "rolled" in news[0]["title"].lower(), [dict(r) for r in news])
check("news names the forfeited revenue", news and "$" in news[0]["body"], news and news[0]["body"])

# idempotency: running again rolls nothing new (stale already WITHDRAWN)
gone2 = cargo_orders.withdraw_stale(con, now)
check("second run rolls nothing (idempotent)", gone2 == 0, gone2)
check("still just one ledger line", con.execute("SELECT COUNT(*) FROM company_ledger").fetchone()[0] == 1)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
