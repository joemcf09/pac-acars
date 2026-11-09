"""Operations (cargo campaigns): starting total, cash reward, patch, top contributors and the one-time wrap-up.
Run from the PAC folder: python tests/test_operations.py"""
import os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    with tempfile.TemporaryDirectory(prefix="pac-ops-") as temp:
        data = Path(temp) / "data"; data.mkdir()
        shutil.copy2(ROOT / "data" / "runways.json", data / "runways.json")
        sys.exit(subprocess.run([sys.executable, __file__, "--isolated"], cwd=ROOT, env=dict(os.environ, PAC_DATA_DIR=str(data))).returncode)
sys.path.insert(0, str(ROOT))
import app as A  # noqa: E402
import cargo_programs as CP  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond: failures.append(name)

c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Ops-Test-1"})
today = time.strftime("%Y-%m-%d", time.gmtime())
r = c.post("/api/staff/cargo-campaigns", json={"title": "Operation Island Supply", "description": "Relief", "start_date": today,
                                               "end_date": today, "target_lbs": 300000, "destinations": ["MYNN", "TJSJ", "TNCM"]})
cid = r.json["id"]
check("extras save", c.post(f"/api/staff/cargo-campaigns/{cid}", json={"action": "extras", "patch": "/static/patches/island-supply.png",
                                                                      "reward_cash": 5000, "baseline_lbs": 213500}).status_code == 200)
check("bad patch link refused", c.post(f"/api/staff/cargo-campaigns/{cid}", json={"action": "extras", "patch": "javascript:x"}).status_code == 400)
c.post(f"/api/staff/cargo-campaigns/{cid}", json={"action": "publish"})
now = time.time()
with A.db() as con:
    con.execute("INSERT OR IGNORE INTO pilots (id, name, status) VALUES ('PAC0002','Alex B.','Active')")
    for pid, arr, lbs in (("PAC0001", "TJSJ", 50000), ("PAC0002", "MYNN", 40000), ("PAC0002", "KMIA", 99999)):
        con.execute("""INSERT INTO pireps (filed_at, pilot_id, dep, arr, payload_lbs, status, review_status, demo, category)
                       VALUES (?,?,?,?,?,'Delivered','Accepted',0,'Scheduled')""", (now - 60, pid, "KMIA" if arr != "KMIA" else "KCVG", arr, lbs))
d = c.get("/api/pilot/cargo-campaigns").json["campaigns"][0]
check("progress counts the starting total plus flown cargo", d["cargo_lbs"] == 213500 + 90000 and d["goal_met"], d["cargo_lbs"])
check("top contributors ranked by pounds", [t["name"] for t in d["top"]][:2] == [d["top"][0]["name"], "Alex B."] and d["top"][0]["cargo_lbs"] == 50000, d["top"])
check("patch and reward shown", d["patch"].endswith("island-supply.png") and d["reward_cash"] == 5000)
with A.db() as con:
    con.execute("UPDATE cargo_campaigns SET ends=? WHERE id=?", (now - 1, cid))
c.get("/api/pilot/cargo-campaigns"); c.get("/api/pilot/cargo-campaigns")
with A.db() as con:
    pay = con.execute("SELECT pilot_id, amount FROM wallet WHERE kind='campaign' ORDER BY pilot_id").fetchall()
    news = con.execute("SELECT title, body FROM news WHERE title LIKE 'Operation Island Supply%'").fetchall()
check("each contributor paid once", [(p[0], p[1]) for p in pay] == [("PAC0001", 5000), ("PAC0002", 5000)], [tuple(p) for p in pay])
check("one wrap-up post with the result", len(news) == 1 and "mission accomplished" in news[0][0] and "Alex B." in news[0][1], [tuple(n) for n in news])
check("closed campaigns can't be changed", c.post(f"/api/staff/cargo-campaigns/{cid}", json={"action": "extras", "reward_cash": 9}).status_code == 409)
with A.db() as con:
    aw = A.cargo_experience.awards(con, "PAC0002") if hasattr(A, "cargo_experience") else __import__("cargo_experience").awards(con, "PAC0002")
check("the contributor's award carries the patch", aw and aw[0]["patch"].endswith("island-supply.png"), aw)
print(); print("All operations checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
