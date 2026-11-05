"""Transfer hours: a pilot requests verified hours from other VAs, staff approve (half, capped at 75, network hours
don't stack on VA hours) or reject, the pilot gets one appeal, proof screenshots stay private, and rank counts it.

Run from the PAC folder:   python tests/test_transfers.py
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import transfers as T  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Transfer-Test-Pass-1"})
pub = A.app.test_client()


def new_pilot(name):
    pub.post("/api/applications", json={"name": name, "email": f"{name.split()[0].lower()}@example.com", "agree": True,
                                        "simulator": "MSFS", "hub": "KCVG"})
    aid = [a for a in staff.get("/api/staff/overview").json["applications"] if a["status"] == "Pending"][0]["id"]
    pid = staff.post(f"/api/staff/applications/{aid}", json={"action": "approve", "email_it": False}).json["pilot_id"]
    tok = staff.post(f"/api/staff/pilots/{pid}/signin-link").json["link"].split("set-password=")[1]
    c = A.app.test_client()
    c.post("/api/auth/accept", json={"token": tok, "password": "Transfer-Test-Pass-2"})
    return pid, c


def send(c, sources, proofs=None):
    data = {"sources": json.dumps(sources), "comment": "test"}
    for i in range(len(sources)) if proofs is None else proofs:
        data[f"proof{i}"] = (io.BytesIO(PNG), f"p{i}.png")
    return c.post("/api/transfers", data=data, content_type="multipart/form-data")


def pending(pid):
    return [q for q in staff.get("/api/staff/transfers").json["requests"] if q["pilot_id"] == pid and q["status"] == "Pending"][0]


print("Credit rules")
check("VA hours add up, then half", T.credit_for([{"kind": "va", "hours": 40}, {"kind": "va", "hours": 30}]) == (35.0, 70.0))
check("network hours don't stack on VA hours", T.credit_for([{"kind": "va", "hours": 60}, {"kind": "network", "hours": 100}]) == (50.0, 100.0))
check("capped at 75", T.credit_for([{"kind": "va", "hours": 900}])[0] == 75.0)

pid, c = new_pilot("Transfer Pilot")
print("Pilot request")
st = c.get("/api/transfers").json
check("a new pilot can request", st["can_request"] and not st["is_appeal"], st)
r = send(c, [{"kind": "va", "name": "Other VA", "url": "https://example.com/p/1", "hours": 120}], proofs=[])
check("a screenshot is required", r.status_code == 400 and "screenshot" in r.json["error"], r.json)
r = send(c, [{"kind": "va", "name": "Other VA", "url": "not a link", "hours": 120}])
check("a real link is required", r.status_code == 400 and "link" in r.json["error"], r.json)
r = send(c, [{"kind": "va", "name": f"VA {i}", "url": "https://example.com", "hours": 10} for i in range(4)])
check("at most 3 sources", r.status_code == 400, r.json)
r = send(c, [{"kind": "va", "name": "Other VA", "url": "https://example.com/p/1", "hours": 120},
             {"kind": "network", "name": "VATSIM", "url": "https://stats.vatsim.net/1", "hours": 300}])
check("a valid request is accepted", r.status_code == 200 and not r.json["can_request"], r.json)
r = send(c, [{"kind": "va", "name": "Again", "url": "https://example.com", "hours": 5}])
check("no second request while one is pending", r.status_code == 400, r.json)

print("Private proof")
q = pending(pid)
proof = q["sources"][0]["proof"]
check("the pilot can open their own screenshot", c.get(proof).status_code == 200)
check("staff can open it", staff.get(proof).status_code == 200)
other_pid, other = new_pilot("Nosy Pilot")
check("another pilot can't", other.get(proof).status_code == 404)
check("a visitor can't", A.app.test_client().get(proof).status_code in (401, 403, 404))

print("Staff reject, then appeal")
r = staff.post(f"/api/staff/transfers/{q['id']}", json={"action": "reject", "note": ""})
check("rejecting needs a reason", r.status_code == 400, r.json)
r = staff.post(f"/api/staff/transfers/{q['id']}", json={"action": "reject", "note": "Logbook link doesn't show your name."})
check("rejected", r.status_code == 200 and r.json["status"] == "Rejected", r.json)
st = c.get("/api/transfers").json
check("the pilot can appeal once", st["can_request"] and st["is_appeal"], st)
check("the pilot sees the staff note", st["requests"][0]["note"].startswith("Logbook"), st["requests"][0])
send(c, [{"kind": "va", "name": "Other VA", "url": "https://example.com/p/1", "hours": 120},
         {"kind": "va", "name": "Second VA", "url": "https://example.org/p/9", "hours": 50},
         {"kind": "network", "name": "VATSIM", "url": "https://stats.vatsim.net/1", "hours": 300}])
q = pending(pid)
r = staff.post(f"/api/staff/transfers/{q['id']}", json={"action": "approve", "sources": [{"approved": False}] * 3})
check("approving needs at least one verified source", r.status_code == 400, r.json)
# staff verify both VAs (correcting the second to 40 h) and not VATSIM: (120 + 40) / 2 = 80, capped to 75
r = staff.post(f"/api/staff/transfers/{q['id']}", json={"action": "approve", "note": "Checked.",
              "sources": [{"approved": True, "verified": 120}, {"approved": True, "verified": 40}, {"approved": False}]})
check("approved with 75 h (capped)", r.status_code == 200 and r.json["credited"] == 75.0, r.json)
st = c.get("/api/transfers").json
check("credited hours show on Career", st["transfer_hours"] == 75.0 and not st["can_request"], st)
car = c.get("/api/va/career").json["career"]
check("rank hours include the transfer", car["transfer_hours"] == 75.0 and car["hours"] >= 75, car)
check("PAC hours don't", car["pac_hours"] == 0, car)
check("no checkride means still Cadet", car["rank"] == "Cadet", car["rank"])
check("no more requests after the appeal", send(c, [{"kind": "va", "name": "X", "url": "https://x.com", "hours": 9}]).status_code == 400)

print("Window and staff-set hours")
with A.db() as con:
    con.execute("UPDATE pilots SET joined=?, transfer_hours=? WHERE id=?", (T.PROGRAM_OPENS - 90 * 86400, 0, other_pid))
st = other.get("/api/transfers").json
check("pilots who joined before the program get the 60 days from launch", st["can_request"], st)
_orig = T.PROGRAM_OPENS
T.PROGRAM_OPENS = _orig - 70 * 86400   # as if the program opened 70 days ago, before this pilot's join date below
with A.db() as con:
    con.execute("UPDATE pilots SET joined=? WHERE id=?", (T.PROGRAM_OPENS - 90 * 86400, other_pid))
st = other.get("/api/transfers").json
check("the window closes after 60 days", not st["can_request"] and "closed" in (st["why_not"] or ""), st)
T.PROGRAM_OPENS = _orig
with A.db() as con:
    con.execute("UPDATE pilots SET transfer_hours=? WHERE id=?", (20, other_pid))
send(other, [{"kind": "va", "name": "Small VA", "url": "https://example.com", "hours": 10}])
q = pending(other_pid)
staff.post(f"/api/staff/transfers/{q['id']}", json={"action": "approve", "sources": [{"approved": True, "verified": 10}]})
st = other.get("/api/transfers").json
check("approving never lowers hours staff set by hand", st["transfer_hours"] == 20, st)
check("staff tab badge counts pending requests", staff.get("/api/staff/overview").json["transfer_pending"] == 0)

print()
print("All transfer checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
