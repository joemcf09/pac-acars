"""PAC Operations: the Pagani Air Cargo Discord bot.

Runs on the PAC server as its own service (deploy/pac-discord.service) and talks to PAC over PAC's private bot API
(botlink.py) on this machine. Everything it needs (its token, the server, channel and role names) comes from
Staff › Site and rules › Discord bot on the website, so nothing here needs editing.

  /flights          the latest PAC flights
  /live             who's flying for PAC right now, with a link to the live map
  /pilot [who]      a pilot's PAC card (yours if you leave it blank)
  /link CODE        link your Discord account to your PAC pilot (get the code in Settings on the website)
  /unlink           unlink it

It also gives linked pilots their roles (PAC Pilot, their rank, PAC Staff), posts accepted PIREPs, promotions, new
pilots, shop purchases and new liveries, posts new missions, partner crew requests and urgent requests in the dispatch
channel (within an hourly limit), and welcomes people who join the Discord server.

Bot trap: a channel (do-not-post) that tells people not to post. Spam bots post everywhere, so anyone who posts there
(except staff and the server's own bots) is soft-banned: banned and unbanned straight away, which removes them and
deletes their messages from the last 24 hours across the server. A real person can rejoin with an invite. This needs
the bot's role to have Ban Members and Manage Messages, and to sit above ordinary members' roles."""

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAC = os.environ.get("PAC_URL", "http://127.0.0.1:%s" % os.environ.get("PAC_PORT", "5050")).rstrip("/")
PAC_RED = 0xD4111E
GRADE_COLOURS = {"A": 0x1E9E5A, "B": 0x6BAA2A, "C": 0xE0A100, "D": 0xE06A00, "F": 0x9AA1AB}


# ---------------------------------------------------------------- talking to PAC
def secret():
    return (HERE / "data" / "bot_secret").read_text(encoding="utf-8").strip()


def pac(method, path, body=None, timeout=10):
    """Call PAC's private bot API. Returns (status, json)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PAC + path, data=data, method=method,
                                 headers={"X-PAC-Bot": secret(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"error": str(e)}


async def apac(method, path, body=None):
    return await asyncio.to_thread(pac, method, path, body)


# ---------------------------------------------------------------- what the bot says (plain data, easy to test)
def hm(minutes):
    m = int(minutes or 0)
    return f"{m // 60}h {m % 60:02d}m"


def altitude(ft, on_ground=False):
    if on_ground:
        return "On the ground"
    ft = int(ft or 0)
    return f"FL{round(ft / 100):03d}" if ft >= 18000 else f"{ft:,} ft"


def mention(ev):
    return f"<@{ev['discord_id']}>" if ev.get("discord_id") else f"**{ev.get('pilot') or ev.get('pilot_id')}**"


def pirep_card(ev, site):
    grade = (ev.get("grade") or "").upper()[:1]
    late = "late" in (ev.get("status") or "").lower()
    fields = [("Route", f"{ev['dep']} → {ev['arr']}"), ("Aircraft", ev.get("aircraft_name") or ev.get("aircraft") or "–"),
              ("Block", hm(ev.get("block_min")))]
    if ev.get("landing_rate") is not None:
        fields.append(("Landing", f"{int(ev['landing_rate'])} fpm"))
    if ev.get("score") is not None:
        fields.append(("Score", f"{ev['score']}{f' ({grade})' if grade else ''}"))
    if ev.get("points"):
        fields.append(("Points", f"{ev['points']:,}"))
    return {"title": f"🛬 {ev['flight']} landed {ev['arr']}",
            "description": f"Flown by {mention(ev)}" + (" · delivered late" if late else " · delivered") + (f"\n*{ev['mission']}*" if ev.get("mission") else ""),
            "colour": GRADE_COLOURS.get(grade, PAC_RED), "fields": fields, "url": f"{site}/#logbook"}


def status_card(r, site):
    """/status: where the pilot is, where they sleep tonight, what's next, money and rank."""
    here = f"**{r.get('location') or '–'}**" + (f" {r['city']}" if r.get("city") else "") + ("  ·  🏠 home base" if r.get("location") == r.get("hub") else f"  ·  base {r.get('hub') or '–'}")
    fields = [("📍 Location", here)]
    rest = r.get("rest") or {}
    if rest.get("away"):
        fields.append(("🛏 Tonight", rest.get("text") or "–"))
    if r.get("booking"):
        b = r["booking"]
        fields.append(("✈️ Booked flight", f"{b.get('flight') or ''} {b['route']}" + (f" · {b['aircraft']}" if b.get("aircraft") else "") + (f"\n*{b['title']}*" if b.get("title") else "")))
    if r.get("trip"):
        t = r["trip"]
        line = f"{t['id']}: leg {t['done'] + 1} of {t['legs']}" + (f" ({t['next']})" if t.get("next") else "")
        if t.get("next_after"):
            line += f"\nRest ends <t:{int(t['next_after'])}:R>"
        fields.append(("🧳 Trip", line))
    fields.append(("💰 Wallet", f"${int(r.get('balance') or 0):,}"))
    rank = f"{r.get('rank')} · {r.get('hours') or 0} h"
    if r.get("next_rank"):
        rank += f"\nNext: **{r['next_rank']}**" + ("".join(f"\n• {x}" for x in r.get("todo") or []))
    fields.append(("🎖 Rank", rank))
    return {"title": f"{r.get('name')} · {r.get('pilot_id')}", "colour": PAC_RED, "fields": fields, "url": f"{site}/#dashboard"}


