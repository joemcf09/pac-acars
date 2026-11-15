"""Crew rest: HQ rooms free, trip hotels on the company, own stays charged nights 3-4 only, never below $0."""
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
con.execute("INSERT INTO pilots VALUES ('Z1','Z1','LIMC','KCVG','Active')")   # joined, never flew
for day in range(0, 10):
    hotels.tick(con, add, T0 + day * 86400 + 3600)
paid = lambda pid: round(sum(a for p, a in wallet if p == pid))
assert paid("P1") == 0, "first into HQ rooms: free"
assert paid("Q5") == -2 * hotels.rate("KCVG"), paid("Q5")     # seventh at HQ: overflow, nights 3-4 charged
assert paid("P2") == -2 * hotels.rate("KMIA"), paid("P2")
assert paid("P3") == 0 and paid("P4") == 0
trip = con.execute("SELECT SUM(amount) FROM company_ledger WHERE kind='hotel'").fetchone()[0]
assert trip == -9 * round(hotels.rate("VHHH") * hotels.CONTRACT), trip
h = hotels.hq(con); assert h["used"] == 6 and "Z1" not in [g["pilot_id"] for g in h["guests"]], h
print("All hotel checks passed.")

# wallet floor: a hotel night empties a thin wallet but never pushes it negative
con2 = sqlite3.connect(":memory:")
con2.execute("CREATE TABLE pilots (id TEXT, name TEXT, hub TEXT, location TEXT, status TEXT)")
con2.execute("CREATE TABLE pireps (pilot_id TEXT, arr TEXT, filed_at REAL, demo INT)")
con2.execute("CREATE TABLE trips (pilot_id TEXT, status TEXT)")
con2.execute("CREATE TABLE wallet (pilot_id TEXT, time REAL, kind TEXT, amount REAL, description TEXT, pirep_id TEXT)")
con2.execute("INSERT INTO pilots VALUES ('F1','F1','KCVG','KMIA','Active')")
con2.execute("INSERT INTO pireps VALUES ('F1','KMIA',?,0)", (T0 + 100,))
con2.execute("INSERT INTO wallet VALUES ('F1',?,'flight_pay',100,'seed',NULL)", (T0,))   # only $100, less than one KMIA night ($189)
add2 = lambda pid, kind, amt, desc, pir, c: c.execute("INSERT INTO wallet VALUES (?,?,?,?,?,?)", (pid, T0, kind, amt, desc, pir))
for day in range(0, 10):
    hotels.tick(con2, add2, T0 + day * 86400 + 3600)
bal = round(con2.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id='F1'").fetchone()[0], 2)
assert bal == 0, f"a $100 wallet should be drawn to exactly 0 by hotel charges, never below; got {bal}"
print("Wallet floor check passed.")
