"""The Discord dispatch channel: PAC hands the bot new missions, partner crew requests and urgent requests as they
appear, keeps the boards moving on quiet days, and the bot posts them within an hourly limit, most urgent first.

Run from the PAC folder:   python tests/test_dispatch_channel.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "bot_secret"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import botlink  # noqa: E402
import discord_bot as DB  # noqa: E402
import mission_worker  # noqa: E402  (the scheduled job that fills the boards on the server)

failures = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


c = A.app.test_client()
H = {"X-PAC-Bot": botlink.secret()}


def feed(after=None):
    r = c.get("/api/bot/dispatch" + ("" if after is None else f"?after={after}"), headers=H)
    return r.status_code, r.get_json() or {}


print("The feed")
st, first = feed()
check("the bot's first ask starts from now, without replaying the board", st == 200 and first["items"] == [] and first.get("last"), first)
mission_worker.run_once()   # on the server a timer runs this every few minutes
with A.db() as con:
    counts = {k: con.execute(q).fetchone()[0] for k, q in (
        ("missions", "SELECT COUNT(*) FROM live_missions WHERE status='open'"),
        ("partners", "SELECT COUNT(*) FROM jobs WHERE kind='contract' AND status='open'"),
        ("urgent", "SELECT COUNT(*) FROM urgent WHERE status='open'"))}
check("the scheduled worker fills the boards even with nobody signed in", counts["missions"] >= 10 and counts["partners"] >= 4 and counts["urgent"] >= 1, counts)
st, first = feed(first["last"])     # the worker's offers, published after the bot started
st, again = feed(first["last"])
check("nothing new means nothing to post", again["items"] == [], [i["id"] for i in again["items"]])

# time passes: everything on the boards is taken or expires, so new work appears on the next ask
with A.db() as con:
    con.execute("UPDATE live_missions SET status='expired' WHERE status='open'")
    con.execute("UPDATE jobs SET status='expired' WHERE kind='contract' AND status='open'")
    con.execute("UPDATE urgent SET status='expired' WHERE status='open'")
mission_worker.run_once()
st, new = feed(again["last"])
kinds = {i["kind"] for i in new["items"]}
check("new work of every kind comes through", kinds == {"mission", "partner", "urgent"}, kinds)
check("oldest first", [i["created"] for i in new["items"]] == sorted(i["created"] for i in new["items"]))
check("and 'last' moves on", new["last"] >= max(i["created"] for i in new["items"]))
st, after = feed(new["last"])
check("nothing is handed over twice", not ({i["id"] for i in after["items"]} & {i["id"] for i in new["items"]}))
check("the feed is private to the bot", c.get("/api/bot/dispatch").status_code == 404)
check("and closed to anything coming through Caddy",
      c.get("/api/bot/dispatch", headers={**H, "X-Forwarded-For": "1.2.3.4"}).status_code == 404)

print("What the bot posts")
by = {k: next(i for i in new["items"] if i["kind"] == k) for k in ("mission", "partner", "urgent")}
site = "https://pac-va.com"
m = DB.dispatch_card(by["mission"], site)
check("a mission card names the mission and links to the board", m["title"].startswith("📦 New mission · PAC") and m["url"] == site + "/#missions", m["title"])
check("with route, aircraft, cargo and distance", [f[0] for f in m["fields"]][:4] == ["Route", "Aircraft", "Cargo", "Distance"], m["fields"])
check("and when it has to be booked by, with the date, in Discord's own time format", any(f[0] == "Book by" and f[1].startswith("<t:") and ":f>" in f[1] for f in m["fields"]), m["fields"])
p = DB.dispatch_card(by["partner"], site)
check("a crew request names the partner airline", p["title"].startswith("🤝 Crew request · ") and by["partner"]["operator"] in p["title"], p["title"])
check("with its callsign and shortage bonus", {"Callsign", "Shortage bonus"} <= {f[0] for f in p["fields"]}, p["fields"])
u = DB.dispatch_card(by["urgent"], site)
check("an urgent request stands out and says when to deliver", u["title"].startswith("🚨 Urgent") and u["colour"] == DB.PAC_RED
      and any(f[0] == "Deliver by" for f in u["fields"]), u)
check("descriptions stay short", all(len(DB.dispatch_card(i, site)["description"]) <= 360 for i in new["items"]))
for card in (m, p, u):
    print("     " + card["title"])

print("Last call before an urgent request closes")
import time as _t
with A.db() as con:
    con.execute("UPDATE urgent SET status='expired' WHERE status='open'")
    now_ = _t.time()
    con.execute("INSERT INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, 'open')",
                ("PAC8899", json.dumps({**by["urgent_raw"], "id": "PAC8899", "expires": now_ + 4 * 3600}) if by.get("urgent_raw") else json.dumps(
                    {"id": "PAC8899", "title": "AOG recovery: N1PC at Balice", "category": "Urgent", "priority": "Critical", "urgent": True,
                     "origin": {"icao": "LIMC"}, "destination": {"icao": "EPKK"}, "aircraft": [], "expires": now_ + 4 * 3600, "deliver_by": now_ + 7 * 3600}),
                 now_ - 32 * 3600, now_ + 4 * 3600))
    con.execute("INSERT INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, 'open')",
                ("PAC7777", json.dumps({"id": "PAC7777", "title": "Short-notice job", "origin": {"icao": "KCVG"}, "destination": {"icao": "KMIA"},
                                        "aircraft": [], "expires": now_ + 3 * 3600}), now_ - 3600, now_ + 3 * 3600))
st, lc = feed(new["last"])
calls = [i for i in lc["items"] if i.get("last_call")]
check("an unbooked AOG recovery gets one last call six hours before it closes", [i["id"] for i in calls] == ["PAC8899"], [i["id"] for i in calls])
card = DB.dispatch_card(calls[0], site) if calls else {"title": "", "description": "", "fields": []}
check("the card says so, with the closing time", card["title"].startswith("⏰ Last call") and "<t:" in card["description"], card["title"])
check("and shows the booking deadline with its date", any(f[0] == "Book by" and ":f>" in f[1] for f in card["fields"]), card["fields"])
st, lc2 = feed(new["last"])
check("only once", not any(i.get("last_call") for i in lc2["items"]))
post, _ = DB.dispatch_pick(calls + new["items"], {"missions": True, "partners": True, "urgent": True, "per_hour": 1}, [], 1e10)
check("a last call goes out ahead of new work", post and post[0].get("last_call"), [i["id"] for i in post])

print("Not flooding the channel")
items = new["items"]
s = {"missions": True, "partners": True, "urgent": True, "per_hour": 4}
post, skip = DB.dispatch_pick(items, s, [], 1e10)
check("no more than the hourly limit", len(post) == min(4, len(items)), len(post))
check("urgent first, then crew requests, then missions",
      [i["kind"] for i in post] == sorted((i["kind"] for i in post), key=lambda k: DB.DISPATCH_ORDER[k]), [i["kind"] for i in post])
post, _ = DB.dispatch_pick(items, s, [1e10 - 600] * 3, 1e10)
check("posts in the last hour count towards the limit", len(post) == 1, len(post))
post, _ = DB.dispatch_pick(items, s, [1e10 - 4000] * 10, 1e10)
check("older posts don't", len(post) == 4, len(post))
post, _ = DB.dispatch_pick(items, {**s, "urgent": False, "partners": False}, [], 1e10)
check("kinds switched off aren't posted", post and all(i["kind"] == "mission" for i in post), [i["kind"] for i in post])

print("Settings")
st_ = A.settings()
st_.update(discord_dispatch_per_hour="99", discord_dispatch_urgent=False, discord_ch_dispatch="#ops-board")
A.save_json(A.SETTINGS_PATH, st_)
cfg = c.get("/api/bot/config", headers=H).get_json()
check("the bot is told the dispatch channel", cfg["channels"].get("dispatch") == "ops-board", cfg["channels"])
check("and its settings, with the hourly limit kept sensible", cfg["dispatch"] == {"missions": True, "partners": True, "urgent": False, "per_hour": 30},
      cfg["dispatch"])
check("the feed carries the same settings", feed(after["last"])[1]["settings"]["urgent"] is False)

print("\nDISPATCH CHANNEL TEST", "PASSED" if not failures else f"FAILED ({len(failures)}): {failures}")
sys.exit(1 if failures else 0)