def departed_card(ev, site):
    """🛫 a PAC flight just took off (from PAC ACARS, once per flight)."""
    fields = [("Route", f"{ev.get('dep')} → {ev.get('arr')}"),
              ("Aircraft", f"{ev.get('aircraft_name') or '–'}{' · ' + ev['tail'] if ev.get('tail') else ''}")]
    if ev.get("cargo_lbs"):
        fields.append(("Cargo", f"{int(ev['cargo_lbs']):,} lb" + (f" · {ev['cargo']}" if ev.get("cargo") else "")))
    if ev.get("cruise_ft"):
        fields.append(("Cruise", f"FL{round(ev['cruise_ft'] / 100):03d}"))
    if ev.get("eta_min"):
        fields.append(("Planned block", hm(ev["eta_min"])))
    where = " to ".join(x for x in (ev.get("dep_city") or ev.get("dep"), ev.get("arr_city") or ev.get("arr")) if x)
    return {"title": f"🛫 {ev.get('callsign') or ev.get('flight')} departed {ev.get('dep')}",
            "description": f"{mention(ev)} is on the way{': ' + where if where else ''}." + (f"\n*{ev['mission']}*" if ev.get("mission") else ""),
            "colour": PAC_RED, "fields": fields, "url": f"{site}/#live"}


def recap_card(r):
    """The Monday post: last week at PAC. Returns None for a week with nothing to say."""
    if not (r.get("flights") or r.get("new_pilots") or r.get("promotions")):
        return None
    import datetime as dt
    d0 = dt.datetime.fromtimestamp(r["start"], dt.timezone.utc)
    d1 = dt.datetime.fromtimestamp(r["end"] - 1, dt.timezone.utc)
    span = f"{d0:%b} {d0.day}–{d1.day}" if d0.month == d1.month else f"{d0:%b} {d0.day} – {d1:%b} {d1.day}"
    fields = []
    if r.get("flights"):
        fields.append(("Flights", f"{r['flights']:,}"))
        fields.append(("Block hours", f"{r['hours']:,.1f}"))
        fields.append(("Cargo delivered", f"{r['cargo_lbs']:,} lb"))
    tl = r.get("top_landing")
    if tl:
        fields.append(("🧈 Smoothest landing", f"{mention(tl)}\n{int(tl['landing_rate'])} fpm · {tl['flight_number']} into {tl['arr']}"))
    th = r.get("top_hours") or []
    if th:
        medals = ["🥇", "🥈", "🥉"]
        fields.append(("⏱️ Most hours", "\n".join(f"{medals[i]} {mention(x)} · {x['hours']:.1f} h ({x['flights']} flight{'s' if x['flights'] != 1 else ''})"
                                                for i, x in enumerate(th))))
    if r.get("promotions"):
        fields.append(("🎖️ Promotions", "\n".join(f"{mention(x)} → **{x['rank']}**" for x in r["promotions"])))
    if r.get("new_pilots"):
        fields.append(("✈️ New pilots", "\n".join(f"{mention(x)} · {x['pilot_id']}" for x in r["new_pilots"])))
    pilots = r.get("pilots") or 0
    desc = (f"{pilots} pilot{'s' if pilots != 1 else ''} flew for PAC last week. Thanks for moving the impossible! 🛫"
            if r.get("flights") else "A quiet week in the air, but the crew keeps growing.")
    return {"title": f"PAC weekly recap · {span}", "description": desc, "colour": PAC_RED, "url": r.get("site"),
            "fields": [(n, v) for n, v in fields], "inline": False}


def activity_dm(r, site):
    """The DM a pilot gets a few days before their next flight is due."""
    import datetime as dt
    day = dt.datetime.fromtimestamp(r["due"], dt.timezone.utc).strftime("%A, %B %-d")
    when = "today" if r["days_left"] <= 0 else "tomorrow" if r["days_left"] == 1 else f"in {r['days_left']} days"
    return (f"Hi {r['name'].split(' ')[0]}, a quick heads-up from PAC Operations: your next flight is due {when} ({day}).\n"
            f"Any flight counts. The board is here: {site}/#missions\n"
            f"Away for a while? Take a leave of absence on your home page ({site}/#home) and the clock pauses until you're back.")


