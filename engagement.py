"""Pilot engagement: timely nudges so new sign-ups fly their first flight and lapsed pilots come back.

The monthly report (monthly_report.py) already emails everyone on the 1st, but a pilot who joins on the 5th waits
most of a month for any contact -- long enough to drift off. This fills that gap with prompt, capped reminders:

  * NEVER FLOWN  -- a pilot with no (non-rejected) PIREP gets a gentle nudge 3, 7 and 14 days after joining, then
                    stops and lets the monthly report take over.
  * LAPSED       -- a pilot who flew before but has gone quiet gets one nudge at 30 days since their last flight and
                    one more at 60, then stops.

Each nudge goes out by email (always) and, for pilots who linked Discord, by a short DM (sent by the bot). Every
nudge is recorded per channel so a restart never sends it twice, and only the *highest* step currently due is sent,
so turning the feature on with an old roster sends each pilot one message, not a backlog of three. Pilots on leave,
Inactive or opted out are left alone, and every email carries an unsubscribe link.

Nothing here ever blocks a flight or changes a pilot's standing; it only sends reminders and powers the staff panel.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html
import json
import time

DAY = 86400
NEVER_STEPS = (3, 7, 14)          # days after joining
LAPSE_STEPS = (30, 60)            # days since last flight
MAX_PER_TICK = 40                 # a few at a time, so a big roster never floods the mail account


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS engagement_nudges (pilot_id TEXT, tag TEXT, channel TEXT, sent_at REAL,
                   PRIMARY KEY (pilot_id, tag, channel))""")
    con.execute("CREATE TABLE IF NOT EXISTS engagement_meta (k TEXT PRIMARY KEY, v TEXT)")
    if not con.execute("SELECT 1 FROM engagement_meta WHERE k='dedup_v1'").fetchone():
        _dedup_once(con)      # one-time: drop the redundant superseded rows an earlier build recorded (see _record)
        con.execute("INSERT OR IGNORE INTO engagement_meta (k, v) VALUES ('dedup_v1', ?)", (str(time.time()),))


def _dedup_once(con):
    """Keep only the highest step actually sent per pilot/channel/family; the lower rows were never real sends."""
    best = {}
    for rid, pid, tag, ch in con.execute("SELECT rowid, pilot_id, tag, channel FROM engagement_nudges"):
        fam = "new" if str(tag).startswith("new") else "lapse"
        try:
            step = int(str(tag)[len(fam):])
        except ValueError:
            continue
        key = (pid, ch, fam)
        if key not in best or step > best[key][0]:
            best[key] = (step, rid)
    keep = {v[1] for v in best.values()}
    if keep:
        con.execute("DELETE FROM engagement_nudges WHERE rowid NOT IN (%s)" % ",".join("?" * len(keep)), tuple(keep))


# ---------------------------------------------------------------- tokens (unsubscribe)
def unsub_token(secret, pid):
    return hmac.new(str(secret).encode(), f"reminders|{pid}".encode(), hashlib.sha256).hexdigest()[:24]


# ---------------------------------------------------------------- classification
def _prefs(row):
    try:
        return json.loads(row["prefs"] or "{}")
    except (ValueError, TypeError):
        return {}


def _on_leave(prefs, now):
    lv = prefs.get("leave")
    return bool(lv and now < lv.get("until", 0))


def _due_tag(category, age_days):
    steps = NEVER_STEPS if category == "never" else LAPSE_STEPS
    reached = [s for s in steps if age_days >= s]
    return f"{'new' if category == 'never' else 'lapse'}{max(reached)}" if reached else None


def candidates(con, now=None):
    """Active pilots who are never-flown or lapsed, each with the single nudge tag currently due (or None).
    Returns dicts: pilot_id, name, email, discord_id, prefs, category, tag, age_days, last_flight, joined."""
    now = now or time.time()
    migrate(con)
    out = []
    for row in con.execute("SELECT id, name, email, discord_id, prefs, status, joined FROM pilots WHERE COALESCE(status,'Active')='Active'"):
        prefs = _prefs(row)
        if _on_leave(prefs, now):
            continue
        last = con.execute("""SELECT MAX(filed_at) FROM pireps WHERE pilot_id=? AND COALESCE(demo,0)=0
                              AND COALESCE(review_status,'') != 'Rejected'""", (row["id"],)).fetchone()[0]
        if last:
            category, since = "lapsed", (now - last) / DAY
        else:
            category, since = "never", (now - (row["joined"] or now)) / DAY
        tag = _due_tag(category, since)
        if not tag:
            continue
        out.append({"pilot_id": row["id"], "name": row["name"] or "Captain", "email": row["email"],
                    "discord_id": row["discord_id"], "prefs": prefs, "category": category, "tag": tag,
                    "age_days": int(since), "last_flight": last, "joined": row["joined"]})
    return out


