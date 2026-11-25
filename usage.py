"""Anonymous usage counts: which pages of the site get opened, how fast the site loads, and which script errors
visitors hit. For staff deciding what to improve, not for watching pilots.

What is stored (data/usage.db, separate from the logbook):
  * per day, page, kind of visitor (guest, pilot, staff) and device (phone, tablet, desktop): how many times the page
    was opened and by how many different visitors;
  * per day, how long the first page load took, as counts in a few time buckets;
  * per day, script error messages (first 200 characters) and where in the script they happened, with a count.
What is not stored: no cookies, no IP addresses, no pilot IDs, nothing per visit. "Different visitors" is counted
with a fingerprint of the visitor's address and browser mixed with a random key that changes every day; the
fingerprints of a day are deleted the day after and the key with them, so they can't be traced back or linked across
days. Bot traffic that doesn't run the page script isn't counted at all."""
import hashlib
import re
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

VIEW_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
IGNORED_ERRORS = re.compile(r"ResizeObserver loop", re.I)   # a browser warning, not a bug (older pages still send it)
KINDS = ("guest", "pilot", "staff")
DEVICES = ("phone", "tablet", "desktop")
LOAD_BUCKETS = (1000, 2000, 3000, 5000, 8000)          # ms: <1 s, 1–2 s, 2–3 s, 3–5 s, 5–8 s, over 8 s
KEEP_DAYS = 400
KEEP_ERROR_DAYS = 90
MAX_PER_MINUTE = 60                                    # per visitor fingerprint; a page sends one beacon per page change

_lock = threading.Lock()
_rate = {}
_path = None


