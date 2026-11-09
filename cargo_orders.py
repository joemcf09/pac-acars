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


def make_order(con, route, fleet, pilot, rng, now):
    """One or two consignments from a full paperwork run on this route, stored as waiting freight at its origin."""
    ac = [a for a in route.get("aircraft") or [] if a in fleet]
    if not ac:
        return []
    code = rng.choice(ac)
    seed = f"order-{uuid.uuid4().hex[:12]}"
    fake = {"mission": route, "aircraft": code, "ofp": None, "flight_number": route["id"], "requested_at": now,
            "airframe": None, "manifest_seed": seed}
    d = dispatch.generate(fake, fleet, pilot)
    if d.get("ferry") or not d.get("shipments"):
        return []
    shipments.enrich(d)
    origin, dest = route["origin"]["icao"], route["destination"]["icao"]
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
        deadline = now + hours * 3600
        data = dict(s, awb=awb, cargo_source_awb=s["awb"], shipment_id=sid, unit_details=units, order=True,
                    deadline=deadline, destination={"icao": dest, "city": route["destination"].get("city")})
        a = s.get("awb_doc") or {}
        con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination, current_station, status,
            shipper, consignee, commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status,
            reserved_booking_key, reserved_previous_status, data, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, awb, f"ORDER:{sid}", s["awb"], origin, dest, origin, "AT_STATION", s["shipper"]["name"], s["consignee"]["name"],
             s.get("contents") or "", int(s.get("pieces") or 0), float(s.get("weight_lbs") or 0), a.get("chg_kg"), s.get("service"),
             json.dumps(s.get("handling") or []), (a.get("screen") or {}).get("status"), None, None,
             json.dumps(data, separators=(",", ":"), ensure_ascii=False), now, now))
        con.execute("""INSERT OR IGNORE INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station, to_station,
            pilot_id, flight_number, status, details) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sid, f"order:{sid}", "ORDER_RECEIVED", now, None, origin, ORDER_PILOT, None, "AT_STATION",
             json.dumps({"deadline": deadline, "service": s.get("service"), "forwarder": s.get("agent")}, separators=(",", ":"))))
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
    rng = random.Random(f"orders|{int(now // TICK_S)}")
    for station in stations(routes, pol["stations"]):
        target = pol["hub_target"] if station in HUBS else pol["station_target"]
        need = target - _waiting(con, station)
        out_routes = [r for r in routes if r.get("category") == "Scheduled" and (r.get("origin") or {}).get("icao") == station
                      and (r.get("destination") or {}).get("icao") != station]
        tries = 0
        while need > 0 and out_routes and tries < target * 3:
            tries += 1
            try:
                made = make_order(con, rng.choice(out_routes), fleet, pilot, rng, now)
            except Exception as e:      # one bad route must never stop stocking the rest
                print("cargo order:", station, e)
                made = []
            need -= len(made)
            out["created"] += len(made)
    return out
