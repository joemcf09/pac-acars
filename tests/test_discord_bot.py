"""The PAC Discord bot: its private API, account linking, roles and the announcements PAC records for it."""
import asyncio
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
for _f in ("logbook.db", "settings.json", "secret_key", "site.json", "profile.json"):
    (DATA / _f).unlink(missing_ok=True)

import app as A  # noqa: E402
import auth  # noqa: E402
import botlink  # noqa: E402
import discord_bot as DB  # noqa: E402
import va  # noqa: E402

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
bot = A.app.test_client()
H = {"X-PAC-Bot": botlink.secret()}
TOKEN = "MTIzNDU2Nzg5.fake.bot-token-for-tests"

print("The bot's private API")
check("refused without the secret", bot.get("/api/bot/config").status_code == 404)
check("refused with a wrong secret", bot.get("/api/bot/config", headers={"X-PAC-Bot": "nope"}).status_code == 404)
check("refused from the internet even with the secret", bot.get("/api/bot/config", headers={**H, "X-Forwarded-For": "1.2.3.4"}).status_code == 404)
check("pilots can't use it", pilot.get("/api/bot/roster").status_code == 404)
c = bot.get("/api/bot/config", headers=H).get_json()
check("answers the bot", c and c["enabled"] is False and c["channels"]["flights"] == "flight-log")

print("Switching it on")
check("pilots can't change the bot settings", pilot.post("/api/settings", json={"discord_bot_enabled": True}).status_code == 403)
founder.post("/api/settings", json={"discord_bot_enabled": True, "discord_bot_token": TOKEN})
c = bot.get("/api/bot/config", headers=H).get_json()
check("the bot gets its token and settings", c["enabled"] and c["token"] == TOKEN and c["pilot_role"] == "PAC Pilot" and "Senior Captain" in c["ranks"])
check("the token never reaches a browser", TOKEN not in json.dumps(founder.get("/api/bootstrap").get_json()))
founder.post("/api/settings", json={"discord_bot_token": ""})
check("an empty token box keeps the token", A.settings()["discord_bot_token"] == TOKEN)
first = bot.get("/api/bot/events", headers=H).get_json()
check("on first start the bot doesn't replay old news", first["events"] == [])
last = first["last"]
check("staff see the bot online once it's collecting", founder.get("/api/staff/discord-bot").get_json()["online"])

print("Linking")
check("the bot won't link without a valid code", bot.post("/api/bot/link", headers=H, json={"code": "PAC-ZZZZZ", "discord_id": "123456789012345678"}).status_code == 400)
code = pilot.post("/api/discord/code").get_json()["code"]
check("pilots get a code", code.startswith("PAC-") and len(code) == 9)
r = bot.post("/api/bot/link", headers=H, json={"code": code.lower().replace("pac-", ""), "discord_id": "123456789012345678", "discord_name": "bob#0001"})
check("/link with the code links the account", r.status_code == 200 and r.get_json()["pilot_id"] == "PAC0002", r.get_json())
check("a code works once", bot.post("/api/bot/link", headers=H, json={"code": code, "discord_id": "1"}).status_code == 400)
check("the website shows it's linked", pilot.get("/api/discord/me").get_json()["linked"])
roster = bot.get("/api/bot/roster", headers=H).get_json()["pilots"]
check("the roster gives the bot the pilot's rank", roster and roster[0]["discord_id"] == "123456789012345678" and roster[0]["rank"])
with A.db() as con:
    con.execute("INSERT INTO discord_codes (code, pilot_id, expires) VALUES ('PAC-OLD22', 'PAC0002', ?)", (time.time() - 1,))
check("expired codes don't work", bot.post("/api/bot/link", headers=H, json={"code": "PAC-OLD22", "discord_id": "123456789012345678"}).status_code == 400)

