"""The PAC side of the PAC Discord bot.

The bot (discord_bot.py) runs as its own service on the same server and talks to PAC over a private API under
/api/bot/. Every bot request carries the secret in data/bot_secret, which only exists on the server, and requests
that came in from the internet through Caddy are refused outright.

PAC records things worth announcing in the bot_events table (accepted PIREPs, promotions, new pilots, shop
purchases); the bot collects them every few seconds and posts them. Pilots link their Discord account with a short
code from PAC's Settings window (/link CODE in Discord), and the bot keeps their rank roles in step."""
import hmac
import json
import secrets
import string
import time

from flask import Blueprint, jsonify, request

bp = Blueprint("botlink", __name__)
C = {}                                  # db, settings, DATA, va, live_flights, FLEET, AIRPORTS
CODE_MINUTES = 15
RECENT_PIREP_S = 24 * 3600              # never announce old flights (e.g. when back pay runs)
_seen = {"poll": 0}                     # when the bot last collected events, to show staff it's online


def init(ctx):
    C.update(ctx)
    with C["db"]() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS bot_events (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL,
            kind TEXT, data TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS discord_codes (code TEXT PRIMARY KEY, pilot_id TEXT, expires REAL)""")
        cols = {r[1] for r in con.execute("PRAGMA table_info(pilots)")}
        if "discord_id" not in cols:
            con.execute("ALTER TABLE pilots ADD COLUMN discord_id TEXT")
            con.execute("ALTER TABLE pilots ADD COLUMN discord_name TEXT")
        if "rank_seen" not in cols:
            con.execute("ALTER TABLE pilots ADD COLUMN rank_seen TEXT")      # the rank last announced
    secret()


def secret():
    p = C["DATA"] / "bot_secret"
    if not p.exists():
        p.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            p.chmod(0o600)
        except OSError:
            pass
    return p.read_text(encoding="utf-8").strip()


def enabled():
    st = C["settings"]()
    return bool(st.get("discord_bot_enabled") and (st.get("discord_bot_token") or "").strip())


# ---------------------------------------------------------------- events PAC records for the bot
def emit(kind, data):
    if not enabled():
        return
    try:
        with C["db"]() as con:
            con.execute("INSERT INTO bot_events (time, kind, data) VALUES (?,?,?)", (time.time(), kind, json.dumps(data)))
            con.execute("DELETE FROM bot_events WHERE time < ?", (time.time() - 14 * 86400,))   # kept two weeks for the weekly recap
    except Exception as e:
        print(f"Discord bot event not recorded: {e}")


def _pilot(con, pid):
    r = con.execute("SELECT id, name, discord_id, rank_seen, staff FROM pilots WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else {"id": pid, "name": pid}


def pirep_accepted(pirep_id):
    """Called once when a PIREP is accepted and paid: announce it, and any promotion it brought."""
    if not enabled():
        return
    va, FLEET = C["va"], C["FLEET"]
    with C["db"]() as con:
        r = con.execute("SELECT * FROM pireps WHERE id=?", (pirep_id,)).fetchone()
        if not r or r["demo"] or (r["filed_at"] or 0) < time.time() - RECENT_PIREP_S:
            return
        p = _pilot(con, r["pilot_id"])
    ac = FLEET.get(r["aircraft"], {})
    s_ = C["settings"]() if C.get("settings") else {}
    if s_.get("discord_webhook") and s_.get("discord_arrivals", True):
        check_promotion(r["pilot_id"])      # the webhook already posted this arrival: never twice
        return
    emit("pirep", {"pirep_id": r["id"], "flight": r["flight_number"], "dep": r["dep"], "arr": r["arr"],
                   "aircraft": ac.get("icao") or r["aircraft"], "aircraft_name": ac.get("name", ""),
                   "mission": r["mission_title"], "pilot_id": p["id"], "pilot": p["name"], "discord_id": p.get("discord_id"),
                   "block_min": r["block_min"], "landing_rate": r["landing_rate"], "score": r["score"], "grade": r["grade"],
                   "status": r["status"], "points": r["points"], "cargo_lbs": r["cargo_lbs"] if "cargo_lbs" in r.keys() else None})
    check_promotion(r["pilot_id"])


def check_promotion(pid):
    try:
        rank = C["va"].career(pid)["rank"]
    except Exception:
        return
    with C["db"]() as con:
        p = _pilot(con, pid)
        seen = p.get("rank_seen")
        con.execute("UPDATE pilots SET rank_seen=? WHERE id=?", (rank, pid))
    if seen and seen != rank:
        emit("promotion", {"pilot_id": pid, "pilot": p["name"], "discord_id": p.get("discord_id"), "from": seen, "rank": rank})


def new_pilot(pid, name, discord_handle=""):
    emit("new_pilot", {"pilot_id": pid, "pilot": name, "discord": (discord_handle or "").strip()})


def shop_purchase(pid, item_name, kind, extra=""):
    with C["db"]() as con:
        p = _pilot(con, pid)
    emit("shop", {"pilot_id": pid, "pilot": p["name"], "discord_id": p.get("discord_id"), "item": item_name,
                  "kind": kind, "extra": extra})


# ---------------------------------------------------------------- linking (signed-in pilots on the website)
@bp.get("/api/discord/me")
def discord_me():
    pid = C["va"].current_pilot_id()
    with C["db"]() as con:
        p = _pilot(con, pid)
        r = con.execute("SELECT discord_name FROM pilots WHERE id=?", (pid,)).fetchone()
    return jsonify({"enabled": enabled(), "linked": bool(p.get("discord_id")), "discord_name": r["discord_name"] if r else None,
                    "invite": (C["va"].site().get("discord_invite") or "").strip()})


@bp.post("/api/discord/code")
def discord_code():
    if not enabled():
        return jsonify({"error": "The PAC Discord bot isn't switched on yet."}), 400
    pid = C["va"].current_pilot_id()
    code = "PAC-" + "".join(secrets.choice(string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789") for _ in range(5))
    with C["db"]() as con:
        con.execute("DELETE FROM discord_codes WHERE pilot_id=? OR expires<?", (pid, time.time()))
        con.execute("INSERT INTO discord_codes (code, pilot_id, expires) VALUES (?,?,?)", (code, pid, time.time() + CODE_MINUTES * 60))
    return jsonify({"code": code, "minutes": CODE_MINUTES})


@bp.post("/api/discord/unlink")
def discord_unlink():
    pid = C["va"].current_pilot_id()
    with C["db"]() as con:
        old = con.execute("SELECT discord_id FROM pilots WHERE id=?", (pid,)).fetchone()
        con.execute("UPDATE pilots SET discord_id=NULL, discord_name=NULL WHERE id=?", (pid,))
    if old and old["discord_id"]:
        emit("unlinked", {"pilot_id": pid, "discord_id": old["discord_id"]})
    return jsonify({"ok": True})


# ---------------------------------------------------------------- the bot's private API
def _bot_only():
    """The bot runs on this server: no request through Caddy (which adds X-Forwarded-For) and the right secret."""
    if request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP"):
        return jsonify({"error": "Not found."}), 404
    given = request.headers.get("X-PAC-Bot", "")
    if not given or not hmac.compare_digest(given, secret()):
        return jsonify({"error": "Not found."}), 404
    return None


@bp.before_request
def _guard():
    if request.path.startswith("/api/bot/"):
        return _bot_only()
    return None


@bp.get("/api/bot/config")
def bot_config():
    st = C["settings"]()
    ranks = [r["name"] for r in C["va"].ranks_effective()]
    return jsonify({"enabled": enabled(), "token": (st.get("discord_bot_token") or "").strip(),
                    "guild": (st.get("discord_guild") or "").strip(),
                    "channels": {k: (st.get(f"discord_ch_{k}") or "").strip().lstrip("#") for k in ("flights", "news", "welcome", "dispatch", "notams", "honeypot", "modlog", "recap", "butter")},
                    "dispatch": dispatch_settings(st),
                    "butter_fpm": max(10, min(300, int(C["va"].C["num"](st.get("discord_butter_fpm"), 100) or 100))),
                    "pilot_role": (st.get("discord_pilot_role") or "PAC Pilot").strip(),
                    "staff_role": (st.get("discord_staff_role") or "").strip(),
                    "rank_roles": bool(st.get("discord_rank_roles", True)), "ranks": ranks,
                    "site": (C["va"].site().get("public_url") or "https://pac-va.com").rstrip("/") or "https://pac-va.com"})


@bp.get("/api/bot/events")
def bot_events():
    _seen["poll"] = time.time()
    with C["db"]() as con:
        if "after" not in request.args:      # the bot has just started: begin from now, never replay old news
            last = con.execute("SELECT COALESCE(MAX(id),0) FROM bot_events").fetchone()[0]
            return jsonify({"events": [], "last": last})
        after = int(request.args.get("after") or 0)
        rows = [dict(r) for r in con.execute("SELECT * FROM bot_events WHERE id>? ORDER BY id LIMIT 50", (after,))]
    for r in rows:
        r["data"] = json.loads(r["data"] or "{}")
    return jsonify({"events": rows, "last": rows[-1]["id"] if rows else after})


# ---------------------------------------------------------------- the dispatch channel: new work as it appears
def dispatch_settings(st=None):
    st = st or C["settings"]()
    try:
        per_hour = max(1, min(30, int(float(st.get("discord_dispatch_per_hour", 4)))))
    except (TypeError, ValueError):
        per_hour = 4
    return {"missions": bool(st.get("discord_dispatch_missions", True)), "partners": bool(st.get("discord_dispatch_partners", True)),
            "urgent": bool(st.get("discord_dispatch_urgent", True)), "per_hour": per_hour}


def _place(a):
    a = a or {}
    return {"icao": a.get("icao", ""), "city": a.get("city") or a.get("name") or a.get("icao", "")}


def _work_item(kind, m, created):
    F = C["FLEET"]
    out = {"kind": kind, "id": m.get("id"), "title": m.get("title", ""), "category": m.get("category", ""), "priority": m.get("priority", ""),
           "briefing": (m.get("briefing") or "")[:400], "cargo": m.get("cargo", ""), "payload_lbs": m.get("payload_lbs") or 0,
           "distance_nm": m.get("distance_nm") or 0, "block_min": m.get("target_block_min") or 0,
           "aircraft": [F[t]["name"] for t in (m.get("aircraft") or [])[:2] if t in F],
           "origin": _place(m.get("origin")), "destination": _place(m.get("destination")),
           "expires": m.get("expires"), "created": created}
    special = [x for x in ((m.get("challenge") or {}).get("label") and f"{m['challenge']['icao']}: {m['challenge']['label']}",
                           (m.get("handling") or {}).get("label")) if x]
    if special:
        out["special"] = " · ".join(special)
    if kind == "partner":
        op = m.get("operator") or {}
        num = "".join(ch for ch in str(m.get("id", "")) if ch.isdigit())
        out.update(operator=op.get("name", ""), callsign=f"{op.get('callsign', '')} {num}".strip(), bonus=m.get("contract_bonus") or 0)
    if kind == "urgent":
        out.update(deliver_by=m.get("deliver_by"), airframe=m.get("suggested_airframe", ""))
        if m.get("relief"):
            out.update(relief=True, event=m["relief"].get("event", ""), deliver_by=None)
    return out


@bp.get("/api/bot/dispatch")
def bot_dispatch():
    """New missions, partner crew requests and urgent requests since `after` (a time), oldest first.
    The scheduled mission worker keeps the boards moving even on quiet days. Without `after` (the bot has just started) it returns nothing and the time to start from."""
    va = C["va"]
    now = time.time()  # The scheduled worker publishes offers independently.
    if "after" not in request.args:
        return jsonify({"items": [], "last": now, "settings": dispatch_settings()})
    try:
        after = float(request.args.get("after") or 0)
    except ValueError:
        after = now
    items = []
    with C["db"]() as con:
        for kind, sql in (("mission", "SELECT data, created FROM live_missions WHERE status='open' AND created>?"),
                          ("partner", "SELECT data, created FROM jobs WHERE kind='contract' AND status='open' AND created>?"),
                          ("urgent", "SELECT data, created FROM urgent WHERE status='open' AND created>?")):
            for r in con.execute(sql, (after,)):
                data = json.loads(r["data"])
                if (data.get("expires") or float("inf")) >= now:
                    items.append(_work_item(kind, data, r["created"]))
        items += _freight_items(con, after, now)
    items.sort(key=lambda x: x["created"])
    return jsonify({"items": items, "last": max([after] + [x["created"] for x in items]), "settings": dispatch_settings()})


def _freight_items(con, after, now):
    """The freight board: new customer orders worth shouting about (seasonal freight, or due within 36 hours)."""
    out = []
    try:
        rows = con.execute("""SELECT awb, commodity, origin, destination, current_station, gross_weight_lbs, pieces, created_at,
            json_extract(data,'$.deadline') AS deadline, json_extract(data,'$.season_name') AS season, json_extract(data,'$.truck_from') AS truck
            FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION' AND created_at>?
              AND (json_extract(data,'$.season') IS NOT NULL OR json_extract(data,'$.deadline') - created_at <= 36*3600)
            ORDER BY created_at""", (after,)).fetchall()
    except Exception as e:
        print("freight board:", e)
        return out
    for r in rows:
        out.append({"kind": "freight", "id": r["awb"], "title": r["commodity"], "category": r["season"] or "Express", "priority": "",
                    "briefing": (f"In season: {r['season']}. " if r["season"] else "") + (f"Last leg by truck from {r['truck']}. " if r["truck"] else "")
                                + f"Use /claim {r['awb']} to hold it for your next flight.",
                    "cargo": r["commodity"], "payload_lbs": r["gross_weight_lbs"], "distance_nm": 0, "block_min": 0, "aircraft": [],
                    "origin": _place({"icao": r["current_station"], "city": (C.get("AIRPORTS", {}).get(r["current_station"]) or {}).get("city")}),
                    "destination": _place({"icao": r["destination"], "city": (C.get("AIRPORTS", {}).get(r["destination"]) or {}).get("city")}),
                    "deliver_by": r["deadline"], "expires": None, "created": r["created_at"], "pieces": r["pieces"], "season": r["season"]})
    return out


@bp.post("/api/bot/claim")
def bot_claim():
    """/claim 901-1000034 in Discord: hold that freight for the linked pilot's next flight."""
    b = request.json or {}
    did, awb = str(b.get("discord_id") or ""), str(b.get("awb") or "").strip().upper().replace(" ", "")
    with C["db"]() as con:
        p = con.execute("SELECT id, name FROM pilots WHERE discord_id=?", (did,)).fetchone() if did else None
        if not p:
            return jsonify({"error": "Link your PAC pilot first: use /link with the code from Settings on the website."}), 404
        row = con.execute("SELECT id, commodity, current_station, destination FROM cargo_shipments WHERE awb=?", (awb,)).fetchone()
        if not row:
            return jsonify({"error": f"No PAC shipment {awb}. Check the air waybill number (like 901-10000034)."}), 404
        try:
            r = C["cargo_network"].claim(con, row["id"], p["id"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "pilot": p["name"], "awb": awb, "commodity": row["commodity"], "station": row["current_station"],
                    "destination": row["destination"], "until": r["until"]})


@bp.get("/api/bot/roster")
def bot_roster():
    """Linked pilots with the roles they should have."""
    va = C["va"]
    out = []
    with C["db"]() as con:
        rows = [dict(r) for r in con.execute("SELECT id, name, discord_id, staff, status FROM pilots WHERE discord_id IS NOT NULL")]
    for p in rows:
        active = p.get("status") not in ("Suspended", "Removed")
        out.append({"pilot_id": p["id"], "name": p["name"], "discord_id": p["discord_id"], "active": active,
                    "staff": bool(p.get("staff")), "rank": va.career(p["id"])["rank"] if active else None})
    return jsonify({"pilots": out})


@bp.post("/api/bot/link")
def bot_link():
    b = request.json or {}
    code = str(b.get("code") or "").strip().upper()
    if code and not code.startswith("PAC-"):
        code = "PAC-" + code
    did, dname = str(b.get("discord_id") or ""), str(b.get("discord_name") or "")[:80]
    if not did.isdigit():
        return jsonify({"error": "Missing Discord account."}), 400
    with C["db"]() as con:
        r = con.execute("SELECT pilot_id FROM discord_codes WHERE code=? AND expires>?", (code, time.time())).fetchone()
        if not r:
            return jsonify({"error": "That code isn't valid or has expired. Get a new one from Settings on pac-va.com."}), 400
        pid = r["pilot_id"]
        con.execute("UPDATE pilots SET discord_id=NULL, discord_name=NULL WHERE discord_id=? AND id!=?", (did, pid))
        con.execute("UPDATE pilots SET discord_id=?, discord_name=? WHERE id=?", (did, dname, pid))
        con.execute("DELETE FROM discord_codes WHERE code=?", (code,))
        p = _pilot(con, pid)
    return jsonify({"ok": True, "pilot_id": pid, "name": p["name"], "rank": C["va"].career(pid)["rank"], "staff": bool(p.get("staff"))})


@bp.post("/api/bot/unlink")
def bot_unlink():
    did = str((request.json or {}).get("discord_id") or "")
    with C["db"]() as con:
        r = con.execute("SELECT id FROM pilots WHERE discord_id=?", (did,)).fetchone()
        con.execute("UPDATE pilots SET discord_id=NULL, discord_name=NULL WHERE discord_id=?", (did,))
    return jsonify({"ok": bool(r), "pilot_id": r["id"] if r else None})


def _pilot_card(pid):
    va = C["va"]
    with C["db"]() as con:
        p = con.execute("SELECT id, name, hub, status, joined FROM pilots WHERE id=?", (pid,)).fetchone()
        if not p or p["status"] in ("Removed",):
            return None
        last = con.execute("""SELECT flight_number, dep, arr, aircraft, filed_at, grade FROM pireps WHERE pilot_id=? AND demo=0
            AND review_status='Accepted' ORDER BY filed_at DESC LIMIT 1""", (pid,)).fetchone()
    car = va.career(pid)
    return {"pilot_id": p["id"], "name": p["name"], "rank": car["rank"], "hours": car["hours"], "flights": car["flights"],
            "avg_score": car.get("avg_score"), "base": p["hub"], "location": va.pilot_location(pid),
            "joined": p["joined"], "last": dict(last) if last else None}


@bp.get("/api/bot/pilot")
def bot_pilot():
    q = str(request.args.get("q") or "").strip()
    with C["db"]() as con:
        if q.isdigit() and len(q) > 12:                 # a Discord user id
            r = con.execute("SELECT id FROM pilots WHERE discord_id=?", (q,)).fetchone()
        else:
            q2 = q.upper()
            if q2.isdigit():
                q2 = "PAC" + q2.zfill(4)
            r = con.execute("SELECT id FROM pilots WHERE upper(id)=? OR lower(name)=lower(?)", (q2, q)).fetchone()
    card = _pilot_card(r["id"]) if r else None
    return (jsonify(card), 200) if card else (jsonify({"error": "No PAC pilot found."}), 404)


@bp.get("/api/bot/live")
def bot_live():
    return jsonify({"flights": C["live_flights"](True)})


@bp.get("/api/bot/recent")
def bot_recent():
    with C["db"]() as con:
        rows = [dict(r) for r in con.execute("""SELECT p.flight_number, p.dep, p.arr, p.aircraft, p.filed_at, p.grade, p.landing_rate,
            p.pilot_id, r.name AS pilot FROM pireps p LEFT JOIN pilots r ON r.id=p.pilot_id WHERE p.demo=0 AND p.review_status='Accepted'
            ORDER BY p.filed_at DESC LIMIT 8""")]
    for x in rows:
        x["aircraft"] = C["FLEET"].get(x["aircraft"], {}).get("icao") or x["aircraft"]
    return jsonify({"flights": rows})


# ---------------------------------------------------------------- weekly recap (posted by the bot every Monday)
RECAP_HOUR_UTC = 14            # Monday 14:00 UTC: 9 AM in Cincinnati in winter, 10 AM in summer


def week_bounds(now=None):
    """The last full week, Monday 00:00 UTC to Monday 00:00 UTC, and its key (the Monday it started)."""
    import datetime as dt
    t = dt.datetime.fromtimestamp(now or time.time(), dt.timezone.utc)
    this_monday = (t - dt.timedelta(days=t.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = this_monday - dt.timedelta(days=7)
    return start.timestamp(), this_monday.timestamp(), start.date().isoformat()


def weekly_recap(now=None):
    start, end, key = week_bounds(now)
    base = ("FROM pireps p LEFT JOIN pilots r ON r.id=p.pilot_id WHERE p.demo=0 AND p.review_status='Accepted' "
            "AND p.filed_at>=? AND p.filed_at<?")
    with C["db"]() as con:
        tot = con.execute(f"SELECT COUNT(*) n, COALESCE(SUM(p.block_min),0)/60.0 h, COALESCE(SUM(CASE WHEN p.status!='Failed' "
                          f"THEN p.payload_lbs ELSE 0 END),0) lbs, COUNT(DISTINCT p.pilot_id) pilots {base}", (start, end)).fetchone()
        landing = con.execute(f"SELECT p.pilot_id, r.name pilot, r.discord_id, p.landing_rate, p.flight_number, p.arr {base} "
                              "AND p.landing_rate IS NOT NULL AND p.status!='Failed' AND COALESCE(p.bonus_points,0)>=0 "
                              "ORDER BY p.landing_rate DESC LIMIT 1", (start, end)).fetchone()
        hours = con.execute(f"SELECT p.pilot_id, r.name pilot, r.discord_id, SUM(p.block_min)/60.0 hours, COUNT(*) flights {base} "
                            "GROUP BY p.pilot_id ORDER BY hours DESC LIMIT 3", (start, end)).fetchall()
        newbies = con.execute("SELECT id pilot_id, name pilot, discord_id FROM pilots WHERE joined>=? AND joined<? ORDER BY joined",
                              (start, end)).fetchall()
        promos = []
        for r in con.execute("SELECT data FROM bot_events WHERE kind='promotion' AND time>=? AND time<? ORDER BY id", (start, end)):
            d = json.loads(r["data"])
            promos = [x for x in promos if x["pilot_id"] != d["pilot_id"]] + [d]     # the latest rank, once per pilot
    return {"week": key, "start": start, "end": end, "posted": C["settings"]().get("discord_recap_last") == key,
            "flights": tot["n"], "hours": round(tot["h"], 1), "cargo_lbs": int(tot["lbs"] or 0), "pilots": tot["pilots"],
            "top_landing": dict(landing) if landing else None, "top_hours": [dict(x) | {"hours": round(x["hours"], 1)} for x in hours],
            "new_pilots": [dict(x) for x in newbies], "promotions": promos,
            "site": (C["va"].site().get("public_url") or "https://pac-va.com").rstrip("/") or "https://pac-va.com"}


@bp.get("/api/bot/weekly")
def bot_weekly():
    st = C["settings"]()
    out = weekly_recap()
    out["enabled"] = bool(st.get("discord_recap_enabled", True))
    out["hour_utc"] = RECAP_HOUR_UTC
    return jsonify(out)


@bp.post("/api/bot/weekly/posted")
def bot_weekly_posted():
    week = str((request.json or {}).get("week") or "")
    st = C["settings"]()
    st["discord_recap_last"] = week
    C["save_settings"](st)
    return jsonify({"ok": True})


@bp.get("/api/staff/weekly-recap")
def staff_weekly_preview():
    """Staff › Site and rules › Discord bot: what the bot will post (or posted) for last week."""
    return jsonify(weekly_recap())


@bp.get("/api/staff/discord-bot")
def staff_bot_status():
    """For the staff page: is the bot service collecting events?"""
    last = _seen["poll"]
    with C["db"]() as con:
        linked = con.execute("SELECT COUNT(*) FROM pilots WHERE discord_id IS NOT NULL").fetchone()[0]
    return jsonify({"enabled": enabled(), "online": bool(last and time.time() - last < 30), "last_seen": last or None,
                    "linked": linked})


# ---------------------------------------------------------------- reminders: next flight due
@bp.get("/api/bot/activity")
def bot_activity():
    """Pilots to remind by DM that their next flight is due soon."""
    import activity
    st = C["settings"]()
    return jsonify({"reminders": activity.reminders_due(), "site": (C["va"].site().get("public_url") or "https://pac-va.com").rstrip("/") or "https://pac-va.com",
                    "enabled": bool(st.get("discord_activity_dm", True))})


@bp.post("/api/bot/activity/reminded")
def bot_activity_reminded():
    import activity
    activity.mark_reminded((request.json or {}).get("items") or [])
    return jsonify({"ok": True})
