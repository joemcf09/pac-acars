"""The Pilots page: a roster of PAC pilots and each pilot's profile, for signed-in pilots only, with nothing private
(email, Discord, VATSIM/IVAO, wallet, settings) ever sent.

Run from the PAC folder:   python tests/test_pilots_page.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


founder = A.app.test_client()
founder.post("/api/auth/setup", json={"password": "Pilots-Page-Test-1"})
with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location,country,discord,prefs) VALUES "
                "('PAC0002','Jose Miguel Martin','secret-jose@example.com','KCVG',?,'Active','Passed',0,'KBNA','Spain','jose#1234',"
                "'{\"vatsim_cid\": \"1234567\"}')", (time.time(),))
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location) VALUES "
                "('PAC0003','Old Timer','old@example.com','KMIA',?,'Inactive','Passed',0,'KMIA')", (time.time() - 99999,))
    cols = {r[1] for r in con.execute("PRAGMA table_info(pireps)")}
    row = {"pilot_id": "PAC0002", "flight_number": "PAC001", "dep": "KCVG", "arr": "KBNA", "aircraft": "B738F", "landing_rate": -265,
           "score": 95, "grade": "A", "status": "Delivered", "demo": 0, "source": "X-Plane", "filed_at": time.time(),
           "review_status": "Accepted", "detail": "{}", "block_min": 70, "distance_nm": 297, "payload_lbs": 30000}
    row = {k: v for k, v in row.items() if k in cols}
    con.execute(f"INSERT INTO pireps ({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))
auth._set_password("PAC0002", "Jose-Test-Pass-1")
jose = A.app.test_client()
jose.post("/api/auth/login", json={"pilot_id": "PAC0002", "password": "Jose-Test-Pass-1"})
guest = A.app.test_client()

print("Who can see it")
check("visitors are asked to sign in for the roster", guest.get("/api/pilots").status_code == 401)
check("and for a profile", guest.get("/api/pilots/PAC0002").status_code == 401)
r = jose.get("/api/pilots")
check("pilots see the roster", r.status_code == 200 and {p["pilot_id"] for p in r.get_json()["pilots"]} == {"PAC0001", "PAC0002", "PAC0003"},
      r.get_data(as_text=True)[:200])
check("pilots can open another pilot's profile", jose.get("/api/pilots/PAC0001").status_code == 200)
check("an unknown pilot ID says so", jose.get("/api/pilots/PAC0999").status_code == 404)

print("Nothing private")
everything = r.get_data(as_text=True) + jose.get("/api/pilots/PAC0002").get_data(as_text=True) + founder.get("/api/pilots/PAC0002").get_data(as_text=True)
for secret in ("secret-jose@example.com", "jose#1234", "1234567", "password", "wallet", "simbrief"):
    check(f"never sends {secret!r}", secret not in everything.lower() if secret.islower() else secret not in everything)

print("What a profile shows")
d = founder.get("/api/pilots/PAC0002").get_json()
check("name, rank and base", d["profile"]["name"] == "Jose Miguel Martin" and d["career"]["rank"] and d["profile"]["base"] == "KCVG", d["profile"])
check("where they are now", d["location"] == "KBNA", d["location"])
check("their flights and hours", d["stats"]["totals"]["flights"] == 1 and d["career"]["hours"] == 1.2, d["stats"]["totals"])
check("recent flights with grade and landing", d["stats"]["recent"][0]["grade"] == "A" and d["stats"]["recent"][0]["landing_rate"] == -265)
check("earned awards only", d["awards"] and all(a["earned"] for a in d["awards"]), d["awards"])
check("the route map", d["map"]["routes"] and {a["icao"] for a in d["map"]["airports"]} == {"KCVG", "KBNA"}, d["map"])
check("whose page it is", d["you"] is False and jose.get("/api/pilots/PAC0002").get_json()["you"] is True)
roster = {p["pilot_id"]: p for p in r.get_json()["pilots"]}
check("inactive pilots are marked, so the page can hide them", roster["PAC0003"]["status"] == "Inactive")
check("the roster carries the last flight date", roster["PAC0002"]["last_flight"] and roster["PAC0001"]["last_flight"] is None)

print("\nPILOTS PAGE TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
