"""The PAC shop and the pilots' Finance summary."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402
import va  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


founder = A.app.test_client()
founder.post("/api/auth/setup", json={"password": "Founder-Pass-123"})
with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location) VALUES "
                "('PAC0002','Bob Member','bob@example.com','KCVG',1767225600,'Active','Passed',0,'KCVG')")
auth._set_password("PAC0002", "Member-Pass-123")
pilot = A.app.test_client()
pilot.post("/api/auth/login", json={"pilot_id": "PAC0002", "password": "Member-Pass-123"})

print("Buying")
c = pilot.get("/api/shop").get_json()
check("the shop lists patches, frames and perks", len(c["patches"]) >= 5 and len(c["frames"]) >= 3 and c["perks"])
r = pilot.post("/api/shop/buy", json={"item": "night_cargo"})
check("can't buy without the money", r.status_code == 400 and "wallet" in r.get_json()["error"], r.get_json())
va.add_tx("PAC0002", "adjustment", 50000, "test money")
r = pilot.post("/api/shop/buy", json={"item": "night_cargo"})
check("buys a patch", r.status_code == 200 and r.get_json()["balance"] == 47000, r.get_json().get("balance"))
check("can't buy the same patch twice", pilot.post("/api/shop/buy", json={"item": "night_cargo"}).status_code == 400)
check("unknown items are refused", pilot.post("/api/shop/buy", json={"item": "free_money"}).status_code == 400)
with A.db() as con:
    kinds = [r["kind"] for r in con.execute("SELECT kind FROM wallet WHERE pilot_id='PAC0002' AND amount<0")]
check("purchases show in the wallet as PAC shop", kinds == ["shop"], kinds)

print("Frames and patches on the profile")
pilot.post("/api/shop/buy", json={"item": "carbon"})
prof = pilot.get("/api/profile").get_json()["profile"]
check("the first frame bought goes straight on", prof["flair"]["frame"] == "carbon", prof.get("flair"))
check("patches show on the profile", [p["id"] for p in prof["flair"]["patches"]] == ["night_cargo"])
check("can't wear a frame you don't own", pilot.post("/api/shop/wear", json={"frame": "gold"}).status_code == 400)
pilot.post("/api/shop/wear", json={"frame": None})
check("can take a frame off", pilot.get("/api/profile").get_json()["profile"]["flair"]["frame"] is None)
check("flair isn't saved into the profile file", "flair" not in A.load_profile("PAC0002"))

print("Jumpseat passes")
pilot.post("/api/shop/buy", json={"item": "jumpseat_pass"})
q = pilot.post("/api/pilot/jumpseat/quote", json={"to": "KMIA"}).get_json()
check("a pass is offered as a free option", q["options"][0]["kind"] == "pass" and q["options"][0]["cost"] == 0, q["options"][:1])
bal = va.balance("PAC0002")
r = pilot.post("/api/pilot/jumpseat", json={"to": "KMIA", "kind": "pass"}).get_json()
check("using it moves the pilot for free", r["location"] == "KMIA" and va.balance("PAC0002") == bal, r)
check("the pass is used up", pilot.post("/api/pilot/jumpseat", json={"to": "KCVG", "kind": "pass"}).status_code == 400)
for _ in range(5):
    pilot.post("/api/shop/buy", json={"item": "jumpseat_pass"})
check("holds at most five", pilot.get("/api/shop").get_json()["perks"][0]["owned"] == 5)

print("Aircraft reposition")
with A.db() as con:
    frame = con.execute("SELECT reg, location FROM airframes WHERE status='Available' AND location!='KMIA' LIMIT 1").fetchone()
q = pilot.post("/api/shop/reposition/quote", json={"reg": frame["reg"]}).get_json()
check("quotes base plus distance", q.get("cost", 0) >= 500 and q["to"] == "KMIA", q)
bal = va.balance("PAC0002")
r = pilot.post("/api/shop/reposition", json={"reg": frame["reg"]}).get_json()
with A.db() as con:
    loc = con.execute("SELECT location FROM airframes WHERE reg=?", (frame["reg"],)).fetchone()[0]
check("the aircraft is moved to the pilot", loc == "KMIA" and round(va.balance("PAC0002")) == round(bal - q["cost"]), (loc, r))
with A.db() as con:
    other = con.execute("SELECT reg FROM airframes WHERE status='Available' AND location!='KMIA' LIMIT 1").fetchone()[0]
    con.execute("UPDATE airframes SET status='Booked' WHERE reg=?", (other,))
bal = va.balance("PAC0002")
check("a booked aircraft can't be moved", pilot.post("/api/shop/reposition", json={"reg": other}).status_code == 400
      and va.balance("PAC0002") == bal)

print("Naming rights")
va.add_tx("PAC0002", "adjustment", 100000, "test money")
r = pilot.post("/api/shop/name", json={"reg": frame["reg"], "name": "Spirit of Cincinnati"})
check("names an aircraft", r.status_code == 200)
afs = {a["reg"]: a for a in pilot.get("/api/airframes").get_json()}
check("the name and namer show on the fleet", afs[frame["reg"]]["name"] == "Spirit of Cincinnati" and afs[frame["reg"]]["named_by_name"] == "Bob Member")
bal = va.balance("PAC0002")
pilot.post("/api/shop/name", json={"reg": frame["reg"], "name": "Pride of Kentucky"})
check("renaming your own aircraft is free", va.balance("PAC0002") == bal and pilot.get("/api/airframes").get_json() and
      {a["reg"]: a for a in pilot.get("/api/airframes").get_json()}[frame["reg"]]["name"] == "Pride of Kentucky")
va.add_tx("PAC0001", "adjustment", 100000, "test money")
check("someone else can't rename it", founder.post("/api/shop/name", json={"reg": frame["reg"], "name": "Mine Now"}).status_code == 400)
check("names must be unique", founder.post("/api/shop/name", json={"reg": other, "name": "pride of kentucky"}).status_code == 400)
check("silly names are refused", pilot.post("/api/shop/name", json={"reg": other, "name": "<script>"}).status_code == 400)
check("pilots can't remove names", pilot.post("/api/staff/shop/name", json={"reg": frame["reg"]}).status_code == 403)
founder.post("/api/staff/shop/name", json={"reg": frame["reg"]})
check("staff can remove a name", not {a["reg"]: a for a in pilot.get("/api/airframes").get_json()}[frame["reg"]]["name"])

print("Closing the shop")
founder.post("/api/settings", json={"shop_enabled": False})
check("a closed shop sells nothing", pilot.post("/api/shop/buy", json={"item": "silver"}).status_code == 400)
check("…but what was bought still shows", pilot.get("/api/profile").get_json()["profile"]["flair"]["patches"])
check("pilots can't open or close it", pilot.post("/api/settings", json={"shop_enabled": True}).status_code == 403)
founder.post("/api/settings", json={"shop_enabled": True})

print("Pilot gear")
va.add_tx("PAC0002", "adjustment", 100000, "test money")
pilot.post("/api/shop/buy", json={"item": "flight_bag"})
c = pilot.post("/api/shop/buy", json={"item": "efb_tablet"}).get_json()
check("gear adds up", c["gear_bonus"] == 3, c.get("gear_bonus"))
exp1 = next(g for g in c["gear"] if g["id"] == "flight_bag")["expires"]
c = pilot.post("/api/shop/buy", json={"item": "flight_bag"}).get_json()
exp2 = next(g for g in c["gear"] if g["id"] == "flight_bag")["expires"]
check("buying again extends it", round((exp2 - exp1) / 86400) == 180, (exp1, exp2))
check("…without counting twice", c["gear_bonus"] == 3)
with A.db() as con:
    con.execute("""INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, flight_number, profit, flags)
        VALUES ('PAC0002', ?, 0, 'Accepted', 'B738F', 'KCVG', 'KMIA', 120, 'PAC7001', 20000, '[]')""", (time.time(),))
    gp = con.execute("SELECT max(id) FROM pireps").fetchone()[0]
va.pay_pirep(gp)
va.pay_pirep(gp)
with A.db() as con:
    rows = {r["kind"]: r["amount"] for r in con.execute("SELECT kind, SUM(amount) amount FROM wallet WHERE pirep_id=? GROUP BY kind", (gp,))}
check("each flight pays the gear bonus once", round(rows.get("gear_bonus", 0), 2) == round((rows["flight_pay"] + rows.get("profit_share", 0)) * 0.03, 2), rows)
with A.db() as con:
    con.execute("UPDATE shop_owned SET expires=? WHERE pilot_id='PAC0002' AND item IN ('flight_bag','efb_tablet')", (time.time() - 1,))
check("expired gear stops counting", pilot.get("/api/shop").get_json()["gear_bonus"] == 0)
import shop as SH  # noqa: E402
with A.db() as con:
    for k in SH.GEAR:
        con.execute("INSERT OR REPLACE INTO shop_owned (pilot_id, item, qty, bought, expires) VALUES ('PAC0002', ?, 1, ?, ?)", (k, time.time(), time.time() + 86400))
check("all gear together is capped", pilot.get("/api/shop").get_json()["gear_bonus"] == SH.GEAR_CAP)

print("Hard landing pass")
with A.db() as con:
    con.execute("""INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, flight_number, profit, flags, landing_rate)
        VALUES ('PAC0002', ?, 0, 'Rejected', 'B738F', 'KCVG', 'KMIA', 120, 'PAC7002', 20000, '["Hard landing -712 fpm", "Score 60 below 70"]', -712)""", (time.time(),))
    hard = con.execute("SELECT max(id) FROM pireps").fetchone()[0]
    con.execute("""INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, flight_number, profit, flags)
        VALUES ('PAC0002', ?, 0, 'Pending', 'B738F', 'KCVG', 'KMIA', 120, 'PAC7003', 20000, '["Hard landing -650 fpm", "Position jump or slew"]')""", (time.time(),))
    slew = con.execute("SELECT max(id) FROM pireps").fetchone()[0]
c = pilot.get("/api/shop").get_json()
elig = [p["id"] for p in c["landing_eligible"]]
check("a PIREP rejected only for its landing qualifies", hard in elig, elig)
check("one with a position jump doesn't", slew not in elig)
check("can't use a pass you don't have", pilot.post("/api/shop/use", json={"item": "hard_landing_pass", "pirep_id": hard}).status_code == 400)
pilot.post("/api/shop/buy", json={"item": "hard_landing_pass"})
r = pilot.post("/api/shop/use", json={"item": "hard_landing_pass", "pirep_id": hard})
with A.db() as con:
    st = con.execute("SELECT review_status FROM pireps WHERE id=?", (hard,)).fetchone()[0]
    paid = con.execute("SELECT COUNT(*) FROM wallet WHERE pirep_id=? AND kind='flight_pay'", (hard,)).fetchone()[0]
check("using it accepts and pays the flight", r.status_code == 200 and st == "Accepted" and paid == 1, (r.get_json(), st, paid))
check("the pass is used up", next(p for p in r.get_json()["perks"] if p["id"] == "hard_landing_pass")["owned"] == 0)
pilot.post("/api/shop/buy", json={"item": "hard_landing_pass"})
check("it can't be used on the slew flight", pilot.post("/api/shop/use", json={"item": "hard_landing_pass", "pirep_id": slew}).status_code == 400)

print("Fleet pass")
founder.post("/api/settings", json={"require_type_ratings": True})
rated = A.va.type_ratings("PAC0002")
m = next(x for x in A.MISSIONS.values() if not x.get("tour") and not x.get("contract") and not x.get("type_checkride")
         and any(A.va.rating_family(a) not in rated for a in x["aircraft"]))
ac = next(a for a in m["aircraft"] if A.va.rating_family(a) not in rated)
with A.app.test_request_context():
    real = auth.current_id
    auth.current_id = lambda: "PAC0002"
    try:
        err1, _ = A.va.check_booking(m, ac, None, A.settings())
        pilot.post("/api/shop/buy", json={"item": "fleet_pass_7"})
        err2, _ = A.va.check_booking(m, ac, None, A.settings())
    finally:
        auth.current_id = real
check("without a fleet pass the type rating is needed", err1 and "type rating" in err1, err1)
check("with one it isn't", not err2 or "type rating" not in err2, err2)
check("the fleet pass shows how long it lasts", pilot.get("/api/shop").get_json()["fleet_pass"] > time.time() + 6 * 86400)

print("Finance")
f = pilot.get("/api/finance").get_json()
check("pilots get the short summary", f.get("summary") and "ledger" not in f and "best_routes" not in f and "cost_split" not in f, list(f))
check("…with their own profit share", "my_share" in f and "cash" in f)
f = founder.get("/api/finance").get_json()
check("staff get the full books", "ledger" in f and "cost_split" in f and not f.get("summary"))

print("\n" + ("SHOP TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