def recap_due(now_utc, r, hour_utc=14):
    """Monday from the posting hour, once per week (the website remembers the last week posted)."""
    return bool(r.get("enabled", True)) and not r.get("posted") and now_utc.weekday() == 0 and now_utc.hour >= hour_utc


def butter_text(ev, limit_fpm=100):
    """A soft landing for the butter board, or None. Landing rates are negative (descending), e.g. -48 fpm."""
    rate = ev.get("landing_rate")
    if rate is None or rate >= 0 or rate < -abs(limit_fpm) or "fail" in (ev.get("status") or "").lower():
        return None
    ac = ev.get("aircraft_name") or ev.get("aircraft") or "PAC aircraft"
    return f"🧈 {mention(ev)} greased the {ac} into **{ev['arr']}** at **{int(rate)} fpm**! ({ev['flight']})"


def promotion_text(ev):
    return f"🎖️ Congratulations {mention(ev)}, promoted from {ev['from']} to **{ev['rank']}**!"


def new_pilot_text(ev, member_mention=None):
    who = member_mention or f"**{ev['pilot']}**"
    return (f"✈️ Please welcome {who} to Pagani Air Cargo as **{ev['pilot_id']}**! "
            "Link your Discord account with `/link` (your code is in Settings on the PAC website).")


def shop_text(ev):
    if ev.get("kind") == "naming":
        return f"🏷️ {mention(ev)} has named PAC aircraft **{ev.get('extra')}** “{ev['item']}”."
    if ev.get("kind") == "gear":
        return f"🛍️ {mention(ev)} has picked up a **{ev['item']}** from the PAC shop."
    if ev.get("kind") == "frame":
        return f"🪪 {mention(ev)} is now wearing the **{ev['item']}** crew-badge frame."
    return f"🧵 {mention(ev)} has earned the **{ev['item']}** patch from the PAC shop."


def livery_text(ev, site):
    """A new livery on the Fleet page. The painter gets the credit, with their link when they gave one."""
    painter = ev.get("painter") or "a PAC painter"
    by = f"[{painter}](<{ev['painter_link']}>)" if ev.get("painter_link") else f"**{painter}**"
    what = " · ".join(x for x in (ev.get("sim"), ev.get("model"), ev.get("registration")) if x)
    return (f"🎨 New livery: the **{ev.get('aircraft', ev.get('type', ''))}** in {ev.get('title') or 'PAC colors'}, painted by {by}."
            + (f"\n{what}" if what else "") + f"\nGet it on the Fleet page: {site.rstrip('/')}/#fleet")


def site_news_card(ev, site):
    """A post from Staff › News: company NOTAMs for the NOTAM channel, news for announcements."""
    notam = ev.get("kind") == "notam"
    title = ev.get("title") or ""
    if notam:
        head = f"⚠️ NOTAM {ev['number']} · {title}" if ev.get("number") else f"⚠️ NOTAM · {title}"
    else:
        head = f"📣 {title}"
    if ev.get("updated"):
        head += " (updated)"
    body = (ev.get("body") or "").strip()
    if len(body) > 3900:
        body = body[:3897].rsplit(" ", 1)[0] + "…"
    colour = PAC_RED if ev.get("important") else (0xF2A900 if notam else 0x1E2126)
    return {"title": head[:250], "description": body or None, "colour": colour,
            "fields": [("From", ev.get("author") or "PAC Operations")], "url": f"{site.rstrip('/')}/#home"}


DISPATCH_COLOURS = {"urgent": PAC_RED, "freight": 0xD9A428, "partner": 0x2B6CB0, "Critical": 0xE06A00, "High": 0xE0A100}
DISPATCH_ORDER = {"urgent": 0, "partner": 1, "mission": 2}      # when there's more than the hourly limit allows


def dispatch_wanted(item, settings):
    return bool(settings.get({"mission": "missions", "partner": "partners", "urgent": "urgent"}[item["kind"]], True))