def init(data_dir):
    global _path
    _path = Path(data_dir) / "usage.db"
    with closing(_con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS views (day TEXT, view TEXT, kind TEXT, device TEXT, opens INTEGER DEFAULT 0,
                visitors INTEGER DEFAULT 0, PRIMARY KEY (day, view, kind, device));
            CREATE TABLE IF NOT EXISTS seen (day TEXT, scope TEXT, fp TEXT, PRIMARY KEY (day, scope, fp));
            CREATE TABLE IF NOT EXISTS day_keys (day TEXT PRIMARY KEY, key TEXT);
            CREATE TABLE IF NOT EXISTS visitors (day TEXT, kind TEXT, n INTEGER DEFAULT 0, PRIMARY KEY (day, kind));
            CREATE TABLE IF NOT EXISTS loads (day TEXT, kind TEXT, device TEXT, bucket INTEGER, n INTEGER DEFAULT 0,
                PRIMARY KEY (day, kind, device, bucket));
            CREATE TABLE IF NOT EXISTS errors (day TEXT, message TEXT, place TEXT, n INTEGER DEFAULT 0, last_at REAL,
                PRIMARY KEY (day, message, place));
        """)


def _con():
    con = sqlite3.connect(_path, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def _day(t=None):
    return time.strftime("%Y-%m-%d", time.gmtime(t or time.time()))


def _fingerprint(con, day, addr, agent):
    row = con.execute("SELECT key FROM day_keys WHERE day=?", (day,)).fetchone()
    if row:
        key = row["key"]
    else:
        key = secrets.token_hex(16)
        con.execute("INSERT OR IGNORE INTO day_keys (day, key) VALUES (?, ?)", (day, key))
        key = con.execute("SELECT key FROM day_keys WHERE day=?", (day,)).fetchone()["key"]
        # yesterday's fingerprints and keys are no longer needed: forget them
        con.execute("DELETE FROM seen WHERE day < ?", (day,))
        con.execute("DELETE FROM day_keys WHERE day < ?", (day,))
        con.execute("DELETE FROM views WHERE day < ?", (_day(time.time() - KEEP_DAYS * 86400),))
        con.execute("DELETE FROM visitors WHERE day < ?", (_day(time.time() - KEEP_DAYS * 86400),))
        con.execute("DELETE FROM loads WHERE day < ?", (_day(time.time() - KEEP_DAYS * 86400),))
        con.execute("DELETE FROM errors WHERE day < ?", (_day(time.time() - KEEP_ERROR_DAYS * 86400),))
    return hashlib.sha256(f"{key}|{addr}|{agent}".encode("utf-8", "replace")).hexdigest()[:32]


def _too_fast(fp):
    now = time.time()
    hits = [t for t in _rate.get(fp, []) if now - t < 60]
    if len(_rate) > 5000:
        _rate.clear()
    _rate[fp] = hits + [now]
    return len(hits) >= MAX_PER_MINUTE


def record(body, addr, agent, now=None):
    """One beacon from a page: {"view", "kind", "device", optional "load_ms", optional "error": {"message", "place"}}.
    Returns False when the beacon was ignored (bad fields or too many)."""
    if not _path or not isinstance(body, dict):
        return False
    kind = body.get("kind") if body.get("kind") in KINDS else "guest"
    device = body.get("device") if body.get("device") in DEVICES else "desktop"
    view = str(body.get("view") or "")
    day = _day(now)
    with _lock, closing(_con()) as con, con:
        fp = _fingerprint(con, day, addr or "?", (agent or "")[:300])
        if _too_fast(fp):
            return False
        if VIEW_RE.match(view):
            con.execute("INSERT OR IGNORE INTO views (day, view, kind, device) VALUES (?, ?, ?, ?)", (day, view, kind, device))
            new = con.execute("INSERT OR IGNORE INTO seen (day, scope, fp) VALUES (?, ?, ?)", (day, f"v:{view}:{kind}:{device}", fp)).rowcount
            con.execute("UPDATE views SET opens = opens + 1, visitors = visitors + ? WHERE day=? AND view=? AND kind=? AND device=?",
                        (new, day, view, kind, device))
            if con.execute("INSERT OR IGNORE INTO seen (day, scope, fp) VALUES (?, ?, ?)", (day, f"d:{kind}", fp)).rowcount:
                con.execute("INSERT OR IGNORE INTO visitors (day, kind) VALUES (?, ?)", (day, kind))
                con.execute("UPDATE visitors SET n = n + 1 WHERE day=? AND kind=?", (day, kind))
        load = body.get("load_ms")
        if isinstance(load, (int, float)) and 0 < load < 600000:
            bucket = next((i for i, b in enumerate(LOAD_BUCKETS) if load < b), len(LOAD_BUCKETS))
            con.execute("INSERT OR IGNORE INTO loads (day, kind, device, bucket) VALUES (?, ?, ?, ?)", (day, kind, device, bucket))
            con.execute("UPDATE loads SET n = n + 1 WHERE day=? AND kind=? AND device=? AND bucket=?", (day, kind, device, bucket))
        err = body.get("error")
        if isinstance(err, dict) and err.get("message") and not IGNORED_ERRORS.search(str(err["message"])):
            msg = re.sub(r"\s+", " ", str(err["message"]))[:200]
            place = re.sub(r"\s+", " ", str(err.get("place") or ""))[:120]
            con.execute("INSERT OR IGNORE INTO errors (day, message, place) VALUES (?, ?, ?)", (day, msg, place))
            con.execute("UPDATE errors SET n = n + 1, last_at = ? WHERE day=? AND message=? AND place=?", (now or time.time(), day, msg, place))
    return True


def report(days=30, now=None):
    days = max(1, min(int(days or 30), KEEP_DAYS))
    now = now or time.time()
    since = _day(now - (days - 1) * 86400)
    if not _path or not _path.exists():
        return {"days": days, "since": since, "pages": [], "daily": [], "loads": {}, "errors": [], "totals": {}}
    with closing(_con()) as con:
        pages = {}
        for r in con.execute("SELECT view, kind, device, SUM(opens) o, SUM(visitors) v FROM views WHERE day >= ? GROUP BY view, kind, device", (since,)):
            p = pages.setdefault(r["view"], {"view": r["view"], "opens": 0, "visitors": 0, "guest": 0, "pilot": 0, "staff": 0, "phone": 0})
            p["opens"] += r["o"]; p["visitors"] += r["v"]; p[r["kind"]] += r["o"]
            if r["device"] == "phone":
                p["phone"] += r["o"]
        daily = {}
        for r in con.execute("SELECT day, kind, SUM(opens) o FROM views WHERE day >= ? GROUP BY day, kind", (since,)):
            d = daily.setdefault(r["day"], {"day": r["day"], "guest": 0, "pilot": 0, "staff": 0})
            d[r["kind"]] = r["o"]
        for r in con.execute("SELECT day, kind, n FROM visitors WHERE day >= ?", (since,)):
            d = daily.setdefault(r["day"], {"day": r["day"], "guest": 0, "pilot": 0, "staff": 0})
            d["visitors"] = d.get("visitors", 0) + r["n"]
            d[r["kind"] + "_visitors"] = r["n"]
        for d in daily.values():
            d.setdefault("visitors", 0)
        loads = {}
        for r in con.execute("SELECT device, bucket, SUM(n) n FROM loads WHERE day >= ? GROUP BY device, bucket", (since,)):
            loads.setdefault(r["device"], [0] * (len(LOAD_BUCKETS) + 1))[r["bucket"]] = r["n"]
        errors = [dict(r) for r in con.execute(
            "SELECT message, place, SUM(n) n, MAX(last_at) last_at FROM errors WHERE day >= ? GROUP BY message, place ORDER BY n DESC LIMIT 25", (since,))]
        errors = [e for e in errors if not IGNORED_ERRORS.search(e["message"] or "")]   # counted before they were ignored
    for e in errors:   # "/static/app.js:51234:25" -> "/static/app.js:51234:25 (05-logbook.js:120)", the piece to open
        m = re.match(r"/static/app\.js:(\d+)(?::\d+)?$", e["place"] or "")
        if m:
            try:
                import app_bundle
                where = app_bundle.locate(int(m.group(1)))
                if where:
                    e["place"] += f" ({where})"
            except OSError:
                pass
    rows = sorted(pages.values(), key=lambda p: -p["opens"])
    total = sum(p["opens"] for p in rows)
    return {"days": days, "since": since, "pages": rows, "daily": sorted(daily.values(), key=lambda d: d["day"]),
            "loads": loads, "buckets_ms": list(LOAD_BUCKETS), "errors": errors,
            "totals": {"opens": total, "guest": sum(p["guest"] for p in rows), "pilot": sum(p["pilot"] for p in rows),
                       "staff": sum(p["staff"] for p in rows), "phone": sum(p["phone"] for p in rows),
                       "avg_visitors": round(sum(d["visitors"] for d in daily.values()) / max(1, len(daily)), 1)}}


def register(app, g):
    from flask import jsonify, request
    init(g["DATA"])

    @app.post("/api/usage")
    def usage_beacon():
        body = request.get_json(silent=True, force=True) or {}
        from client_ip import client_ip      # the visitor's own address, not Cloudflare's
        record(body, client_ip(), request.headers.get("User-Agent", ""))
        return ("", 204)

    @app.get("/api/staff/usage")
    def usage_report():
        return jsonify(report(request.args.get("days", 30)))
