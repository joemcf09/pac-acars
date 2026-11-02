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
channel (within an hourly limit), and welcomes people who join the Discord server."""

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
    return {"title": f"{ev['flight']} · {ev.get('mission') or 'PAC flight'}",
            "description": f"Flown by {mention(ev)}" + (" · delivered late" if late else " · delivered"),
            "colour": GRADE_COLOURS.get(grade, PAC_RED), "fields": fields, "url": f"{site}/#logbook"}


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
    return (f"🎨 New livery: the **{ev.get('aircraft', ev.get('type', ''))}** in {ev.get('title') or 'PAC colours'}, painted by {by}."
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


DISPATCH_COLOURS = {"urgent": PAC_RED, "partner": 0x2B6CB0, "Critical": 0xE06A00, "High": 0xE0A100}
DISPATCH_ORDER = {"urgent": 0, "partner": 1, "mission": 2}      # when there's more than the hourly limit allows


def dispatch_wanted(item, settings):
    return bool(settings.get({"mission": "missions", "partner": "partners", "urgent": "urgent"}[item["kind"]], True))


def dispatch_card(item, site):
    """A new piece of work for the dispatch channel. Times use Discord's own timestamps, so everyone sees their local time."""
    o, d = item["origin"], item["destination"]
    route = f"{o['icao']} → {d['icao']}"
    places = f"{o['city']} to {d['city']}" if o.get("city") and d.get("city") else ""
    if item["kind"] == "urgent":
        title = f"🚨 Urgent · {item['id']} · {item['title']}"
    elif item["kind"] == "partner":
        title = f"🤝 Crew request · {item.get('operator') or 'Partner airline'} · {route}"
    else:
        title = f"📦 New mission · {item['id']} · {item['title']}"
    brief = item.get("briefing") or ""
    desc = (f"**{places}**\n" if places else "") + (brief if len(brief) <= 300 else brief[:297].rsplit(" ", 1)[0] + "…")
    load = f"{int(item['payload_lbs']):,} lb" if item.get("payload_lbs") else ""
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
    if item["kind"] == "urgent" and item.get("deliver_by"):
        fields.append(("Deliver by", f"<t:{int(item['deliver_by'])}:t> (<t:{int(item['deliver_by'])}:R>)"))
    if item.get("expires"):
        fields.append(("Book by", f"<t:{int(item['expires'])}:R>"))
    colour = DISPATCH_COLOURS.get(item["kind"]) or DISPATCH_COLOURS.get(item.get("priority"), 0x5E6470)
    return {"title": title[:250], "description": desc, "colour": colour, "fields": fields, "url": f"{site.rstrip('/')}/#missions"}


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
            e.add_field(name=name, value=value, inline=True)
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
        return discord.utils.find(lambda c: c.name.lower() == name or str(c.id) == name, g.text_channels)

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
                if n % 120 == 0:                 # every ten minutes: keep everyone's roles right
                    await sync_all()
                    st, c = await apac("GET", "/api/bot/config")
                    if st == 200 and (c.get("token") != cfg["token"] or not c.get("enabled")):
                        print("Discord bot settings changed: restarting.")
                        await client.close()
                        return
                    if st == 200:
                        cfg.update({k: c[k] for k in ("channels", "pilot_role", "staff_role", "rank_roles", "ranks", "site", "guild", "dispatch")
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
