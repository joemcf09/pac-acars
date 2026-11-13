"""Growing the airline: route proving flights, hub candidates, ramp inspections, the yearly safety audit, press releases,
competitors, mentoring and seniority.

  * Proving flights: the CEO proposes a new route; the first flight anyone files between the two airports proves it, and
    the route joins the scheduled network (real airlines fly proving flights before opening a route).
  * Hub candidates: the busiest non-hub stations, ranked, as the case for PAC's next hub.
  * Ramp inspections: now and then an arrival is inspected; an overweight aircraft or a curfew bust gets written up.
  * Safety audit: a yearly report card from landing rates, hard landings, AOG events, on-time rate and ramp findings.
  * Press releases: automatic news for milestones (the 100th, 250th, 500th... flight) and record months.
  * Competitors: when a shipper's account falls to At risk, a rival carrier wins some of its freight (a news story).
  * Mentoring: a new pilot is paired with an experienced one; after the mentee's first three flights both get a bonus.
  * Seniority: for the first 12 hours after a trip pairing is posted, only the more senior half of the pilots can bid.

Real carriers named in stories are used for realism only; PAC has no affiliation with them."""
from __future__ import annotations

import datetime as dt
import json
import time
import zlib

HUBS = ("KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC")
MILESTONES = (100, 250, 500, 1000, 2500, 5000, 10000)
COMPETITORS = ("FedEx Express", "UPS Airlines", "DHL Aviation", "Atlas Air", "Cargolux", "Kalitta Air")
STORY_NOTE = "(PAC is a virtual airline: real carriers named in its stories are used for realism only.)"
RAMP_ONE_IN = 12
MENTOR_FLIGHTS, MENTOR_BONUS = 3, 500
SENIOR_WINDOW_H = 12
_G = {}


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS route_proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, origin TEXT, dest TEXT, proposed REAL,
        by_pilot TEXT, status TEXT DEFAULT 'proposed', proven REAL, proven_by TEXT, pirep_id INTEGER, route TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS ramp_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, pirep_id INTEGER, pilot_id TEXT, station TEXT, time REAL, findings TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS press (key TEXT PRIMARY KEY, time REAL)")
    con.execute("""CREATE TABLE IF NOT EXISTS mentorships (id INTEGER PRIMARY KEY AUTOINCREMENT, mentor TEXT, mentee TEXT, started REAL,
        flights INTEGER DEFAULT 0, status TEXT DEFAULT 'active', finished REAL)""")


def _press_once(con, key):
    if con.execute("SELECT 1 FROM press WHERE key=?", (key,)).fetchone():
        return False
    con.execute("INSERT INTO press (key, time) VALUES (?,?)", (key, time.time()))
    return True


