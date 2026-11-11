"""Shipper accounts: standing from on-time, late and failed shipments; unhappy accounts send freight elsewhere.
Run from the PAC folder: python tests/test_accounts.py"""
import random, sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import accounts, cargo_network  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

con = sqlite3.connect(":memory:"); con.row_factory = sqlite3.Row
cargo_network.migrate(con)
now = time.time()
def ship(i, shipper, status, ago=1):
    con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper,
        consignee, commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status, data, created_at, updated_at)
        VALUES (?,?,?,?,'KCVG','KMIA','KMIA',?,?,'C','x',1,100,50,'P','[]','S','{}',?,?)""", (f"s{i}", f"901-{i}", f"k{i}", f"x{i}", status, shipper, now, now - ago * 86400))
for i in range(6): ship(i, "Good Pharma", "DELIVERED")
for i in range(6, 11): ship(i, "Grumpy Parts", "DELIVERED_LATE")
ship(11, "Grumpy Parts", "EXCEPTION")
ship(12, "Old News", "DELIVERED_LATE", ago=120)
acc = accounts.refresh(con, now)
check("on-time deliveries make a preferred account", acc["Good Pharma"]["tier"] == "Preferred", acc["Good Pharma"])
check("late and failed shipments put an account at risk", acc["Grumpy Parts"]["tier"] == "At risk", acc["Grumpy Parts"])
check("only the last 90 days count", "Old News" not in acc)
rng = random.Random(1)
kept = sum(accounts.keeps_order("Grumpy Parts", rng) for _ in range(1000))
check("an account at risk sends most new orders elsewhere", 300 < kept < 500, kept)
check("a good account keeps every order", all(accounts.keeps_order("Good Pharma", rng) for _ in range(200)))
check("a new customer always books", accounts.keeps_order("Brand New Co", rng))
print("\nACCOUNTS TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
