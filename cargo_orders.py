"""Customer orders: freight that exists before any pilot books a flight.

PAC's hubs and busiest stations keep a stock of real-company consignments waiting for their next leg, the way a
cargo airline's warehouse always has freight booked by forwarders. Orders are built by the same paperwork engine
as a booked flight (units, handling codes, dangerous goods, air waybill), stored as persistent shipments at the
station, and loaded onto a flight like any other waiting freight.

Each order has a deadline. One nobody picks up goes to "another carrier" a day after its deadline: it leaves the
inventory with a logged movement and costs no one anything. Stocking runs at most every 30 minutes, when someone
opens a cargo page, so there's no background process to keep alive.
"""
from __future__ import annotations

import json
import random
import time
import uuid

import cargo_network
import dispatch
import lanes as lane_rep
import seasons
import warehouses
import shipments

ORDER_PILOT = "PAC-OPS"
TICK_S = 30 * 60
HUBS = ("KCVG", "KMIA", "LIMC", "OMDW", "VHHH", "PANC")
SERVICE_HOURS = {"EXPRESS": 36, "PRIORITY": 48, "TEMP CONTROLLED": 48, "TEMP CONTROLLED FROZEN": 48, "LIVE ANIMALS": 36,
                 "DANGEROUS GOODS": 96, "VALUABLES": 48, "AOG": 24, "HUMANITARIAN": 72}


def policy(st):
    def num(k, d, lo, hi):
        try:
            return max(lo, min(hi, int(float(st.get(k, d)))))
        except (TypeError, ValueError):
            return d
    return {"enabled": st.get("cargo_orders_enabled", True) is not False, "hub_target": num("cargo_orders_hub_target", 6, 0, 40),
            "station_target": num("cargo_orders_station_target", 2, 0, 20), "stations": num("cargo_orders_stations", 12, 0, 60)}


def stations(routes, n):
    """The hubs, then the stations with the most scheduled departures."""
    dep = {}
    for r in routes:
        if r.get("category") == "Scheduled":
            o = (r.get("origin") or {}).get("icao")
            dep[o] = dep.get(o, 0) + 1
    busy = [s for s, _ in sorted(dep.items(), key=lambda kv: -kv[1]) if s not in HUBS]
    return [h for h in HUBS if h in dep] + busy[:n]


def _waiting(con, station):
    return con.execute("""SELECT COUNT(*) FROM cargo_shipments WHERE current_station=? AND status IN ('AT_STATION','HELD_AT_STATION')
        AND reserved_booking_key IS NULL""", (station,)).fetchone()[0]


def _fits(fleet, route, weight):
    caps = [(fleet.get(a) or {}).get("max_payload_lbs") or 0 for a in route.get("aircraft") or []]
    return any(c >= weight for c in caps)


_net = {"airports": [], "routes": []}
TRUCK_SHARE = 0.3


def learn(routes):
    routes = list(routes)
    _net.update(routes=routes, airports=sorted(({(r.get("destination") or {}).get("icao") for r in routes} |
                                               {(r.get("origin") or {}).get("icao") for r in routes}) - {None}))


def _truck_final(route, rng):
    """Sometimes a forwarder books freight for a town near the route's destination: PAC flies it in and the last
    leg (up to 300 nm) goes by truck. Only airports PAC can't fly on to from the destination."""
    dest = route["destination"]["icao"]
    if rng.random() >= TRUCK_SHARE:
        return None
    near = [a for a in _net["airports"] if a not in (dest, route["origin"]["icao"]) and cargo_network.nearby(dest, a)
            and not cargo_network.has_route(_net["routes"], dest, a)]
    return rng.choice(sorted(near)) if near else None


