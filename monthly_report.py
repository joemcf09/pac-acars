"""The monthly pilot report: on the 1st of each month every active pilot gets an email about last month.

Three versions, by what the pilot did:
  * flew last month: their flights, hours, cargo, best landing, average score and earnings, plus PAC's month
  * has never flown: a friendly first-flight nudge with the three steps to get going
  * flew before but not last month: what they're missing, and how to get back in
Each pilot gets one report per month (recorded, so a restart never sends twice). Pilots can turn it off with the link
at the bottom of the email."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html
import json
import time

SEND_DAYS = 3              # sent on the 1st (or within the first 3 days, if the site was down then)


def migrate(con):
    con.execute("CREATE TABLE IF NOT EXISTS monthly_reports (pilot_id TEXT, month TEXT, sent_at REAL, kind TEXT, PRIMARY KEY (pilot_id, month))")


def _month_bounds(month):
    y, m = map(int, month.split("-"))
    a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    b = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc)
    return a.timestamp(), b.timestamp(), a.strftime("%B %Y")


def last_month(now=None):
    d = dt.datetime.fromtimestamp(now or time.time(), dt.timezone.utc).replace(day=1) - dt.timedelta(days=1)
    return d.strftime("%Y-%m")


def unsub_token(secret, pid):
    return hmac.new(str(secret).encode(), f"monthly|{pid}".encode(), hashlib.sha256).hexdigest()[:24]


def stats(con, pid, month):
    a, b, _ = _month_bounds(month)
    r = con.execute("""SELECT COUNT(*), COALESCE(SUM(block_min),0), COALESCE(SUM(payload_lbs),0), MAX(landing_rate), AVG(score),
            COALESCE(SUM(points),0) FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted' AND filed_at>=? AND filed_at<?""",
                    (pid, a, b)).fetchone()
    earned = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id=? AND amount>0 AND time>=? AND time<?", (pid, a, b)).fetchone()[0]
    ever = con.execute("SELECT COUNT(*) FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted'", (pid,)).fetchone()[0]
    routes = [f"{x[0]}–{x[1]}" for x in con.execute("""SELECT dep, arr FROM pireps WHERE pilot_id=? AND demo=0 AND review_status='Accepted'
            AND filed_at>=? AND filed_at<? ORDER BY filed_at""", (pid, a, b))]
    return {"flights": r[0], "hours": round(r[1] / 60, 1), "cargo_lbs": int(r[2] or 0), "best_landing": r[3], "avg_score": round(r[4]) if r[4] else None,
            "points": int(r[5] or 0), "earned": round(earned or 0), "ever": ever, "routes": routes}


def company_month(con, month):
    a, b, _ = _month_bounds(month)
    r = con.execute("""SELECT COUNT(*), COUNT(DISTINCT pilot_id), COALESCE(SUM(payload_lbs),0) FROM pireps WHERE demo=0 AND review_status='Accepted'
            AND filed_at>=? AND filed_at<?""", (a, b)).fetchone()
    return {"flights": r[0], "pilots": r[1], "cargo_lbs": int(r[2] or 0)}


