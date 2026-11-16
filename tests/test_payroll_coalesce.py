"""A pay catch-up should ping a pilot once (their latest paycheck), not once per backfilled week. When several
weeks are paid at once, only the most recent period stays pending for the site notice and the Discord DM."""
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
con.execute("INSERT INTO pilots VALUES ('MULTI','Multi Week','123123')")
payroll.migrate(con)

def add_tx(pid, kind, amount, desc, pir, c):
    c.execute("INSERT INTO wallet VALUES (?,?,?,?,?,?)", (pid, time.time(), kind, amount, desc, pir))

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got}]"))
    if not ok:
        fails.append(name)

now = time.time()
# the pilot flew in every one of the 4 complete lookback weeks
for key, start, end in payroll.recent_periods(now):
    mid = dt.datetime(start.year, start.month, start.day, 12, tzinfo=dt.timezone.utc).timestamp() + 2 * 86400
    con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at, block_min) VALUES ('MULTI',0,'Accepted',?,80)", (mid,))

paid = payroll.tick(con, add_tx, lambda pid, c: "Captain", now)
check("all 4 backfilled weeks were paid into the wallet", len(paid) == 4, len(paid))
check("wallet holds 4 base payments", con.execute("SELECT COUNT(*) FROM wallet WHERE kind='base_pay'").fetchone()[0] == 4)

# but only ONE period remains pending for notification (the newest)
unseen = con.execute("SELECT COUNT(*) FROM payroll_runs WHERE notified=0").fetchone()[0]
undmed = con.execute("SELECT COUNT(*) FROM payroll_runs WHERE dm_sent=0").fetchone()[0]
check("only one period pending a site notice", unseen == 1, unseen)
check("only one period pending a DM", undmed == 1, undmed)

newest = con.execute("SELECT MAX(period) FROM payroll_runs").fetchone()[0]
pend = payroll.pending_site(con, "MULTI")
check("the site notice points at the newest period", pend and pend["period"] == newest, pend)
due = payroll.dm_due(con, "https://pac-va.com")
check("exactly one DM is due, for the newest period", len(due) == 1 and due[0]["period"] == newest, due)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
