"""Crew rest: where pilots sleep when they're away from home base.

  * On a trip (a bid trip pairing): the company books and pays the hotel at the crew contract rate. The pilot pays nothing.
  * KCVG headquarters has 6 crew rest rooms: free for any pilot who isn't based there, first come, first served. Every
    pilot sleeping at HQ saves PAC a hotel night.
  * Sitting away from base by choice (not on a trip, not at home, HQ full or another city): the first night after landing
    is free (a normal turnaround); nights 2 to 4 are paid by the pilot from their wallet at the city's hotel rate; after
    that the pilot counts as off duty and charges stop, so nobody comes back from a break to an empty wallet.
A night is counted every 24 hours after the pilot's last landing at that station."""
from __future__ import annotations

import re
import time

HQ = "KCVG"
HQ_ROOMS = 6
FREE_NIGHTS = 1
CHARGED_NIGHTS = 3                      # nights 2-4
ACTIVE_DAYS = 14                        # a pilot without a flight in this long is at home, not in a hotel
CONTRACT = 0.6                          # crew contract rate: 60% of the walk-in price
# typical walk-in airport-hotel night, US dollars
RATES = {"KCVG": 139, "KMIA": 189, "KMEM": 129, "KSDF": 125, "KILN": 109, "KPAE": 159, "LIMC": 165, "OMDW": 180,
         "VHHH": 210, "PANC": 189}
REGION = {"K": 139, "C": 149, "M": 129, "T": 159, "S": 119, "E": 155, "L": 155, "O": 175, "V": 160, "R": 170, "Z": 120,
          "P": 189, "Y": 165, "N": 175, "F": 135, "H": 120, "D": 110, "G": 110, "W": 95, "U": 120, "A": 160, "B": 170}


def rate(icao):
    icao = str(icao or "").upper()
    return RATES.get(icao) or REGION.get(icao[:1], 150)


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS crew_rest (pilot_id TEXT PRIMARY KEY, station TEXT, since REAL, nights INTEGER DEFAULT 0,
        kind TEXT, updated REAL)""")


def _base(hub):
    m = re.search(r"\b[A-Z]{4}\b", str(hub or ""))
    return m.group(0) if m else HQ


def _on_trip(con, pid):
    try:
        return bool(con.execute("SELECT 1 FROM trips WHERE pilot_id=? AND status='bid'", (pid,)).fetchone())
    except Exception:
        return False


def _landed(con, pid, station, fallback):
    r = con.execute("SELECT MAX(filed_at) FROM pireps WHERE pilot_id=? AND arr=? AND demo=0", (pid, station)).fetchone()
    return (r and r[0]) or fallback


def tick(con, add_tx, now=None):
    """Brings everyone's crew rest up to date and charges any whole nights that have passed."""
    import company
    now = now or time.time()
    migrate(con)
    pilots = con.execute("SELECT id, hub, location FROM pilots WHERE COALESCE(status,'Active')='Active'").fetchall()
    rest = {r[0]: r for r in con.execute("SELECT pilot_id, station, since, nights, kind FROM crew_rest")}
    away = []
    # only pilots actually flying the line need a bed: no flight in the last 14 days (or never) means they're at home
    recent = {r[0] for r in con.execute("SELECT DISTINCT pilot_id FROM pireps WHERE demo=0 AND filed_at>?", (now - ACTIVE_DAYS * 86400,))}
    for pid, hub, loc in pilots:
        loc = (loc or "").upper()
        if not loc or loc == _base(hub) or pid not in recent:
            con.execute("DELETE FROM crew_rest WHERE pilot_id=?", (pid,))
            continue
        r = rest.get(pid)
        if not r or r[1] != loc:
            since = max(_landed(con, pid, loc, now), now - 86400)   # no back-billing for nights before this started
            con.execute("INSERT OR REPLACE INTO crew_rest (pilot_id, station, since, nights, kind, updated) VALUES (?,?,?,?,?,?)",
                        (pid, loc, since, 0, None, now))
            r = (pid, loc, since, 0, None)
        away.append(r)
    # HQ rooms go to the earliest arrivals who aren't on a company trip
    hq_queue = sorted((r for r in away if r[1] == HQ and not _on_trip(con, r[0])), key=lambda r: r[2])
    in_rooms = {r[0] for r in hq_queue[:HQ_ROOMS]}
    for pid, station, since, nights, _ in away:
        due = int(max(0, now - since) // 86400)          # whole nights since landing
        kind = "trip" if _on_trip(con, pid) else "hq" if pid in in_rooms else "own"
        for n in range(nights + 1, due + 1):
            if kind == "trip":
                company.post(con, "hotel", -round(rate(station) * CONTRACT), f"Crew hotel {station}, {pid} (trip layover, night {n})",
                             f"hotel-{pid}-{int(since)}-{n}", None, since + n * 86400)
            elif kind == "own" and FREE_NIGHTS < n <= FREE_NIGHTS + CHARGED_NIGHTS:
                add_tx(pid, "hotel", -rate(station), f"Hotel at {station}, night {n} (away from base, not on a trip)", None, con)
        con.execute("UPDATE crew_rest SET nights=?, kind=?, updated=? WHERE pilot_id=?", (max(nights, due), kind, now, pid))


def status(con, pid, now=None):
    """What this pilot's crew rest looks like right now."""
    now = now or time.time()
    migrate(con)
    r = con.execute("SELECT station, since, nights, kind FROM crew_rest WHERE pilot_id=?", (pid,)).fetchone()
    if not r:
        return {"away": False}
    station, since, nights, kind = r
    n = int(max(0, now - since) // 86400) + 1             # the night they're on now
    out = {"away": True, "station": station, "night": n, "kind": kind, "rate": rate(station)}
    if kind == "trip":
        out["text"] = f"On a trip: PAC pays your hotel at {station}."
    elif kind == "hq":
        out["text"] = "Sleeping in the KCVG crew rest rooms at headquarters, free of charge."
    elif n <= FREE_NIGHTS:
        out["text"] = f"First night at {station} is free. From tomorrow you pay ${rate(station)} a night unless you fly on or head home."
    elif n <= FREE_NIGHTS + CHARGED_NIGHTS:
        out["text"] = f"Hotel at {station}: ${rate(station)} a night from your wallet (night {n}). Charges stop after night {FREE_NIGHTS + CHARGED_NIGHTS}."
    else:
        out["text"] = f"Off duty at {station}: no more hotel charges."
    return out


def hq(con):
    migrate(con)
    rows = con.execute("""SELECT c.pilot_id, p.name, c.since FROM crew_rest c LEFT JOIN pilots p ON p.id=c.pilot_id
        WHERE c.kind='hq' ORDER BY c.since""").fetchall()
    return {"rooms": HQ_ROOMS, "used": len(rows), "guests": [{"pilot_id": r[0], "name": r[1], "since": r[2]} for r in rows],
            "saved_per_night": len(rows) * round(rate(HQ) * CONTRACT)}


def register(app, g):
    from flask import jsonify

    @app.get("/api/crew-rest")
    def crew_rest_me():
        with g["db"]() as con:
            tick(con, g["va"].add_tx)            # up to date the moment the pilot looks (after a jumpseat, say)
            return jsonify({"me": status(con, g["va"].current_pilot_id()), "hq": hq(con)})