def dispatch_card(item, site):
    """A new piece of work for the dispatch channel. Times use Discord's own timestamps, so everyone sees their local time."""
    o, d = item["origin"], item["destination"]
    route = f"{o['icao']} → {d['icao']}"
    places = f"{o['city']} to {d['city']}" if o.get("city") and d.get("city") else ""
    if item["kind"] == "freight":
        title = f"{'🌸' if item.get('season') else '📦'} Freight waiting · {item['id']} · {item['title']}"
    elif item["kind"] == "urgent" and item.get("relief"):     # calm on purpose: a real disaster, not a race
        title = f"Humanitarian relief · {item['id']} · {item['title']}"
    elif item["kind"] == "urgent":
        title = f"🚨 Urgent · {item['id']} · {item['title']}"
    elif item["kind"] == "partner":
        title = f"🤝 Crew request · {item.get('operator') or 'Partner airline'} · {route}"
    else:
        title = f"📦 New mission · {item['id']} · {item['title']}"
    brief = item.get("briefing") or ""
    desc = (f"**{places}**\n" if places else "") + (brief if len(brief) <= 300 else brief[:297].rsplit(" ", 1)[0] + "…")
    load = f"{int(item['payload_lbs']):,} lb" if item.get("payload_lbs") else ""
    if item["kind"] == "freight":
        fields = [("Waiting at", o["icao"]), ("Going to", d["icao"]), ("Freight", f"{load} · {int(item.get('pieces') or 0)} pcs"),
                  ("Claim it", f"`/claim {item['id']}`")]
    else:
        fields = [("Route", route), ("Aircraft", " or ".join(item.get("aircraft") or []) or "–"),
                  ("Cargo", " · ".join(x for x in (load, item.get("cargo")) if x) or "–"),
                  ("Distance", f"{int(item.get('distance_nm') or 0):,} nm · about {hm(item.get('block_min'))}")]
    if item.get("special"):
        fields.append(("Watch out for", item["special"]))
    if item["kind"] == "partner":
        if item.get("callsign"):
            fields.append(("Callsign", item["callsign"]))
        if item.get("bonus"):
            fields.append(("Shortage bonus", f"${int(item['bonus']):,}"))
    if item["kind"] in ("urgent", "freight") and item.get("deliver_by"):
        fields.append(("Deliver by", f"<t:{int(item['deliver_by'])}:t> (<t:{int(item['deliver_by'])}:R>)"))
    if item.get("expires"):
        fields.append(("Book by", f"<t:{int(item['expires'])}:R>"))
    if item.get("relief"):
        desc = (f"Based on a real disaster: {item.get('event')}. Flown in respect for those affected; no bonus rewards.\n" + desc)[:600]
    colour = 0x2D4F7C if item.get("relief") else DISPATCH_COLOURS.get(item["kind"]) or DISPATCH_COLOURS.get(item.get("priority"), 0x5E6470)
    return {"title": title[:250], "description": desc, "colour": colour, "fields": fields,
            "url": f"{site.rstrip('/')}/#{'cargo' if item['kind'] == 'freight' else 'missions'}"}


def dispatch_pick(items, settings, posted_times, now):
    """Which new items to post: the kinds staff switched on, within the hourly limit, most urgent first.
    Returns (to_post, skipped). posted_times are the times of posts in the last hour."""
    recent = [t for t in posted_times if now - t < 3600]
    room = max(0, int(settings.get("per_hour", 4)) - len(recent))
    wanted = sorted((i for i in items if dispatch_wanted(i, settings)), key=lambda i: (DISPATCH_ORDER[i["kind"]], i["created"]))
    return wanted[:room], wanted[room:]


def welcome_text(member_mention, site):
    return (f"Welcome to Pagani Air Cargo, {member_mention}! 📦✈️\n"
            f"Already a PAC pilot? Type `/link` with the code from Settings on {site}. "
            f"Not yet? Apply to fly at {site}.")


def pilot_card(p, site):
    fields = [("Rank", p["rank"]), ("Hours", f"{p['hours']:,}"), ("Flights", f"{p['flights']:,}"),
              ("Average score", str(p["avg_score"]) if p.get("avg_score") else "–"), ("Home base", p.get("base") or "–"),
              ("Now at", p.get("location") or "–")]
    if p.get("last"):
        l = p["last"]
        fields.append(("Last flight", f"{l['flight_number']} {l['dep']} → {l['arr']}"))
    return {"title": f"{p['name']} · {p['pilot_id']}", "colour": PAC_RED, "fields": fields, "url": f"{site}/#home"}


def live_lines(flights, site):
    if not flights:
        return f"Nobody's flying for PAC right now. The live map is at {site}/#live"
    rows = [f"**{f['flight']}** {f.get('dep') or ''} → {f.get('arr') or ''} · {f.get('aircraft')} · "
            f"{altitude(f.get('alt_ft'), f.get('on_ground'))} · {f.get('phase_label') or ''}"
            + (f" · {f['pilot']}" if f.get("pilot") else "") for f in flights[:15]]
    return f"**{len(flights)} PAC flight{'s' if len(flights) != 1 else ''} on the move**\n" + "\n".join(rows) + f"\n\nLive map: {site}/#live"


def recent_lines(flights):
    if not flights:
        return "No PAC flights filed yet."
    return "\n".join(f"**{f['flight_number']}** {f['dep']} → {f['arr']} · {f['aircraft']} · {f.get('pilot') or f['pilot_id']}"
                     + (f" · {f['grade']}" if f.get("grade") else "")
                     + f" · <t:{int(f['filed_at'])}:R>" for f in flights)


