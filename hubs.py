"""PAC's hubs: the six founding hubs plus any the CEO opens from the CEO desk.

Opening a hub is a real business decision: a one-time setup cost (warehouse lease deposit, ground equipment, staff hiring)
and a monthly station cost from then on, both on the company ledger. Every part of the site that works with hubs (live
missions, trips, cargo orders, AOG spares, warehouses, the CEO desk, crew bases) reads the same list from here."""
from __future__ import annotations

import time

CORE = {"KCVG": "Cincinnati", "LIMC": "Milan Malpensa", "KMIA": "Miami", "OMDW": "Dubai World Central",
        "VHHH": "Hong Kong", "PANC": "Anchorage"}
OPEN_COST = 1_500_000          # one time: warehouse deposit, ground support equipment, hiring and training
MONTHLY_COST = 85_000          # every month: station lease, handling staff, utilities
MAX_HUBS = 12
_OPENED = {}                   # icao -> city, loaded from the database


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS hubs_opened (icao TEXT PRIMARY KEY, city TEXT, opened_at REAL, opened_by TEXT,
        closed_at REAL, last_billed TEXT)""")


def load(con):
    migrate(con)
    _OPENED.clear()
    _OPENED.update({r[0]: r[1] for r in con.execute("SELECT icao, city FROM hubs_opened WHERE closed_at IS NULL ORDER BY opened_at")})
    apply()


def names():
    return {**CORE, **_OPENED}


def codes():
    return list(names())


def apply():
    """Points every module's hub list at the current set (they read their module global at call time)."""
    import importlib
    allh = codes()
    for mod, attr, kind in (("cargo_orders", "HUBS", tuple), ("aog", "HUBS", list), ("shipments", "PAC_HUBS", set),
                            ("training", "HUBS", tuple), ("growth", "HUBS", tuple), ("trips", "HUBS", tuple),
                            ("fleet_market", "HUBS", tuple), ("va", "LIVE_HUBS", list), ("va", "DELIVERY_HUBS_LIST", tuple)):
        try:
            m = importlib.import_module(mod)
            if hasattr(m, attr):
                setattr(m, attr, kind(allh))
        except Exception as e:
            print("hubs:", mod, e)
    try:
        import ceo
        ceo.HUBS = dict(names())
    except Exception as e:
        print("hubs: ceo", e)
    try:
        import warehouses
        warehouses.HUBS = {h: warehouses.HUBS.get(h, 400_000) for h in allh}
    except Exception as e:
        print("hubs: warehouses", e)


def open_hub(con, icao, city, by, airports):
    import company
    icao = str(icao or "").upper().strip()
    if icao in names():
        raise ValueError(f"{icao} is already a PAC hub.")
    if icao not in airports:
        raise ValueError("Choose a known airport ICAO code.")
    if len(names()) >= MAX_HUBS:
        raise ValueError(f"PAC can run at most {MAX_HUBS} hubs. Close one first.")
    migrate(con)
    city = city or airports[icao].get("city") or airports[icao].get("name") or icao
    con.execute("INSERT OR REPLACE INTO hubs_opened (icao, city, opened_at, opened_by, closed_at, last_billed) VALUES (?,?,?,?,NULL,?)",
                (icao, city, time.time(), by, time.strftime("%Y-%m", time.gmtime())))
    company.post(con, "hub_opening", -OPEN_COST, f"New hub opened: {icao} {city} (warehouse, ground equipment, hiring)", f"hub-{icao}", by)
    load(con)
    return city


def close_hub(con, icao, by):
    icao = str(icao or "").upper()
    if icao in CORE:
        raise ValueError("The founding hubs can't be closed.")
    migrate(con)
    if not con.execute("UPDATE hubs_opened SET closed_at=? WHERE icao=? AND closed_at IS NULL", (time.time(), icao)).rowcount:
        raise ValueError(f"{icao} isn't an open hub.")
    load(con)


def tick(con, now=None):
    """Bills each opened hub's monthly station cost once a month."""
    import company
    migrate(con)
    month = time.strftime("%Y-%m", time.gmtime(now or time.time()))
    for icao, city, last in con.execute("SELECT icao, city, last_billed FROM hubs_opened WHERE closed_at IS NULL").fetchall():
        if last != month:
            company.post(con, "hub_station", -MONTHLY_COST, f"Station costs {icao} {city} ({month})", f"hubcost-{icao}-{month}", None, now)
            con.execute("UPDATE hubs_opened SET last_billed=? WHERE icao=?", (month, icao))
