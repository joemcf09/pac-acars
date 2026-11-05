"""Transfer hours: pilots ask for verified hours from other virtual airlines (or VATSIM/IVAO) to count towards rank.

The rules (also in the handbook):
  * up to 3 sources per request, each with a logbook link and a screenshot showing the pilot's name or ID with the
    hours (many VA systems need a login, so staff may go by the screenshot or ask for a screen share)
  * hours at different VAs add up; network hours (VATSIM/IVAO) don't stack on top of VA hours, because they're
    usually the same flights, so the larger of the two totals is used
  * PAC credits half the verified hours, at most 75 hours (so transfers can take a pilot to Senior First Officer,
    never to Captain: Captain is earned at PAC)
  * one request and one appeal per pilot, within 60 days of joining (or of the program opening, for pilots who
    joined before it)
  * transfer hours count towards rank only: no pay, points, wallet money or leaderboard hours, and the checkride,
    average score and type ratings are still required

Proof screenshots are private: they live in data/transfers (not the public gallery) and only the pilot and staff
can open them.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid

from flask import Blueprint, jsonify, request, send_from_directory

bp = Blueprint("transfers", __name__)
C = {}

CAP_HOURS = 75.0          # the most PAC credits from transfers
CREDIT_SHARE = 0.5        # half of the verified hours
MAX_SOURCES = 3
MAX_REQUESTS = 2          # the request and one appeal
WINDOW_DAYS = 60
PROGRAM_OPENS = dt.datetime(2026, 11, 5, 5, 0, tzinfo=dt.timezone.utc).timestamp()   # midnight Nov 5, US Eastern
MAX_CLAIM = 50000         # hours; anything above is a typo
PROOF_MAX_BYTES = 15 * 1024 * 1024
IMAGE_MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png", b"RIFF": "webp"}
KINDS = ("va", "network")


def init(ctx):
    C.update(ctx)
    with C["db"]() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS transfer_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT,
            submitted REAL, status TEXT DEFAULT 'Pending', sources TEXT, comment TEXT, credited REAL, note TEXT,
            reviewed_at REAL, reviewed_by TEXT, previous_hours REAL)""")
        con.execute("CREATE INDEX IF NOT EXISTS transfer_req_pilot ON transfer_requests(pilot_id, submitted)")


def _dir():
    d = C["DATA"] / "transfers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def credit_for(sources):
    """Hours PAC credits for a list of sources (each with kind and hours): VA hours add up, network hours don't stack
    on top of them (the larger total counts), then half, capped."""
    va = sum(float(s.get("hours") or 0) for s in sources if s.get("kind") != "network")
    net = sum(float(s.get("hours") or 0) for s in sources if s.get("kind") == "network")
    base = max(va, net)
    return round(min(CAP_HOURS, base * CREDIT_SHARE), 1), round(base, 1)


def _window(pilot):
    start = max(PROGRAM_OPENS, float(pilot.get("joined") or 0))
    return start + (WINDOW_DAYS + 1) * 86400 - 1   # to the end of the 60th day (Jan 4, 2027 for pilots who joined earlier)


def _rows(con, pid):
    rows = [dict(r) for r in con.execute("SELECT * FROM transfer_requests WHERE pilot_id=? ORDER BY submitted", (pid,))]
    for r in rows:
        r["sources"] = json.loads(r["sources"] or "[]")
    return rows


def _public(r, staff=False):
    out = {k: r.get(k) for k in ("id", "submitted", "status", "comment", "credited", "note", "reviewed_at")}
    out["sources"] = [{**{k: s.get(k) for k in ("kind", "name", "url", "hours", "verified", "approved")},
                       "proof": f"/api/transfers/{r['id']}/proof/{i}" if s.get("proof") else None}
                      for i, s in enumerate(r["sources"])]
    if staff:
        out.update(pilot_id=r.get("pilot_id"), reviewed_by=r.get("reviewed_by"), previous_hours=r.get("previous_hours"))
    return out


def status_for(con, pid):
    """What the pilot sees: their requests and whether they can send one now (and why not)."""
    p = con.execute("SELECT * FROM pilots WHERE id=?", (pid,)).fetchone()
    p = dict(p) if p else {}
    rows = _rows(con, pid)
    closes = _window(p)
    now = time.time()
    current = float(p.get("transfer_hours") or 0)
    why = None
    if any(r["status"] == "Pending" for r in rows):
        why = "Your request is with staff. You'll hear back by email and here."
    elif current > CAP_HOURS:
        why = "Your transfer hours were set by staff, above the 75-hour limit for requests, so there's nothing more to request."
    elif current >= CAP_HOURS:
        why = f"You already have the maximum {CAP_HOURS:g} transfer hours."
    elif len(rows) >= MAX_REQUESTS:
        why = "You've used your request and your appeal."
    elif now > closes:
        why = "The 60-day window for transfer requests has closed."
    return {"requests": [_public(r) for r in reversed(rows)], "can_request": why is None, "why_not": why,
            "is_appeal": bool(rows) and why is None, "closes": closes, "transfer_hours": current,
            "rules": {"cap": CAP_HOURS, "share": CREDIT_SHARE, "max_sources": MAX_SOURCES, "window_days": WINDOW_DAYS}}


