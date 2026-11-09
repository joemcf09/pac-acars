"""The load planner works for every freighter: read the main deck, swap two units, save to the release.
Run from the PAC folder: python tests/test_load_planner_all.py"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-lp-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)
c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Lp-Test-1"})
c.post("/api/settings", json={"enforce_pilot_location": False, "enforce_airframes": False, "enforce_ranks": False,
                              "require_type_ratings": False, "require_release_signature": False, "cargo_orders_enabled": False})
for code in ("MD11F", "B763F", "B748F"):
    route = next(r for r in A.ROUTES.values() if code in r["aircraft"] and r.get("category") == "Scheduled")
    ls = c.post("/api/plan/loadsheet", json={"mission_id": route["id"], "aircraft": code}).json
    c.delete("/api/booking")
    b = c.post("/api/booking", json={"mission_id": route["id"], "aircraft": code, "manifest_seed": ls["seed"], "zone_ack": True})
    g = c.get("/api/load-plan")
    d = g.json
    main = d.get("main") or []
    units = [p for p in d.get("positions", []) if p["pos"] in main]
    check(f"{code}: the planner reads the main deck", g.status_code == 200 and len(main) >= 10 and units, (g.status_code, d.get("error")))
    if len(units) < 2:
        continue
    a, z = units[0]["pos"], units[-1]["pos"]
    asg = {p["pos"]: p["pos"] for p in d["positions"]}
    asg[a], asg[z] = z, a
    s = c.post("/api/load-plan", json={"assignments": asg, "revision": d["revision"], "requested_at": d["requested_at"]})
    moved = {p["pos"]: p["weight_lbs"] for p in s.json.get("positions", [])}
    check(f"{code}: swapping two units saves to the release", s.status_code == 200 and s.json.get("changed")
          and moved.get(a) == units[-1]["weight_lbs"] and moved.get(z) == units[0]["weight_lbs"], (s.status_code, s.json.get("error")))
    bad = dict(asg); bad[a] = "LOWER-99"
    check(f"{code}: a main-deck unit can't leave the main deck", c.post("/api/load-plan", json={"assignments": bad, "revision": s.json.get("revision"),
          "requested_at": d["requested_at"]}).status_code == 400)
print(); print("All load planner checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
