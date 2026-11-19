"""Who can see and do what: visitors, ordinary pilots and staff."""
import io
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)
for _p in (DATA / "profiles").glob("*") if (DATA / "profiles").exists() else []:
    _p.unlink()

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
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff) VALUES "
                "('PAC0002','Bob Member','bob@example.com','KCVG',1767225600,'Active','Passed',0)")
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff) VALUES "
                "('PAC0003','Cara Member','cara@example.com','KCVG',1767225600,'Active','Passed',0)")
auth._set_password("PAC0002", "Member-Pass-123")
pilot = A.app.test_client()
check("an ordinary pilot can sign in", pilot.post("/api/auth/login", json={"pilot_id": "PAC0002", "password": "Member-Pass-123"}).status_code == 200)
guest = A.app.test_client()

FILL = {"pid": "1", "gid": "1", "fid": "1", "code": "B738F", "reg": "N1", "icao": "KCVG", "name": "x", "token": "x", "filename": "x"}


def url(rule):
    return re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", lambda m: FILL.get(m.group(1), "1"), rule)


print("Visitors")
PUBLIC_OK = {
    # public on purpose: search engines, the Academy, conflict maps, the public roster and group flight, partner photos,
    # basic site settings; the load planner pages are empty shells whose data (/api/load-plan) needs a sign-in
    "/academy", "/academy/", "/academy/<path:name>", "/api/academy/content", "/api/academy/files/<int:item_id>", "/robots.txt", "/sitemap.xml", "/api/conflict-zones",
    "/api/conflict-zones/map", "/media/image", "/api/partner-photos", "/api/partner-photo/<key>/<ac>", "/load-planner",
    "/load-planner-all", "/load-planner-727", "/api/va/config", "/api/public/roster", "/api/public/group-flight",
    "/api/group-flight.ics", "/track", "/track/<path:awb>", "/api/public/track/<path:awb>", "/network", "/api/public/network", "/healthz", "/up",   # air waybill tracking is public (test_tracking.py); /healthz and /up are for outside monitors
    "/", "/api/acars/app/download", "/api/bootstrap", "/api/fleet", "/api/fleet/<code>/photo", "/api/gallery",
             # liveries are on the public Fleet page; an uploaded file still needs a sign-in (checked in test_liveries.py)
             "/api/fleet/liveries", "/api/fleet/liveries/<lid>/preview", "/api/fleet/liveries/<lid>/download",
             "/api/va/home/network-logo/<net>",   # the VATSIM logo in the home page's Network partners section
             "/api/group/v1/summary", "/api/group/v1/metar",   # group hub feeds: off by default, need the group key (test_group_feed.py)
             "/api/news", "/api/profile/photo", "/api/va/board", "/api/va/home", "/gallery/<path:name>", "/api/applications",
             # the sign-in page itself, and public pages whose data endpoints still need a sign-in:
             "/badge-login", "/unicom", "/unicom/ivao", "/unicom/flight",
             # email unsubscribe links are public but token-protected (an invalid/absent token returns 400, not a leak):
             "/unsubscribe/monthly", "/unsubscribe/reminders"}
leaks = []
for r in A.app.url_map.iter_rules():
    if r.rule.startswith(("/static", "/api/auth/")):
        continue
    for m in r.methods - {"HEAD", "OPTIONS"}:
        code = guest.open(url(r.rule), method=m, json={}).status_code
        if r.rule.startswith("/api/bot/") and code == 404:
            continue                       # the Discord bot's private API: refused without its secret
        if code != 401 and r.rule not in PUBLIC_OK:
            leaks.append(f"{m} {r.rule} → {code}")
check("every members' page and action asks visitors to sign in", not leaks, leaks)
g = guest.get("/api/bootstrap").get_json()
check("visitors get no settings, missions or booking", g["settings"] == {} and g["missions"] == [] and g["booking"] is None)
check("visitors see the founder's public profile", g["profile"]["pilot_id"] == "PAC0001")
check("visitors can't see another pilot's photo", guest.get("/api/profile/photo?pilot=PAC0002").status_code == 401)
check("visitors can see the founder's photo (home page)", guest.get("/api/profile/photo").status_code == 200)

print("Ordinary pilot: the staff area")
open_staff = []
for r in A.app.url_map.iter_rules():
    if r.rule.startswith("/api/staff/"):
        for m in r.methods - {"HEAD", "OPTIONS"}:
            code = pilot.open(url(r.rule), method=m, json={}).status_code
            if code != 403:
                open_staff.append(f"{m} {r.rule} → {code}")
