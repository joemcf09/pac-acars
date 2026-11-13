"""Sign-in for the PAC website and the PAC ACARS app.

* Pilots sign in with their pilot ID and a password (stored only as a salted hash).
* The very first time, the founder chooses a password for their existing pilot record,
  so the logbook, career and settings stay exactly as they are.
* New pilots (and forgotten passwords) get a one-time link from staff to set a password.
* The ACARS app signs in once and keeps a key (only its hash is stored here).
* A gatekeeper checks every request: public pages for visitors, the rest for signed-in
  pilots, and Staff for staff accounts.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint("auth", __name__)
C = {}  # db, settings, founder_id: set by init()

MIN_PASSWORD = 8
SESSION_DAYS = 30
INVITE_DAYS = 7

# Requests anyone may make (the public pages: Home, Fleet, Handbook, applying, downloading PAC ACARS)
PUBLIC_GET = ("/api/group/", "/api/conflict-zones", "/api/bootstrap", "/api/va/home", "/api/va/board", "/api/fleet", "/api/news", "/api/gallery",
              "/api/profile/photo", "/api/acars/app/download", "/api/auth/", "/api/live",
              "/api/bot/",   # the Discord bot's own API checks its secret itself (botlink.py)
              "/api/partner-photos", "/api/partner-photo/", "/api/public/roster", "/api/public/group-flight", "/api/public/track/", "/api/public/network", "/healthz",
              "/api/group-flight.ics")   # credited Commons photos on landing cards
PUBLIC_POST = ("/api/applications", "/api/auth/setup", "/api/auth/login", "/api/auth/accept", "/api/auth/token", "/api/auth/logout", "/api/auth/badge/tap", "/api/auth/badge/forget",
               "/api/bot/link", "/api/bot/unlink", "/api/bot/weekly/posted", "/api/bot/activity/reminded", "/api/bot/claim")   # the bot API checks its own secret (botlink.py)
STAFF_PREFIXES = ("/api/staff/",)
STAFF_EXACT_POST = ("/api/fleet",)  # editing aircraft types and photos on the Fleet page

_attempts = {}  # sign-in attempts per address, to slow down password guessing


def init(ctx):
    C.update(ctx)
    C["db"]().close()  # opening the database prepares it (see migrate)


def migrate(con):
    """Sign-in columns and tables, added to any logbook that doesn't have them yet."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(pilots)")}
    if cols and "password_hash" not in cols:
        con.execute("ALTER TABLE pilots ADD COLUMN password_hash TEXT")
    if cols and "password_set" not in cols:
        con.execute("ALTER TABLE pilots ADD COLUMN password_set REAL")
    con.execute("""CREATE TABLE IF NOT EXISTS invites (token_hash TEXT PRIMARY KEY, pilot_id TEXT, created REAL, expires REAL,
        used REAL, purpose TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS badge_tokens (token_hash TEXT PRIMARY KEY, pilot_id TEXT, created REAL,
        last_used REAL, agent TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS api_keys (key_hash TEXT PRIMARY KEY, pilot_id TEXT, label TEXT, created REAL,
        last_used REAL)""")


def _hash_token(t):
    return hashlib.sha256(t.encode()).hexdigest()


def founder_id():
    return C["settings"]().get("pilot_id") or "PAC0001"


def setup_needed():
    """No pilot has a password yet: the site is being secured for the first time."""
    with C["db"]() as con:
        return not con.execute("SELECT 1 FROM pilots WHERE password_hash IS NOT NULL LIMIT 1").fetchone()


