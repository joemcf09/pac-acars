"""Campaign end to end (Holiday Rush style): create, extras, publish, upcoming, credit, patch badge, close, pay once, news."""
import os, sys, tempfile, time
os.environ.setdefault("PAC_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
from werkzeug.security import generate_password_hash
import cargo_programs as cp

with A.db() as con:
    for pid, staff in (("PAC0001", 1), ("PAC0006", 0)):
        if not con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone():
            con.execute("INSERT INTO pilots (id, name) VALUES (?, ?)", (pid, pid))
        con.execute("UPDATE pilots SET password_hash=?, staff=?, status='Active' WHERE id=?", (generate_password_hash("x"), staff, pid))
staff = A.app.test_client()
with staff.session_transaction() as s: s["pid"] = "PAC0001"
pilot = A.app.test_client()
with pilot.session_transaction() as s: s["pid"] = "PAC0006"

r = staff.post("/api/staff/cargo-campaigns", json={"title": "Holiday Rush", "description": "Peak parcels", "target_lbs": 150000,
               "destinations": ["KCVG", "KMIA"], "start_date": "2026-11-16", "end_date": "2026-12-24"})
assert r.status_code == 201, r.get_json(); cid = r.get_json()["id"]
assert staff.post(f"/api/staff/cargo-campaigns/{cid}", json={"action": "extras", "patch": "/static/patches/holiday.png", "reward_cash": 2500}).status_code == 200
assert pilot.get("/api/pilot/cargo-campaigns").get_json()["campaigns"] == [] , "drafts stay hidden"
assert staff.post(f"/api/staff/cargo-campaigns/{cid}", json={"action": "publish"}).status_code == 200
c = pilot.get("/api/pilot/cargo-campaigns").get_json()["campaigns"][0]
assert c["phase"] in ("Upcoming", "Active"), c["phase"]

# flights: two qualifying, one outside the window, one checkride, one to a non-campaign airport
with A.db() as con:
    cols = {r[1] for r in con.execute("PRAGMA table_info(pireps)")}
    def pirep(pid, arr, lbs, when, cat="Scheduled"):
        row = {"pilot_id": pid, "dep": "KMEM", "arr": arr, "payload_lbs": lbs, "filed_at": when, "demo": 0, "review_status": "Accepted",
               "status": "Delivered", "category": cat}
        row = {k: v for k, v in row.items() if k in cols}
        con.execute(f"INSERT INTO pireps ({','.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
    t0 = c["starts"]
    pirep("PAC0006", "KCVG", 100000, t0 + 3600)
    pirep("PAC0001", "KMIA", 60000, t0 + 7200)
    pirep("PAC0006", "KCVG", 99999, t0 - 3600)
    pirep("PAC0006", "KCVG", 50000, t0 + 9000, "Checkride")
    pirep("PAC0006", "LIMC", 50000, t0 + 9000)
    camp = cp.campaigns(con, "PAC0006")[0]
assert camp["cargo_lbs"] == 160000 and camp["personal_lbs"] == 100000 and camp["flights"] == 2, camp
assert camp["goal_met"] and camp["contributor_badge"]
paid = []
with A.db() as con:
    cp.wrap_up(con, lambda pid, kind, amt, desc, ref, c2: paid.append((pid, amt)), now=camp["ends"] + 1)
    cp.wrap_up(con, lambda pid, kind, amt, desc, ref, c2: paid.append((pid, amt)), now=camp["ends"] + 2)
    news = con.execute("SELECT title, body FROM news WHERE title LIKE 'Holiday Rush%'").fetchall()
assert sorted(paid) == [("PAC0001", 2500.0), ("PAC0006", 2500.0)], paid
assert len(news) == 1 and "mission accomplished" in news[0][0], news
print("CAMPAIGN E2E PASSED:", news[0][1][:120])