print("Commands")
check("/pilot finds a pilot by ID", bot.get("/api/bot/pilot?q=PAC0002", headers=H).get_json().get("name") == "Bob Member")
check("…by number", bot.get("/api/bot/pilot?q=2", headers=H).get_json().get("pilot_id") == "PAC0002")
check("…by Discord account", bot.get("/api/bot/pilot?q=123456789012345678", headers=H).get_json().get("pilot_id") == "PAC0002")
check("…and says when there's nobody", bot.get("/api/bot/pilot?q=PAC9999", headers=H).status_code == 404)
check("/live and /flights have data", bot.get("/api/bot/live", headers=H).status_code == 200 and bot.get("/api/bot/recent", headers=H).status_code == 200)

print("Announcements")
with A.db() as con:
    con.execute("""INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, score, points, status,
        flight_number, mission_title, grade, landing_rate, profit) VALUES ('PAC0002', ?, 0, 'Accepted', 'B738F', 'KCVG', 'KMIA', 125, 96, 240,
        'Delivered', 'PAC1024', 'Express parcels to Miami', 'A', -212, 20000)""", (time.time(),))
    pid = con.execute("SELECT max(id) FROM pireps").fetchone()[0]
    con.execute("UPDATE pilots SET rank_seen='Cadet' WHERE id='PAC0002'")
va.pay_pirep(pid)
va.pay_pirep(pid)                   # paying twice mustn't announce twice
ev = bot.get(f"/api/bot/events?after={last}", headers=H).get_json()
kinds = [e["kind"] for e in ev["events"]]
check("an accepted PIREP is announced once", kinds.count("pirep") == 1, kinds)
p = next(e["data"] for e in ev["events"] if e["kind"] == "pirep")
check("…with the flight, pilot and landing", p["flight"] == "PAC1024" and p["discord_id"] == "123456789012345678" and p["landing_rate"] == -212)
check("a promotion is announced", "promotion" in kinds, kinds)
last = ev["last"]
with A.db() as con:
    con.execute("""INSERT INTO pireps (pilot_id, filed_at, demo, review_status, aircraft, dep, arr, block_min, flight_number, profit)
        VALUES ('PAC0002', ?, 0, 'Accepted', 'B738F', 'KCVG', 'KMIA', 60, 'PAC0001', 100)""", (time.time() - 3 * 86400,))
    old = con.execute("SELECT max(id) FROM pireps").fetchone()[0]
va.pay_pirep(old)
va.add_tx("PAC0002", "adjustment", 50000, "test")
pilot.post("/api/shop/buy", json={"item": "night_cargo"})
pilot.post("/api/applications", json={"name": "Ava Chen", "email": "ava@example.com", "hub": "KCVG", "discord": "ava_flies",
                                      "simulator": "MSFS", "experience": "Some", "motivation": "Cargo!", "country": "US", "agree": True})
aid = A.db().execute("SELECT max(id) FROM applications").fetchone()[0]
founder.post(f"/api/staff/applications/{aid}", json={"action": "approve", "email_it": False})
pilot.post("/api/discord/unlink")
ev = bot.get(f"/api/bot/events?after={last}", headers=H).get_json()
kinds = [e["kind"] for e in ev["events"]]
check("old flights (back pay) aren't announced", "pirep" not in kinds, kinds)
check("shop purchases are announced", "shop" in kinds)
check("new pilots are announced with their Discord name", any(e["kind"] == "new_pilot" and e["data"]["discord"] == "ava_flies" for e in ev["events"]), kinds)
check("unlinking tells the bot to remove roles", "unlinked" in kinds)
founder.post("/api/settings", json={"discord_bot_enabled": False})
n = A.db().execute("SELECT COUNT(*) FROM bot_events").fetchone()[0]
pilot.post("/api/shop/buy", json={"item": "carbon"})
check("switched off: nothing is recorded", A.db().execute("SELECT COUNT(*) FROM bot_events").fetchone()[0] == n)

print("What the bot says")
card = DB.pirep_card(p, "https://pac-va.com")
check("PIREP card", card["title"].startswith("PAC1024") and "<@123456789012345678>" in card["description"]
      and ("Landing", "-212 fpm") in card["fields"] and card["colour"] == DB.GRADE_COLOURS["A"])
