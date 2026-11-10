"""AOG recovery: a grounded airframe gets a recovery case and mission; delivery starts the repair; it returns to service by
itself; a contractor steps in when nobody flies it; staff clearing closes the case.
Run from the PAC folder: python tests/test_aog.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-aog-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import va, aog  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Aog-Test-1"})

print("Classification")
check("smooth landing: nothing", aog.classify(-180, 1.2, False) is None)
check("-650 fpm: hard landing inspection", aog.classify(-650, 1.4, False) == "hard_landing")
check("gentle rate but 2.1 G: hard landing inspection", aog.classify(-300, 2.1, False) == "hard_landing")
check("tail strike: tail strike repair", aog.classify(-200, 1.2, True) == "tail_strike")
check("-1,100 fpm: structural", aog.classify(-1100, 1.9, False) == "structural")
check("2.7 G: structural", aog.classify(-500, 2.7, False) == "structural")
check("widebody kit is heavier and slower", aog.kit_for("structural", "B77F")["weight_lbs"] > aog.kit_for("structural", "B738F")["weight_lbs"]
      and aog.kit_for("structural", "B77F")["repair_hours"] > aog.kit_for("structural", "B738F")["repair_hours"])

code = next(k for k in ("B738F", "B733F", "B763F") if k in A.FLEET)
station = next(i for i in ("KCLT", "KATL", "KJFK", "KORD") if i in A.AIRPORTS)
now = time.time()
with A.db() as con:
    con.execute("INSERT OR REPLACE INTO airframes (reg, type, location, status, hours, cycles, hours_since_check) VALUES ('N901PC',?,?,'Available',100,50,10)", (code, station))
    con.execute("INSERT OR REPLACE INTO airframes (reg, type, location, status, hours, cycles, hours_since_check) VALUES ('N902PC',?,'KCVG','Available',100,50,10)", (code,))
    iid = va.create_item(con, "N901PC", 5, "Hard landing inspection after PAC1234", "grounding", source="acars", flight="PAC1234")
    case, ev = aog.open_case(con, "N901PC", code, station, "hard_landing", [iid], "PAC1234", None, va.C, now)

print("Opening a case away from a hub")
check("a case is opened, awaiting parts", case and ev and not ev["at_hub"])
check("a recovery mission is posted from a PAC hub", ev["mission"] and ev["mission"].startswith("PAC88") and ev["hub"] in aog.HUBS, ev)
m, st = va.urgent_by_id(ev["mission"])
check("the mission is an open urgent request to the stranded aircraft", st == "open" and m["destination"]["icao"] == station and m["aog_case"] == case["id"])
check("its cargo is the recovery kit", m["payload_lbs"] == aog.kit_for("hard_landing", code)["weight_lbs"] and "NDT" in m["cargo"])
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "cargo_orders_enabled": False})
ls = c.post("/api/plan/loadsheet", json={"mission_id": ev["mission"], "aircraft": m["aircraft"][0]}).get_json() or {}
contents = {p["contents"] for p in ls.get("positions") or []}
kit_parts = {x.strip()[0].upper() + x.strip()[1:] for x in m["cargo"].split(",")}
check("the load sheet carries the repair kit itself, every part of it", contents and contents <= kit_parts and len(contents) == min(len(kit_parts), len(ls.get("positions") or [])),
      (contents, kit_parts, ls.get("error")))
check("every unit is marked AOG", all("AOG" in p["shc"] for p in ls.get("positions") or []))
sh = ls.get("shipments") or []
check("PAC Engineering ships it to PAC's own AOG team", sh and all(s["shipper"]["name"] == "PAC Engineering Stores" and s["consignee"]["name"].startswith("PAC AOG Team") for s in sh),
      [(s["shipper"], s["consignee"]) for s in sh])
check("the story names the grounded aircraft", sh and "N901PC" in (sh[0].get("story") or ""), sh and sh[0].get("story"))
check("the aircraft is grounded", {a["reg"]: a for a in va.airframes()}["N901PC"]["status"] == "Maintenance")
check("the fleet list shows the AOG case", ({a["reg"]: a for a in va.airframes()}["N901PC"]["aog"] or {}).get("status") == "awaiting_parts")
with A.db() as con:
    news = con.execute("SELECT title FROM news WHERE title LIKE 'AOG: N901PC%'").fetchall()
    again, _ = aog.open_case(con, "N901PC", code, station, "hard_landing", [iid], "PAC1235", None, va.C, now)
check("a news post announces it", len(news) == 1)
check("a second grounding doesn't open a second case", again is None)

print("Recovery flight delivers, repair, return to service")
with A.db() as con:
    d = aog.parts_delivered(con, case["id"], ev["mission"], "PAC0001", now + 3 * 3600)
    r = dict(con.execute("SELECT * FROM aog_cases WHERE id=?", (case["id"],)).fetchone())
check("delivery starts the repair clock", d and r["status"] == "repairing" and abs(r["repair_until"] - (now + 3 * 3600 + 10 * 3600)) < 5, r)
with A.db() as con:
    early = aog.tick(con, now + 5 * 3600)
check("not back before the repair is done", early == [] and {a["reg"]: a for a in va.airframes()}["N901PC"]["status"] == "Maintenance")
with A.db() as con:
    done = aog.tick(con, now + 14 * 3600)
af = {a["reg"]: a for a in va.airframes()}["N901PC"]
check("back in service after the repair", done and done[0]["reg"] == "N901PC" and af["status"] == "Available" and not af["aog"], (done, af["status"]))
with A.db() as con:
    it = con.execute("SELECT status, note FROM maint WHERE id=?", (iid,)).fetchone()
check("the write-up is closed with the recovery flight named", it["status"] == "cleared" and ev["mission"] in it["note"], dict(it))

print("Nobody flies it: contractor")
with A.db() as con:
    iid2 = va.create_item(con, "N901PC", 53, "Tail strike inspection after PAC2000", "grounding", source="acars", flight="PAC2000")
    case2, ev2 = aog.open_case(con, "N901PC", code, station, "tail_strike", [iid2], "PAC2000", None, va.C, now)
    aog.tick(con, now + (aog.BOOK_WINDOW_H + 1) * 3600)
    r2 = dict(con.execute("SELECT * FROM aog_cases WHERE id=?", (case2["id"],)).fetchone())
    st2 = con.execute("SELECT status FROM urgent WHERE id=?", (ev2["mission"],)).fetchone()[0]
check("after the window, a contractor takes over at a higher cost", r2["contractor"] == 1 and r2["cost_usd"] > aog.kit_for("tail_strike", code)["cost_usd"] and st2 == "expired", (r2, st2))
with A.db() as con:
    aog.tick(con, r2["parts_due"] + 1)
    aog.tick(con, r2["parts_due"] + 1 + 31 * 3600)
af = {a["reg"]: a for a in va.airframes()}["N901PC"]
check("the contractor repair still returns it to service", af["status"] == "Available", af["status"])

print("Grounded at a hub, and staff clearing")
with A.db() as con:
    iid3 = va.create_item(con, "N902PC", 5, "Hard landing inspection after PAC3000", "grounding", source="acars", flight="PAC3000")
    case3, ev3 = aog.open_case(con, "N902PC", code, "KCVG", "hard_landing", [iid3], "PAC3000", None, va.C, now)
check("at a hub, parts are on site: repair starts with no mission", ev3["at_hub"] and ev3["mission"] is None)
with A.db() as con:
    iid4 = va.create_item(con, "N901PC", 32, "Structural damage after PAC4000", "grounding", source="acars", flight="PAC4000")
    case4, ev4 = aog.open_case(con, "N901PC", code, station, "structural", [iid4], "PAC4000", None, va.C, now)
va.clear_item(iid4, "Inspected, no damage", "Staff")
with A.db() as con:
    r4 = con.execute("SELECT status, note FROM aog_cases WHERE id=?", (case4["id"],)).fetchone()
    st4 = con.execute("SELECT status FROM urgent WHERE id=?", (ev4["mission"],)).fetchone()[0]
check("staff clearing closes the case and withdraws the mission", r4["status"] == "closed" and st4 == "expired", (dict(r4), st4))
print(); print("All AOG checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
