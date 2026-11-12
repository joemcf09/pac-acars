"""Aircraft that age: the heavy (C) check.

Every airframe builds up flight hours. Light A-checks (every 500 hours, va.A_CHECK_HOURS) are done where the aircraft is.
The heavy check comes due every HEAVY_CHECK_HOURS and is done only at one of PAC's maintenance bases (one per region):
the aircraft is ferried to the nearest one, then it is out of service for 3 to 5 days. (Real C-checks take one to four
weeks; PAC keeps it short so pilots aren't without their aircraft for long.) Booking checks ahead: a flight that would
leave the airframe without enough hours left to reach a base is refused.

So the fleet isn't all brand-new, existing airframes start part-way through their check cycle (a fixed amount per
registration, so it never changes between restarts)."""
from __future__ import annotations

import time
import zlib

HEAVY_CHECK_HOURS = 6000
HEAVY_CHECK_DAYS = (3, 5)       # out of service this many days, fixed per registration
MX_BASES = ("KCVG", "LIMC", "VHHH")   # Americas, Europe/Africa/Middle East, Asia-Pacific
MX_BASE = MX_BASES[0]           # kept for older callers
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


def check_days(reg):
    lo, hi = HEAVY_CHECK_DAYS
    return lo + zlib.crc32(f"days|{reg}".encode()) % (hi - lo + 1)


def nearest_base(icao, airport_obj, gc_distance_nm):
    """(base ICAO, distance nm) of the closest maintenance base, or (MX_BASE, 0) if the airport is unknown."""
    a = airport_obj(icao) if icao else None
    if icao in MX_BASES:
        return icao, 0
    if not a:
        return MX_BASE, 0
    best = min(((b, gc_distance_nm(a["lat"], a["lon"], o["lat"], o["lon"])) for b in MX_BASES if (o := airport_obj(b))), key=lambda x: x[1], default=(MX_BASE, 0))
    return best[0], best[1]


def dispatch_problem(row, mission, fleet, airport_obj, gc_distance_nm):
    """Why this flight can't be booked on this airframe because of its coming heavy check, or None.
    The hours left must cover the flight and then a ferry from its destination to the nearest base."""
    if not row or row.get("status") == DUE:
        return None
    left = HEAVY_CHECK_HOURS - (row.get("hours_since_heavy") or 0)
    flight_h = (mission.get("target_block_min") or 0) / 60
    dest = (mission.get("destination") or {}).get("icao")
    base, nm = nearest_base(dest, airport_obj, gc_distance_nm)
    cruise = (fleet.get(row.get("type")) or {}).get("cruise_ktas") or 450
    ferry_h = 0 if dest in MX_BASES else (45 + nm / cruise * 60 * 1.05) / 60
    if flight_h + ferry_h <= left:
        return None
    reg = row.get("reg")
    if dest in MX_BASES:
        return f"{reg} has {max(0, left):.0f} h left before its heavy (C) check and this flight needs about {flight_h:.0f} h. Pick another aircraft."
    return (f"{reg} has {max(0, left):.0f} h left before its heavy (C) check. This flight (about {flight_h:.0f} h) plus the ferry from "
            f"{dest} to the nearest maintenance base ({base}, about {ferry_h:.0f} h) won't fit. Pick another aircraft, or fly {reg} to a maintenance base first.")


def after_flight(since_heavy, location, status, now=None, reg=""):
    """The airframe's status after a flight. Returns (status, note, heavy_until) or None when nothing changes."""
    if since_heavy < HEAVY_CHECK_HOURS or status != "Available":
        return None
    now = now or time.time()
    if location in MX_BASES:
        until = now + check_days(reg) * 86400
        return IN_CHECK, f"Heavy (C) check at {location} until {time.strftime('%b %d', time.gmtime(until))}", until
    return DUE, f"Heavy (C) check due at {since_heavy:,.0f} hours: ferry it to a maintenance base ({', '.join(MX_BASES)})", None


