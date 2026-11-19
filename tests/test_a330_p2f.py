"""The Airbus A330-200P2F (A332F): it has to be a complete fleet type, show up in the fleet market as a used aircraft
(and on lease), unlock at a rank, and carry the dispatch data the other freighters have.
Run from the PAC folder: python tests/test_a330_p2f.py"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-a332-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, company, fleet_market as FM, dispatch, va, stations, aog, economics, ops_rules, relief  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

T = "A332F"
ac = A.FLEET.get(T) or {}
check("the A330-200P2F is in the fleet data", ac.get("name") == "Airbus A330-200P2F" and ac.get("icao") == "A332")
check("it has every field the other freighters have", not (set(A.FLEET["A306F"]) - set(ac)), set(A.FLEET["A306F"]) - set(ac))
check("it is not retired and has sensible weights", not ac.get("retired") and 100_000 < ac["max_payload_lbs"] < ac["mtow_lbs"] < 700_000)

now = time.time()
offers = [o for o in FM.offers(A.FLEET, A.app.static_folder, now) if o["aircraft"] == T]
ways = {o["way"] for o in offers}
check("the market offers it used and on lease", {"used", "lease"} <= ways, ways)
used = next((o for o in offers if o["way"] == "used"), {})
check("the used offer has a price and a delivery time", used.get("price", 0) > 1e6 and used.get("lead_days"))
check("it is not sold new (no production line in the PAC fleet)", "new" not in ways)

with A.db() as con:
    company.migrate(con); FM.migrate(con)
    con.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES ('PAC0001', 'Joseph Pagani')")
    r = FM.order(con, used["id"], "N330PC", "KCVG", 0, 100_000_000, A.FLEET, A.app.static_folder, "PAC0001", now)
    row = con.execute("SELECT type, ownership, status FROM airframes WHERE reg='N330PC'").fetchone()
    check("buying it creates an owned airframe of the right type", row and (row["type"], row["ownership"]) == (T, "owned"), row and dict(row))
    check("the purchase is paid from the company ledger", r["paid"] == used["price"])
    FM.tick(con, lambda *a: None, now + 15 * 86400)
    check("it joins the fleet once delivered", con.execute("SELECT status FROM airframes WHERE reg='N330PC'").fetchone()["status"] == "Available")

check("it unlocks at Captain", va.type_unlock_rank(T) == "Captain", va.type_unlock_rank(T))
check("it has its own type-rating family", va.RATING_FAMILY.get(T) == "A330")
check("dispatch knows its cargo deck and structural limits", T in dispatch.DECKS and T in dispatch.LIMITS and dispatch.LIMITS[T][0] < ac["mtow_lbs"])
check("it parks at a Code E stand", stations.AIRCRAFT_CODE.get(T) == "E")
check("the twin and widebody lists include it", T in ops_rules.TWINS and T in aog.WIDE and T in economics.WIDEBODIES)
check("the flight planner knows its ceiling", A.CEILING_FL.get(T))

print("\nA330-200P2F TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