def make_order(con, route, fleet, pilot, rng, now, season=None):
    """One or two consignments from a full paperwork run on this route, stored as waiting freight at its origin."""
    ac = [a for a in route.get("aircraft") or [] if a in fleet]
    if not ac:
        return []
    code = rng.choice(ac)
    seed = f"order-{uuid.uuid4().hex[:12]}"
    if season:
        route = dict(route, cargo=season["cargo"])      # the dispatcher builds that season's freight
    fake = {"mission": route, "aircraft": code, "ofp": None, "flight_number": route["id"], "requested_at": now,
            "airframe": None, "manifest_seed": seed}
    d = dispatch.generate(fake, fleet, pilot)
    if d.get("ferry") or not d.get("shipments"):
        return []
    shipments.enrich(d)
    origin, dest = route["origin"]["icao"], route["destination"]["icao"]
    final = None if season else _truck_final(route, rng)
    small_cap = min((fleet.get(a) or {}).get("max_payload_lbs") or 1e9 for a in ac)
    pool = [s for s in d["shipments"] if (s.get("weight_lbs") or 0) <= small_cap * 0.5 and (s.get("destination") or {}).get("icao") in (None, dest)]
    rng.shuffle(pool)
    made = []
    for s in pool[:rng.choice((1, 1, 2))]:
        units = [{**p, "dg_entry": next((g for g in d.get("dg") or [] if g.get("pos") == p.get("pos") and g.get("awb") == s["awb"]), None)}
                 for p in d.get("positions") or [] if p.get("awb") == s["awb"]]
        if not units:
            continue
        awb = cargo_network._next_awb(con, set())
        sid = uuid.uuid4().hex
        hours = SERVICE_HOURS.get(s.get("service"), 72) + rng.choice((0, 12, 24))
        deadline = now + hours * 3600 + (12 * 3600 if final else 0)     # the truck needs its time too
        data = dict(s, awb=awb, cargo_source_awb=s["awb"], shipment_id=sid, unit_details=units, order=True,
                    deadline=deadline,
                    destination={"icao": final or dest, "city": None if final else route["destination"].get("city")},
                    **({"truck_from": dest} if final else {}),
                    **({"season": season["id"], "season_name": season["name"]} if season else {}))
        a = s.get("awb_doc") or {}
        con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status,
            shipper, consignee, commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status,
            reserved_booking_key, reserved_previous_status, data, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, awb, f"ORDER:{sid}", s["awb"], origin, final or dest, origin, "AT_STATION", s["shipper"]["name"], s["consignee"]["name"],
             s.get("contents") or "", int(s.get("pieces") or 0), float(s.get("weight_lbs") or 0), a.get("chg_kg"), s.get("service"),
             json.dumps(s.get("handling") or []), (a.get("screen") or {}).get("status"), None, None,
             json.dumps(data, separators=(",", ":"), ensure_ascii=False), now, now))
        con.execute("""INSERT OR IGNORE INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station, to_station,
            pilot_id, flight_number, status, details) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sid, f"order:{sid}", "ORDER_RECEIVED", now, None, origin, ORDER_PILOT, None, "AT_STATION",
             json.dumps({"deadline": deadline, "service": s.get("service"), "forwarder": s.get("agent"),
                         **({"truck_from": dest} if final else {}),
                         **({"season": season["name"]} if season else {})}, separators=(",", ":"))))
        made.append(awb)
    return made


def withdraw_stale(con, now):
    """Orders nobody took within a day of their deadline go to another carrier."""
    gone = 0
    for row in con.execute("""SELECT id, current_station, data FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%'
            AND status='AT_STATION' AND reserved_booking_key IS NULL AND current_station=origin""").fetchall():
        try:
            deadline = json.loads(row["data"]).get("deadline") or 0
        except (TypeError, ValueError):
            continue
        if deadline and now > deadline + 86400:
            con.execute("UPDATE cargo_shipments SET status='WITHDRAWN', updated_at=? WHERE id=?", (now, row["id"]))
            con.execute("""INSERT OR IGNORE INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station, to_station,
                pilot_id, status, details) VALUES (?,?,?,?,?,?,?,?,?)""",
                (row["id"], f"withdrawn:{row['id']}", "ORDER_WITHDRAWN", now, row["current_station"], None, ORDER_PILOT, "WITHDRAWN",
                 json.dumps({"reason": "Not picked up before its deadline; the forwarder moved it to another carrier."})))
            gone += 1
    return gone


def tick(con, routes, fleet, pilot, st, now=None, force=False):
    """Top up each station's waiting freight to its target. Returns how many orders were created and withdrawn."""
    now = now or time.time()
    pol = policy(st)
    out = {"created": 0, "withdrawn": 0}
    if not pol["enabled"]:
        return out
    con.execute("CREATE TABLE IF NOT EXISTS cargo_orders_state (id INTEGER PRIMARY KEY CHECK(id=1), last REAL NOT NULL)")
    last = con.execute("SELECT last FROM cargo_orders_state WHERE id=1").fetchone()
    if not force and last and now - last[0] < TICK_S:
        return out
    con.execute("INSERT INTO cargo_orders_state (id, last) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET last=excluded.last", (now,))
    out["withdrawn"] = withdraw_stale(con, now)
    routes = list(routes)
    learn(routes)
    rng = random.Random(f"orders|{int(now // TICK_S)}")
    try:
        reps = lane_rep.compute(con, now)
    except Exception as e:            # reputation shapes demand; it must never stop stocking
        print("lane reputation:", e)
        reps = {}
    out["embargoed"] = []
    for station in stations(routes, pol["stations"]):
        target = pol["hub_target"] if station in HUBS else pol["station_target"]
        need = target - _waiting(con, station)
        if need > 0 and warehouses.embargoed(con, station):
            out["embargoed"].append(station)      # the shed is congested: no new orders until pilots fly some out
            continue
        out_routes = [r for r in routes if r.get("category") == "Scheduled" and (r.get("origin") or {}).get("icao") == station
                      and (r.get("destination") or {}).get("icao") != station]
        tries = 0
        while need > 0 and out_routes and tries < target * 3:
            tries += 1
            if warehouses.embargoed(con, station):
                out["embargoed"].append(station)
                break
            try:
                pick = rng.choices(out_routes, weights=[lane_rep.weight(reps, station, (r.get("destination") or {}).get("icao"))
                                                        for r in out_routes])[0]
                made = make_order(con, pick, fleet, pilot, rng, now)
            except Exception as e:      # one bad route must never stop stocking the rest
                print("cargo order:", station, e)
                made = []
            need -= len(made)
            out["created"] += len(made)
    out["season"] = stock_seasons(con, routes, fleet, pilot, rng, now, pol)
    return out


