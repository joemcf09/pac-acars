"""Warehouses (cargo sheds) that fill up.

Every station has a shed with room for so much freight. Waiting freight fills it: customer orders, transfers left by
pilots, freight held after a diversion. A busy shed is fine; a congested one (85% or more) stops accepting new customer
orders until pilots fly freight out, and the Missions board flags flights that help clear it.
"""
from __future__ import annotations

HUBS = {"KCVG": 220_000, "KMIA": 150_000, "LIMC": 150_000, "OMDW": 150_000, "VHHH": 150_000, "PANC": 150_000}
STATION_LBS = 60_000
LEVELS = ((100, "Full"), (85, "Congested"), (60, "Busy"), (0, "Normal"))


def capacity(station):
    return HUBS.get(station, STATION_LBS)


def level(pct):
    return next(name for floor, name in LEVELS if pct >= floor)


def fill(con):
    """{station: {"lbs", "capacity", "pct", "level", "shipments"}} for every station with freight waiting."""
    out = {}
    for r in con.execute("""SELECT current_station AS s, COUNT(*) AS n, COALESCE(SUM(gross_weight_lbs),0) AS lbs FROM cargo_shipments
            WHERE status IN ('AT_STATION','HELD_AT_STATION') GROUP BY current_station"""):
        cap = capacity(r["s"])
        pct = round(100 * r["lbs"] / cap)
        out[r["s"]] = {"station": r["s"], "lbs": round(r["lbs"]), "capacity": cap, "pct": pct, "level": level(pct), "shipments": r["n"]}
    return out


def embargoed(con, station, extra_lbs=0):
    """True when a new customer order would push this shed to 85% or more."""
    lbs = con.execute("""SELECT COALESCE(SUM(gross_weight_lbs),0) FROM cargo_shipments WHERE current_station=?
        AND status IN ('AT_STATION','HELD_AT_STATION')""", (station,)).fetchone()[0]
    return (lbs + extra_lbs) >= 0.85 * capacity(station)
