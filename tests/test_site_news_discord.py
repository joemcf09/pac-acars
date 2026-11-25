"""Posts from Staff › News reach Discord: company NOTAMs in the NOTAM channel, news in announcements.

Run from the PAC folder:   python tests/test_site_news_discord.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402
import company  # noqa: E402
import discord_bot as DB  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
c.post("/api/auth/setup", json={"password": "News-Discord-Pass-1"})
c.post("/api/settings", json={"discord_bot_enabled": True, "discord_bot_token": "test-token"})

def events():
    with A.db() as con:
        return [json.loads(r[0]) for r in con.execute("SELECT data FROM bot_events WHERE kind='site_news' ORDER BY id")]


import botlink  # noqa: E402
cfg = c.get("/api/bot/config", headers={"X-PAC-Bot": botlink.secret()}).json
if True:
    check("the bot knows the NOTAM channel (notams by default)", cfg["channels"].get("notams") == "notams", cfg["channels"])

already = sum(1 for n in c.get("/api/staff/news").json if n["kind"] == "notam")
c.post("/api/staff/news", json={"kind": "notam", "title": "ACARS 1.0.4 required", "body": "Track every flight with 1.0.4 or later.", "discord": True})
c.post("/api/staff/news", json={"kind": "news", "title": "664 routes", "body": "Line one.\n\nLine two.", "important": True, "discord": True})
c.post("/api/staff/news", json={"kind": "news", "title": "Quiet post", "body": "Site only.", "discord": False})
ev = events()
check("a new NOTAM and a new news post are sent to the bot", [e["title"] for e in ev] == ["ACARS 1.0.4 required", "664 routes"], [e["title"] for e in ev])
check("unticking the box keeps a post off Discord", not any(e["title"] == "Quiet post" for e in ev))
check("NOTAMs are numbered for the year", ev[0]["number"] and ev[0]["number"].startswith(f"{already + 1:03d}/"), ev[0])
nid = [n for n in c.get("/api/staff/news").json if n["title"] == "664 routes"][0]["id"]
c.post("/api/staff/news", json={"id": nid, "kind": "news", "title": "664 routes", "body": "Fixed typo."})
check("an edit isn't reposted unless staff ask", len(events()) == 2)
c.post("/api/staff/news", json={"id": nid, "kind": "news", "title": "664 routes", "body": "Fixed typo.", "discord": True})
check("but is when they do, marked as updated", len(events()) == 3 and events()[-1]["updated"])

card = DB.site_news_card(ev[0], "https://pac-va.com")
check("the NOTAM card looks like a NOTAM", card["title"].startswith(f"⚠️ NOTAM {already + 1:03d}/") and "ACARS 1.0.4 required" in card["title"], card["title"])
card = DB.site_news_card(ev[1], "https://pac-va.com")
check("news keeps its paragraphs", card["description"] == "Line one.\n\nLine two." and card["title"].startswith("📣"), card)
check("important posts are PAC red", card["colour"] == DB.PAC_RED)
long = DB.site_news_card({"kind": "news", "title": "x", "body": "word " * 1200}, "https://pac-va.com")
check("very long posts fit Discord's limit", len(long["description"]) <= 3900)

with A.db() as con:
    con.execute("INSERT INTO pilots (id,name,email,hub,joined,status,checkride,staff) VALUES "
                "('PAC0006','Ops Manager','ops@example.com','KCVG',1767225600,'Active','Passed',0)")
    company.assign(con, "PAC0006", "dir_ops", "")
auth._set_password("PAC0006", "Ops-News-Pass-123")
ops = A.app.test_client()
check("Ops role holder can sign in", ops.post("/api/auth/login", json={"pilot_id": "PAC0006", "password": "Ops-News-Pass-123"}).status_code == 200)
check("Ops role holder sees notices capability", "notices" in ops.get("/api/pilot/me").json["staff_caps"])
posted = ops.post("/api/staff/news", json={"kind": "notam", "title": "AOG at EPKK", "body": "N743PC remains grounded pending inspection.", "discord": True})
check("Ops role holder can publish a company NOTAM", posted.status_code == 200, posted.status_code)
check("Ops NOTAM appears in the public site feed", any(n["title"] == "AOG at EPKK" for n in ops.get("/api/news").json))
check("Ops NOTAM is queued for the Discord channel", events()[-1]["title"] == "AOG at EPKK")
announcement = ops.post("/api/staff/news", json={"kind": "news", "title": "Recovery update", "body": "Inspection is underway.", "discord": True})
check("Ops role holder can publish an announcement", announcement.status_code == 200, announcement.status_code)
check("Ops announcement appears in the public site feed", any(n["title"] == "Recovery update" for n in ops.get("/api/news").json))
check("Ops announcement is queued for Discord", events()[-1]["title"] == "Recovery update")

long_body = ("Runway 18C closed for resurfacing. " * 100).strip()      # about 3,500 characters
ops.post("/api/staff/news", json={"kind": "notam", "title": "Long NOTAM", "body": long_body, "discord": True})
saved = next(n for n in ops.get("/api/news").json if n["title"] == "Long NOTAM")
check("a long NOTAM is kept whole (up to what one Discord post holds)", saved["body"] == long_body, len(saved["body"]))
check("and goes to Discord whole", events()[-1]["body"] == long_body)
import app_bundle
js = app_bundle.plain_source()
check("the missions board shows the full NOTAM, not a cut-off preview", "n.body.slice(0, 257)" not in js.split("function notamBars")[1].split("function newsCards")[0])

print("\nSITE NEWS DISCORD TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
