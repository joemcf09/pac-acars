"""Staying active: next flight due, leave of absence, reminders and the optional auto-inactive switch.

Run from the PAC folder:   python tests/test_activity.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import activity  # noqa: E402
import botlink  # noqa: E402

failures = []
DAY = 86400


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Activity-Test-1"})
pid = A.settings().get("pilot_id") or "PAC0001"


def set_joined(days_ago):
    with A.db() as con:
        con.execute("UPDATE pilots SET joined=?, status='Active', prefs='{}' WHERE id=?", (time.time() - days_ago * DAY, pid))


print("Off until staff switch it on")
set_joined(60)
a = c.get("/api/pilot/activity").json
check("off by default: pilots see nothing", a["enabled"] is False, a)
check("no leave while it's off", c.post("/api/pilot/leave", json={"days": 14}).status_code == 400)
with A.db() as con:
    con.execute("UPDATE pilots SET discord_id='123456789' WHERE id=?", (pid,))
check("no reminders while it's off", activity.reminders_due() == [])
check("no overdue badge on the staff tab", c.get("/api/staff/overview").json.get("activity_overdue") == 0)
with A.db() as con:
    con.execute("UPDATE pilots SET discord_id=NULL WHERE id=?", (pid,))
c.post("/api/settings", json={"activity_rule_on": True})

print("Next flight due")
set_joined(0)
a = c.get("/api/pilot/activity").json
check("a new pilot is due 45 days after joining", a["state"] == "ok" and 44 <= a["days_left"] <= 45, a)
check("it's on the pilot's record too", (c.get("/api/pilot/me").json.get("activity") or {}).get("policy_days") == 45)
set_joined(40)
check("inside the last week it's due soon", c.get("/api/pilot/activity").json["state"] == "soon")
set_joined(50)
a = c.get("/api/pilot/activity").json
check("past the date it's overdue", a["state"] == "overdue" and a["days_left"] < 0, a)

print("Leave of absence")
check("too long is refused", c.post("/api/pilot/leave", json={"days": 400}).status_code == 400)
r = c.post("/api/pilot/leave", json={"days": 14, "reason": "Vacation"})
a = r.json
check("leave starts", r.status_code == 200 and a["state"] == "leave" and a["leave"]["reason"] == "Vacation", a)
check("the roster shows On leave", a["status"] == "On leave", a["status"])
check("the clock restarts after the leave", 58 <= a["days_left"] <= 59, a["days_left"])
check("a second leave on top is refused", c.post("/api/pilot/leave", json={"days": 7}).status_code == 400)
a = c.delete("/api/pilot/leave").json
check("ending it early makes the pilot Active again", a["state"] == "ok" and a["status"] == "Active", a)
check("with a fresh 45 days", 44 <= a["days_left"] <= 45, a["days_left"])

print("A leave that has run out ends by itself")
set_joined(100)
with A.db() as con:
    con.execute("UPDATE pilots SET status='On leave', prefs=? WHERE id=?",
                (__import__("json").dumps({"leave": {"from": time.time() - 20 * DAY, "until": time.time() - 2 * DAY, "reason": ""}}), pid))
a = c.get("/api/pilot/activity").json
check("back to Active, due 45 days after it ended", a["status"] == "Active" and a["state"] == "ok" and 42 <= a["days_left"] <= 43, a)

print("Reminders")
set_joined(40)
with A.db() as con:
    con.execute("UPDATE pilots SET discord_id='123456789' WHERE id=?", (pid,))
hdr = {"X-PAC-Bot": botlink.secret()}
r = c.get("/api/bot/activity", headers=hdr)
check("the bot API needs its secret", c.get("/api/bot/activity").status_code == 404)
rem = r.json.get("reminders") or []
check("a linked pilot due soon is listed", r.status_code == 200 and any(x["pilot_id"] == pid for x in rem), r.json)
c.post("/api/bot/activity/reminded", json={"items": rem}, headers=hdr)
check("once reminded, not again for the same date", not c.get("/api/bot/activity", headers=hdr).json["reminders"])

print("Auto-inactive is off unless staff switch it on")
set_joined(60)
c.get("/api/staff/activity")
with A.db() as con:
    st_ = con.execute("SELECT status FROM pilots WHERE id=?", (pid,)).fetchone()[0]
check("an overdue pilot stays Active by default", st_ == "Active", st_)
c.post("/api/settings", json={"activity_auto_inactive": True})
d = c.get("/api/staff/activity").json
check("with it on, overdue pilots become Inactive", any(p["pilot_id"] == pid and p["status"] == "Inactive" for p in d["pilots"]), d["pilots"][:1])
check("staff see the counts", d["counts"]["overdue"] >= 1, d["counts"])
c.post("/api/settings", json={"activity_days": "nonsense"})
check("a bad policy value falls back safely", activity.policy()["days"] == 45, activity.policy())

print()
print("All activity checks passed." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
