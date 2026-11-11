"""Trip pairings: multi-day trips, the way real cargo pilots work.

A pairing is 3 to 6 scheduled legs that leave a PAC hub and come back to it, flown in one aircraft type over several
duty days with layovers in between. A pilot bids for a trip, then books its legs one at a time through the normal
booking flow. The rules follow real duty limits in a simple form:

  * a duty day is at most 13 hours: 1 hour to report, the legs, 30 minutes between legs (FAR 117 allows 9 to 13)
  * between duty days the crew rests at least 10 hours at the layover city (real time: the next leg opens then)
  * per diem is paid for the whole time away from base when the last leg is filed, as cargo airlines do

Trips stay open for a week. A pilot holds one trip at a time and can drop it before the last leg."""
from __future__ import annotations

import json
import random
import time

HUBS = ("KCVG", "KMIA", "LIMC", "OMDW", "VHHH", "PANC")
OPEN_TRIPS = 6
OPEN_DAYS = 7
MAX_DUTY_MIN = 13 * 60
REPORT_MIN, TURN_MIN = 60, 30
REST_MIN = 10 * 60
PER_DIEM_PER_HOUR = 2.75          # dollars per hour away from base


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS trips (id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, pilot_id TEXT,
        created REAL, expires REAL, legs_done INTEGER DEFAULT 0, next_after REAL, started REAL, finished REAL)""")


def _duty_days(legs):
    """Splits legs into duty days under the 13-hour limit; returns the day number of each leg."""
    day, used, out = 1, 0, []
    for leg in legs:
        need = leg["target_block_min"] + (REPORT_MIN if used == 0 else TURN_MIN)
        if used and used + need > MAX_DUTY_MIN:
            day, used, need = day + 1, 0, leg["target_block_min"] + REPORT_MIN
        used += need
        out.append(day)
    return out


def build(routes, fleet, rng, trip_id, now):
    """One pairing from the scheduled routes, or None if no loop works from the chosen hub and type."""
    by_origin = {}
    for r in routes:
        if r.get("category") == "Scheduled":
            by_origin.setdefault(r["origin"]["icao"], []).append(r)
    hub = rng.choice([h for h in HUBS if h in by_origin] or [None])
    if not hub:
        return None
    types = sorted({t for r in by_origin[hub] for t in r.get("aircraft") or [] if t in fleet and not fleet[t].get("retired")})
    rng.shuffle(types)
    for ac in types[:4]:
        for _ in range(40):
            want = rng.choice((3, 4, 4, 5, 6))
            here, seen, legs = hub, {hub}, []
            while len(legs) < want:
                last = len(legs) == want - 1
                opts = [r for r in by_origin.get(here, []) if ac in (r.get("aircraft") or [])
                        and ((r["destination"]["icao"] == hub) if last else r["destination"]["icao"] not in seen)]
                if not opts:
                    break
                r = rng.choice(opts)
                legs.append(r)
                here = r["destination"]["icao"]
                seen.add(here)
            if len(legs) == want and here == hub:
                days = _duty_days(legs)
                out = []
                for i, (r, d) in enumerate(zip(legs, days)):
                    layover = i < len(legs) - 1 and days[i + 1] != d
                    m = dict(r, id=f"{trip_id}-{i + 1}", aircraft=[ac], types_only=True,
                             trip={"id": trip_id, "leg": i + 1, "legs": len(legs), "day": d, "route_id": r["id"],
                                   "layover": r["destination"]["icao"] if layover else None})
                    m.pop("briefing", None)
                    m["briefing"] = (f"Leg {i + 1} of {len(legs)} of trip {trip_id}, duty day {d}. "
                                     + (f"Layover in {r['destination'].get('city') or r['destination']['icao']} after this leg: at least 10 hours' rest before the next one."
                                        if layover else "Back to base after this leg." if i == len(legs) - 1 else "The next leg follows the same duty day."))
                    out.append(m)
                block = sum(x["target_block_min"] for x in out)
                return {"id": trip_id, "hub": hub, "aircraft": ac, "legs": out, "days": days[-1], "block_min": block,
                        "stations": [hub] + [x["destination"]["icao"] for x in out],
                        "per_diem_estimate": round(((days[-1] - 1) * 24 + 12) * PER_DIEM_PER_HOUR)}
    return None


def refresh(con, routes, fleet, now=None):
    """Expires old open trips and tops the board up to OPEN_TRIPS."""
    now = now or time.time()
    migrate(con)
    con.execute("UPDATE trips SET status='expired' WHERE status='open' AND expires<?", (now,))
    have = con.execute("SELECT COUNT(*) FROM trips WHERE status='open'").fetchone()[0]
    rng = random.Random(f"trips|{int(now // 3600)}")
    month = time.strftime("%y%m", time.gmtime(now))
    n = con.execute("SELECT COUNT(*) FROM trips WHERE id LIKE ?", (f"T{month}-%",)).fetchone()[0]
    made = 0
    for _ in range((OPEN_TRIPS - have) * 3):
        if have + made >= OPEN_TRIPS:
            break
        tid = f"T{month}-{n + made + 1:03d}"
        t = build(list(routes), fleet, rng, tid, now)
        if t:
            con.execute("INSERT INTO trips (id, data, status, created, expires) VALUES (?,?,?,?,?)",
                        (tid, json.dumps(t), "open", now, now + OPEN_DAYS * 86400))
            made += 1
    return made


def _row(con, tid):
    r = con.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
    if not r:
        return None
    t = json.loads(r["data"])
    t.update(status=r["status"], pilot_id=r["pilot_id"], legs_done=r["legs_done"] or 0, next_after=r["next_after"],
             expires=r["expires"], started=r["started"], finished=r["finished"])
    return t


def board(con, pilot_id, now=None):
    now = now or time.time()
    migrate(con)
    mine = con.execute("SELECT id FROM trips WHERE pilot_id=? AND status='bid'", (pilot_id,)).fetchone()
    trips = [_row(con, r[0]) for r in con.execute("SELECT id FROM trips WHERE status='open' ORDER BY created DESC")]
    return {"mine": _row(con, mine[0]) if mine else None, "open": trips, "now": now,
            "rules": {"max_duty_h": MAX_DUTY_MIN / 60, "rest_h": REST_MIN / 60, "per_diem": PER_DIEM_PER_HOUR}}


def bid(con, tid, pilot_id, now=None):
    now = now or time.time()
    if con.execute("SELECT 1 FROM trips WHERE pilot_id=? AND status='bid'", (pilot_id,)).fetchone():
        raise ValueError("You already hold a trip. Finish or drop it first.")
    cur = con.execute("UPDATE trips SET status='bid', pilot_id=?, started=NULL WHERE id=? AND status='open' AND expires>?", (pilot_id, tid, now))
    if not cur.rowcount:
        raise ValueError("That trip has been taken or has expired.")


def drop(con, tid, pilot_id):
    con.execute("UPDATE trips SET status='dropped', finished=? WHERE id=? AND pilot_id=? AND status='bid'", (time.time(), tid, pilot_id))


def leg(con, mission_id, pilot_id, now=None):
    """The mission for a trip leg, if it's this pilot's next leg and the rest is done. Raises ValueError with the reason otherwise."""
    if not str(mission_id or "").startswith("T") or "-" not in str(mission_id):
        return None
    now = now or time.time()
    migrate(con)
    tid = str(mission_id).rsplit("-", 1)[0]
    t = _row(con, tid)
    if not t:
        return None
    if t["status"] != "bid" or t["pilot_id"] != pilot_id:
        raise ValueError("Bid for this trip on the Trips board before booking its legs.")
    n = t["legs_done"] + 1
    if mission_id != f"{tid}-{n}":
        raise ValueError(f"Fly the legs in order: leg {n} is next.")
    if t.get("next_after") and now < t["next_after"]:
        raise ValueError(f"You're on your layover rest. Leg {n} opens at {time.strftime('%H:%M UTC on %b %d', time.gmtime(t['next_after']))}.")
    return t["legs"][n - 1]


def on_filed(con, pilot_id, mission, delivered, now=None):
    """Moves a trip on after one of its legs is filed. Returns the trip when it has just been completed."""
    tr = (mission or {}).get("trip")
    if not tr:
        return None
    now = now or time.time()
    migrate(con)
    t = _row(con, tr["id"])
    if not t or t["status"] != "bid" or t["pilot_id"] != pilot_id or tr["leg"] != t["legs_done"] + 1:
        return None
    if not delivered:
        return None      # a failed or diverted leg: fly it again (or drop the trip)
    started = t.get("started") or now - (mission.get("target_block_min") or 60) * 60
    next_after = now + REST_MIN * 60 if tr.get("layover") else None
    if tr["leg"] == tr["legs"]:
        con.execute("UPDATE trips SET status='done', legs_done=?, finished=?, next_after=NULL, started=? WHERE id=?", (tr["leg"], now, started, t["id"]))
        t.update(started=started, finished=now)
        return t
    con.execute("UPDATE trips SET legs_done=?, next_after=?, started=? WHERE id=?", (tr["leg"], next_after, started, t["id"]))
    return None


def per_diem(trip):
    hours = max(0, ((trip.get("finished") or 0) - (trip.get("started") or 0)) / 3600)
    return round(hours * PER_DIEM_PER_HOUR, 2), round(hours, 1)


def settle(con, pilot_id, mission, p, add_tx, pirep_id=None):
    """Called after a filed flight: moves the trip on and pays per diem when the trip is done."""
    delivered = p.get("status") in ("Delivered", "Delivered late") and p.get("review_status") != "Rejected" and not p.get("demo")
    t = on_filed(con, pilot_id, mission, delivered)
    if not t:
        return None
    pay, hours = per_diem(t)
    if pay > 0:
        add_tx(pilot_id, "per_diem", pay, f"Per diem, trip {t['id']} ({hours} h away from {t['hub']})", pirep_id, con)
    return {"id": t["id"], "per_diem": pay, "hours": hours}


def register(app, g):
    from flask import jsonify, request

    def _pid():
        return g["va"].current_pilot_id()

    @app.get("/api/trips")
    def trips_board():
        with g["db"]() as con:
            refresh(con, g["ROUTES"].values(), g["FLEET"])
            return jsonify(board(con, _pid()))

    @app.post("/api/trips/<tid>/<action>")
    def trips_action(tid, action):
        try:
            with g["db"]() as con:
                if action == "bid":
                    bid(con, tid, _pid())
                elif action == "drop":
                    drop(con, tid, _pid())
                else:
                    return jsonify({"error": "Unknown action."}), 400
                return jsonify(board(con, _pid()))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
