"""Landing and takeoff cards credit the pilot who flew the flight, not whoever is looking at it.
(The front end draws the cards from the logbook entry: its pilot_name and its simulator, `source`.)

Run from the PAC folder:   python tests/test_flight_cards.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "Flight-Cards-Test-1"})


def pirep(pilot_id, source):
    with A.db() as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(pireps)")}
        row = {"pilot_id": pilot_id, "flight_number": "PAC001", "dep": "KCVG", "arr": "KBNA", "aircraft": "B738F", "source": source,
               "landing_rate": -265, "score": 95, "grade": "A", "status": "Delivered", "demo": 0, "filed_at": time.time(),
               "review_status": "Accepted", "detail": json.dumps({}), "block_min": 70}
        row = {k: v for k, v in row.items() if k in cols}
        return con.execute(f"INSERT INTO pireps ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values())).lastrowid


with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location) VALUES "
                "('PAC0002','Jose Miguel Martin','j@example.com','KCVG',?,'Active','Passed',0,'KBNA')", (time.time(),))
e = c.get(f"/api/logbook/{pirep('PAC0002', 'X-Plane')}").get_json()
check("another pilot's flight names that pilot", e.get("pilot_name") == "Jose Miguel Martin", e.get("pilot_name"))
check("and keeps the simulator it was flown in", e.get("source") == "X-Plane", e.get("source"))
e = c.get(f"/api/logbook/{pirep('PAC0001', 'MSFS')}").get_json()
check("the founder's own flight names the founder", bool(e.get("pilot_name")) and e.get("pilot_id") == "PAC0001", e.get("pilot_name"))
e = c.get(f"/api/logbook/{pirep('EX-PAC0009', 'MSFS')}").get_json()
check("a removed pilot's flight is credited to a former PAC pilot", e.get("pilot_name") == "Former PAC pilot", e.get("pilot_name"))
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
check("the cards use the flight's pilot and simulator", "src.pilot_name ?" in js and "c.sim || ac.sim" in js)

print("\nFLIGHT CARDS TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