check("every staff action is refused", not open_staff, open_staff)
check("fleet types can't be edited", pilot.post("/api/fleet/B738F", json={"name": "x"}).status_code == 403)
check("fleet photos can't be changed", pilot.delete("/api/fleet/B738F/photo").status_code == 403)

print("Ordinary pilot: airline settings")
r = pilot.post("/api/settings", json={"enforce_pilot_location": False, "require_type_ratings": False})
check("can't switch airline rules off", r.status_code == 403 and A.settings()["enforce_pilot_location"] is True, r.status_code)
check("can't change the founder's pilot ID", pilot.post("/api/settings", json={"pilot_id": "PAC0002"}).status_code == 403
      and A.settings()["pilot_id"] == "PAC0001")
check("can't change fuel prices", pilot.post("/api/settings", json={"fuel_price_gal": 0.01}).status_code == 403)
check("secrets never reach the browser", not any(k in pilot.get("/api/bootstrap").get_json()["settings"] for k in ("smtp_pass", "discord_webhook")))

print("Ordinary pilot: personal settings")
founder.post("/api/settings", json={"vatsim_cid": "1111111", "simbrief_username": "joseph_sb"})
st = pilot.get("/api/bootstrap").get_json()["settings"]
check("doesn't inherit the founder's VATSIM CID", st.get("vatsim_cid") == "", st.get("vatsim_cid"))
check("doesn't inherit the founder's SimBrief username", st.get("simbrief_username") == "", st.get("simbrief_username"))
r = pilot.post("/api/settings", json={"vatsim_cid": "2222222", "ivao_vid": "333", "simbrief_username": "bob_sb", "map_style": "satellite"})
check("can save their own settings", r.status_code == 200, r.get_data(as_text=True))
st = pilot.get("/api/bootstrap").get_json()["settings"]
check("their settings are theirs", (st["vatsim_cid"], st["ivao_vid"], st["simbrief_username"], st["map_style"]) == ("2222222", "333", "bob_sb", "satellite"), st)
fs = founder.get("/api/bootstrap").get_json()["settings"]
check("…and don't change the founder's", (fs["vatsim_cid"], fs["simbrief_username"], fs["map_style"]) == ("1111111", "joseph_sb", "dark"), fs)
with A.app.test_request_context():
    check("SimBrief fetches use the pilot's own username", A.simbrief_settings("PAC0003")["simbrief_username"] == "")

print("Ordinary pilot: profiles")
p = pilot.get("/api/profile").get_json()["profile"]
check("sees their own profile, not the founder's", p["pilot_id"] == "PAC0002" and p["name"] == "Bob Member", p)
check("the pilot chip shows them", pilot.get("/api/bootstrap").get_json()["profile"]["name"] == "Bob Member")
r = pilot.post("/api/profile", json={**p, "name": "Joseph  PAGANI", "pilot_id": "PAC0001", "rank": "Senior Captain", "bio": "Hello, I'm Bob."})
check("can't take another pilot's name (the founder's here)", r.status_code == 400, (r.status_code, r.get_json()))
r = pilot.post("/api/profile", json={**p, "pilot_id": "PAC0001", "rank": "Senior Captain", "bio": "Hello, I'm Bob."})
q = r.get_json()["profile"]
check("can edit their own bio", q["bio"] == "Hello, I'm Bob.")
check("can't rename themselves, take another ID or promote themselves",
      (q["name"], q["pilot_id"], q["rank"]) == ("Bob Member", "PAC0002", p["rank"]), q)
r = pilot.post("/api/profile", json={**p, "callsign": "MAVERICK", "title": "Chief Pilot", "base": "LIMC", "member_since": "2001-01-01",
                                      "secondary_base": "KMIA", "type_ratings": [{"type": "B748", "name": "747-8F"}],
                                      "credentials": [{"label": "Licence", "value": "ATPL"}]})
q = r.get_json()["profile"]
check("can set their secondary base", q["secondary_base"] == "KMIA")
check("can't change callsign, title, home base or join date",
      (q["callsign"], q["title"], q["base"], q["member_since"]) == ("PAGANI", "PAC line pilot", "KCVG", "2026-01-01"), q)
check("can't give themselves type ratings", not any(t["type"] == "B748" for t in q["type_ratings"]), q["type_ratings"])
check("can't add credentials", q["credentials"] == [], q["credentials"])
with A.db() as con:
    A.va.grant_rating(con, "PAC0002", A.va.rating_family("B77F"), "staff")