# --------------------------------------------------------------------------------------------- proving flights
def build_route(pid_, origin, dest, g):
    o, d = g["airport_obj"](origin), g["airport_obj"](dest)
    if not o or not d:
        raise ValueError("Unknown airport.")
    dist = g["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
    if dist < 150:
        raise ValueError("That's too short for an air route. Freight that close goes by truck.")
    fleet = g["FLEET"]
    types = [k for k, a in fleet.items() if not a.get("retired") and (a.get("range_nm") or 0) >= dist * 1.05]
    if not types:
        raise ValueError(f"No PAC type can fly {dist:,.0f} nm nonstop.")
    types.sort(key=lambda k: fleet[k].get("max_payload_lbs") or 0)
    import economics
    first = fleet[types[0]]
    return {"id": f"PAC{8000 + pid_}", "title": f"{o.get('city') or origin} to {d.get('city') or dest}", "category": "Scheduled",
            "region": "New route", "priority": "Normal", "origin": o, "destination": d, "aircraft": types[:5],
            "cargo": "General freight", "payload_lbs": int(round((first.get("max_payload_lbs") or 40000) * 0.7, -3)),
            "target_block_min": round(economics.planned_block(first, dist)), "reward": int(round(dist * 0.2 / 10) * 10) + 30,
            "distance_nm": round(dist), "briefing": f"A route PAC opened after a proving flight. {round(dist):,} nm of general freight."}


def propose(con, origin, dest, by, g):
    origin, dest = origin.strip().upper(), dest.strip().upper()
    if origin == dest:
        raise ValueError("Pick two different airports.")
    for r in g["ROUTES"].values():
        if {r["origin"]["icao"], r["destination"]["icao"]} == {origin, dest}:
            raise ValueError(f"PAC already flies {origin}–{dest} ({r['id']}).")
    if con.execute("SELECT 1 FROM route_proposals WHERE status='proposed' AND ((origin=? AND dest=?) OR (origin=? AND dest=?))", (origin, dest, dest, origin)).fetchone():
        raise ValueError("That route is already waiting for its proving flight.")
    build_route(0, origin, dest, g)         # checks the route is flyable before keeping it
    con.execute("INSERT INTO route_proposals (origin, dest, proposed, by_pilot) VALUES (?,?,?,?)", (origin, dest, time.time(), by))
    return con.execute("SELECT last_insert_rowid()").fetchone()[0]


def load_routes(con, routes):
    for (r,) in con.execute("SELECT route FROM route_proposals WHERE status='proven' AND route IS NOT NULL"):
        x = json.loads(r)
        routes[x["id"]] = x


# --------------------------------------------------------------------------------------------- on each filed flight
def on_filed(con, pid, p, mission, pirep_id, g, now=None):
    now = now or time.time()
    migrate(con)
    out = {}
    if p.get("demo"):
        return out
    dep, arr = p.get("dep"), p.get("arr")
    # proving flights
    for r in con.execute("SELECT * FROM route_proposals WHERE status='proposed'").fetchall():
        if {dep, arr} == {r["origin"], r["dest"]} and p.get("status") in ("Delivered", "Delivered late"):
            route = build_route(r["id"], r["origin"], r["dest"], g)
            con.execute("UPDATE route_proposals SET status='proven', proven=?, proven_by=?, pirep_id=?, route=? WHERE id=?",
                        (now, pid, pirep_id, json.dumps(route), r["id"]))
            g["ROUTES"][route["id"]] = route
            name = (con.execute("SELECT name FROM pilots WHERE id=?", (pid,)).fetchone() or [pid])[0]
            news(con, f"New route: {route['title']}", f"{name} flew the proving flight from {dep} to {arr}. {route['id']} {route['origin']['icao']}–"
                 f"{route['destination']['icao']} ({route['distance_nm']:,} nm) is now on the scheduled network.")
            out["proved_route"] = route["id"]
    # ramp inspection
    if pirep_id and zlib.crc32(f"ramp|{pirep_id}".encode()) % RAMP_ONE_IN == 0:
        findings = []
        ac = g["FLEET"].get(p.get("aircraft")) or {}
        if ac.get("max_payload_lbs") and (p.get("payload_lbs") or 0) > ac["max_payload_lbs"]:
            findings.append(f"Payload {p['payload_lbs']:,.0f} lb is over the {ac['max_payload_lbs']:,} lb limit for the {ac.get('name', 'type')}.")
        try:
            import ops_rules
            c = ops_rules.curfew(arr, dt.datetime.fromtimestamp(now, dt.timezone.utc))
            if c and c["inside"]:
                findings.append(f"Arrived at {arr} at {c['local']} local, inside the {c['start']}–{c['end']} night curfew.")
        except Exception:
            pass
        if (p.get("landing_rate") or 0) <= -600:
            findings.append(f"Hard landing ({p['landing_rate']:.0f} fpm) not yet written up in the tech log.")
        con.execute("INSERT INTO ramp_checks (pirep_id, pilot_id, station, time, findings) VALUES (?,?,?,?,?)",
                    (pirep_id, pid, arr, now, json.dumps(findings)))
        out["ramp_check"] = {"station": arr, "findings": findings}
    # mentoring
    m = con.execute("SELECT * FROM mentorships WHERE mentee=? AND status='active'", (pid,)).fetchone()
    if m:
        n = (m["flights"] or 0) + 1
        con.execute("UPDATE mentorships SET flights=? WHERE id=?", (n, m["id"]))
        if n >= MENTOR_FLIGHTS:
            con.execute("UPDATE mentorships SET status='done', finished=? WHERE id=?", (now, m["id"]))
            for who in (m["mentor"], m["mentee"]):
                g["va"].add_tx(who, "mentoring", MENTOR_BONUS, f"Mentoring complete ({m['mentor']} → {m['mentee']})", pirep_id, con)
            names = {r[0]: r[1] for r in con.execute("SELECT id, name FROM pilots WHERE id IN (?,?)", (m["mentor"], m["mentee"]))}
            news(con, "Mentoring complete", f"{names.get(m['mentee'], m['mentee'])} has finished their first {MENTOR_FLIGHTS} flights with "
                 f"{names.get(m['mentor'], m['mentor'])} as mentor. Welcome to the line!")
            out["mentoring_done"] = True
    # milestones
    total = con.execute("SELECT COUNT(*) FROM pireps WHERE demo=0").fetchone()[0]
    for ms in MILESTONES:
        if total >= ms and _press_once(con, f"flights-{ms}"):
            news(con, f"PAC flies its {ms:,}th flight", f"Pagani Air Cargo has now flown {ms:,} flights. Thank you to every pilot who got us here.")
    return out


def news(con, title, body):
    con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                (time.time(), "news", title, body, 0, None, "PAC Communications"))


