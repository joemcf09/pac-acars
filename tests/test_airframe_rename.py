"""Renaming an airframe: the new registration takes its hours, history, write-ups and job references with it.

Run from the PAC folder:   python tests/test_airframe_rename.py
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = Path(os.environ.get("PAC_DATA_DIR") or ROOT / "data")   # the folder the site itself uses
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
staff.post("/api/auth/setup", json={"password": "Rename-Test-Pass-1"})
guest = A.app.test_client()

regs = {a["reg"] for a in va.airframes()}
check("new installs seed the 737s on the type-coded tails", {"N738PC", "N739PC", "N740PC", "N741PC"} <= regs, sorted(regs))

# give an airframe some history under an old-scheme registration
with va.C["db"]() as con:
    con.execute("INSERT INTO airframes (reg, type, location, status, hours, cycles, hours_since_check, updated, name, named_by) "
                "VALUES ('N801PC','B738F','KBNA','Available',1.7,2,1.7,?, 'Spirit of Cincy', 'PAC0001')", (time.time(),))
    for i in range(2):
        con.execute("INSERT INTO pireps (filed_at, mission_title, aircraft, registration, airframe, dep, arr, demo, pilot_id, review_status, status) "
                    "VALUES (?, 'Ferry N801PC to Nashville', 'B738F', 'N801PC', 'N801PC', 'KCVG', 'KBNA', 0, 'PAC0001', 'Accepted', 'Accepted')", (time.time() - 100 + i,))
    con.execute("INSERT INTO maint (reg, ata, description, severity, status, time) VALUES ('N801PC', 32, 'Brake wear', 'deferred', 'open', ?)", (time.time(),))
    con.execute("INSERT INTO jobs (id, day, kind, data, status, created) VALUES ('J1','2026-10-15','ferry',?, 'open', ?)",
                (json.dumps({"title": "Ferry N801PC to Nashville", "suggested_airframe": "N801PC", "note": "not N801PCX"}), time.time()))
    con.execute("INSERT INTO airframes (reg, type, location, status, updated) VALUES ('N802PC','B738F','KBNA','Booked',?)", (time.time(),))
    con.execute("DELETE FROM airframes WHERE reg='N738PC'")

print("Renaming")
r = staff.post("/api/staff/airframes/N801PC/rename", json={"to": "n738pc"})
j = r.get_json() or {}
check("staff can rename an airframe", r.status_code == 200, j)
check("it reports what moved", j.get("renamed", {}).get("flights") == 2 and j["renamed"].get("write_ups") == 1 and j["renamed"].get("other") == 3, j.get("renamed"))
frame = next((a for a in va.airframes() if a["reg"] == "N738PC"), {})
check("hours, cycles, location and name carry over", frame.get("hours") == 1.7 and frame.get("cycles") == 2 and frame.get("location") == "KBNA"
      and frame.get("name") == "Spirit of Cincy", frame)
check("the old registration is gone", not any(a["reg"] == "N801PC" for a in va.airframes()))
check("the write-up follows it", [i["description"] for i in frame.get("open_items", [])] == ["Brake wear"], frame.get("open_items"))
h = staff.get("/api/airframes/N738PC").get_json() or {}
check("its flight history shows under the new tail", len(h.get("flights", [])) == 2, h)
with va.C["db"]() as con:
    job = json.loads(con.execute("SELECT data FROM jobs WHERE id='J1'").fetchone()[0])
    regs_in_pireps = {r[0] for r in con.execute("SELECT DISTINCT registration FROM pireps")}
    titles = {r[0] for r in con.execute("SELECT DISTINCT mission_title FROM pireps")}
check("jobs suggest the new tail and their titles name it; other tails are left alone",
      job == {"title": "Ferry N738PC to Nashville", "suggested_airframe": "N738PC", "note": "not N801PCX"}, job)
check("past flights' mission titles name the new tail", titles == {"Ferry N738PC to Nashville"}, titles)
check("PIREPs show the new registration", regs_in_pireps == {"N738PC"}, regs_in_pireps)

print("Repairing an earlier rename")
with va.C["db"]() as con:
    con.execute("INSERT INTO jobs (id, day, kind, data, status, created) VALUES ('J2','2026-10-15','ferry',?, 'open', ?)",
                (json.dumps({"title": "Ferry N803PC to Miami", "fixed_airframe": "N740PC"}), time.time()))
import subprocess  # noqa: E402
out = subprocess.run([sys.executable, str(ROOT / "tools" / "fix_renamed_text.py"), "N803PC=N740PC"], capture_output=True, text=True)
with va.C["db"]() as con:
    j2 = json.loads(con.execute("SELECT data FROM jobs WHERE id='J2'").fetchone()[0])
check("the repair tool fixes titles left by an earlier rename", out.returncode == 0 and j2["title"] == "Ferry N740PC to Miami", (out.stdout, out.stderr, j2))

print("Refusals")
r = staff.post("/api/staff/airframes/N802PC/rename", json={"to": "N739PC"})
check("a booked airframe can't be renamed", r.status_code == 400 and "booked" in r.get_json()["error"], r.get_json())
r = staff.post("/api/staff/airframes/N738PC/rename", json={"to": "N740PC"})
check("it won't take a registration that already exists", r.status_code == 400 and "already exists" in r.get_json()["error"], r.get_json())
r = staff.post("/api/staff/airframes/N999PC/rename", json={"to": "N998PC"})
check("an unknown airframe is refused", r.status_code == 400, r.get_json())
r = guest.post("/api/staff/airframes/N738PC/rename", json={"to": "N700PC"})
check("pilots who aren't staff can't rename", r.status_code in (401, 403), r.status_code)

print()
print("All good." if not failures else f"{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