SEASON_TARGET = 6          # waiting orders per active season, across its lanes


def stock_seasons(con, routes, fleet, pilot, rng, now, pol):
    """While a real cargo season runs, forwarders book its freight on PAC's matching routes."""
    made = 0
    day = __import__("datetime").datetime.utcfromtimestamp(now).date()
    for season in seasons.active(day):
        lanes = [r for r in seasons.routes_for(season, routes) if not warehouses.embargoed(con, (r.get("origin") or {}).get("icao"))]
        if not lanes:
            continue
        have = con.execute("""SELECT COUNT(*) FROM cargo_shipments WHERE booking_key LIKE 'ORDER:%' AND status='AT_STATION'
            AND json_extract(data,'$.season')=?""", (season["id"],)).fetchone()[0]
        tries = 0
        while have < SEASON_TARGET and tries < SEASON_TARGET * 3:
            tries += 1
            lane = rng.choice(lanes)
            if warehouses.embargoed(con, (lane.get("origin") or {}).get("icao")):
                continue
            try:
                n = len(make_order(con, lane, fleet, pilot, rng, now, season=season))
            except Exception as e:
                print("season order:", season["id"], e)
                n = 0
            have += n
            made += n
        announce(con, season, day, now)
    return made


def announce(con, season, day, now):
    """One news post per season per year, when it opens."""
    con.execute("CREATE TABLE IF NOT EXISTS cargo_seasons_announced (id TEXT NOT NULL, year INTEGER NOT NULL, PRIMARY KEY (id, year))")
    start = seasons.starts(season, day)
    if con.execute("SELECT 1 FROM cargo_seasons_announced WHERE id=? AND year=?", (season["id"], start.year)).fetchone():
        return
    con.execute("INSERT INTO cargo_seasons_announced (id, year) VALUES (?,?)", (season["id"], start.year))
    try:
        end = __import__("datetime").date(start.year + (1 if season["window"][1] < season["window"][0] else 0), *season["window"][1])
        con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                    (now, "event", f"Cargo season: {season['name']}",
                     f"{season['blurb']} Until {end.strftime('%B')} {end.day}, extra freight ({season['cargo']}) is waiting on PAC's routes. "
                     "Find it on the Cargo inventory.", 0, now + 14 * 86400, "PAC Operations"))
    except Exception as e:      # no news table in a bare test database: the season still runs
        print("season news:", e)


ROUTE_TOPUP_S = 2 * 3600


def ensure_route(con, route, fleet, pilot, aircraft, st, now=None, routes=None):
    """When a pilot plans a scheduled flight, make sure there's customer freight waiting for that exact leg: at least
    two shipments, or a fifth of the chosen aircraft's payload, whichever comes first. At most once every two hours per
    route, so reopening the load sheet doesn't keep adding freight. Returns how many orders were added."""
    now = now or time.time()
    if not policy(st)["enabled"] or route.get("category") != "Scheduled" or route.get("charter"):
        return 0
    origin, dest = (route.get("origin") or {}).get("icao"), (route.get("destination") or {}).get("icao")
    if not origin or not dest or origin == dest:
        return 0
    if routes is not None and not _net["routes"]:
        learn(routes)
    if warehouses.embargoed(con, origin):
        return 0
    con.execute("CREATE TABLE IF NOT EXISTS cargo_orders_route (route_id TEXT PRIMARY KEY, last REAL NOT NULL)")
    last = con.execute("SELECT last FROM cargo_orders_route WHERE route_id=?", (route["id"],)).fetchone()
    if last and now - last[0] < ROUTE_TOPUP_S:
        return 0
    con.execute("INSERT INTO cargo_orders_route (route_id, last) VALUES (?, ?) ON CONFLICT(route_id) DO UPDATE SET last=excluded.last",
                (route["id"], now))
    cap = (fleet.get(aircraft) or {}).get("max_payload_lbs") or 0
    n, w = con.execute("""SELECT COUNT(*), COALESCE(SUM(gross_weight_lbs),0) FROM cargo_shipments WHERE current_station=? AND destination=?
        AND status IN ('AT_STATION','HELD_AT_STATION') AND reserved_booking_key IS NULL""", (origin, dest)).fetchone()
    rng = random.Random(f"route|{route['id']}|{int(now // ROUTE_TOPUP_S)}")

    made, tries = 0, 0
    while (n < 2 and (not cap or w < cap * 0.2)) and tries < 4:
        tries += 1
        try:
            new = make_order(con, route, fleet, pilot, rng, now)
        except Exception as e:
            print("cargo order (route):", route.get("id"), e)
            break
        for awb in new:
            w += con.execute("SELECT gross_weight_lbs FROM cargo_shipments WHERE awb=?", (awb,)).fetchone()[0] or 0
        n += len(new)
        made += len(new)
    return made
