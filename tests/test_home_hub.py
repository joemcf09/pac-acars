"""New pilots start at the home base they chose, train there by default, and return there after the line checkride."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import va  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Home-Hub-Test-1"})
A.app.test_client().post("/api/applications", json={"name": "Euro Pilot", "email": "euro@example.com", "country": "IT", "simulator": "MSFS",
                                                    "hub": "LIMC", "experience": "300 hours", "motivation": "cargo", "handbook": True,
                                                    "agree": True, "read_handbook": True})
aid = [a for a in staff.get("/api/staff/overview").json["applications"] if a["status"] == "Pending"][0]["id"]
pid = staff.post(f"/api/staff/applications/{aid}", json={"action": "approve"}).json["pilot_id"]
check("a new pilot starts at the hub they chose", va.pilot_location(pid) == "LIMC", va.pilot_location(pid))
tok = staff.post(f"/api/staff/pilots/{pid}/signin-link").json["link"].split("set-password=")[1]
c = A.app.test_client()
c.post("/api/auth/accept", json={"token": tok, "password": "Home-Hub-Test-2"})
opts = c.get("/api/training/options").json
first = opts["courses"][0]["choices"][0]["spec"]
check("their home base is the first training airport", first["origin"] == "LIMC", first)
with A.db() as con:   # e.g. a fleet checkride that ended in New York
    con.execute("UPDATE pilots SET location='KEWR' WHERE id=?", (pid,))
    va.mark_line_checkride_passed(con, pid)
with A.db() as con:
    row = con.execute("SELECT checkride, location FROM pilots WHERE id=?", (pid,)).fetchone()
    tx = con.execute("SELECT amount FROM wallet WHERE pilot_id=? AND kind='training_travel'", (pid,)).fetchall()
check("passing the line checkride moves them home, free", row["checkride"] == "Passed" and row["location"] == "LIMC" and all(t[0] == 0 for t in tx) and tx, (dict(row), tx))
with A.db() as con:
    con.execute("UPDATE pilots SET location='KJFK' WHERE id=?", (pid,))
    again = va.mark_line_checkride_passed(con, pid)
check("only the first pass moves them", not again and va.pilot_location(pid) == "KJFK")
print(f"\n{len(failures)} failure(s)" if failures else "\nall passed")
sys.exit(1 if failures else 0)
