"""The live map: members see everyone flying for PAC; visitors only if staff make it public, and never names."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


founder = A.app.test_client()
founder.post("/api/auth/setup", json={"password": "Founder-Pass-123"})
with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff,location) VALUES "
                "('PAC0002','Bob Member','bob@example.com','KCVG',1767225600,'Active','Passed',0,'KCVG')")
auth._set_password("PAC0002", "Member-Pass-123")
pilot = A.app.test_client()
pilot.post("/api/auth/login", json={"pilot_id": "PAC0002", "password": "Member-Pass-123"})
guest = A.app.test_client()

check("/api/live opens nothing else to visitors", [r.rule for r in A.app.url_map.iter_rules() if r.rule.startswith("/api/live")] == ["/api/live"])
m = next(x for x in A.MISSIONS.values() if x["origin"]["icao"] == "KCVG")
A.save_booking({"mission": m, "aircraft": m["aircraft"][0], "ofp": None, "flight_number": "PAC4321", "requested_at": time.time(),
                "airframe": "N001PC"}, "PAC0002")
track = [[39.05 + i * 0.01, -84.66 - i * 0.01, 1000 + i * 100, "CLIMB"] for i in range(800)]
A.SESSIONS["PAC0002"] = {**A.SESSION_BLANK, "remote": {"flight": "PAC4321"}, "remote_seen": time.time(),
                         "remote_status": {"phase": "CRUISE", "phase_label": "Cruise", "dtg_nm": 412.3, "track": track,
                                           "live": {"lat": 40.1, "lon": -86.2, "alt_ft": 35012, "gs": 455.6, "hdg": 271, "on_ground": False}}}

print("Members")
d = pilot.get("/api/live").get_json()
f = d["flights"][0] if d["flights"] else {}
check("a flying pilot appears", len(d["flights"]) == 1 and f["flight"] == "PAC4321", d)
check("with position, altitude, speed and heading", (f["lat"], f["alt_ft"], f["gs"], f["hdg"]) == (40.1, 35012, 456, 271), f)
check("members see who's flying and the cargo", f.get("pilot") == "Bob Member" and f.get("reg") == "N001PC" and f.get("cargo") == m.get("cargo"))
check("the track is thinned for the map", 2 < len(f["track"]) <= 170 and f["track"][-1] == [track[-1][0], track[-1][1]], len(f["track"]))
check("the destination is given for the line to it", f.get("arr_pos") and len(f["arr_pos"]) == 2)

print("Visitors")
check("hidden from visitors by default", guest.get("/api/live").status_code == 401)
check("pilots can't make it public", pilot.post("/api/settings", json={"live_map_public": True}).status_code == 403)
founder.post("/api/settings", json={"live_map_public": True})
g = guest.get("/api/live").get_json()["flights"]
check("staff can make it public", len(g) == 1 and g[0]["flight"] == "PAC4321")
check("visitors never see names, registrations or cargo", not any(k in g[0] for k in ("pilot", "pilot_id", "reg", "cargo", "mission")), list(g[0]))
check("visitors are told the live map is open", guest.get("/api/bootstrap").get_json().get("live_public") is True)
founder.post("/api/settings", json={"live_map_public": False})
check("…and private again", guest.get("/api/live").status_code == 401)

print("Who drops off")
A.SESSIONS["PAC0002"]["remote_seen"] = time.time() - 300
check("a flight that stopped reporting drops off", pilot.get("/api/live").get_json()["flights"] == [])
A.SESSIONS["PAC0002"]["remote_seen"] = time.time()
A.SESSIONS["PAC0002"]["remote_status"]["live"] = {}
check("a flight without a position yet isn't shown", pilot.get("/api/live").get_json()["flights"] == [])
A.SESSIONS["PAC0002"]["remote"] = None
check("a handed-over flight is gone", pilot.get("/api/live").get_json()["flights"] == [])

print("\n" + ("LIVE MAP TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