def wanted_roles(p, cfg):
    """The PAC roles a linked pilot should have."""
    roles = set()
    if not p.get("active"):
        return roles
    if cfg.get("pilot_role"):
        roles.add(cfg["pilot_role"])
    if cfg.get("rank_roles") and p.get("rank"):
        roles.add(p["rank"])
    if p.get("staff") and cfg.get("staff_role"):
        roles.add(cfg["staff_role"])
    return roles


def managed_roles(cfg):
    """Every role the bot looks after, so it can take away ones a pilot no longer has."""
    out = set(cfg.get("ranks") or []) if cfg.get("rank_roles") else set()
    out |= {r for r in (cfg.get("pilot_role"), cfg.get("staff_role")) if r}
    return out


# ---------------------------------------------------------------- bot trap (honeypot channel)
TRAP_DELETE_SECONDS = 24 * 3600   # how far back their messages are deleted across the server


def _bare(name):
    """A channel name without emoji or separators, so "🚫・do-not-post" matches "do-not-post"."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum() or ch == "-").strip("-")


def is_trap_channel(channel_name, channel_id, configured):
    configured = (configured or "").strip().lstrip("#")
    if not configured:
        return False
    if configured.isdigit():
        return str(channel_id) == configured
    return _bare(channel_name) == _bare(configured) and bool(_bare(configured))


def trap_exempt(is_bot, is_owner, perms, role_names, staff_role):
    """Who the trap never touches: the server's own bots, the owner, anyone who can moderate, and PAC staff."""
    if is_bot or is_owner:
        return True
    if any(perms.get(k) for k in ("administrator", "manage_messages", "ban_members", "kick_members", "manage_guild")):
        return True
    return bool(staff_role) and staff_role in (role_names or [])


def trap_dm(server_name, site):
    return (f"You were removed from **{server_name}** because your account posted in the bot-trap channel, which says not to post. "
            f"This catches spam bots and hacked accounts.\n\nIf you're a real person, sorry! Secure your account (change your "
            f"password, check connected apps) and rejoin with the Discord link on {site}.")


def trap_log(member_label, member_id, channel_name, ok, why=""):
    if ok:
        return f"🪤 **Bot trap:** removed {member_label} (`{member_id}`) for posting in #{channel_name}. Their messages from the last 24 hours were deleted."
    return f"🪤 **Bot trap:** {member_label} (`{member_id}`) posted in #{channel_name}, but I couldn't remove them: {why}"