# --------------------------------------------------------------------------------------------- the monthly tick
def tick(con, now=None):
    now = now or time.time()
    migrate(con)
    d = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    # record month
    if d.day <= 3:
        prev = (d.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
        rows = {r[0]: r[1] for r in con.execute("""SELECT strftime('%Y-%m', filed_at, 'unixepoch') m, SUM(payload_lbs) FROM pireps
            WHERE demo=0 AND review_status='Accepted' GROUP BY m""")}
        if rows.get(prev) and len(rows) > 1 and rows[prev] >= max(v for k, v in rows.items() if k != prev) and _press_once(con, f"record-{prev}"):
            label = dt.datetime.strptime(prev, "%Y-%m").strftime("%B %Y")
            news(con, f"Record month: {label}", f"PAC moved {rows[prev] / 2204.62:,.0f} tonnes of freight in {label}, its best month yet.")
    # competitors
    try:
        import accounts
        for a in accounts.compute(con, now).values():
            if a["tier"] == "At risk" and _press_once(con, f"rival-{a['shipper']}-{d.strftime('%Y-%m')}"):
                rival = COMPETITORS[zlib.crc32(a["shipper"].encode()) % len(COMPETITORS)]
                news(con, f"{rival} wins freight from {a['shipper']}",
                     f"After recent problems with PAC shipments, {a['shipper']} has moved part of its freight to {rival}. "
                     f"A visit from management and on-time deliveries can win it back. {STORY_NOTE}")
    except Exception as e:
        print("competitors:", e)


# --------------------------------------------------------------------------------------------- reports
def safety_audit(con, now=None, days=365):
    now = now or time.time()
    since = now - days * 86400
    f = con.execute("""SELECT COUNT(*), AVG(landing_rate), SUM(CASE WHEN landing_rate <= -600 THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Delivered' THEN 1 ELSE 0 END) FROM pireps WHERE demo=0 AND review_status='Accepted' AND filed_at>?""", (since,)).fetchone()
    flights = f[0] or 0
    aog = con.execute("SELECT COUNT(*) FROM maint WHERE time>? AND severity IN ('aog','AOG','grounding')", (since,)).fetchone()[0]
    ramp = [json.loads(r[0]) for r in con.execute("SELECT findings FROM ramp_checks WHERE time>?", (since,))]
    findings = sum(len(x) for x in ramp)
    hard_pct = round(100 * (f[2] or 0) / flights, 1) if flights else 0
    on_time = round(100 * (f[3] or 0) / flights) if flights else None
    checks = [("Average landing rate gentler than 300 fpm", f[1] is not None and f[1] > -300),
              ("Hard landings under 2% of flights", hard_pct < 2),
              ("On-time rate 85% or better", on_time is not None and on_time >= 85),
              ("Ramp findings on fewer than 1 in 5 inspections", not ramp or findings / len(ramp) < 0.2)]
    return {"flights": flights, "avg_rate": round(f[1]) if f[1] is not None else None, "hard_pct": hard_pct, "on_time": on_time,
            "aog": aog, "inspections": len(ramp), "findings": findings,
            "checks": [{"text": t, "ok": bool(ok)} for t, ok in checks], "passed": flights >= 10 and all(ok for _, ok in checks)}


def hub_candidates(con, now=None, n=5):
    now = now or time.time()
    rows = con.execute(f"""SELECT arr, COUNT(*) c, COUNT(DISTINCT pilot_id) p FROM pireps WHERE demo=0 AND filed_at>? AND arr NOT IN ({','.join('?' * len(HUBS))})
        GROUP BY arr ORDER BY c DESC LIMIT ?""", (now - 90 * 86400, *HUBS, n)).fetchall()
    return [{"icao": r[0], "arrivals_90d": r[1], "pilots": r[2]} for r in rows]


# --------------------------------------------------------------------------------------------- seniority
def seniority(con):
    """[pilot id] from most to least senior (active pilots, by join date)."""
    return [r[0] for r in con.execute("SELECT id FROM pilots WHERE COALESCE(status,'Active') NOT IN ('Suspended','Removed','Inactive') ORDER BY COALESCE(joined, 9e18), id")]


def senior_window_problem(con, pid, trip_created, now=None):
    now = now or time.time()
    if not trip_created or now - trip_created >= SENIOR_WINDOW_H * 3600:
        return None
    order = seniority(con)
    if len(order) < 4 or pid not in order or order.index(pid) < (len(order) + 1) // 2:
        return None
    opens = time.strftime("%H:%M UTC", time.gmtime(trip_created + SENIOR_WINDOW_H * 3600))
    return f"Senior pilots get first pick on new trips. This one opens to everyone at {opens}. (Your seniority: {order.index(pid) + 1} of {len(order)}.)"


# --------------------------------------------------------------------------------------------- the API
def register(app, g):
    from flask import jsonify, request
    import company
    _G.update(g=g)
    with g["db"]() as con:
        migrate(con)
        load_routes(con, g["ROUTES"])

    def pid():
        return g["va"].current_pilot_id()

    @app.get("/api/staff/growth")
    def growth_desk():
        with g["db"]() as con:
            migrate(con)
            if not company.may(con, pid(), "ceo_desk"):
                return jsonify({"error": "This is for the CEO (or the role it's been handed to)."}), 403
            names = {r[0]: r[1] for r in con.execute("SELECT id, name FROM pilots")}
            return jsonify({
                "proposals": [dict(r) | {"route": None} for r in con.execute("SELECT * FROM route_proposals ORDER BY proposed DESC LIMIT 20")],
                "candidates": hub_candidates(con), "audit": safety_audit(con),
                "ramp": [{"time": r[0], "pilot": names.get(r[1], r[1]), "station": r[2], "findings": json.loads(r[3])}
                         for r in con.execute("SELECT time, pilot_id, station, findings FROM ramp_checks ORDER BY time DESC LIMIT 10")],
                "mentors": [dict(r) | {"mentor_name": names.get(r["mentor"]), "mentee_name": names.get(r["mentee"])}
                            for r in con.execute("SELECT * FROM mentorships ORDER BY started DESC LIMIT 20")],
                "seniority": [{"pilot_id": p, "name": names.get(p)} for p in seniority(con)][:20],
                "mentor_flights": MENTOR_FLIGHTS, "mentor_bonus": MENTOR_BONUS})

    @app.post("/api/staff/growth/<action>")
    def growth_action(action):
        b = request.get_json(silent=True) or {}
        try:
            with g["db"]() as con:
                migrate(con)
                if not company.may(con, pid(), "ceo_desk"):
                    return jsonify({"error": "This is for the CEO."}), 403
                if action == "propose":
                    return jsonify({"id": propose(con, b.get("origin", ""), b.get("dest", ""), pid(), g)})
                if action == "cancel_route":
                    con.execute("UPDATE route_proposals SET status='cancelled' WHERE id=? AND status='proposed'", (b.get("id"),))
                    return jsonify({"ok": True})
                if action == "mentor":
                    mentor, mentee = str(b.get("mentor", "")).upper(), str(b.get("mentee", "")).upper()
                    for x in (mentor, mentee):
                        if not con.execute("SELECT 1 FROM pilots WHERE id=?", (x,)).fetchone():
                            raise ValueError(f"No pilot {x}.")
                    if mentor == mentee:
                        raise ValueError("Pick two different pilots.")
                    if con.execute("SELECT 1 FROM mentorships WHERE mentee=? AND status='active'", (mentee,)).fetchone():
                        raise ValueError(f"{mentee} already has a mentor.")
                    con.execute("INSERT INTO mentorships (mentor, mentee, started) VALUES (?,?,?)", (mentor, mentee, time.time()))
                    return jsonify({"ok": True})
                return jsonify({"error": "Unknown action."}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
