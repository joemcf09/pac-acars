"""Growth: proving flights, ramp inspections, safety audit, press releases, competitors, mentoring and seniority.
Run from the PAC folder: python tests/test_growth.py"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-growth-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A, growth as G, trips as T  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

g = vars(A); now = time.time()
with A.db() as con:
    G.migrate(con)
    for i, p in enumerate(("PAC0001", "PAC0002", "PAC0003", "PAC0004", "PAC0005")):
        con.execute("INSERT OR REPLACE INTO pilots (id, name, joined, status) VALUES (?,?,?,?)", (p, f"Pilot {i+1}", now - (10 - i) * 86400, "Active"))
    # proving flight
    pair = ("KCVG", "EGNX")
    if any({r["origin"]["icao"], r["destination"]["icao"]} == set(pair) for r in A.ROUTES.values()):
        pair = ("KCVG", "LFPG") if not any({r["origin"]["icao"], r["destination"]["icao"]} == {"KCVG", "LFPG"} for r in A.ROUTES.values()) else ("PANC", "RJBB")
    rid = G.propose(con, *pair, "PAC0001", g)
    try:
        G.propose(con, *pair, "PAC0001", g); check("the same route can't be proposed twice", False)
    except ValueError:
        check("the same route can't be proposed twice", True)
    try:
        G.propose(con, "KCVG", "KCVG", "PAC0001", g); check("a route needs two airports", False)
    except ValueError:
        check("a route needs two airports", True)
    n0 = len(A.ROUTES)
    out = G.on_filed(con, "PAC0003", {"dep": pair[1], "arr": pair[0], "status": "Delivered"}, {}, 9001, g, now)
    check("a flight between the two airports proves the route", out.get("proved_route") and len(A.ROUTES) == n0 + 1, out)
    r = A.ROUTES[out["proved_route"]]
    check("the new route has types that can reach it", r["aircraft"] and all((A.FLEET[t].get("range_nm") or 0) >= r["distance_nm"] for t in r["aircraft"]))
    check("the opening is announced", con.execute("SELECT 1 FROM news WHERE title LIKE 'New route:%'").fetchone())
    routes2 = {}; G.load_routes(con, routes2)
    check("proven routes come back after a restart", out["proved_route"] in routes2)
    # ramp inspection
    pid_hit = next(i for i in range(1, 500) if __import__("zlib").crc32(f"ramp|{i}".encode()) % G.RAMP_ONE_IN == 0)
    heavy = (A.FLEET["B752F"].get("max_payload_lbs") or 80000) + 5000
    out = G.on_filed(con, "PAC0002", {"dep": "KCVG", "arr": "KMIA", "status": "Delivered", "aircraft": "B752F", "payload_lbs": heavy, "landing_rate": -150}, {}, pid_hit, g, now)
    check("an inspected arrival writes up an overweight aircraft", out.get("ramp_check") and any("over the" in f for f in out["ramp_check"]["findings"]), out)
    # mentoring
    con.execute("INSERT INTO mentorships (mentor, mentee, started) VALUES ('PAC0001','PAC0005',?)", (now,))
    for i in range(3):
        out = G.on_filed(con, "PAC0005", {"dep": "KCVG", "arr": "KMIA", "status": "Delivered"}, {}, 20000 + i, g, now)
    paid = con.execute("SELECT COUNT(*) FROM wallet WHERE kind='mentoring'").fetchone()[0]
    check("after three flights both mentor and mentee get the bonus", out.get("mentoring_done") and paid == 2)
    # milestone press release
    for i in range(100):
        con.execute("INSERT INTO pireps (filed_at, pilot_id, demo, review_status, payload_lbs, landing_rate, status) VALUES (?,?,0,'Accepted',30000,-150,'Delivered')", (now, "PAC0002"))
    G.on_filed(con, "PAC0002", {"dep": "A", "arr": "B"}, {}, None, g, now)
    check("the 100th flight gets a press release, once", con.execute("SELECT COUNT(*) FROM news WHERE title LIKE '%100th flight%'").fetchone()[0] == 1)
    G.on_filed(con, "PAC0002", {"dep": "A", "arr": "B"}, {}, None, g, now)
    check("milestone releases aren't repeated", con.execute("SELECT COUNT(*) FROM news WHERE title LIKE '%100th flight%'").fetchone()[0] == 1)
    # safety audit
    a = G.safety_audit(con, now)
    check("the audit credits smooth, on-time flying", all(c["ok"] for c in a["checks"][:3]), a)
    check("the audit flags the ramp write-up", not a["checks"][3]["ok"] and not a["passed"])
    # seniority
    order = G.seniority(con)
    check("seniority follows join date", order[:2] == ["PAC0001", "PAC0002"], order)
    check("junior pilots wait 12 hours on a new trip", G.senior_window_problem(con, "PAC0005", now - 3600, now) is not None)
    check("senior pilots can bid at once", G.senior_window_problem(con, "PAC0001", now - 3600, now) is None)
    check("everyone can bid after 12 hours", G.senior_window_problem(con, "PAC0005", now - 13 * 3600, now) is None)
    T.refresh(con, A.ROUTES.values(), A.FLEET, now)
    tid = con.execute("SELECT id FROM trips WHERE status='open'").fetchone()[0]
    try:
        T.bid(con, tid, "PAC0005", now); check("a junior pilot's early bid is refused with the reason", False)
    except ValueError as e:
        check("a junior pilot's early bid is refused with the reason", "Senior pilots" in str(e))
print("\n" + ("All growth checks passed." if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
