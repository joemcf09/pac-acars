"""Staff role stipend: a role-holder draws a weekly stipend on top of base pay, out of the treasury, for weeks
they held the role (no back-pay before they were given it), it shows on the pay statement, and it's idempotent."""
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
con.execute("CREATE TABLE roles (pilot_id TEXT, role TEXT, note TEXT, since REAL, PRIMARY KEY (pilot_id, role))")
con.execute("INSERT INTO pilots VALUES ('PAC0014','Alan Z', NULL)")
con.execute("INSERT INTO pilots VALUES ('PAC0020','New Staff', NULL)")
payroll.migrate(con)

def add_tx(pid, kind, amount, desc, pir, c):
    c.execute("INSERT INTO wallet VALUES (?,?,?,?,?,?)", (pid, time.time(), kind, amount, desc, pir))

fails = []
def check(name, ok, got=None):
    print(("PASS" if ok else "FAIL") + ": " + name + ("" if ok else f"  [{got}]"))
    if not ok:
        fails.append(name)

now = time.time()
periods = payroll.recent_periods(now)
oldest_start = periods[0][1]
# Alan held livery_mgr since before the lookback window (established) -> catch-up for all lookback weeks
con.execute("INSERT INTO roles VALUES ('PAC0014','livery_mgr','', ?)", (payroll._epoch(oldest_start) - 7 * 86400,))
# New staffer assigned the role just now -> no back-pay for completed weeks
con.execute("INSERT INTO roles VALUES ('PAC0020','livery_mgr','', ?)", (now,))

payroll.tick(con, add_tx, lambda pid, c: "Second Officer", now)

alan_stip = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id='PAC0014' AND kind='role_stipend'").fetchone()[0]
check("established staffer draws the livery stipend ($1,500/wk x 4 weeks)", alan_stip == 1500 * 4, alan_stip)
check("stipend-only staffer got pay runs so the paycheck notice fires", con.execute("SELECT COUNT(*) FROM payroll_runs WHERE pilot_id='PAC0014'").fetchone()[0] == 4)
newstaff_stip = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id='PAC0020' AND kind='role_stipend'").fetchone()[0]
check("freshly-assigned staffer gets NO retroactive stipend", newstaff_stip == 0, newstaff_stip)

# the stipend shows on the pay statement as its own earnings line
s = payroll.statement(con, "PAC0014", periods[-1][0])
earn = {l["kind"]: l["amount"] for l in s["lines"]}
check("pay statement shows the staff stipend line", earn.get("role_stipend") == 1500, earn)
check("net reflects the stipend (no flying, base 0)", s["net"] == 1500, s["net"])

# idempotent
payroll.tick(con, add_tx, lambda pid, c: "Second Officer", now)
alan_stip2 = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id='PAC0014' AND kind='role_stipend'").fetchone()[0]
check("second tick pays no extra stipend (idempotent)", alan_stip2 == 1500 * 4, alan_stip2)

# a role with no stipend configured pays nothing
con.execute("INSERT INTO roles VALUES ('PAC0020','ceo','', ?)", (payroll._epoch(oldest_start) - 7 * 86400,))
payroll.tick(con, add_tx, lambda pid, c: "Captain", now)
ceo_stip = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id='PAC0020' AND kind='role_stipend'").fetchone()[0]
check("the CEO role draws no stipend", ceo_stip == 0, ceo_stip)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
