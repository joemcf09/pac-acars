"""Insurance: deductibles cap repair costs, premiums are billed monthly and rise with claims.
Run from the PAC folder: python tests/test_insurance.py"""
import os, shutil, subprocess, sys, tempfile, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-ins-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, insurance as I, company, economics  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

notes = []; costs = {"fuel": 1000, "damage_repairs": 2_500_000}
paid = I.apply(costs, True, notes)
check("a widebody repair is capped at the $750k deductible", costs["damage_repairs"] == 750_000 and paid == 1_750_000 and I.CLAIM_NOTE in notes[0])
notes = []; costs = {"tail_strike_repairs": 180_000}
check("repairs under the deductible are paid in full", I.apply(costs, False, notes) == 0 and costs["tail_strike_repairs"] == 180_000)
m = next(iter(A.ROUTES.values()))
p = {"status": "Delivered", "payload_lbs": m["payload_lbs"], "block_min": m["target_block_min"], "fuel_used_lbs": 20000, "landing_rate": -1200}
e = economics.flight_economics(p, {"mission": m, "aircraft": m["aircraft"][0]}, A.FLEET, A.settings(), m["distance_nm"])
check("a heavy landing now costs the flight only the deductible", (e.get("costs") or {}).get("damage_repairs") in (750_000, 250_000), e.get("costs"))
now = time.time()
with A.db() as con:
    company.migrate(con)
    pol = I.policy(con, A.FLEET, now)
    check("every fleet type has a premium", pol["lines"] and pol["monthly"] > 0)
    I.tick(con, A.FLEET, now); I.tick(con, A.FLEET, now)
    check("the premium is billed once a month", con.execute("SELECT COUNT(*) FROM company_ledger WHERE kind='insurance'").fetchone()[0] == 1)
    for i in range(2):
        con.execute("INSERT INTO pireps (filed_at, pilot_id, demo, review_status, detail) VALUES (?,?,0,'Accepted',?)", (now, "PAC0001", json.dumps({"notes": [I.CLAIM_NOTE]})))
    p2 = I.policy(con, A.FLEET, now)
    check("claims raise the premium 10% each", p2["loading_pct"] == 20 and p2["monthly"] > pol["monthly"])
    st = company.statements(con, 1)[0]
    check("premiums show on the P&L", "Insurance premiums" in st["other"])
print("\n" + ("All insurance checks passed." if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
