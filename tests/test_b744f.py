"""The Boeing 747-400F (B744F): a complete fleet type, in the fleet market used, on lease and on an Atlas wet lease,
unlocking at a rank with its own type rating, with dispatch data, four engines for ACARS, and a cargo volume.
Run from the PAC folder: python tests/test_b744f.py"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-b744-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, company, fleet_market as FM, dispatch, va, stations, aog, economics, ops_rules, relief  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

T = "B744F"
ac = A.FLEET.get(T) or {}
check("the 747-400F is in the fleet data", ac.get("name") == "Boeing 747-400F" and ac.get("icao") == "B744")
check("it has every field the other freighters have", not (set(A.FLEET["A306F"]) - set(ac)), set(A.FLEET["A306F"]) - set(ac))
check("it is not retired and has sensible weights", not ac.get("retired") and 200_000 < ac["max_payload_lbs"] < ac["mtow_lbs"] < 1_000_000)

now = time.time()
offers = [o for o in FM.offers(A.FLEET, A.app.static_folder, now) if o["aircraft"] == T]
ways = {o["way"] for o in offers}
check("the market offers it used, on lease and wet-leased", {"used", "lease", "wet"} <= ways, ways)
used = next((o for o in offers if o["way"] == "used"), {})
check("the used offer has a price and a delivery time", used.get("price", 0) > 1e6 and used.get("lead_days"))
check("it is not sold new (no production line in the PAC fleet)", "new" not in ways)

with A.db() as con:
    company.migrate(con); FM.migrate(con)
    con.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES ('PAC0001', 'Joseph Pagani')")
    r = FM.order(con, used["id"], "N744PC", "KCVG", 0, 100_000_000, A.FLEET, A.app.static_folder, "PAC0001", now)
    row = con.execute("SELECT type, ownership, status FROM airframes WHERE reg='N744PC'").fetchone()
    check("buying it creates an owned airframe of the right type", row and (row["type"], row["ownership"]) == (T, "owned"), row and dict(row))
    check("the purchase is paid from the company ledger", r["paid"] == used["price"])
    FM.tick(con, lambda *a: None, now + 15 * 86400)
    check("it joins the fleet once delivered", con.execute("SELECT status FROM airframes WHERE reg='N744PC'").fetchone()["status"] == "Available")

check("it unlocks at Captain", va.type_unlock_rank(T) == "Captain", va.type_unlock_rank(T))
check("it has its own type-rating family", va.RATING_FAMILY.get(T) == "B747-400")
check("dispatch knows its cargo deck and structural limits", T in dispatch.DECKS and T in dispatch.LIMITS and dispatch.LIMITS[T][0] < ac["mtow_lbs"])
check("it parks at a Code E stand", stations.AIRCRAFT_CODE.get(T) == "E")
check("the widebody lists include it and it is not a twin", T not in ops_rules.TWINS and T in aog.WIDE and T in economics.WIDEBODIES)
from tracker import expected_engines  # noqa: E402
check("ACARS expects four engines", expected_engines({"aircraft": T, "aircraft_info": ac}) == 4)
check("the flight planner knows its ceiling", A.CEILING_FL.get(T))

print("\n747-400F TESTS PASSED" if not failures else f"\n{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)