def build(con, pid, name, month, site_url, unsub_url, now=None):
    """(kind, subject, text, html) for one pilot."""
    s, co = stats(con, pid, month), company_month(con, month)
    _, _, label = _month_bounds(month)
    first = (name or "Captain").split()[0]
    site = (site_url or "").rstrip("/")
    lines, kind = [], "flew"
    if s["flights"]:
        subject = f"Your PAC {label}: {s['flights']} flight{'s' * (s['flights'] != 1)}, {s['hours']} hours"
        lines = [f"Hi {first},", "", f"Here's your {label} with Pagani Air Cargo.", "",
                 f"  Flights        {s['flights']}", f"  Block hours    {s['hours']}", f"  Cargo moved    {s['cargo_lbs']:,} lb"]
        if s["best_landing"] is not None:
            lines.append(f"  Best landing   {s['best_landing']:.0f} fpm")
        if s["avg_score"] is not None:
            lines.append(f"  Average score  {s['avg_score']}")
        lines += [f"  Points         {s['points']:,}", f"  Earned         ${s['earned']:,}", ""]
        if s["routes"]:
            lines += ["Where you flew: " + ", ".join(s["routes"][:12]) + (" …" if len(s["routes"]) > 12 else ""), ""]
    elif not s["ever"]:
        kind = "first"
        subject = "Your first PAC flight is waiting"
        lines = [f"Hi {first},", "", "You're on the PAC roster, but you haven't flown your first flight yet. Here's how to get going:", "",
                 "  1. Sign in and open the First-flight guide on your Dashboard.",
                 "  2. Pick a mission from your current station on the Missions board.",
                 "  3. Start PAC ACARS, fly it, and your PIREP files itself at the gate.", "",
                 "Stuck on anything? Ask in #pilot-help on Discord. Someone will help you.", ""]
    else:
        kind = "lapsed"
        subject = f"We missed you in {label}"
        lines = [f"Hi {first},", "", f"You didn't fly with PAC in {label}. Your aircraft and missions are waiting.", "",
                 "  • Check the Missions board for freight waiting at your station.",
                 "  • Campaigns and events pay extra right now.", ""]
    pl = lambda n, w: f"{n} {w}{'s' * (n != 1)}"
    lines += [f"PAC in {label}: {pl(co['flights'], 'flight')} by {pl(co['pilots'], 'pilot')}, {co['cargo_lbs']:,} lb of cargo.", "",
              f"Fly safe,", "PAC Operations Control", "", site or "", "",
              f"Don't want these monthly emails? {unsub_url}"]
    text = "\n".join(lines)
    body = "".join(f"<p style='margin:0 0 4px;white-space:pre-wrap;font-family:{'monospace' if l.startswith('  ') else 'Arial,sans-serif'}'>{html.escape(l) or '&nbsp;'}</p>" for l in lines[:-1])
    htm = (f"<div style='max-width:560px;margin:auto;font-size:15px;color:#1E2126'><div style='background:#c80000;color:#fff;padding:14px 18px;"
           f"font:800 18px Arial,sans-serif'>PAC · {html.escape(label)}</div><div style='padding:18px'>{body}"
           f"<p style='margin-top:18px'><a href='{html.escape(site)}' style='background:#c80000;color:#fff;padding:10px 16px;text-decoration:none;"
           f"font-weight:700;border-radius:4px'>Open PAC</a></p><p style='font-size:12px;color:#5E6470;margin-top:24px'>"
           f"<a href='{html.escape(unsub_url)}' style='color:#5E6470'>Turn off monthly emails</a></p></div></div>")
    return kind, subject, text, htm


def due(con, now=None):
    """The (pilot id, name, email) still waiting for last month's report, once it's the 1st or later."""
    now = now or time.time()
    migrate(con)
    month = last_month(now)
    rows = con.execute("""SELECT id, name, email, prefs FROM pilots WHERE COALESCE(status,'Active')='Active' AND email LIKE '%@%'
            AND id NOT IN (SELECT pilot_id FROM monthly_reports WHERE month=?)""", (month,)).fetchall()
    out = []
    for pid, name, email, prefs in rows:
        try:
            p = json.loads(prefs or "{}")
        except ValueError:
            p = {}
        if p.get("email_monthly") is False:
            continue
        out.append((pid, name, email))
    return month, out


def _site(st, fallback=""):
    import auth
    return auth.site_address(st.get("public_url") or fallback or "https://pac-va.com")


