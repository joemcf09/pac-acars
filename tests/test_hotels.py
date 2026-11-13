"""Crew rest: HQ rooms free, trip hotels on the company, own stays charged nights 2-4 only."""
import sqlite3, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hotels, company

con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE pilots (id TEXT, name TEXT, hub TEXT, location TEXT, status TEXT)")
con.execute("CREATE TABLE pireps (pilot_id TEXT, arr TEXT, filed_at REAL, demo INT)")
con.execute("CREATE TABLE trips (pilot_id TEXT, status TEXT)")
T0 = 1_800_000_000
pilots = [("P1", "LIMC", "KCVG"), ("P2", "KCVG", "KMIA"), ("P3", "KCVG", "VHHH"), ("P4", "KCVG", "KCVG")]
pilots += [(f"Q{i}", "LIMC", "KCVG") for i in range(6)]      # 7 non-KCVG pilots at KCVG: one too many for 6 rooms
for pid, hub, loc in pilots:
    con.execute("INSERT INTO pilots VALUES (?,?,?,?,'Active')", (pid, pid, hub, loc))
    con.execute("INSERT INTO pireps VALUES (?,?,?,0)", (pid, loc, T0 + (0 if pid == "P1" else 100)))
con.execute("INSERT INTO trips VALUES ('P3','bid')")
wallet = []
add = lambda pid, kind, amt, desc, pir, c: wallet.append((pid, amt))
for day in range(0, 10):
    hotels.tick(con, add, T0 + day * 86400 + 3600)
paid = lambda pid: round(sum(a for p, a in wallet if p == pid))
assert paid("P1") == 0, "first into HQ rooms: free"
assert paid("Q5") == -3 * hotels.rate("KCVG"), paid("Q5")     # seventh at HQ: overflow, nights 2-4 charged
assert paid("P2") == -3 * hotels.rate("KMIA"), paid("P2")
assert paid("P3") == 0 and paid("P4") == 0
trip = con.execute("SELECT SUM(amount) FROM company_ledger WHERE kind='hotel'").fetchone()[0]
assert trip == -9 * round(hotels.rate("VHHH") * hotels.CONTRACT), trip
h = hotels.hq(con); assert h["used"] == 6, h
print("All hotel checks passed.")