def _already(con, pid, tag, channel):
    return con.execute("SELECT 1 FROM engagement_nudges WHERE pilot_id=? AND tag=? AND channel=?",
                       (pid, tag, channel)).fetchone() is not None


def _record(con, pid, tag, channel, now=None):
    """Record this nudge as sent on this channel. Only the step actually sent is stored, so the count stays truthful.
    A backlog never drips because candidates() always offers the single highest step due, never the lower ones."""
    now = now or time.time()
    con.execute("INSERT OR IGNORE INTO engagement_nudges (pilot_id, tag, channel, sent_at) VALUES (?,?,?,?)",
                (pid, tag, channel, now))


# ---------------------------------------------------------------- email
def _site(st, fallback=""):
    import auth
    return auth.site_address(st.get("public_url") or fallback or "https://pac-va.com")


def build_email(first, category, tag, site, unsub_url):
    """(subject, text, html) for one nudge. Tone escalates gently; nothing guilt-trips."""
    site = (site or "").rstrip("/")
    first = (first or "Captain").split()[0]
    if category == "never":
        body = {
            "new3": ("Your first PAC flight is waiting",
                     ["You're on the PAC roster and your first flight is ready whenever you are. Three steps to get going:", "",
                      "  1. Sign in and open the First-flight guide on your Dashboard.",
                      "  2. Pick a mission from your station on the Missions board.",
                      "  3. Start PAC ACARS, fly it, and your PIREP files itself at the gate."]),
            "new7": ("Still haven't flown? Here's a hand",
                     ["Your first PAC flight is still waiting, and that's alright -- the first one is the biggest step.",
                      "If anything's in the way (planning, the ACARS app, picking an aircraft), ask in #pilot-help on Discord and someone will walk you through it.", "",
                      "When you're ready, the First-flight guide on your Dashboard lays out every step."]),
            "new14": ("Your aircraft is still waiting at PAC",
                      ["It's been two weeks and we'd love to see you fly your first PAC leg.",
                       "Everything's ready for you: pick a short mission from your station, start PAC ACARS, and you're flying.", "",
                       "After this we'll ease off -- you'll just get our monthly note. Hope to see you on the board soon."]),
        }[tag]
    else:
        body = {
            "lapse30": ("We miss you at PAC",
                        ["It's been about a month since your last PAC flight. Your aircraft and missions are waiting whenever you want to get back in.", "",
                         "  - Check the Missions board for freight at your station.",
                         "  - Campaigns and events are paying extra right now."]),
            "lapse60": ("Your seat at PAC is still yours",
                        ["It's been a couple of months -- no pressure, just a note that your spot on the roster is still here.",
                         "Flying away for a while? You can take a leave of absence on your home page and the activity clock pauses until you're back.", "",
                         "Whenever you're ready, the Missions board is the place to start."]),
        }[tag]
    subject, lines = body
    lines = [f"Hi {first},", ""] + lines + ["", "Fly safe,", "PAC Operations Control", "", site or "", "",
                                            f"Don't want these reminders? {unsub_url}"]
    text = "\n".join(lines)
    inner = "".join(f"<p style='margin:0 0 4px;white-space:pre-wrap;font-family:{'monospace' if l.startswith('  ') else 'Arial,sans-serif'}'>"
                    f"{html.escape(l) or '&nbsp;'}</p>" for l in lines[:-1])
    htm = (f"<div style='max-width:560px;margin:auto;font-size:15px;color:#1E2126'>"
           f"<div style='background:#c80000;color:#fff;padding:14px 18px'>"
           f"<img src='{html.escape(site)}/static/pac-wordmark-white.png' alt='PAC' height='28' style='display:block;height:28px;border:0'></div>"
           f"<div style='padding:18px'>{inner}"
           f"<p style='margin-top:18px'><a href='{html.escape(site)}' style='background:#c80000;color:#fff;padding:10px 16px;"
           f"text-decoration:none;font-weight:700;border-radius:4px'>Open PAC</a></p>"
           f"<p style='font-size:12px;color:#5E6470;margin-top:24px'><a href='{html.escape(unsub_url)}' style='color:#5E6470'>"
           f"Turn off reminder emails</a></p></div></div>")
    return subject, text, htm