q = pilot.get("/api/profile").get_json()["profile"]
check("ratings granted by staff appear on the profile", any(t["notes"] == "Granted by staff" for t in q["type_ratings"]), q["type_ratings"])
check("the founder's profile is untouched", A.load_profile("PAC0001")["name"] == "Joseph Pagani")
png = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
r = pilot.post("/api/profile/photo", data={"photo": (io.BytesIO(png), "me.png", "image/png")}, content_type="multipart/form-data")
check("can upload their own photo", r.status_code == 200 and "pilot=PAC0002" in r.get_json()["photo"], r.get_json())
check("…which doesn't replace the founder's", not list(DATA.glob("pilot_photo.*")))
check("members can see it", pilot.get("/api/profile/photo?pilot=PAC0002").data == png)
with A.app.test_request_context():
    auth_id = auth.current_id
    auth.current_id = lambda: "PAC0002"
    try:
        check("ACARS app and dispatch show the pilot's own name", "Bob Member" in A.dispatch_pilot()["name"], A.dispatch_pilot())
    finally:
        auth.current_id = auth_id

print("Ordinary pilot: logbook and gallery")
with A.db() as con:
    con.execute("INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr) VALUES ('PAC0001', 1, 0, 'Accepted', 'B738F', 'KCVG', 'KJFK')")
    pirep = con.execute("SELECT max(id) FROM pireps").fetchone()[0]
    con.execute("INSERT INTO gallery (pilot_id, file, time, featured) VALUES ('PAC0001', 'a.jpg', 1, 0)")
    founders_shot = con.execute("SELECT max(id) FROM gallery").fetchone()[0]
    con.execute("INSERT INTO gallery (pilot_id, file, time, featured) VALUES ('PAC0002', 'b.jpg', 1, 0)")
    own_shot = con.execute("SELECT max(id) FROM gallery").fetchone()[0]
check("can't delete PIREPs", pilot.delete(f"/api/logbook/{pirep}").status_code == 403
      and A.db().execute("SELECT 1 FROM pireps WHERE id=?", (pirep,)).fetchone())
check("can't delete someone else's screenshot", pilot.delete(f"/api/gallery/{founders_shot}").status_code == 403)
check("can't recaption someone else's screenshot", pilot.post(f"/api/gallery/{founders_shot}", json={"caption": "x"}).status_code == 403)
check("can't feature screenshots", pilot.post(f"/api/gallery/{own_shot}", json={"featured": True}).status_code == 403)
check("can recaption their own", pilot.post(f"/api/gallery/{own_shot}", json={"caption": "Sunset over KCVG"}).status_code == 200)
check("can delete their own", pilot.delete(f"/api/gallery/{own_shot}").status_code == 200)

print("Logbooks")
with A.db() as con:
    con.execute("INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, score, points, status) "
                "VALUES ('PAC0001', 2, 0, 'Accepted', 'B738F', 'KCVG', 'KBNA', 60, 100, 200, 'Delivered')")
    con.execute("INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, score, points, status) "
                "VALUES ('PAC0002', 3, 0, 'Accepted', 'B738F', 'KCVG', 'KMIA', 120, 90, 150, 'Delivered')")
lb = pilot.get("/api/logbook").get_json()
check("a pilot's logbook shows only their flights", {p["pilot_id"] for p in lb["pireps"]} == {"PAC0002"}, [p["pilot_id"] for p in lb["pireps"]])
check("…and their totals", lb["totals"]["flights"] == 1 and lb["totals"]["points"] == 150, lb["totals"])
check("a pilot can't open someone else's logbook", pilot.get("/api/logbook?pilot=PAC0001").status_code == 403)
fl = founder.get("/api/logbook").get_json()
check("the founder's logbook has only the founder's flights", "PAC0002" not in {p["pilot_id"] for p in fl["pireps"]})
check("staff can open any pilot's logbook", {p["pilot_id"] for p in founder.get("/api/logbook?pilot=PAC0002").get_json()["pireps"]} == {"PAC0002"})

print("Links in letters")
check("http becomes https for the real domain", auth.site_address("http://pac-va.com") == "https://pac-va.com")
check("a bare domain gets https", auth.site_address("pac-va.com/") == "https://pac-va.com")
check("addresses on this PC stay as they are", auth.site_address("http://localhost:5050") == "http://localhost:5050"
      and auth.site_address("http://192.168.1.20:5050") == "http://192.168.1.20:5050")

print("Staff")
check("staff can feature screenshots", founder.post(f"/api/gallery/{founders_shot}", json={"featured": True}).status_code == 200)
check("staff can change airline rules", founder.post("/api/settings", json={"require_type_ratings": False}).status_code == 200
      and A.settings()["require_type_ratings"] is False)
check("staff can delete a PIREP", founder.delete(f"/api/logbook/{pirep}").status_code == 200)

print("\n" + ("PERMISSIONS TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