def tick(con, st, secret, now=None):
    """Sends whatever's due. Uses PAC's email account; does nothing if email isn't set up."""
    import mailer
    if not mailer.config_ready(st):
        return 0
    if dt.datetime.fromtimestamp(now or time.time(), dt.timezone.utc).day > SEND_DAYS:
        return 0           # only in the first days of the month: a mid-month deploy never mails last month's report late
    month, todo = due(con, now)
    site = _site(st)
    sent = 0
    for pid, name, email in todo[:40]:          # a few at a time, so a big roster never floods the mail account
        unsub = f"{site}/unsubscribe/monthly?p={pid}&t={unsub_token(secret, pid)}"
        kind, subject, text, htm = build(con, pid, name, month, site, unsub, now)
        con.execute("INSERT OR IGNORE INTO monthly_reports (pilot_id, month, sent_at, kind) VALUES (?,?,?,?)", (pid, month, time.time(), kind))
        mailer.send(st, email, subject, text, htm)
        sent += 1
    return sent


def register(app, g):
    from flask import jsonify, request

    @app.get("/unsubscribe/monthly")
    def monthly_unsub():
        pid, tok = request.args.get("p", ""), request.args.get("t", "")
        if not pid or not hmac.compare_digest(tok, unsub_token(app.secret_key, pid)):
            return "That link isn't valid.", 400
        with g["db"]() as con:
            r = con.execute("SELECT prefs FROM pilots WHERE id=?", (pid,)).fetchone()
            if r:
                p = json.loads(r[0] or "{}")
                p["email_monthly"] = False
                con.execute("UPDATE pilots SET prefs=? WHERE id=?", (json.dumps(p), pid))
        return ("<p style='font:16px Arial;margin:40px auto;max-width:480px'>Done. You won't get PAC's monthly report emails any more. "
                "You can turn them back on any time in your profile settings.</p>")

    @app.get("/api/staff/monthly-report/preview")
    def monthly_preview():
        pid = (request.args.get("pilot") or g["va"].current_pilot_id()).upper()
        with g["db"]() as con:
            r = con.execute("SELECT name FROM pilots WHERE id=?", (pid,)).fetchone()
            if not r:
                return jsonify({"error": "No such pilot."}), 404
            month = request.args.get("month") or last_month()
            site = _site(g["settings"](), request.host_url)
            kind, subject, text, htm = build(con, pid, r[0], month, site, f"{site}/unsubscribe/monthly?p={pid}&t={unsub_token(app.secret_key, pid)}")
        if request.args.get("format") != "json":
            return htm                      # the email exactly as it looks in an inbox
        return jsonify({"pilot": pid, "month": month, "kind": kind, "subject": subject, "text": text})

    @app.get("/api/staff/monthly-report/send-test")
    def monthly_send_test():
        """Sends one pilot's report to the signed-in staff member's own email, marked TEST. Records nothing."""
        import mailer
        me = g["va"].current_pilot_id()
        pid = (request.args.get("pilot") or me).upper()
        st = g["settings"]()
        if not mailer.config_ready(st):
            return "PAC's email account isn't set up (Staff → Settings → Email).", 400
        with g["db"]() as con:
            r = con.execute("SELECT name FROM pilots WHERE id=?", (pid,)).fetchone()
            to = request.args.get("to") or (con.execute("SELECT email FROM pilots WHERE id=?", (me,)).fetchone() or [""])[0]
            if not r:
                return "No such pilot.", 404
            if not mailer.valid_email(to):
                return "Your own pilot profile has no email address. Add &to=you@example.com to the link to choose where the test goes.", 400
            month = request.args.get("month") or last_month()
            site = _site(st, request.host_url)
            kind, subject, text, htm = build(con, pid, r[0], month, site, f"{site}/unsubscribe/monthly?p={pid}&t={unsub_token(app.secret_key, pid)}")
        ok, err = mailer.send(st, to, "[TEST] " + subject, text, htm, wait=True)
        return (f"Sent a test of {pid}'s {month} report to {to}. Check your inbox (and spam)." if ok else f"It couldn't be sent: {err}"), (200 if ok else 502)