def build_dm(first, category, tag, site):
    """The short Discord DM for one nudge."""
    site = (site or "").rstrip("/")
    first = (first or "there").split()[0]
    msg = {
        "new3": f"Hi {first}, welcome to PAC! Your first flight is ready whenever you are -- open the First-flight guide on your Dashboard, "
                f"pick a short mission, and fly it. {site}/#missions",
        "new7": f"Hi {first}, still want to fly your first PAC leg? If anything's in the way, ask in #pilot-help and we'll help. "
                f"The board's here when you're ready: {site}/#missions",
        "new14": f"Hi {first}, your aircraft's still waiting at PAC. Pick a short mission from your station and you're flying: {site}/#missions",
        "lapse30": f"Hi {first}, it's been about a month -- we'd love to see you back. Missions and campaigns are waiting: {site}/#missions",
        "lapse60": f"Hi {first}, your seat at PAC is still yours. Back whenever you want: {site}/#missions "
                   f"(need a break? you can take a leave of absence on your home page).",
    }[tag]
    return msg


# ---------------------------------------------------------------- the email sender (daily)
def tick(con, st, secret, now=None):
    """Sends the due email nudges. Uses PAC's email account; does nothing if email isn't set up. DMs go via the bot."""
    import mailer
    if not mailer.config_ready(st):
        return 0
    now = now or time.time()
    site = _site(st)
    sent = 0
    for c in candidates(con, now):
        if sent >= MAX_PER_TICK:
            break
        if c["prefs"].get("email_reminders") is False or not mailer.valid_email(c["email"]):
            continue
        if _already(con, c["pilot_id"], c["tag"], "email"):
            continue
        unsub = f"{site}/unsubscribe/reminders?p={c['pilot_id']}&t={unsub_token(secret, c['pilot_id'])}"
        subject, text, htm = build_email(c["name"], c["category"], c["tag"], site, unsub)
        _record(con, c["pilot_id"], c["tag"], "email", now)
        mailer.send(st, c["email"], subject, text, htm)
        sent += 1
    return sent


# ---------------------------------------------------------------- Discord DMs (served to the bot)
def dm_due(con, site, now=None, limit=25):
    """DM items for the bot: pilots with a nudge due who linked Discord and didn't opt out. Mirrors activity reminders."""
    now = now or time.time()
    out = []
    for c in candidates(con, now):
        if len(out) >= limit:
            break
        if not c["discord_id"] or c["prefs"].get("dm_reminders") is False:
            continue
        if _already(con, c["pilot_id"], c["tag"], "dm"):
            continue
        out.append({"src": "engagement", "key": f"{c['pilot_id']}|{c['tag']}", "discord_id": c["discord_id"],
                    "text": build_dm(c["name"], c["category"], c["tag"], site)})
    return out


def mark_dmed(con, items, now=None):
    """The bot reports which engagement DMs it sent (or gave up on); record them so they never repeat."""
    now = now or time.time()
    for it in items or []:
        if it.get("src") != "engagement" or "|" not in str(it.get("key") or ""):
            continue
        pid, tag = it["key"].split("|", 1)
        _record(con, pid, tag, "dm", now)


# ---------------------------------------------------------------- staff panel data + manual nudge
def _flights(con, pid):
    return con.execute("""SELECT COUNT(*) FROM pireps WHERE pilot_id=? AND COALESCE(demo,0)=0
                          AND COALESCE(review_status,'') != 'Rejected'""", (pid,)).fetchone()[0]


def roster(con, hq_icao=None, now=None):
    """Segmented roster for the CEO desk: active / never-flown / lapsed, with join date, idle days, contact reach,
    whether we've nudged them, and whether they're sitting at HQ without flying."""
    now = now or time.time()
    migrate(con)
    seg = {"never": [], "lapsed": [], "active": []}
    for row in con.execute("""SELECT id, name, email, discord_id, prefs, status, joined, hub, location
                              FROM pilots WHERE COALESCE(status,'Active')='Active' ORDER BY joined"""):
        prefs = _prefs(row)
        last = con.execute("""SELECT MAX(filed_at) FROM pireps WHERE pilot_id=? AND COALESCE(demo,0)=0
                              AND COALESCE(review_status,'') != 'Rejected'""", (row["id"],)).fetchone()[0]
        flights = _flights(con, row["id"])
        nudges = con.execute("SELECT COUNT(DISTINCT tag) FROM engagement_nudges WHERE pilot_id=?", (row["id"],)).fetchone()[0]
        at_hq = bool(hq_icao and (row["location"] or row["hub"]) == hq_icao)
        info = {"pilot_id": row["id"], "name": row["name"], "joined": row["joined"], "flights": flights,
                "last_flight": last, "idle_days": int((now - last) / DAY) if last else None,
                "age_days": int((now - (row["joined"] or now)) / DAY), "has_email": bool(mailer_valid(row["email"])),
                "linked_discord": bool(row["discord_id"]), "nudges_sent": nudges, "at_hq": at_hq,
                "on_leave": _on_leave(prefs, now), "opted_out": prefs.get("email_reminders") is False}
        if _on_leave(prefs, now):
            continue
        if flights == 0:
            seg["never"].append(info)
        elif last and (now - last) / DAY >= LAPSE_STEPS[0]:
            seg["lapsed"].append(info)
        else:
            seg["active"].append(info)
    seg["never"].sort(key=lambda p: p["joined"] or 0)
    seg["lapsed"].sort(key=lambda p: p["last_flight"] or 0)
    return {"never": seg["never"], "lapsed": seg["lapsed"], "active_count": len(seg["active"]),
            "never_count": len(seg["never"]), "lapsed_count": len(seg["lapsed"]),
            "hq": hq_icao, "hq_idle_count": sum(1 for g in ("never", "lapsed") for p in seg[g] if p["at_hq"])}


