"""The bigger network and the new kinds of work: about 600 scheduled routes, challenging airports, special cargo,
ferry flights and multi-leg rotations.

Run from the PAC folder:   python tests/test_network_growth.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)
for _p in (DATA / "flights").glob("*.pkl"):
    _p.unlink()

import analysis  # noqa: E402
import app as A  # noqa: E402
import missiongen as MG  # noqa: E402
import va  # noqa: E402
from flightgen import fly  # noqa: E402
from tracker import FlightRecorder  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


print("The scheduled network")
R = A.ROUTES
check("at least 600 routes (the network keeps growing)", 600 <= len(R) <= 1500, len(R))
# the routes pilots already fly keep their numbers
for rid, o, d in [("PAC1001", "KCVG", "KLAX"), ("PAC1061", "TJSJ", "KMIA"), ("PAC2029", "CYUL", "CYFB"), ("PAC3017", "SBKP", "LIMC"),
                  ("PAC4030", "BIKF", "EGSS"), ("PAC5031", "FMMI", "OMDW"), ("PAC6038", "PGUM", "RPLL"), ("PAC7016", "KSEA", "RKSI")]:
    r = R.get(rid) or {}
    check(f"{rid} is still {o} to {d}", (r.get("origin", {}).get("icao"), r.get("destination", {}).get("icao")) == (o, d), r.get("title"))
check("no route number is used twice", len({r["id"] for r in R.values()}) == len(R))
check("no lane is listed twice", len({(r["origin"]["icao"], r["destination"]["icao"]) for r in R.values()}) == len(R))
for region in ("Americas", "Middle East & Africa", "Asia-Pacific", "Europe", "Transatlantic"):
    check(f"{region} has grown", sum(1 for r in R.values() if r["region"] == region) >= 55)
F = A.FLEET
longest = max(f["range_nm"] for f in F.values())
# the High Arctic gravel-kit operation flies the 737-200 into strips shorter than its usual minimum, on purpose and light
gravel_kit = lambda r, k: k == "B732F" and "gravel kit" in (r.get("briefing") or "").lower()
bad = [r["id"] for r in R.values() if r["distance_nm"] <= longest for k in r["aircraft"]
       if F[k]["range_nm"] < r["distance_nm"] * 1.0 or (F[k]["min_rwy_ft"] > min(A.AIRPORTS[r["origin"]["icao"]]["rwy_ft"] or 99999,
                                                                                  A.AIRPORTS[r["destination"]["icao"]]["rwy_ft"] or 99999)
                                                         and not gravel_kit(r, k))]
check("every recommended aircraft can fly its route (a few long legacy sectors need a tech stop)", not bad, bad[:10])
sims = {s: sum(1 for r in R.values() if any(F[k]["sim"] == s for k in r["aircraft"])) for s in ("MSFS", "X-Plane")}
check("MSFS and X-Plane pilots both have most of the network", min(sims.values()) >= 0.85 * len(R), sims)
check("every station has a proper name", all(r[e]["city"] for r in R.values() for e in ("origin", "destination")))
check("no city name is left as an airport-data oddity", not [r["title"] for r in R.values() if "Ciudad de la Costa" in r["title"] or "Matoury" in r["title"]])

print("New kinds of mission")
with A.db() as con:
    made = {}
    for sc in MG.SCENARIOS:
        for i in range(25):
            m = va._scenario_mission(random.Random(i), sc, con, "KCVG", set())
            if m:
                made.setdefault(sc["key"], []).append(m)
check("every scenario can produce a mission", set(made) == {sc["key"] for sc in MG.SCENARIOS},
      sorted({sc["key"] for sc in MG.SCENARIOS} - set(made)))
ch = [m for k, ms in made.items() if k.startswith("challenge_") for m in ms]
check("challenge missions name the airport and what makes it hard",
      ch and all(m.get("challenge", {}).get("icao") in MG.CHALLENGES and m["challenge"]["note"] in m["briefing"] for m in ch))
check("challenge missions pay a little more", all(m["category"] == "Challenge" for m in ch))
sp = [m for k in ("dg_batteries", "dg_chemicals", "live_cattle", "zoo_transfer", "valuables", "outsize", "tour_gear") for m in made.get(k, [])]
check("special cargo comes with handling notes", sp and all(m.get("handling", {}).get("notes") for m in sp))
fe = [m for k in ("ferry_mro", "ferry_paint", "ferry_delivery", "ferry_storage", "positioning") for m in made.get(k, [])]
check("ferry flights carry no cargo and pay the ferry bonus", fe and all(m["payload_lbs"] == 0 and m["ferry_bonus"] == va.FERRY_BONUS
                                                                       and m["category"] == "Ferry" for m in fe))
dl = made.get("ferry_delivery", [])
check("a factory delivery is only offered for types built there", dl and all(set(m["aircraft"]) <= {"B77F", "B748F", "B763F"} and m["types_only"] for m in dl))
st = made.get("ferry_storage", [])
check("only older types go to desert storage", st and all(m["aircraft"][0] in ("B722F", "B732F", "B742F", "A306F", "B733F", "MD11F") for m in st))
mixed = [m for ms in made.values() for m in ms if len(m["aircraft"]) >= 2]
both = sum(1 for m in mixed if len({F[k]["sim"] for k in m["aircraft"]}) == 2)
check("recommendations mix MSFS and X-Plane types where both fit", both >= 0.8 * len(mixed), f"{both}/{len(mixed)}")
check("place names read properly", not [m["briefing"] for m in made.get("challenge_himalaya", []) if "Shannan" in m["briefing"]])
err, _ = va.check_booking(dl[0], "B738F", None, A.settings())
check("a delivery can't be flown in another type", err and "for the" in err, err)

print("Rotations")
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Rotation-Test-Pass-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "require_type_ratings": False, "enforce_airframes": False, "enforce_ranks": False})
boot = c.get("/api/bootstrap").json
rots = {r["id"]: r for r in boot["rotations"]}
check("rotations are offered", len(rots) >= 15, len(rots))
check("each can be flown by at least one type", all(r["aircraft"] for r in rots.values()), [k for k, r in rots.items() if not r["aircraft"]])
check("most can be flown on either simulator", sum(1 for r in rots.values() if len({F[k]["sim"] for k in r["aircraft"]}) == 2) >= 0.75 * len(rots))
legs = {l["id"]: l for l in boot["tour_legs"] if l.get("rotation")}
check("rotation legs are listed with the tour legs", len(legs) >= 60, len(legs))
check("rotation numbers don't clash with jobs, routes or live missions",
      all(9000 < int(i[3:]) < 9100 or 9500 < int(i[3:]) < 9600 for i in legs))
r6 = rots["R6"]
ids = [f"PAC{r6['series'] + i + 1}" for i in range(len(r6["legs"]) - 1)]
check("a pilot starts on leg 1", boot["rotation_progress"]["R6"]["next"] == ids[0])
b = c.post("/api/booking", json={"mission_id": ids[1], "aircraft": "B738F", "airframe": None}).json
check("legs can't be flown out of order", "error" in b and "leg 1" in b["error"], b)
b = c.post("/api/booking", json={"mission_id": ids[0], "aircraft": "B77F", "airframe": None}).json
check("only the rotation's types", "error" in b and "rotation is flown with" in b["error"], b)

rw = analysis.runways(A.DATA)


def fly_leg(mid, ac):
    b = c.post("/api/booking", json={"mission_id": mid, "aircraft": ac, "airframe": None}).json
    if "error" in b:
        return b
    m = legs[mid]
    c.post("/api/acars/app/start", json={"source": "MSFS", "requested_at": b["requested_at"]})
    rec = FlightRecorder(b)
    o, d = m["origin"]["icao"], m["destination"]["icao"]
    for s in fly(o, rw[o][0][0], d, rw[d][0][0]):
        rec.update(s)
    c.post("/api/acars/app/complete", json={"record": rec.export(), "requested_at": b["requested_at"], "source": "MSFS"})
    return c.post("/api/pirep", json={"remarks": "rotation test"}).json


types = ["B738F", "B733F", "A306F", "B752F"]     # either simulator, any leg
filed = [fly_leg(mid, types[i % len(types)]) for i, mid in enumerate(ids)]
check("every leg of the lap files", all(p.get("id") for p in filed), [p.get("error") for p in filed])
with A.db() as con:
    rows = [json.loads(r["detail"] or "{}") for r in con.execute("SELECT detail FROM pireps ORDER BY id")]
bon = [x for x in rows[-1].get("bonuses", []) if x[0].startswith("Rotation complete")]
check("the last leg pays the rotation bonus", bon and bon[0][1] == r6["bonus"], rows[-1].get("bonuses"))
check("earlier legs don't", not any(x[0].startswith("Rotation complete") for d in rows[:-1] for x in d.get("bonuses", [])))
prog = c.get("/api/bootstrap").json["rotation_progress"]["R6"]
check("after a full lap it starts again at leg 1", prog["next"] == ids[0] and prog["completed"] == 0 and prog["laps"] == 1, prog)
badges = {x["id"]: x for x in c.get("/api/va/career").json["badges"]}
check("a full lap earns the Rotation award", badges["rotation"]["earned"] and not badges["rotations_5"]["earned"])
p = fly_leg(ids[0], "B752F")
check("the rotation can be flown again", bool(p.get("id")), p)
prog = c.get("/api/bootstrap").json["rotation_progress"]["R6"]
check("and the second lap is under way", prog["completed"] == 1 and prog["next"] == ids[1] and prog["laps"] == 1, prog)
career = c.get("/api/va/career").json
check("the Career page lists rotations with progress", career["rotations"] and career["rotation_progress"]["R6"]["laps"] == 1)

print("History")
with A.db() as con:
    con.execute("INSERT INTO live_missions (id, data, scenario_key, created, expires, status) VALUES (?,?,?,?,?, 'completed')",
                ("PAC6100", json.dumps({"id": "PAC6100", "reward": 123, "title": "An old live mission"}), "x", 1, 2))
check("an old live mission keeps its own record if a new route now shares its number",
      "PAC6100" in R and va.live_mission("PAC6100", True)["reward"] == 123)

print("\nNETWORK GROWTH TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