def pilot_row(pid):
    with C["db"]() as con:
        r = con.execute("SELECT * FROM pilots WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else None


def public_pilot(r):
    return {"id": r["id"], "name": r["name"], "staff": bool(r.get("staff")), "status": r.get("status")}


def current():
    """The signed-in pilot for this request (from the session, or an ACARS app key), or None."""
    if "pilot" in g.__dict__:
        return g.pilot
    g.pilot = None
    pid = session.get("pid")
    auth = request.headers.get("Authorization", "")
    if not pid and auth.startswith("Bearer "):
        kh = _hash_token(auth[7:].strip())
        with C["db"]() as con:
            k = con.execute("SELECT pilot_id FROM api_keys WHERE key_hash=?", (kh,)).fetchone()
            if k:
                pid = k["pilot_id"]
                con.execute("UPDATE api_keys SET last_used=? WHERE key_hash=?", (time.time(), kh))
    if pid:
        r = pilot_row(pid)
        if r and r.get("password_hash") and r.get("status") not in ("Suspended", "Removed"):
            g.pilot = r
        elif pid == session.get("pid"):
            session.clear()
    return g.pilot


def current_id():
    p = current()
    return p["id"] if p else None


def is_staff():
    p = current()
    return bool(p and p.get("staff"))


def gatekeeper():
    """Runs before every request."""
    path, method = request.path, request.method
    # Public handbook rules contain no pilot records or credentials.
    if path == "/api/va/config" and method == "GET":
        return None
    if not path.startswith("/api/") and path != "/dispatch":
        return None  # the pages and their files: the page itself asks visitors to sign in
    if path == "/dispatch":
        return None if current() else ("Sign in to see the dispatch release.", 401)
    if path.startswith("/api/group/") and method in ("GET", "OPTIONS"):
        return None  # the group hub feed checks its own key
    if method == "GET" and any(path == p or path.startswith(p.rstrip("/") + "/") or (p.endswith("/") and path.startswith(p))
                               for p in PUBLIC_GET):
        return None
    if method == "POST" and path in PUBLIC_POST:
        return None
    p = current()
    if not p:
        return jsonify({"error": "Please sign in.", "signin": True}), 401
    if path.startswith(STAFF_PREFIXES) or (method != "GET" and any(path == x or path.startswith(x + "/") for x in STAFF_EXACT_POST)):
        if not p.get("staff"):
            return jsonify({"error": "That's for staff only."}), 403
    return None


def _set_password(pid, password):
    with C["db"]() as con:
        con.execute("UPDATE pilots SET password_hash=?, password_set=? WHERE id=?",
                    (generate_password_hash(password), time.time(), pid))


def _check_new_password(pw):
    if len(pw or "") < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters for your password."
    if pw.lower() in ("password", "12345678", "123456789", "qwertyui", "pagani123", "pacacars"):
        return "That password is too easy to guess. Choose another."
    return None


def _sign_in(pid, remember):
    session.clear()
    session["pid"] = pid
    session.permanent = bool(remember)


def _too_many(key):
    now = time.time()
    tries = [t for t in _attempts.get(key, []) if now - t < 900]
    _attempts[key] = tries
    return len(tries) >= 10


# ---------------------------------------------------------------- routes
@bp.get("/api/auth/me")
def me():
    p = current()
    return jsonify({"signed_in": bool(p), "pilot": public_pilot(p) if p else None, "setup_needed": setup_needed(),
                    "founder_id": founder_id() if setup_needed() else None})


@bp.post("/api/auth/setup")
def setup():
    """First time only: the founder chooses a password for their existing pilot record."""
    if not setup_needed():
        return jsonify({"error": "The site already has sign-in set up. Sign in instead."}), 409
    b = request.json or {}
    err = _check_new_password(b.get("password"))
    if err:
        return jsonify({"error": err}), 400
    pid = founder_id()
    with C["db"]() as con:
        if not con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone():
            return jsonify({"error": f"Pilot {pid} wasn't found in the logbook."}), 500
        con.execute("UPDATE pilots SET staff=1 WHERE id=?", (pid,))
    _set_password(pid, b["password"])
    _sign_in(pid, True)
    return jsonify({"ok": True, "pilot": public_pilot(pilot_row(pid))})


@bp.post("/api/auth/login")
def login():
    b = request.json or {}
    key = request.remote_addr or "?"
    if _too_many(key):
        return jsonify({"error": "Too many attempts. Wait 15 minutes and try again."}), 429
    pid = str(b.get("pilot_id") or "").strip().upper()
    r = pilot_row(pid)
    if not r or not r.get("password_hash") or not check_password_hash(r["password_hash"], str(b.get("password") or "")):
        _attempts.setdefault(key, []).append(time.time())
        return jsonify({"error": "That pilot ID and password don't match."}), 401
    if r.get("status") in ("Suspended", "Removed"):
        return jsonify({"error": "This account isn't active. Contact PAC staff."}), 403
    _attempts.pop(key, None)
    _sign_in(pid, b.get("remember", True))
    return jsonify({"ok": True, "pilot": public_pilot(r)})


@bp.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.post("/api/auth/password")
def change_password():
    p = current()
    if not p:
        return jsonify({"error": "Please sign in."}), 401
    b = request.json or {}
    if not check_password_hash(p["password_hash"], str(b.get("current") or "")):
        return jsonify({"error": "Your current password isn't right."}), 400
    err = _check_new_password(b.get("new"))
    if err:
        return jsonify({"error": err}), 400
    _set_password(p["id"], b["new"])
    return jsonify({"ok": True})


def site_address(raw):
    """The website address for links in letters: always https for a real domain, since browsers and mail filters
    distrust plain http links. Addresses on this PC or the home network are left as they are."""
    url = str(raw or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    host = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0].lower()
    local = (host in ("localhost", "127.0.0.1") or host.startswith(("192.168.", "10.", "169.254.")) or host.endswith(".local")
             or any(host.startswith(f"172.{n}.") for n in range(16, 32)))
    if url.lower().startswith("http://") and not local:
        url = "https://" + url[7:]
    return url


def make_invite(pid):
    """A one-time sign-in link for a pilot, valid for INVITE_DAYS. Returns (link, pilot row, purpose) or (None, None, None).
    The address comes from the site's public_url when staff have set one, so links work outside this computer."""
    r = pilot_row(pid)
    if not r:
        return None, None, None
    token = secrets.token_urlsafe(24)
    purpose = "reset" if r.get("password_hash") else "welcome"
    with C["db"]() as con:
        con.execute("UPDATE invites SET used=? WHERE pilot_id=? AND used IS NULL", (time.time(), pid))  # older links stop working
        con.execute("INSERT INTO invites (token_hash, pilot_id, created, expires, purpose) VALUES (?,?,?,?,?)",
                    (_hash_token(token), pid, time.time(), time.time() + INVITE_DAYS * 86400, purpose))
    public = site_address((C["load_json"](C["DATA"] / "site.json", {}) or {}).get("public_url", ""))
    base = public or request.host_url.rstrip("/")
    return f"{base}/#set-password={token}", r, purpose


def invite_link(pid):
    link, _r, _p = make_invite(pid)
    return link


@bp.post("/api/staff/pilots/<pid>/signin-link")
def invite(pid):
    """Staff: a one-time link for a pilot to set (or reset) their password. Valid for 7 days."""
    link, r, purpose = make_invite(pid)
    if not link:
        return jsonify({"error": "Pilot not found."}), 404
    return jsonify({"ok": True, "link": link, "pilot": public_pilot(r), "days": INVITE_DAYS, "purpose": purpose})


@bp.get("/api/auth/invite/<token>")
def invite_info(token):
    with C["db"]() as con:
        i = con.execute("SELECT * FROM invites WHERE token_hash=?", (_hash_token(token),)).fetchone()
    if not i or i["used"] or i["expires"] < time.time():
        return jsonify({"error": "This link has expired or was already used. Ask PAC staff for a new one."}), 410
    r = pilot_row(i["pilot_id"])
    return jsonify({"pilot": public_pilot(r), "purpose": i["purpose"]})


@bp.post("/api/auth/accept")
def accept():
    b = request.json or {}
    th = _hash_token(str(b.get("token") or ""))
    with C["db"]() as con:
        i = con.execute("SELECT * FROM invites WHERE token_hash=?", (th,)).fetchone()
    if not i or i["used"] or i["expires"] < time.time():
        return jsonify({"error": "This link has expired or was already used. Ask PAC staff for a new one."}), 410
    err = _check_new_password(b.get("password"))
    if err:
        return jsonify({"error": err}), 400
    _set_password(i["pilot_id"], b["password"])
    with C["db"]() as con:
        con.execute("UPDATE invites SET used=? WHERE token_hash=?", (time.time(), th))
    _sign_in(i["pilot_id"], True)
    return jsonify({"ok": True, "pilot": public_pilot(pilot_row(i["pilot_id"]))})


@bp.post("/api/auth/token")
def app_key():
    """The PAC ACARS app signs in once and receives a key it keeps (only a hash of it is stored here)."""
    b = request.json or {}
    key = request.remote_addr or "?"
    if _too_many(key):
        return jsonify({"error": "Too many attempts. Wait 15 minutes and try again."}), 429
    pid = str(b.get("pilot_id") or "").strip().upper()
    r = pilot_row(pid)
    if not r or not r.get("password_hash") or not check_password_hash(r["password_hash"], str(b.get("password") or "")):
        _attempts.setdefault(key, []).append(time.time())
        return jsonify({"error": "That pilot ID and password don't match."}), 401
    token = "pac_" + secrets.token_urlsafe(32)
    with C["db"]() as con:
        con.execute("INSERT INTO api_keys (key_hash, pilot_id, label, created) VALUES (?,?,?,?)",
                    (_hash_token(token), pid, str(b.get("label") or "PAC ACARS")[:60], time.time()))
    _attempts.pop(key, None)
    return jsonify({"ok": True, "token": token, "pilot": public_pilot(r)})


@bp.post("/api/auth/token/revoke")
def revoke_key():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        with C["db"]() as con:
            con.execute("DELETE FROM api_keys WHERE key_hash=?", (_hash_token(auth[7:].strip()),))
    return jsonify({"ok": True})


# ---------------------------------------------------------------- badge sign-in (prototype, opt-in)
# The first sign-in on a computer is the normal password. The pilot can then have a badge "issued" to that browser:
# a random token kept in a private cookie (only its hash is stored here). Tapping the badge on the reader signs in
# with that token. Another computer, a cleared browser or "sign out completely" means the password again.
BADGE_COOKIE = "pac_badge"
BADGE_DAYS = 365


def _badge_pilot():
    tok = request.cookies.get(BADGE_COOKIE)
    if not tok:
        return None, None
    with C["db"]() as con:
        r = con.execute("SELECT pilot_id FROM badge_tokens WHERE token_hash=?", (_hash_token(tok),)).fetchone()
    return (pilot_row(r[0]) if r else None), tok


def _badge_card(r):
    return {"pilot_id": r["id"], "name": r.get("name"), "status": r.get("status") or "Active",
            "photo": f"/api/profile/photo?pilot={r['id']}"}


@bp.get("/api/auth/badge")
def badge_status():
    r, _ = _badge_pilot()
    return jsonify({"badge": _badge_card(r) if r else None, "signed_in": bool(current())})


@bp.post("/api/auth/badge/issue")
def badge_issue():
    p = current()
    if not p:
        return jsonify({"error": "Sign in with your password first."}), 401
    tok = secrets.token_urlsafe(32)
    with C["db"]() as con:
        con.execute("INSERT INTO badge_tokens (token_hash, pilot_id, created, agent) VALUES (?,?,?,?)",
                    (_hash_token(tok), p["id"], time.time(), (request.user_agent.string or "")[:200]))
    resp = jsonify({"ok": True, "badge": _badge_card(p)})
    resp.set_cookie(BADGE_COOKIE, tok, max_age=BADGE_DAYS * 86400, httponly=True, samesite="Lax", secure=request.is_secure)
    return resp


@bp.post("/api/auth/badge/tap")
def badge_tap():
    key = "badge|" + (request.remote_addr or "?")
    if _too_many(key):
        return jsonify({"error": "Reader locked. Wait 15 minutes.", "light": "red"}), 429
    r, tok = _badge_pilot()
    if not r:
        _attempts.setdefault(key, []).append(time.time())
        resp = jsonify({"error": "Badge not recognized. Sign in with your password.", "light": "red"})
        resp.delete_cookie(BADGE_COOKIE)
        return resp, 401
    if r.get("status") in ("Suspended", "Removed"):
        return jsonify({"error": "Access denied. See PAC Operations.", "light": "red"}), 403
    with C["db"]() as con:
        con.execute("UPDATE badge_tokens SET last_used=? WHERE token_hash=?", (time.time(), _hash_token(tok)))
    _sign_in(r["id"], True)
    return jsonify({"ok": True, "light": "green", "pilot": public_pilot(r)})


@bp.post("/api/auth/badge/forget")
def badge_forget():
    tok = request.cookies.get(BADGE_COOKIE)
    if tok:
        with C["db"]() as con:
            con.execute("DELETE FROM badge_tokens WHERE token_hash=?", (_hash_token(tok),))
    resp = jsonify({"ok": True})
    resp.delete_cookie(BADGE_COOKIE)
    return resp