def mailer_valid(addr):
    import mailer
    return mailer.valid_email(addr)


def pending_count(con, now=None):
    """How many pilots currently have a nudge due and unsent on any channel -- for the staff tab badge."""
    now = now or time.time()
    n = 0
    for c in candidates(con, now):
        email_due = c["prefs"].get("email_reminders") is not False and mailer_valid(c["email"]) and not _already(con, c["pilot_id"], c["tag"], "email")
        if email_due:
            n += 1
    return n


def send_manual(con, st, secret, pid, now=None):
    """Staff presses 'Send reminder': email the pilot's current-due nudge now (or a first-flight welcome if none is due
    yet), record it, and let the DM follow. Returns (ok, message)."""
    import mailer
    now = now or time.time()
    row = con.execute("SELECT id, name, email, prefs, status, joined FROM pilots WHERE id=?", (pid,)).fetchone()
    if not row:
        return False, "No such pilot."
    if not mailer.config_ready(st):
        return False, "PAC's email account isn't set up (Staff -> Site and rules -> Email)."
    if not mailer.valid_email(row["email"]):
        return False, "That pilot has no email address on file."
    prefs = _prefs(row)
    last = con.execute("""SELECT MAX(filed_at) FROM pireps WHERE pilot_id=? AND COALESCE(demo,0)=0
                          AND COALESCE(review_status,'') != 'Rejected'""", (pid,)).fetchone()[0]
    if last:
        category, since = "lapsed", (now - last) / DAY
    else:
        category, since = "never", (now - (row["joined"] or now)) / DAY
    tag = _due_tag(category, since) or ("new3" if category == "never" else "lapse30")   # welcome even a brand-new pilot
    site = _site(st)
    unsub = f"{site}/unsubscribe/reminders?p={pid}&t={unsub_token(secret, pid)}"
    subject, text, htm = build_email(row["name"], category, tag, site, unsub)
    ok, err = mailer.send(st, row["email"], subject, text, htm, wait=True)
    if ok:
        _record(con, pid, tag, "email", now)
        return True, f"Reminder emailed to {row['name']} ({row['email']})."
    return False, f"It couldn't be sent: {err}"


# ---------------------------------------------------------------- routes
def register(app, g):
    from flask import jsonify, request

    @app.get("/unsubscribe/reminders")
    def reminders_unsub():
        pid, tok = request.args.get("p", ""), request.args.get("t", "")
        if not pid or not hmac.compare_digest(tok, unsub_token(app.secret_key, pid)):
            return "That link isn't valid.", 400
        with g["db"]() as con:
            r = con.execute("SELECT prefs FROM pilots WHERE id=?", (pid,)).fetchone()
            if r:
                p = json.loads(r[0] or "{}")
                p["email_reminders"] = False
                con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(p), pid))
        return ("<p style='font:16px Arial;margin:40px auto;max-width:480px'>Done. You won't get PAC reminder emails any more. "
                "You can turn them back on in your profile settings, and this doesn't affect the monthly report.</p>")

    @app.get("/api/staff/engagement/roster")
    def engagement_roster():
        hq = None
        try:
            import hubs
            hq = hubs.hq_icao() if hasattr(hubs, "hq_icao") else (g["settings"]().get("hq") or "KCVG")
        except Exception:
            hq = g["settings"]().get("hq") or "KCVG"
        with g["db"]() as con:
            data = roster(con, hq)
        return jsonify(data)

    @app.post("/api/staff/engagement/nudge")
    def engagement_nudge():
        pid = ((request.json or {}).get("pilot") or "").upper()
        if not pid:
            return jsonify({"error": "Which pilot?"}), 400
        with g["db"]() as con:
            ok, msg = send_manual(con, g["settings"](), app.secret_key, pid)
        return (jsonify({"ok": True, "message": msg}) if ok else (jsonify({"error": msg}), 400))