check("promotion", "**Second Officer**" in DB.promotion_text({"pilot": "Bob", "from": "Cadet", "rank": "Second Officer"}))
check("altitudes read like ATC", DB.altitude(35012) == "FL350" and DB.altitude(9500) == "9,500 ft" and DB.altitude(0, True) == "On the ground")
cfg = {"pilot_role": "PAC Pilot", "staff_role": "PAC Staff", "rank_roles": True, "ranks": ["Cadet", "Second Officer", "Captain"]}
check("roles for a linked pilot", DB.wanted_roles({"active": True, "rank": "Captain", "staff": True}, cfg) == {"PAC Pilot", "Captain", "PAC Staff"})
check("no roles for a suspended pilot", DB.wanted_roles({"active": False, "rank": "Captain"}, cfg) == set())
check("the bot only touches PAC's roles", DB.managed_roles(cfg) == {"Cadet", "Second Officer", "Captain", "PAC Pilot", "PAC Staff"})
check("/live text", "2 PAC flights" in DB.live_lines([{"flight": "PAC1", "aircraft": "B738", "alt_ft": 35000}, {"flight": "PAC2", "aircraft": "A306", "on_ground": True}], "https://pac-va.com"))
check("/live when nobody's flying", "Nobody's flying" in DB.live_lines([], "https://pac-va.com"))
check("welcome", "/link" in DB.welcome_text("<@1>", "https://pac-va.com"))

print("The bot starts and registers its commands")
import discord  # noqa: E402
seen = {}


async def fake_start(self, token, *a, **k):
    seen["token"] = token


discord.Client.start = fake_start
orig_tree = discord.app_commands.CommandTree


class Tree(orig_tree):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        seen["tree"] = self


discord.app_commands.CommandTree = Tree
DB.run({"token": TOKEN, "guild": "", "channels": {"flights": "flight-log", "news": "announcements", "welcome": "welcome"},
        "pilot_role": "PAC Pilot", "staff_role": "PAC Staff", "rank_roles": True, "ranks": [], "site": "https://pac-va.com"})
names = sorted(cmd.name for cmd in seen["tree"].get_commands())
check("it logs in with the token", seen.get("token") == TOKEN)
check("all five commands are registered", names == ["flights", "link", "live", "pilot", "unlink"], names)

print("Bot trap")
check("the trap channel is in the bot's settings", bot.get("/api/bot/config", headers=H).get_json()["channels"]["honeypot"] == "do-not-post")
check("matches the plain name", DB.is_trap_channel("do-not-post", 1, "do-not-post"))
check("matches with emoji and separators", DB.is_trap_channel("🚫・do-not-post", 1, "#do-not-post"))
check("matches a channel ID", DB.is_trap_channel("anything", 987654321, "987654321"))
check("ignores other channels", not DB.is_trap_channel("general", 1, "do-not-post") and not DB.is_trap_channel("do-not-post-rules", 1, "do-not-post"))
check("switched off when empty", not DB.is_trap_channel("do-not-post", 1, ""))
check("an ordinary member is caught", not DB.trap_exempt(False, False, {"send_messages": True}, ["PAC Pilot"], "PAC Staff"))
check("staff are never caught", DB.trap_exempt(False, False, {}, ["PAC Staff"], "PAC Staff"))
check("moderators and admins are never caught", DB.trap_exempt(False, False, {"manage_messages": True}, [], "PAC Staff")
      and DB.trap_exempt(False, False, {"administrator": True}, [], ""))
check("the owner and the server's bots are never caught", DB.trap_exempt(False, True, {}, [], "") and DB.trap_exempt(True, False, {}, [], ""))
check("the staff report names the account", "spam#0001" in DB.trap_log("spam#0001", 42, "do-not-post", True))

print("\n" + ("DISCORD BOT TEST PASSED" if not failures else f"{len(failures)} failed: {failures}"))
sys.exit(1 if failures else 0)
