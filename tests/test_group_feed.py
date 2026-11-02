"""Pagani Aviation Group: the hub feed, the PRA division and village freight on flights into Anchorage."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402
import dispatch  # noqa: E402
import group  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


FEED = "/api/group/v1/summary"
staff = A.app.test_client()
staff.post("/api/auth/setup", json={"password": "Founder-Pass-123"})
with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,discord,hub,joined,status,checkride,staff) VALUES "
                "('PAC0002','Bob Member','bob@example.com','bob#1','PANC',1767225600,'Active','Passed',0)")
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff) VALUES "
                "('PAC0003','Gone Pilot','gone@example.com','KCVG',1767225600,'Inactive','Passed',0)")
auth._set_password("PAC0002", "Member-Pass-123")
pilot = A.app.test_client()
pilot.post("/api/auth/login", json={"pilot_id": "PAC0002", "password": "Member-Pass-123"})
guest = A.app.test_client()

print("Village freight on the cargo manifest")
dest = {"icao": "PANC", "name": "Anchorage", "lat": 61.17, "lon": -149.99}
orig = {"icao": "KCVG", "name": "Cincinnati", "lat": 39.05, "lon": -84.66}
mission = {"id": "M1", "title": "Cincinnati to Anchorage", "category": "General", "cargo": "General freight", "payload_lbs": 60000,
           "origin": orig, "destination": dest}
booking = {"mission": mission, "aircraft": "B763F", "flight_number": "PAC9301", "requested_at": 1767225600}
pilot_info = {"name": "Capt. Bob", "id": "PAC0002", "rank": "First Officer"}
d = dispatch.generate(booking, A.FLEET, pilot_info)
on = d.get("onward") or []
check("a PAC flight into Anchorage carries freight for PRA", 1 <= len(on) <= 4, d.get("onward"))
check("every piece is bound for a PRA strip", all(x["dest"] in group.PRA_STRIPS for x in on), on)
check("onward freight stays under 1,000 lb", sum(x["lb"] for x in on) <= 1000)
check("it is loaded in a real unit on this flight", all(x["pos"] in {p["pos"] for p in d["positions"]} for x in on))
check("the same booking prints the same pieces", dispatch.generate(booking, A.FLEET, pilot_info)["onward"] == on)
other = dict(booking, mission=dict(mission, destination=orig, origin=dest))
check("flights elsewhere carry none", "onward" not in dispatch.generate(other, A.FLEET, pilot_info))
partner = dict(booking, mission=dict(mission, contract=True, operator={"code": "XYZ", "name": "Partner"}))
check("partner crew hires carry none", "onward" not in dispatch.generate(partner, A.FLEET, pilot_info))
ferry = dict(booking, mission=dict(mission, category="Ferry", cargo="Ferry"))
check("ferries carry none", "onward" not in dispatch.generate(ferry, A.FLEET, pilot_info))

print("The PRA division")
check("staff can tick PRA on a pilot", staff.post("/api/staff/roster/PAC0002", json={"pra": True}).status_code == 200)
with A.db() as con:
    check("it's saved", con.execute("SELECT pra FROM pilots WHERE id='PAC0002'").fetchone()[0] == 1)
check("a pilot can't tick it themselves", pilot.post("/api/staff/roster/PAC0002", json={"pra": False}).status_code == 403)
ov = staff.get("/api/staff/overview").get_json()
check("the staff roster never carries password hashes", all("password_hash" not in p for p in ov["roster"]))
check("the staff roster shows the PRA tick", next(p for p in ov["roster"] if p["id"] == "PAC0002")["pra"] == 1)

print("Staff settings")
check("pilots can't read the group key", pilot.get("/api/staff/group").status_code == 403)
g = staff.get("/api/staff/group").get_json()
check("staff get a key and the feed address", len(g["key"]) >= 20 and g["url"].endswith(FEED) and g["enabled"] is False, g)
check("the key is never in ordinary settings", "group_feed_key" not in json.dumps(staff.get("/api/bootstrap").get_json()))

print("The feed")
check("off: refused even with the key", guest.get(FEED, headers={"X-Group-Key": g["key"]}).status_code == 404)
staff.post("/api/staff/group", json={"enabled": True})
check("on, no key: refused", guest.get(FEED).status_code == 403)
check("on, wrong key: refused", guest.get(FEED, headers={"X-Group-Key": "nope"}).status_code == 403)
pre = guest.options(FEED, headers={"Origin": "https://group.example", "Access-Control-Request-Headers": "X-Group-Key"})
check("browsers on another site may ask (CORS preflight)", pre.status_code == 200 and pre.headers.get("Access-Control-Allow-Origin") == "*"
      and "X-Group-Key" in pre.headers.get("Access-Control-Allow-Headers", ""), pre.status_code)

now = time.time()
detail = json.dumps({"dispatch": d})
with A.db() as con:
    for i, (pid, arr, ac, det) in enumerate([("PAC0002", "PANC", "B763F", detail), ("PAC0002", "PANC", "B722F", "{}"),
                                             ("PAC0002", "KCVG", "B763F", "{}"), ("PAC0001", "PANC", "B763F", json.dumps({"dispatch": {**d, "operator": {"code": "XYZ"}}}))]):
        con.execute("""INSERT INTO pireps (filed_at, flight_number, aircraft, registration, dep, arr, block_min, landing_rate, score, demo,
                       pilot_id, review_status, detail) VALUES (?,?,?,?,?,?,?,?,?,0,?, 'Accepted', ?)""",
                    (now - 3600 * (i + 1), f"PAC93{i:02d}", ac, "N100PC", "KCVG", arr, 300, -150 - i * 20, 90, pid, det))
group.clear_cache()
r = guest.get(FEED, headers={"X-Group-Key": g["key"]})
check("on, right key: answers", r.status_code == 200, r.status_code)
check("readable from another site", r.headers.get("Access-Control-Allow-Origin") == "*")
f = r.get_json()
text = json.dumps(f)
check("nothing private: no emails, Discord or password", not any(x in text for x in ("@example.com", "bob#1", "password", "pbkdf2", "scrypt")))
bob = next((p for p in f["pilots"] if p["callsign"] == "PAC0002"), None)
check("pilots are listed with hours and flights", bob and bob["flights"] == 3 and bob["hours"] == 15.0, bob)
check("divisions: PAC, Regional (flew the 727) and PRA", bob and bob["divisions"] == ["PAC", "PAC Regional", "PRA"], bob and bob["divisions"])
check("recent flights are listed", bob and len(bob["recent"]) == 3 and bob["recent"][0]["to"] == "PANC")
check("inactive pilots are left out", all(p["callsign"] != "PAC0003" for p in f["pilots"]))
hs = f["handoffs"]
check("Anchorage arrivals become handoffs, partner flights don't", len(hs) == 2, [h["flight"] for h in hs])
mine = next((h for h in hs if h["flight"] == "PAC9300"), None)
check("a handoff carries the pieces printed on its manifest", mine and [c["ref"] for c in mine["cargo"]] == [x["ref"] for x in on])
check("older PIREPs without village freight still get some", all(h["cargo"] for h in hs))
check("feed answers are cached briefly", guest.get(FEED, headers={"X-Group-Key": g["key"]}).get_json()["generated"] == f["generated"])

old = g["key"]
g2 = staff.post("/api/staff/group", json={"new_key": True}).get_json()
check("a new key replaces the old one", g2["key"] != old and guest.get(FEED, headers={"X-Group-Key": old}).status_code == 403
      and guest.get(FEED, headers={"X-Group-Key": g2["key"]}).status_code == 200)

print("METARs for PRA's go/no-go")
import weather  # noqa: E402
calls = []
weather._get = lambda url: (calls.append(url), "PAMR 091953Z 24008G15KT 10SM BKN045 08/02 A2990\nPATK 091953Z 00000KT 3SM -RA OVC012 06/05 A2985\n")[1]
M = "/api/group/v1/metar?ids=PAMR,PATK,TYE"
check("needs the key", guest.get(M).status_code == 403)
r = guest.get(M, headers={"X-Group-Key": g2["key"]})
j = r.get_json() or {}
check("returns raw METARs for stations that report", r.status_code == 200 and set(j.get("metars", {})) == {"PAMR", "PATK"}, j)
check("readable from another site", r.headers.get("Access-Control-Allow-Origin") == "*")
check("no stations: a clear error", guest.get("/api/group/v1/metar", headers={"X-Group-Key": g2["key"]}).status_code == 400)
def boom(url):
    raise weather.WeatherError("Weather is unavailable right now.")
weather._get = boom
check("weather down: says so", guest.get(M, headers={"X-Group-Key": g2["key"]}).status_code == 502)
staff.post("/api/staff/group", json={"enabled": False})
check("feed off: METARs off too", guest.get(M, headers={"X-Group-Key": g2["key"]}).status_code == 404)

(DATA / "logbook.db").unlink(missing_ok=True)
print("\nAll passed." if not failures else f"\n{len(failures)} failed: {failures}")
sys.exit(1 if failures else 0)
