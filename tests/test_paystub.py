"""Pay statement: the period breakdown groups earnings and deductions, includes base pay from the payroll run
(issued after the week closes), and the notification helpers are one-shot per pilot per period."""
import datetime as dt
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import payroll

con = sqlite3.connect(":memory:")
con.row_factory = sqlite3.Row
con.execute("CREATE TABLE pireps (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, demo INT, review_status TEXT, filed_at REAL, block_min REAL)")
con.execute("CREATE TABLE wallet (pilot_id TEXT, time REAL, kind TEXT, amount REAL, description TEXT, pirep_id TEXT)")
con.execute("CREATE TABLE pilots (id TEXT PRIMARY KEY, name TEXT, discord_id TEXT)")
con.execute("INSERT INTO pilots VALUES ('PAC0007','Joseph Pagani','99988877')")
con.execute("INSERT INTO pilots VALUES ('PAC0008','No Discord', NULL)")
payroll.migrate(con)

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got}]"))
    if not ok:
        fails.append(name)

now = time.time()
key, start, end = payroll.recent_periods(now)[-1]
ws = dt.datetime(start.year, start.month, start.day, 12, tzinfo=dt.timezone.utc).timestamp()

# wallet activity inside the completed week: flight pay + profit share + a shop deduction
con.execute("INSERT INTO wallet VALUES ('PAC0007',?,'flight_pay',420,'leg','p1')", (ws + 3600,))
con.execute("INSERT INTO wallet VALUES ('PAC0007',?,'profit_share',55,'share','p1')", (ws + 3700,))
con.execute("INSERT INTO wallet VALUES ('PAC0007',?,'shop',-200,'patch',NULL)", (ws + 7200,))
con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at, block_min) VALUES ('PAC0007',0,'Accepted',?,90)", (ws + 3600,))
# base pay issued AFTER the week closed (now), recorded against the period
con.execute("INSERT INTO wallet VALUES ('PAC0007',?,'base_pay',2500,'base',NULL)", (now,))
con.execute("INSERT INTO payroll_runs (pilot_id, period, issued_at, base, rank) VALUES ('PAC0007',?,?,2500,'Captain')", (key, now))

s = payroll.statement(con, "PAC0007", key)
earn = {l["kind"]: l["amount"] for l in s["lines"]}
ded = {d["kind"]: d["amount"] for d in s["deductions"]}
check("flight pay in earnings", earn.get("flight_pay") == 420, earn)
check("profit share in earnings", earn.get("profit_share") == 55, earn)
check("base pay counted from the payroll run, not double", earn.get("base_pay") == 2500, earn)
check("shop is a deduction", ded.get("shop") == -200, ded)
check("gross = 420+55+2500", s["gross"] == 2975, s["gross"])
check("net = gross - 200", s["net"] == 2775, s["net"])
check("flights and block hours reflect the week", s["flights"] == 1 and s["block_hours"] == 1.5, (s["flights"], s["block_hours"]))
check("period label present", bool(s["period_label"]), s["period_label"])

# notifications: one pending until marked
pend = payroll.pending_site(con, "PAC0007")
check("a site notification is pending", pend and pend["period"] == key, pend)
payroll.mark_notified(con, "PAC0007", key)
check("after marking, nothing pending", payroll.pending_site(con, "PAC0007") is None)

# DM due only for the pilot with a linked Discord
con.execute("INSERT INTO payroll_runs (pilot_id, period, issued_at, base, rank) VALUES ('PAC0008',?,?,500,'Cadet')", (key, now))
due = payroll.dm_due(con, "https://pac-va.com")
ids = {d["pilot_id"] for d in due}
check("DM due for the linked pilot", "PAC0007" in ids, ids)
check("no DM for the pilot without Discord", "PAC0008" not in ids, ids)
check("DM text mentions the net and the site", due and "pac-va.com" in due[0]["text"] and "$" in due[0]["text"], due and due[0]["text"])
payroll.mark_dmed(con, due)
check("after marking sent, no DM due", payroll.dm_due(con, "https://pac-va.com") == [])

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