# ---------------------------------------------------------------- the bot
def run(cfg):
    import discord
    from discord import app_commands

    intents = discord.Intents.default()
    intents.members = True               # roles and welcomes (switch on Server Members Intent in the Developer Portal)
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    site = cfg["site"]
    state = {"last": None, "guild": None, "dispatch_after": None, "dispatch_posted": []}

    def embed(card):
        e = discord.Embed(title=card["title"], description=card.get("description"), colour=card["colour"], url=card.get("url"))
        for name, value in card.get("fields", []):
            # short numbers sit side by side; longer lists (names) get the full width
            e.add_field(name=name, value=value, inline=card.get("inline", True) or "\n" not in value and len(value) < 24)
        e.set_footer(text="Pagani Air Cargo · Move the Impossible!")
        return e

    def guild():
        if state["guild"]:
            return state["guild"]
        g = client.get_guild(int(cfg["guild"])) if (cfg.get("guild") or "").isdigit() else (client.guilds[0] if client.guilds else None)
        state["guild"] = g
        return g

    def channel(key):
        g, name = guild(), (cfg["channels"].get(key) or "").lower()
        if not g or not name:
            return None
        # emoji and separators in the Discord name don't matter: "📋flight-log" and "📋・flight-log" both match "flight-log"
        return (discord.utils.find(lambda c: c.name.lower() == name or str(c.id) == name, g.text_channels)
                or discord.utils.find(lambda c: _bare(c.name) == _bare(name) and _bare(name), g.text_channels))

    async def role(g, name):
        r = discord.utils.get(g.roles, name=name)
        if r is None:
            try:
                r = await g.create_role(name=name, colour=discord.Colour(PAC_RED) if name == cfg.get("pilot_role") else discord.Colour.default(),
                                        reason="PAC Operations: PAC rank roles")
            except discord.Forbidden:
                print(f"Can't create the role {name}: give the bot Manage Roles.")
        return r

    async def sync_member(p):
        g = guild()
        if not g or not p.get("discord_id"):
            return
        try:
            m = g.get_member(int(p["discord_id"])) or await g.fetch_member(int(p["discord_id"]))
        except (discord.NotFound, discord.HTTPException):
            return
        want, managed = wanted_roles(p, cfg), managed_roles(cfg)
        add = [r for r in [await role(g, n) for n in want] if r and r not in m.roles]
        drop = [r for r in m.roles if r.name in managed and r.name not in want]
        try:
            if add:
                await m.add_roles(*add, reason="PAC Operations: PAC rank")
            if drop:
                await m.remove_roles(*drop, reason="PAC Operations: PAC rank")
        except discord.Forbidden:
            print("Can't change roles: move the bot's role above the PAC rank roles in Server Settings › Roles.")

    async def sync_all():
        st, r = await apac("GET", "/api/bot/roster")
        if st == 200:
            for p in r.get("pilots", []):
                await sync_member(p)

    async def post(key, content=None, card=None):
        ch = channel(key)
        if not ch:
            return
        try:
            await ch.send(content=content, embed=embed(card) if card else None,
                          allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        except discord.Forbidden:
            print(f"Can't post in #{ch.name}: give the bot Send Messages and Embed Links there.")

    async def handle(ev):
        kind, d = ev["kind"], ev["data"]
        if kind == "pirep":
            await post("flights", card=pirep_card(d, site))
            bt = butter_text(d, cfg.get("butter_fpm", 100))
            if bt and channel("butter"):                       # the butter board: soft landings, posted automatically
                await post("butter", bt)
        elif kind == "departed":
            await post("flights", card=departed_card(d, site))
        elif kind == "promotion":
            await post("news", promotion_text(d))
            await sync_all()
        elif kind == "new_pilot":
            g, mm = guild(), None
            if g and d.get("discord"):
                m = g.get_member_named(d["discord"].lstrip("@"))
                mm = m.mention if m else None
            await post("news", new_pilot_text(d, mm))
        elif kind == "shop":
            await post("news", shop_text(d))
        elif kind == "livery":
            await post("news", livery_text(d, site))
        elif kind == "site_news":
            key = "notams" if d.get("kind") == "notam" and channel("notams") else "news"
            await post(key, card=site_news_card(d, site))
        elif kind == "unlinked":
            await sync_member({"discord_id": d["discord_id"], "active": False})
        elif kind == "aog_opened":
            ch = "dispatch" if channel("dispatch") else "news"
            if d.get("at_hub"):
                await post(ch, f"🔧 **AOG: {d['reg']}** ({d.get('type')}) grounded at **{d['station']}**: {d['title'].lower()} after {d.get('cause') or 'its last flight'}. Parts are on site at the hub; back in about {d['repair_hours']} h.")
            elif d.get("mission"):
                await post(ch, f"🚨 **AOG: {d['reg']}** ({d.get('type')}) is grounded at **{d['station']}**: {d['title'].lower()} after {d.get('cause') or 'its last flight'}.\n"
                               f"Recovery mission **{d['mission']}** from {d['hub']}: fly {d['weight_lbs']:,} lb of parts and the engineers in. Repair takes about {d['repair_hours']} h once they arrive. Who's going? ✈️")
            else:
                await post(ch, f"🔧 **AOG: {d['reg']}** grounded at **{d['station']}**: {d['title'].lower()}. A contractor is flying the parts in.")
        elif kind == "aog_parts":
            mention = f"<@{d['discord_id']}>" if d.get("discord_id") else d.get("pilot")
            await post("dispatch" if channel("dispatch") else "news",
                       f"🧰 Parts and engineers delivered to **{d['station']}** on {d['flight']}{(' by ' + mention) if mention else ''}. {d['reg']} is under repair, about {d['repair_hours']} h to go.")
        elif kind == "aog_resolved":
            await post("dispatch" if channel("dispatch") else "news",
                       f"✅ **{d['reg']}** is back in service at **{d['station']}** after {d['hours']} h AOG ({d.get('by')}).")
        elif kind == "freight_delivered":
            who = f"<@{d['discord_id']}>" if d.get("discord_id") else f"**{d.get('pilot')}**"
            what = f"{d.get('commodity') or 'freight'}" + (f" ({d['season']})" if d.get("season") else "")
            await post("dispatch" if channel("dispatch") else "flights", f"📦 {who} delivered **{d['awb']}**, {what}, to **{d['destination']}** on {d.get('flight') or 'a PAC flight'}.")

    async def dispatch_tick():
        """Every minute: post new missions, partner crew requests and urgent requests in the dispatch channel."""
        q = "" if state["dispatch_after"] is None else f"?after={state['dispatch_after']}"
        st, r = await apac("GET", "/api/bot/dispatch" + q)
        if st != 200:
            return
        state["dispatch_after"] = r.get("last", state["dispatch_after"])
        if not r.get("items") or not channel("dispatch"):
            return
        now = time.time()
        state["dispatch_posted"] = [t for t in state["dispatch_posted"] if now - t < 3600]
        post_now, skipped = dispatch_pick(r["items"], r.get("settings") or cfg.get("dispatch") or {}, state["dispatch_posted"], now)
        for item in post_now:
            await post("dispatch", card=dispatch_card(item, site))
            state["dispatch_posted"].append(time.time())
        if skipped:
            print(f"Dispatch channel: {len(skipped)} new item(s) not posted (hourly limit reached).")

    async def recap_tick():
        import datetime as dt
        st, r = await apac("GET", "/api/bot/weekly")
        if st != 200 or not recap_due(dt.datetime.now(dt.timezone.utc), r, r.get("hour_utc", 14)):
            return
        card = recap_card(r)
        if card:
            await post("recap" if channel("recap") else "news", card=card)
        await apac("POST", "/api/bot/weekly/posted", {"week": r["week"]})    # also for an empty week, so it isn't retried

    async def activity_tick():
        """Every ten minutes: DM pilots whose next flight is due within the reminder window (once per due date)."""
        st, r = await apac("GET", "/api/bot/activity")
        if st != 200 or not r.get("enabled") or not r.get("reminders"):
            return
        done = []
        for it in r["reminders"]:
            try:
                u = client.get_user(int(it["discord_id"])) or await client.fetch_user(int(it["discord_id"]))
                await u.send(activity_dm(it, r.get("site") or site))
                done.append(it)
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                done.append(it)          # DMs closed: don't keep trying for this date
        if done:
            await apac("POST", "/api/bot/activity/reminded", {"items": done})

    async def events_loop():
        await client.wait_until_ready()
        n = 0
        while not client.is_closed():
            try:
                st, r = await apac("GET", "/api/bot/events" + ("" if state["last"] is None else f"?after={state['last']}"))
                if st == 200:
                    for ev in r.get("events", []):
                        await handle(ev)
                    state["last"] = r.get("last", state["last"])
                if n % 12 == 0:                  # every minute: new work for the dispatch channel
                    await dispatch_tick()
                if n % 120 == 60:                # every ten minutes: is the Monday recap due?
                    await recap_tick()
                if n % 120 == 90:                # every ten minutes: next-flight-due reminders by DM
                    await activity_tick()
                if n % 120 == 0:                 # every ten minutes: keep everyone's roles right
                    await sync_all()
                    st, c = await apac("GET", "/api/bot/config")
                    if st == 200 and (c.get("token") != cfg["token"] or not c.get("enabled")):
                        print("Discord bot settings changed: restarting.")
                        await client.close()
                        return
                    if st == 200:
                        cfg.update({k: c[k] for k in ("channels", "pilot_role", "staff_role", "rank_roles", "ranks", "site", "guild", "dispatch", "butter_fpm")
                                    if k in c})
            except Exception as e:
                print(f"Discord bot loop: {e}")
            n += 1
            await asyncio.sleep(5)

    @client.event
    async def on_ready():
        g = guild()
        print(f"PAC Operations is online as {client.user} in {g.name if g else 'no server yet'}.")
        try:
            if g:
                tree.copy_global_to(guild=g)
                await tree.sync(guild=g)
        except Exception as e:
            print(f"Couldn't register the slash commands: {e}")

    @client.event
    async def on_message(message):
        """Bot trap: anyone who posts in the do-not-post channel is soft-banned (see the top of this file)."""
        g = guild()
        if not g or not message.guild or message.guild.id != g.id or message.author.id == client.user.id:
            return
        ch = message.channel
        if not is_trap_channel(getattr(ch, "name", ""), ch.id, cfg["channels"].get("honeypot")):
            return
        if message.webhook_id:                      # a webhook can't be banned; just tidy up
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            return
        m = message.author
        perms = dict(iter(ch.permissions_for(m))) if isinstance(m, discord.Member) else {}
        roles = [r.name for r in getattr(m, "roles", [])]
        if trap_exempt(m.bot, m.id == g.owner_id, perms, roles, cfg.get("staff_role")):
            return
        label = f"{m} ({m.display_name})" if getattr(m, "display_name", None) and m.display_name != m.name else str(m)
        try:
            await m.send(trap_dm(g.name, site))     # before the ban, while we still share a server
        except discord.HTTPException:
            pass
        ok, why = True, ""
        try:
            await g.ban(m, reason="PAC bot trap: posted in the do-not-post channel", delete_message_seconds=TRAP_DELETE_SECONDS)
            await g.unban(m, reason="PAC bot trap: soft ban (they can rejoin with an invite)")
        except discord.Forbidden:
            ok, why = False, "give my role Ban Members and move it above ordinary members' roles (Server Settings › Roles)."
            try:
                await message.delete()
            except discord.HTTPException:
                pass
        except discord.HTTPException as e:
            ok, why = False, str(e)
        print(trap_log(str(m), m.id, ch.name, ok, why))
        await post("modlog", trap_log(label, m.id, ch.name, ok, why))

    @client.event
    async def on_member_join(member):
        if guild() and member.guild.id == guild().id:
            await post("welcome", welcome_text(member.mention, site))
            st, r = await apac("GET", f"/api/bot/pilot?q={member.id}")
            if st == 200:                              # a pilot who'd linked before and rejoined
                st2, roster = await apac("GET", "/api/bot/roster")
                for p in (roster or {}).get("pilots", []):
                    if p["discord_id"] == str(member.id):
                        await sync_member(p)

    @tree.command(name="flights", description="The latest PAC flights")
    async def flights_cmd(inter: discord.Interaction):
        st, r = await apac("GET", "/api/bot/recent")
        await inter.response.send_message(recent_lines(r.get("flights", [])) if st == 200 else "PAC isn't answering just now.")

    @tree.command(name="live", description="Who's flying for PAC right now")
    async def live_cmd(inter: discord.Interaction):
        st, r = await apac("GET", "/api/bot/live")
        await inter.response.send_message(live_lines(r.get("flights", []), site) if st == 200 else "PAC isn't answering just now.")

    @tree.command(name="pilot", description="A PAC pilot's card")
    @app_commands.describe(who="Pilot ID or name (leave blank for yours)", member="Or pick someone in this server")
    async def pilot_cmd(inter: discord.Interaction, who: str | None = None, member: discord.Member | None = None):
        q = who or str((member or inter.user).id)
        st, r = await apac("GET", "/api/bot/pilot?" + urllib.parse.urlencode({"q": q}))
        if st != 200:
            msg = "You haven't linked your PAC pilot yet. Use `/link` with the code from Settings on the website." if not (who or member) \
                else "No PAC pilot found."
            await inter.response.send_message(msg, ephemeral=True)
            return
        await inter.response.send_message(embed=embed(pilot_card(r, site)))

    @tree.command(name="status", description="Your PAC day at a glance (only you see it)")
    async def status_cmd(inter: discord.Interaction):
        st, r = await apac("GET", "/api/bot/status?" + urllib.parse.urlencode({"discord_id": str(inter.user.id)}))
        if st != 200:
            await inter.response.send_message(r.get("error") or "PAC isn't answering just now.", ephemeral=True)
            return
        await inter.response.send_message(embed=embed(status_card(r, site)), ephemeral=True)

    @tree.command(name="claim", description="Hold waiting PAC freight for your next flight (24 hours)")
    @app_commands.describe(awb="The air waybill number, like 901-10000034")
    async def claim_cmd(inter: discord.Interaction, awb: str):
        st, r = await apac("POST", "/api/bot/claim", {"discord_id": str(inter.user.id), "awb": awb})
        if st != 200:
            await inter.response.send_message(r.get("error") or "That didn't work. Try again in a minute.", ephemeral=True)
            return
        await inter.response.send_message(
            f"📦 **{r['awb']}** ({r['commodity']}) is held for you until <t:{int(r['until'])}:f>. It's waiting at **{r['station']}** for **{r['destination']}**: "
            f"book a flight from {r['station']} and tick it under Transfer cargo on the load sheet.")

    @tree.command(name="link", description="Link your Discord account to your PAC pilot")
    @app_commands.describe(code="The code from Settings on the PAC website, like PAC-7F3KX")
    async def link_cmd(inter: discord.Interaction, code: str):
        st, r = await apac("POST", "/api/bot/link", {"code": code, "discord_id": str(inter.user.id), "discord_name": str(inter.user)})
        if st != 200:
            await inter.response.send_message(r.get("error") or "That didn't work. Try a new code.", ephemeral=True)
            return
        await inter.response.send_message(f"Linked! You're **{r['name']}** ({r['pilot_id']}), {r['rank']}. Welcome aboard.", ephemeral=True)
        await sync_member({"discord_id": str(inter.user.id), "active": True, "rank": r["rank"], "staff": r.get("staff")})

    @tree.command(name="unlink", description="Unlink your Discord account from PAC")
    async def unlink_cmd(inter: discord.Interaction):
        st, r = await apac("POST", "/api/bot/unlink", {"discord_id": str(inter.user.id)})
        await inter.response.send_message("Unlinked. Your PAC roles have been removed." if r.get("ok") else "Your Discord account wasn't linked.",
                                          ephemeral=True)
        if r.get("ok"):
            await sync_member({"discord_id": str(inter.user.id), "active": False})

    async def main():
        async with client:
            asyncio.get_running_loop().create_task(events_loop())
            await client.start(cfg["token"])

    asyncio.run(main())


def wait_for_config():
    """Until staff switch the bot on with a token, check every minute without using any resources."""
    while True:
        try:
            st, cfg = pac("GET", "/api/bot/config")
            if st == 200 and cfg.get("enabled") and cfg.get("token"):
                return cfg
            if st != 200:
                print(f"PAC answered {st}; is the PAC website running?")
        except (OSError, ValueError) as e:
            print(f"Waiting for PAC: {e}")
        time.sleep(60)


if __name__ == "__main__":
    cfg = wait_for_config()
    try:
        run(cfg)
    except Exception as e:                 # a bad token, a network drop: systemd starts us again
        print(f"PAC Operations stopped: {e}")
        time.sleep(30)
        sys.exit(1)
    sys.exit(0)                            # settings changed: systemd starts us again with the new ones