def may_book(row, mission):
    """A heavy-check-due airframe may fly one thing: a ferry flight to the maintenance base."""
    return (row.get("status") == DUE and mission.get("category") == "Ferry" and not mission.get("payload_lbs")
            and (mission.get("destination") or {}).get("icao") in MX_BASES)


def tick(con, now=None):
    """Returns airframes whose heavy check has finished to service, as fresh as after any check."""
    now = now or time.time()
    done = [r[0] for r in con.execute("SELECT reg FROM airframes WHERE status=? AND heavy_until IS NOT NULL AND heavy_until<=?", (IN_CHECK, now))]
    for reg in done:
        con.execute("""UPDATE airframes SET status='Available', note=NULL, hours_since_heavy=0, hours_since_check=0, heavy_until=NULL, updated=?
            WHERE reg=?""", (now, reg))
    # checks booked under the old three-week rule finish within the new 3-5 days
    con.execute("UPDATE airframes SET heavy_until=? WHERE status=? AND heavy_until>?", (now + HEAVY_CHECK_DAYS[1] * 86400, IN_CHECK, now + HEAVY_CHECK_DAYS[1] * 86400))
    # an airframe already waiting at one of the new bases goes straight into the hangar
    for r in con.execute(f"SELECT reg, location, hours_since_heavy FROM airframes WHERE status=? AND location IN ({','.join('?' * len(MX_BASES))})",
                         (DUE, *MX_BASES)).fetchall():
        until = now + check_days(r[0]) * 86400
        con.execute("UPDATE airframes SET status=?, note=?, heavy_until=?, updated=? WHERE reg=?",
                    (IN_CHECK, f"Heavy (C) check at {r[1]} until {time.strftime('%b %d', time.gmtime(until))}", until, now, r[0]))
    # an airframe that is due but came back to Available (a cancelled booking, a staff edit) is marked again
    for r in con.execute("SELECT reg, location, hours_since_heavy FROM airframes WHERE status='Available' AND hours_since_heavy>=?",
                         (HEAVY_CHECK_HOURS,)).fetchall():
        status, note, until = after_flight(r[2], r[1], "Available", now, r[0])
        con.execute("UPDATE airframes SET status=?, note=?, heavy_until=?, updated=? WHERE reg=?", (status, note, until, now, r[0]))
    return done


def ferry_job(frame, airport_obj, gc_distance_nm, fleet, job_id, expires, bonus):
    """The ferry flight that takes a heavy-check-due airframe to the nearest maintenance base."""
    base, _ = nearest_base(frame["location"], airport_obj, gc_distance_nm)
    o, d, ac = airport_obj(frame["location"]), airport_obj(base), fleet.get(frame["type"]) or {}
    if not o or not d or not ac:
        return None
    dist = gc_distance_nm(o["lat"], o["lon"], d["lat"], d["lon"])
    return {"id": job_id, "title": f"Ferry {frame['reg']} to {base} for its heavy check", "category": "Ferry", "priority": "High",
            "job": True, "job_kind": "ferry", "origin": o, "destination": d, "aircraft": [frame["type"]], "suggested_airframe": frame["reg"],
            "fixed_airframe": frame["reg"], "cargo": "Ferry flight (no cargo)", "payload_lbs": 0, "distance_nm": round(dist),
            "target_block_min": round(45 + dist / (ac.get("cruise_ktas") or 450) * 60 * 1.05), "expires": expires,
            "reward": int(round(dist * 0.06 / 10) * 10) + 30, "ferry_bonus": bonus, "heavy_check": True,
            "briefing": (f"{frame['reg']} ({ac.get('name', frame['type'])}) is due its heavy (C) check. Ferry it from {o['icao']} to the maintenance "
                         f"base at {base}, where it will spend {check_days(frame['reg'])} days in the hangar. No cargo. "
                         f"{round(dist):,} nm{' (beyond normal range: plan a fuel stop)' if dist > (ac.get('range_nm') or 9e9) * 0.95 else ''}.")}