def _pid():
    import auth
    return auth.current_id()


@bp.get("/api/transfers")
def my_transfers():
    pid = _pid()
    if not pid:
        return jsonify({"error": "Please sign in."}), 401
    with C["db"]() as con:
        return jsonify(status_for(con, pid))


def _clean_url(u):
    u = C["clean_text"](u, 300)
    if not re.match(r"^https?://[^\s/]+\.[^\s]+", u or ""):
        return None
    return u


def _save_proof(f):
    raw = f.stream.read(PROOF_MAX_BYTES + 1)
    if len(raw) > PROOF_MAX_BYTES:
        raise ValueError("Screenshots can be up to 15 MB each.")
    ext = next((e for m, e in IMAGE_MAGIC.items() if raw.startswith(m)), None)
    if not ext or (ext == "webp" and raw[8:12] != b"WEBP"):
        raise ValueError("Upload the screenshot as a JPG, PNG or WebP image.")
    name = f"{uuid.uuid4().hex}.{ext}"
    (_dir() / name).write_bytes(raw)
    return name


@bp.post("/api/transfers")
def submit():
    pid = _pid()
    if not pid:
        return jsonify({"error": "Please sign in."}), 401
    try:
        raw = json.loads(request.form.get("sources") or "[]")
    except ValueError:
        return jsonify({"error": "Something went wrong reading the form. Please try again."}), 400
    if not isinstance(raw, list) or not raw:
        return jsonify({"error": "Add at least one source."}), 400
    if len(raw) > MAX_SOURCES:
        return jsonify({"error": f"Up to {MAX_SOURCES} sources per request."}), 400
    ct = C["clean_text"]
    sources = []
    for i, s in enumerate(raw):
        s = s if isinstance(s, dict) else {}
        n = i + 1
        kind = s.get("kind") if s.get("kind") in KINDS else "va"
        name = ct(s.get("name"), 80)
        url = _clean_url(s.get("url"))
        try:
            hours = round(float(s.get("hours")), 1)
        except (TypeError, ValueError):
            hours = 0
        if not name:
            return jsonify({"error": f"Source {n}: enter the virtual airline or network name."}), 400
        if not url:
            return jsonify({"error": f"Source {n}: add the link to your logbook or profile page (starting with https://)."}), 400
        if not 0 < hours <= MAX_CLAIM:
            return jsonify({"error": f"Source {n}: enter the hours shown on that logbook."}), 400
        if not request.files.get(f"proof{i}"):
            return jsonify({"error": f"Source {n}: add a screenshot that shows your name or pilot ID and your hours."}), 400
        sources.append({"kind": kind, "name": name, "url": url, "hours": hours})
    with C["db"]() as con:
        st = status_for(con, pid)
        if not st["can_request"]:
            return jsonify({"error": st["why_not"]}), 400
        try:
            for i, s in enumerate(sources):
                s["proof"] = _save_proof(request.files[f"proof{i}"])
        except ValueError as e:
            for s in sources:
                if s.get("proof"):
                    (_dir() / s["proof"]).unlink(missing_ok=True)
            return jsonify({"error": str(e)}), 400
        con.execute("INSERT INTO transfer_requests (pilot_id, submitted, status, sources, comment) VALUES (?,?,?,?,?)",
                    (pid, time.time(), "Pending", json.dumps(sources), ct(request.form.get("comment"), 1000)))
        out = status_for(con, pid)
    return jsonify({"ok": True, **out})


