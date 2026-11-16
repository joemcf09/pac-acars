"""Weekly base pay: activity-gated, rank-scaled, paid once per pilot per completed week, idempotent, and it
catches up missed weeks within the lookback window without double-paying."""
import datetime as dt
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import payroll

con = sqlite3.connect(":memory:")
con.row_factory = sqlite3.Row
con.execute("CREATE TABLE pireps (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, demo INT, review_status TEXT, filed_at REAL)")
con.execute("CREATE TABLE wallet (pilot_id TEXT, time REAL, kind TEXT, amount REAL, description TEXT, pirep_id TEXT)")

def add_tx(pid, kind, amount, desc, pir, c):
    c.execute("INSERT INTO wallet VALUES (?,?,?,?,?,?)", (pid, time.time(), kind, amount, desc, pir))

RANKS = {"ACTIVE": "Captain", "CADET": "Cadet", "IDLE": "First Officer"}
rank_of = lambda pid, c: RANKS.get(pid, "Cadet")

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got}]"))
    if not ok:
        fails.append(name)

now = time.time()
# last completed week window
periods = payroll.recent_periods(now)
last_key, last_start, last_end = periods[-1]
mid_last = dt.datetime(last_start.year, last_start.month, last_start.day, 12, tzinfo=dt.timezone.utc).timestamp() + 2 * 86400

# ACTIVE flew in the last complete week; CADET flew but is a cadet; IDLE flew only THIS (incomplete) week
con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at) VALUES ('ACTIVE',0,'Accepted',?)", (mid_last,))
con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at) VALUES ('CADET',0,'Accepted',?)", (mid_last,))
con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at) VALUES ('IDLE',0,'Accepted',?)", (now - 3600,))
# a demo flight should never count
con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at) VALUES ('DEMOONLY',1,'Accepted',?)", (mid_last,))

paid = payroll.tick(con, add_tx, rank_of, now)
by = {p["pilot_id"]: p for p in paid}
check("active captain is paid", "ACTIVE" in by and by["ACTIVE"]["base"] == 2500, by.get("ACTIVE"))
check("active cadet is paid the cadet rate", "CADET" in by and by["CADET"]["base"] == 500, by.get("CADET"))
check("pilot who only flew this (incomplete) week is NOT paid", "IDLE" not in by, list(by))
check("demo-only pilot is NOT paid", "DEMOONLY" not in by, list(by))

wal = {r["pilot_id"]: r["amount"] for r in con.execute("SELECT pilot_id, SUM(amount) amount FROM wallet GROUP BY pilot_id")}
check("base pay reached the wallet as base_pay", round(wal.get("ACTIVE", 0)) == 2500, wal)
check("wallet kind is base_pay", con.execute("SELECT DISTINCT kind FROM wallet").fetchone()["kind"] == "base_pay")

# idempotency: second run pays nothing new
paid2 = payroll.tick(con, add_tx, rank_of, now)
check("second run pays nothing (idempotent)", paid2 == [], paid2)
check("wallet unchanged after second run", con.execute("SELECT COUNT(*) FROM wallet").fetchone()[0] == 2)

# a NEW flight by IDLE in a prior complete week gets caught up on the next tick (lookback)
earlier_key, earlier_start, _ = periods[0]
mid_earlier = dt.datetime(earlier_start.year, earlier_start.month, earlier_start.day, 12, tzinfo=dt.timezone.utc).timestamp() + 2 * 86400
con.execute("INSERT INTO pireps (pilot_id, demo, review_status, filed_at) VALUES ('IDLE',0,'Accepted',?)", (mid_earlier,))
paid3 = payroll.tick(con, add_tx, rank_of, now)
check("missed earlier week is caught up for the newly-active pilot", any(p["pilot_id"] == "IDLE" for p in paid3), paid3)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
