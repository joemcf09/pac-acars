"""Humanitarian relief missions from real disasters (GDACS): drafted, held in conflict zones, posted only after staff
tick all four checks, calm and with no bonus. Also checks the HUM code fix (HUM = human remains).
Run from the PAC folder: python tests/test_relief.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-relief-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import relief, dispatch, conflict_zones  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

now = time.time()
day = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - 2 * 86400))
def feature(eid, kind, alert, lon, lat, iso2, country, name=""):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"eventtype": kind, "eventid": eid, "eventname": name, "name": f"{kind} in {country}", "alertlevel": alert,
                           "fromdate": day, "country": country, "affectedcountries": [{"iso2": iso2, "countryname": country}],
                           "severitydata": {"severitytext": "Example severity"}, "url": {"report": f"https://www.gdacs.org/report.aspx?eventid={eid}"}}}
raw = {"features": [feature(1, "TC", "Red", -76.8, 18.0, "JM", "Jamaica", "DELIA"),     # near Kingston
                    feature(2, "EQ", "Green", 10, 10, "XX", "Nowhere"),                  # green: ignored
                    feature(3, "DR", "Orange", 34, 9, "ET", "Ethiopia"),                 # drought: not an airlift type
                    feature(4, "FL", "Orange", -60.0, -30.0, "AR", "Argentina"),
                    dict(feature(5, "TC", "Red", 80.0, 15.5, "IN", "India", "OLD"), )]}
raw["features"][-1]["properties"].update(iscurrent="false", todate=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now - 8 * 86400)))
raw["features"][0]["properties"].update(iscurrent="true")
events = relief.parse_gdacs(raw, now)
check("only Orange/Red earthquakes, cyclones, floods and volcanoes are kept", [e["type"] for e in events] == ["TC", "FL"], events)
check("an event that ended eight days ago is skipped", all(e["name"] != "OLD" for e in events))
check("GDACS dates are read as UTC", abs(events[0]["start"] - (now - 2 * 86400)) < 2)

ctx = {"airports": A.AIRPORTS, "fleet": A.FLEET, "gc_distance_nm": A.gc_distance_nm, "airport_obj": A.airport_obj,
       "zones": [], "airport_zone": conflict_zones.airport_zone}
d = relief.plan(events[0], ctx)
check("the nearest big airport in the affected country is the destination", d.get("destination") == "MKJP", d.get("destination"))
check("supplies come from the nearest humanitarian depot", d.get("origin") == "MPTO", d.get("origin"))
check("the cargo is relief goods and never carries HUM", d["cargo"] and all(i["code"] != "HUM" for i in d["cargo"]))
check("the event label names the storm", d["label"].startswith("DELIA, Jamaica"), d["label"])
held = relief.plan(events[0], dict(ctx, zones=[{"level": "restricted", "prefixes": ["MK"], "name": "Test"}]))
check("an event in a conflict zone is held, never drafted", held.get("held") and "conflict" in held["reason"])

with A.db() as con:
    relief.migrate(con)
    n = relief.refresh(con, ctx, now, events=events)
    check("one draft per event", n == 2 and relief.refresh(con, ctx, now, events=events) == 0)
    did = events[0]["key"]
    try:
        relief.post(con, did, {"facts": True, "tone": True, "links": True, "timing": True}, ctx, now); posted_early = True
    except ValueError:
        posted_early = False
    check("it can't be posted until all five checks are ticked, including international help requested", not posted_early)
    m = relief.post(con, did, {c: True for c in relief.CHECKS}, ctx, now)
    check("posting creates a relief mission in the PAC8900 range", m["id"].startswith("PAC89") and m["relief"]["notice"].startswith("This flight is based on a real disaster"))
    check("relief pays like a normal flight: no urgency multiplier", m["yield_mult"] == 1.0 and m["urgent_kind"] == relief.KIND)
    relief.dismiss(con, events[1]["key"])
    check("a dismissed draft stays dismissed", relief.refresh(con, ctx, now, events=events) == 0 and
          con.execute("SELECT status FROM relief_drafts WHERE id=?", (events[1]["key"],)).fetchone()[0] == "dismissed")

check("it shows on the urgent board", any(x["id"] == m["id"] for x in A.va.urgent_missions()))
c = A.app.test_client()
check("pilots and visitors can't see relief drafts", c.get("/api/staff/relief").status_code in (401, 403))
c.post("/api/auth/setup", json={"password": "Relief-Test-1"})
r = c.get("/api/staff/relief")
check("staff can list drafts", r.status_code == 200 and any(x["id"] == did for x in r.get_json()["drafts"]), r.status_code)

src = (ROOT / "va.py").read_text(encoding="utf-8")
check("relief flights get no urgent bonus", 'm.get("urgent") and not m.get("relief")' in src)
check("HUM now means human remains", dispatch.SHC_NAMES.get("HUM") == "Human remains" if hasattr(dispatch, "SHC_NAMES") else "\"HUM\": \"Human remains\"" in (ROOT / "dispatch.py").read_text())
check("no relief pool uses HUM", all("HUM" not in codes for _, items in dispatch.POOLS for it in items for codes in [it[1]]))

print("\nRELIEF TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
