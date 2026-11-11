"""Aircraft that age: the heavy (C) check.

Every airframe builds up flight hours. Light A-checks (every 500 hours, va.A_CHECK_HOURS) are done where the aircraft is.
The heavy check comes due every HEAVY_CHECK_HOURS and is done only at PAC's maintenance base: the aircraft must be
ferried there, then it is out of service for HEAVY_CHECK_DAYS while it is opened up and inspected. Real heavy checks
on freighters come every 18-24 months or several thousand flight hours and take a few weeks.

So the fleet isn't all brand-new, existing airframes start part-way through their check cycle (a fixed amount per
registration, so it never changes between restarts)."""
from __future__ import annotations

import time
import zlib

HEAVY_CHECK_HOURS = 6000
HEAVY_CHECK_DAYS = 21
MX_BASE = "KCVG"
DUE = "Heavy check due"         # waiting for its ferry flight to the base
IN_CHECK = "Heavy check"        # in the hangar at the base


def migrate(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(airframes)")}
    if "hours_since_heavy" not in cols:
        con.execute("ALTER TABLE airframes ADD COLUMN hours_since_heavy REAL DEFAULT 0")
        con.execute("ALTER TABLE airframes ADD COLUMN heavy_until REAL")
        for (reg,) in con.execute("SELECT reg FROM airframes").fetchall():
            con.execute("UPDATE airframes SET hours_since_heavy=? WHERE reg=?", (seed_hours(reg), reg))


def seed_hours(reg):
    """Where a new airframe starts in its heavy-check cycle: 300 to 5,700 hours, fixed per registration."""
    return 300 + zlib.crc32(str(reg).encode()) % (HEAVY_CHECK_HOURS - 600)


def after_flight(since_heavy, location, status, now=None):
    """The airframe's status after a flight. Returns (status, note, heavy_until) or None when nothing changes."""
    if since_heavy < HEAVY_CHECK_HOURS or status != "Available":
        return None
    now = now or time.time()
    if location == MX_BASE:
        until = now + HEAVY_CHECK_DAYS * 86400
        return IN_CHECK, f"Heavy (C) check at {MX_BASE} until {time.strftime('%b %d', time.gmtime(until))}", until
    return DUE, f"Heavy (C) check due at {since_heavy:,.0f} hours: ferry it to the maintenance base at {MX_BASE}", None


def may_book(row, mission):
    """A heavy-check-due airframe may fly one thing: a ferry flight to the maintenance base."""
    return (row.get("status") == DUE and mission.get("category") == "Ferry" and not mission.get("payload_lbs")
            and (mission.get("destination") or {}).get("icao") == MX_BASE)


def tick(con, now=None):
    """Returns airframes whose heavy check has finished to service, as fresh as after any check."""
    now = now or time.time()
    done = [r[0] for r in con.execute("SELECT reg FROM airframes WHERE status=? AND heavy_until IS NOT NULL AND heavy_until<=?", (IN_CHECK, now))]
    for reg in done:
        con.execute("""UPDATE airframes SET status='Available', note=NULL, hours_since_heavy=0, hours_since_check=0, heavy_until=NULL, updated=?
            WHERE reg=?""", (now, reg))
    # an airframe that is due but came back to Available (a cancelled booking, a staff edit) is marked again
    for r in con.execute("SELECT reg, location, hours_since_heavy FROM airframes WHERE status='Available' AND hours_since_heavy>=?",
                         (HEAVY_CHECK_HOURS,)).fetchall():
        status, note, until = after_flight(r[2], r[1], "Available", now)
        con.execute("UPDATE airframes SET status=?, note=?, heavy_until=?, updated=? WHERE reg=?", (status, note, until, now, r[0]))
    return done


def ferry_job(frame, airport_obj, gc_distance_nm, fleet, job_id, expires, bonus):
    """The ferry flight that takes a heavy-check-due airframe to the maintenance base."""
    o, d, ac = airport_obj(frame["location"]), airport_obj(MX_BASE), fleet.get(frame["type"]) or {}
    if not o or not d or not ac:
        return None
    dist = gc_distance_nm(o["lat"], o["lon"], d["lat"], d["lon"])
    return {"id": job_id, "title": f"Ferry {frame['reg']} to {MX_BASE} for its heavy check", "category": "Ferry", "priority": "High",
            "job": True, "job_kind": "ferry", "origin": o, "destination": d, "aircraft": [frame["type"]], "suggested_airframe": frame["reg"],
            "fixed_airframe": frame["reg"], "cargo": "Ferry flight (no cargo)", "payload_lbs": 0, "distance_nm": round(dist),
            "target_block_min": round(45 + dist / (ac.get("cruise_ktas") or 450) * 60 * 1.05), "expires": expires,
            "reward": int(round(dist * 0.06 / 10) * 10) + 30, "ferry_bonus": bonus, "heavy_check": True,
            "briefing": (f"{frame['reg']} ({ac.get('name', frame['type'])}) is due its heavy (C) check. Ferry it from {o['icao']} to the maintenance "
                         f"base at {MX_BASE}, where it will spend about {HEAVY_CHECK_DAYS} days in the hangar. No cargo. "
                         f"{round(dist):,} nm{' (beyond normal range: plan a fuel stop)' if dist > (ac.get('range_nm') or 9e9) * 0.95 else ''}.")}