@bp.get("/api/transfers/<int:rid>/proof/<int:i>")
def proof(rid, i):
    import auth
    pid = _pid()
    with C["db"]() as con:
        r = con.execute("SELECT pilot_id, sources FROM transfer_requests WHERE id=?", (rid,)).fetchone()
    if not r or not pid or (r["pilot_id"] != pid and not auth.is_staff()):
        return jsonify({"error": "Not found."}), 404
    srcs = json.loads(r["sources"] or "[]")
    if not 0 <= i < len(srcs) or not srcs[i].get("proof"):
        return jsonify({"error": "Not found."}), 404
    resp = send_from_directory(_dir(), srcs[i]["proof"], max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ---------------------------------------------------------------- staff
@bp.get("/api/staff/transfers")
def staff_list():
    with C["db"]() as con:
        rows = [dict(r) for r in con.execute(
            """SELECT t.*, p.name pilot_name, p.transfer_hours current_hours, p.joined FROM transfer_requests t
               LEFT JOIN pilots p ON p.id=t.pilot_id
               ORDER BY CASE t.status WHEN 'Pending' THEN 0 ELSE 1 END, t.submitted DESC LIMIT 200""")]
        earlier = {}
        for r in rows:
            earlier[r["pilot_id"]] = earlier.get(r["pilot_id"], 0) + 1
    out = []
    for r in rows:
        r["sources"] = json.loads(r["sources"] or "[]")
        o = _public(r, staff=True)
        o.update(pilot_name=r.get("pilot_name"), current_hours=r.get("current_hours") or 0, requests_by_pilot=earlier[r["pilot_id"]])
        out.append(o)
    return jsonify({"requests": out, "rules": {"cap": CAP_HOURS, "share": CREDIT_SHARE}})


def _notify(pid, subject, text):
    """Email the pilot when PAC's email is set up; quietly skipped otherwise (they also see it on Career)."""
    try:
        import mailer
        st = C["settings"]()
        with C["db"]() as con:
            r = con.execute("SELECT email FROM pilots WHERE id=?", (pid,)).fetchone()
        if r and mailer.config_ready(st) and mailer.valid_email(r["email"] or ""):
            mailer.send(st, r["email"], subject, text)
            return True
    except Exception:
        pass
    return False


@bp.post("/api/staff/transfers/<int:rid>")
def staff_decide(rid):
    import auth
    b = request.json or {}
    action = b.get("action")
    if action not in ("approve", "reject"):
        return jsonify({"error": "Choose approve or reject."}), 400
    note = C["clean_text"](b.get("note"), 600)
    with C["db"]() as con:
        r = con.execute("SELECT * FROM transfer_requests WHERE id=?", (rid,)).fetchone()
        if not r:
            return jsonify({"error": "That request isn't there any more."}), 404
        r = dict(r)
        if r["status"] != "Pending":
            return jsonify({"error": "This request has already been decided."}), 400
        sources = json.loads(r["sources"] or "[]")
        decisions = b.get("sources") or []
        for i, s in enumerate(sources):
            d = decisions[i] if i < len(decisions) and isinstance(decisions[i], dict) else {}
            ok = action == "approve" and bool(d.get("approved"))
            s["approved"] = ok
            try:
                v = round(float(d.get("verified")), 1) if d.get("verified") not in (None, "") else s["hours"]
            except (TypeError, ValueError):
                v = s["hours"]
            s["verified"] = max(0.0, min(v, MAX_CLAIM)) if ok else 0
        credit, base = credit_for([{"kind": s["kind"], "hours": s["verified"]} for s in sources if s["approved"]])
        if action == "approve" and credit <= 0:
            return jsonify({"error": "Tick at least one source as verified (with its hours), or reject the request."}), 400
        if action == "reject" and len(note) < 5:
            return jsonify({"error": "Add a short note for the pilot saying why (5+ characters)."}), 400
        p = con.execute("SELECT transfer_hours FROM pilots WHERE id=?", (r["pilot_id"],)).fetchone()
        prev = float((p["transfer_hours"] if p else 0) or 0)
        status = "Approved" if action == "approve" else "Rejected"
        if action == "approve":
            # never lowers hours staff set by hand, and never goes past the cap through a request
            new = max(prev, credit)
            con.execute("UPDATE pilots SET transfer_hours=? WHERE id=?", (new, r["pilot_id"]))
        con.execute("""UPDATE transfer_requests SET status=?, sources=?, credited=?, note=?, reviewed_at=?, reviewed_by=?,
                       previous_hours=? WHERE id=?""",
                    (status, json.dumps(sources), credit if action == "approve" else 0, note, time.time(), auth.current_id(), prev, rid))
        appeal_left = con.execute("SELECT COUNT(*) FROM transfer_requests WHERE pilot_id=?", (r["pilot_id"],)).fetchone()[0] < MAX_REQUESTS
    if action == "approve":
        text = (f"Good news: PAC staff verified your transfer hours.\n\n"
                f"Verified hours: {base:g}\nCredited to your PAC career: {credit:g} hours "
                f"(half of verified hours, up to {CAP_HOURS:g}).\n\n"
                + (f"Staff note: {note}\n\n" if note else "")
                + "Transfer hours count towards rank. The checkride, your average score and type ratings still apply. "
                  "See Career on the PAC website for your new progress.\n\nPAC Operations Control")
        mailed = _notify(r["pilot_id"], "Your PAC transfer hours are approved", text)
    else:
        text = ("PAC staff reviewed your transfer hours request and couldn't verify it this time.\n\n"
                f"Reason: {note}\n\n"
                + ("You can appeal once from Career on the PAC website, within your 60-day window. "
                   "Fixing the reason above (for example a screenshot that shows your name or pilot ID with your hours) is usually enough.\n\n"
                   if appeal_left else "")
                + "PAC Operations Control")
        mailed = _notify(r["pilot_id"], "Your PAC transfer hours request", text)
    return jsonify({"ok": True, "status": status, "credited": credit if action == "approve" else 0, "mailed": mailed})
