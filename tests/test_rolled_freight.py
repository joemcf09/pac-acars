"""Rolled freight (realistic model): waiting orders that sit past deadline are withdrawn to another carrier. The
box still moves, PAC loses the revenue it could have flown (reported, no cash debit), and the shipper's account
standing drops so it tenders less freight afterwards. Pilots are never charged."""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cargo_orders
import accounts

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

def add_order(sid, service, chg_kg, deadline, shipper="Globe Pharma Ltd"):
    data = {"deadline": deadline, "service": service, "agent": "Kuehne+Nagel"}
    con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, origin, destination, current_station, status,
        shipper, gross_weight_lbs, chargeable_weight_kg, priority, reserved_booking_key, data, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid, "123-"+sid, f"ORDER:{sid}", "VHHH", "ELLX", "VHHH", "AT_STATION", shipper, chg_kg*2.20462, chg_kg, service, None,
         json.dumps(data), now, now))

add_order("fresh", "EXPRESS", 1000, now + 10 * 3600)
add_order("stale", "EXPRESS", 2000, now - 2 * 86400)

gone = cargo_orders.withdraw_stale(con, now)
check("only the stale order is rolled", gone == 1, gone)

statuses = {r["id"]: r["status"] for r in con.execute("SELECT id, status FROM cargo_shipments")}
check("stale order is WITHDRAWN", statuses["stale"] == "WITHDRAWN", statuses)
check("fresh order is untouched", statuses["fresh"] == "AT_STATION", statuses)

# realism: NO cash leaves the treasury (no company_ledger activity from a rollover)
has_ledger = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='company_ledger'").fetchone()
check("no treasury debit: company_ledger not even created by a rollover", has_ledger is None, has_ledger)

mv = con.execute("SELECT details FROM cargo_movements WHERE shipment_id='stale'").fetchone()
det = json.loads(mv["details"]) if mv else {}
# EXPRESS midpoint (5.5+8.5)/2 = 7.0/kg x 2000kg = ~14,000 lost revenue (reported, not debited)
check("movement names a carrier and the lost revenue", det.get("carrier") in cargo_orders.CARRIERS and abs(det.get("lost_revenue", 0) - 14000) < 1, det)

news = con.execute("SELECT title, body FROM news").fetchall()
check("a digest news post is written", len(news) == 1 and "rolled" in news[0]["title"].lower(), [dict(r) for r in news])
check("news frames it as lost revenue AND lost accounts", news and "revenue" in news[0]["body"].lower() and "tender" in news[0]["body"].lower(), news and news[0]["body"])

# the shipper's account standing drops because PAC failed to uplift tendered freight
acc = accounts.compute(con, now)
globe = acc.get("Globe Pharma Ltd")
check("the shipper has a rolled consignment on record", globe and globe["rolled"] == 1, globe)
check("a rollover lowers the account below the 70 baseline", globe and globe["score"] == 62, globe and globe["score"])

# idempotency
gone2 = cargo_orders.withdraw_stale(con, now)
check("second run rolls nothing (idempotent)", gone2 == 0, gone2)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
