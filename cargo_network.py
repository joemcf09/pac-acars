"""Persistent records for the shipment documents generated for each booked flight."""
from __future__ import annotations

import json
import time
import uuid


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS cargo_shipments (
        id TEXT PRIMARY KEY,
        awb TEXT NOT NULL UNIQUE,
        booking_key TEXT NOT NULL,
        source_awb TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        current_station TEXT NOT NULL,
        status TEXT NOT NULL,
        shipper TEXT NOT NULL,
        consignee TEXT NOT NULL,
        commodity TEXT NOT NULL,
        pieces INTEGER NOT NULL,
        gross_weight_lbs REAL NOT NULL,
        chargeable_weight_kg REAL,
        priority TEXT,
        handling TEXT NOT NULL,
        security_status TEXT,
        data TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        UNIQUE (booking_key, source_awb)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS cargo_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shipment_id TEXT NOT NULL,
        event_key TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        event_time REAL NOT NULL,
        from_station TEXT,
        to_station TEXT,
        pilot_id TEXT,
        flight_number TEXT,
        pirep_id INTEGER,
        status TEXT NOT NULL,
        details TEXT NOT NULL
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_cargo_shipments_station ON cargo_shipments(current_station, status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_cargo_movements_shipment ON cargo_movements(shipment_id, event_time)")


def _next_awb(con, reserved):
    con.execute("CREATE TABLE IF NOT EXISTS cargo_awb_sequence (id INTEGER PRIMARY KEY CHECK(id=1), next_serial INTEGER NOT NULL)")
    con.execute("INSERT OR IGNORE INTO cargo_awb_sequence (id, next_serial) VALUES (1, 1000000)")
    while True:
        row = con.execute("SELECT next_serial FROM cargo_awb_sequence WHERE id=1").fetchone()
        serial = int(row[0])
        if serial > 9999999:
            raise RuntimeError("The PAC air waybill number range is exhausted.")
        con.execute("UPDATE cargo_awb_sequence SET next_serial=? WHERE id=1", (serial + 1,))
        awb = f"901-{serial:07d}{serial % 7}"
        if awb not in reserved and not con.execute("SELECT 1 FROM cargo_shipments WHERE awb=?", (awb,)).fetchone():
            return awb


def _rewrite_awbs(value, replacements):
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key != "cargo_source_awb":
                value[key] = _rewrite_awbs(item, replacements)
        return value
    if isinstance(value, list):
        for index, item in enumerate(value):
            value[index] = _rewrite_awbs(item, replacements)
        return value
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def register_booking(con, booking, pilot_id):
    dispatch = booking.get("dispatch") or {}
    listed = dispatch.get("shipments") or []
    if not listed:
        return []

    requested_at = booking.get("requested_at")
    if requested_at is None:
        raise ValueError("A booked cargo flight must have a booking timestamp.")
    booking_key = f"{pilot_id}:{requested_at}"
    origin = (dispatch.get("origin") or {}).get("icao") or (booking.get("mission", {}).get("origin") or {}).get("icao") or ""
    destination = (dispatch.get("destination") or {}).get("icao") or (booking.get("mission", {}).get("destination") or {}).get("icao") or ""
    now = time.time()
    registered = []
    replacements = {}
    source_awbs = set()
    reserved_awbs = set()

    for shipment in listed:
        source_awb = str(shipment.get("cargo_source_awb") or shipment.get("awb") or "").strip()
        if not source_awb:
            raise ValueError("A generated shipment is missing its air waybill.")
        if source_awb in source_awbs:
            raise ValueError(f"Multiple shipments share air waybill {source_awb}.")
        source_awbs.add(source_awb)

        row = None
        shipment_id = shipment.get("shipment_id")
        if shipment_id:
            row = con.execute("SELECT id, awb FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()
        if row is None:
            row = con.execute("SELECT id, awb FROM cargo_shipments WHERE booking_key=? AND source_awb=?",
                              (booking_key, source_awb)).fetchone()

        if row:
            shipment_id, permanent_awb = row["id"], row["awb"]
        else:
            shipment_id = uuid.uuid4().hex
            candidate = str(shipment["awb"])
            collision = con.execute("SELECT 1 FROM cargo_shipments WHERE awb=?", (candidate,)).fetchone()
            permanent_awb = _next_awb(con, reserved_awbs) if collision or candidate in reserved_awbs else candidate

        if permanent_awb in reserved_awbs:
            raise ValueError(f"Air waybill {permanent_awb} was assigned more than once in a booking.")
        reserved_awbs.add(permanent_awb)
        replacements[source_awb] = permanent_awb
        registered.append((shipment, shipment_id, source_awb, permanent_awb))

    _rewrite_awbs(dispatch, replacements)
    for shipment, shipment_id, source_awb, permanent_awb in registered:
        shipment["shipment_id"] = shipment_id
        shipment["cargo_source_awb"] = source_awb
        shipment["awb"] = permanent_awb
        payload = json.dumps(shipment, separators=(",", ":"), ensure_ascii=False)
        details = json.dumps({
            "service": shipment.get("service"),
            "units": shipment.get("units") or [],
            "uld_assignments": [
                {"position": p.get("pos"), "uld": p.get("uld"), "unit": p.get("unit")}
                for p in dispatch.get("positions") or [] if p.get("awb") == permanent_awb
            ],
        }, separators=(",", ":"))
        row = con.execute("SELECT id FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()
        if row:
            con.execute("""UPDATE cargo_shipments SET data=?, updated_at=? WHERE id=?""",
                        (payload, now, shipment_id))
        else:
            awb_doc = shipment.get("awb_doc") or {}
            screening = awb_doc.get("screen") or {}
            con.execute("""INSERT INTO cargo_shipments
                (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper, consignee,
                 commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status, data,
                 created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (shipment_id, permanent_awb, booking_key, source_awb, origin, destination, origin, "BOOKED",
                 (shipment.get("shipper") or {}).get("name") or "",
                 (shipment.get("consignee") or {}).get("name") or "",
                 shipment.get("contents") or "", int(shipment.get("pieces") or 0),
                 float(shipment.get("weight_lbs") or 0), awb_doc.get("chg_kg"),
                 dispatch.get("priority") or shipment.get("service"),
                 json.dumps(shipment.get("handling") or []), screening.get("status"), payload, now, now))
            con.execute("""INSERT OR IGNORE INTO cargo_movements
                (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number,
                 status, details)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (shipment_id, f"booking:{booking_key}:{source_awb}", "BOOKED", now, None, origin, pilot_id,
                 dispatch.get("flight"), "BOOKED", details))

    return [shipment_id for _, shipment_id, _, _ in registered]


def record_flight(con, booking, pirep, pirep_id, pilot_id):
    registered = register_booking(con, booking, pilot_id)
    dispatch = booking.get("dispatch") or {}
    shipments = dispatch.get("shipments") or []
    if len(registered) != len(shipments):
        raise RuntimeError("Not every dispatch shipment has a persistent cargo record.")
    actual_station = str(pirep.get("arr") or "").upper()
    flight_status = str(pirep.get("status") or "")
    if flight_status in ("Delivered", "Delivered late"):
        status = "DELIVERED"
    elif flight_status == "Diverted":
        status = "HELD_AT_STATION"
    else:
        status = "EXCEPTION"

    now = time.time()
    for shipment, shipment_id in zip(shipments, registered):
        row = con.execute("SELECT current_station FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()
        if not row:
            raise RuntimeError(f"Persistent shipment {shipment_id} was not created.")
        previous_station = row["current_station"]
        event_key = f"pirep:{pirep_id}:{shipment_id}"
        details = json.dumps({"flight_status": flight_status, "planned_destination": dispatch.get("destination", {}).get("icao"),
                              "cargo_status": status}, separators=(",", ":"))
        inserted = con.execute("""INSERT OR IGNORE INTO cargo_movements
            (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number,
             pirep_id, status, details)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (shipment_id, event_key, "FLIGHT_ARRIVAL", now, previous_station, actual_station, pilot_id,
             dispatch.get("flight"), pirep_id, status, details)).rowcount
        if inserted:
            con.execute("""UPDATE cargo_shipments SET current_station=?, status=?, updated_at=? WHERE id=?""",
                        (actual_station or previous_station, status, now, shipment_id))
