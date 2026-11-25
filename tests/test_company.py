"""Company layer: roles, ledger and P&L statement, fleet market, CEO visits, complaints, pilot of the month and the CEO letter.
Run from the PAC folder: python tests/test_company.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-company-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, company, ceo, fleet_market as FM, accounts  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

now = time.time()
with A.db() as con:
    company.migrate(con); ceo.migrate(con); FM.migrate(con)
    for p in ("PAC0001", "PAC0002"):
        con.execute("INSERT OR IGNORE INTO pilots (id, name) VALUES (?,?)", (p, {"PAC0001": "Joseph Pagani", "PAC0002": "Alex B"}[p]))
    check("the owner holds the CEO role from the start", "ceo" in company.roles_of(con, "PAC0001"))
    check("other pilots hold no role", not company.roles_of(con, "PAC0002") and not company.may(con, "PAC0002", "ceo_desk"))
    company.assign(con, "PAC0002", "chief_pilot")
    check("a role can be handed out", "chief_pilot" in company.roles_of(con, "PAC0002"))
    check("a chief pilot can't use the fleet market", not company.may(con, "PAC0002", "fleet_market"))
    try:
        company.unassign(con, "PAC0001", "ceo"); check("PAC always keeps a CEO", False)
    except ValueError:
        check("PAC always keeps a CEO", True)

    # ledger and statement
    con.execute("""INSERT INTO pireps (filed_at, pilot_id, demo, review_status, revenue, cost, profit, detail, block_min, payload_lbs, status, landing_rate, arr)
        VALUES (?,?,0,'Accepted',100000,60000,40000,?,180,40000,'Delivered',-150,'KCVG')""",
        (now, "PAC0002", json.dumps({"economics": {"costs": {"fuel": 30000, "crew": 10000, "maintenance": 20000}}})))
    company.post(con, "goodwill", -5000, "test goodwill")
    st = company.statements(con, 1)[0]
    check("the statement adds revenue, operating costs and company items", st["revenue"] == 100000 and st["operating_profit"] == 40000 and st["net"] == 35000, st)

    # fleet market
    offers = FM.offers(A.FLEET, A.app.static_folder, now)
    ways = {o["way"] for o in offers}
    check("the market offers all four ways to get aircraft", {"new", "conversion", "lease", "wet"} <= ways, ways)
    check("only types still in production are sold new", {o["aircraft"] for o in offers if o["way"] == "new"} <= {"B77F", "B763F"})
    check("every company offer names a real company", all(o["company_name"] for o in offers if o["company"]))
    lease = next(o for o in offers if o["way"] == "lease" and o["aircraft"] == "B752F")
    try:
        FM.order(con, next(o for o in offers if o["way"] == "new")["id"], "N777PC", "KCVG", 0, 1_000_000, A.FLEET, A.app.static_folder, "PAC0001", now)
        check("a purchase PAC can't afford is refused", False)
    except ValueError as e:
        check("a purchase PAC can't afford is refused", "Lease instead" in str(e))
    r = FM.order(con, lease["id"], "N799ZZ", "KMIA", 0, 50_000_000, A.FLEET, A.app.static_folder, "PAC0001", now)
    row = dict(con.execute("SELECT * FROM airframes WHERE reg='N799ZZ'").fetchone())
    check("a leased aircraft is on order until delivery", row["status"] == FM.ON_ORDER and row["ownership"] == "leased")
    check("the first month's lease is charged", company.ledger_total(con) == -5000 - lease["monthly"])
    news = []
    FM.tick(con, lambda t, b: news.append(t), r["deliver_at"] + 1)
    row = dict(con.execute("SELECT * FROM airframes WHERE reg='N799ZZ'").fetchone())
    check("it's delivered to its hub, with a news post", row["status"] == "Available" and row["location"] == "KMIA" and news)
    FM.tick(con, lambda t, b: None, r["deliver_at"] + 31 * 86400)
    check("the next month's lease is charged", company.ledger_total(con) == -5000 - 2 * lease["monthly"])
    check("a leased aircraft can be returned", "returned" in FM.give_back(con, "N799ZZ", "PAC0001") and not con.execute("SELECT 1 FROM airframes WHERE reg='N799ZZ'").fetchone())
    wet = next(o for o in offers if o["way"] == "wet")
    w = FM.order(con, wet["id"], "N798ZZ", "KCVG", 2, 50_000_000, A.FLEET, A.app.static_folder, "PAC0001", now)
    FM.tick(con, lambda t, b: None, w["deliver_at"] + 1)
    FM.tick(con, lambda t, b: None, w["deliver_at"] + 15 * 86400)
    check("a wet lease goes back when it runs out", not con.execute("SELECT 1 FROM airframes WHERE reg='N798ZZ'").fetchone())

    # complaints and CEO visits lift a shipper's standing
    for i in range(4):
        con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper, consignee,
            commodity, pieces, gross_weight_lbs, handling, data, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"s{i}", f"901-0000000{i}", "b", f"x{i}", "SPJC", "KMIA", "KMIA", "EXCEPTION", "Andes Fresh", "C", "Fruit", 1, 1000, "[]", "{}", now, now))
    accounts.refresh(con, now)
    before = accounts.compute(con, now)["Andes Fresh"]["score"]
    check("a shipper with failed shipments is at risk", accounts.compute(con, now)["Andes Fresh"]["tier"] == "At risk")
    check("failed deliveries bring a complaint (one open per shipper)", ceo.scan_complaints(con, now) == 1)
    cid = con.execute("SELECT id FROM complaints").fetchone()[0]
    a = ceo.answer(con, cid, "discount", "PAC0001", now)
    check("answering it lifts their standing and charges the goodwill", accounts.compute(con, now)["Andes Fresh"]["score"] == before + 8 and a["cost"] == 25000)
    done = ceo.on_filed(con, "PAC0001", {"arr": "SPJC"}, {}, None, now)
    check("the CEO landing at the shipper's station counts as an account visit", ("account", "SPJC", "Andes Fresh") in done)
    check("the visit lifts their standing for 90 days", accounts.compute(con, now)["Andes Fresh"]["score"] == before + 8 + ceo.VISIT_BONUS)
    check("other pilots' flights aren't CEO visits", ceo.on_filed(con, "PAC0002", {"arr": "KCVG"}, {}, None, now) == [])
    check("the CEO landing at a hub is a hub visit", ("hub", "KCVG", None) in ceo.on_filed(con, "PAC0001", {"arr": "KCVG"}, {}, None, now))
    rep = ceo.station_report(con, "KMIA", now)
    check("a hub's station report counts waiting freight and aircraft", "waiting" in rep and "aircraft" in rep)

    # pilot of the month and the letter
    month = time.strftime("%Y-%m", time.gmtime(now))
    for i in range(3):
        con.execute("""INSERT INTO pireps (filed_at, pilot_id, demo, review_status, revenue, cost, profit, block_min, payload_lbs, status, landing_rate, arr)
            VALUES (?,?,0,'Accepted',1,1,0,120,20000,'Delivered',-120,'LIMC')""", (now, "PAC0002"))
    best = ceo.pilot_of_month(con, month)
    check("pilot of the month goes to the standout pilot", best and best["pilot_id"] == "PAC0002" and best["flights"] == 4, best)
    letter = ceo.letter_draft(con, month, "Joseph Pagani")
    check("the CEO letter is drafted from the month's real numbers", "flights" in letter and "Alex B" in letter and "Joseph Pagani" in letter)

c = A.app.test_client()
check("the staff pages answer", all(c.get(u).status_code in (200, 401, 403, 302) for u in ("/api/staff/ceo", "/api/staff/market", "/api/staff/complaints", "/api/staff/roles")))

# selling PAC's own aircraft; the last one of a type takes the type out of the fleet
import va  # noqa: E402
with A.db() as con:
    con.execute("UPDATE pilots SET password_hash='x', status='Active', staff=1 WHERE id='PAC0001'")
    rows = con.execute("SELECT type, reg, ownership FROM airframes WHERE COALESCE(ownership,'') NOT IN ('leased','wet_lease')").fetchall()
by_type = {}
for t, reg, own in rows:
    by_type.setdefault(t, []).append(reg)
typ = min(by_type, key=lambda t: len(by_type[t]))
with c.session_transaction() as s:
    s["pid"] = "PAC0001"
m = c.get("/api/staff/market").json
mine = [f for f in m["fleet"] if f["type"] == typ]
check("the market page lists the original fleet with a sale price", mine and all(f["sale_value"] == FM.sale_value(typ) > 0 for f in mine), mine)
with A.db() as con:
    cash0 = company.ledger_total(con)
regs = by_type[typ]
for i, reg in enumerate(regs):
    r = c.post(f"/api/staff/market/return/{reg}").json
    if i < len(regs) - 1:
        check("selling one of several leaves the type in the fleet", not r.get("type_retired") and not A.FLEET[typ].get("retired"), r)
check("an original-fleet aircraft can be sold, for 60% of the used price", "sold for" in r.get("note", ""), r)
with A.db() as con:
    check("the sale is paid into the ledger", round(company.ledger_total(con) - cash0) == FM.sale_value(typ) * len(regs))
check("selling the last one takes the type out of the fleet", r.get("type_retired") and A.FLEET[typ].get("retired") and "left the fleet" in r["note"], r)
with A.db() as con:
    va.migrate(con)
    check("a restart doesn't bring the sold type back", not con.execute("SELECT 1 FROM airframes WHERE type=?", (typ,)).fetchone())
offer = next((o for o in FM.offers(A.FLEET, A.app.static_folder) if o["aircraft"] == typ and o["way"] == "lease"), None)
if offer:
    r = c.post("/api/staff/market/order", json={"offer": offer["id"], "reg": "N555ZZ", "hub": "KCVG"})
    check("leasing one brings the type back", r.status_code == 200 and not A.FLEET[typ].get("retired"), r.json)

print("\n" + ("All company checks passed." if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
