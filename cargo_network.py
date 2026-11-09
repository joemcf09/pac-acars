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
        reserved_booking_key TEXT,
        reserved_previous_status TEXT,
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
    columns = {row["name"] for row in con.execute("PRAGMA table_info(cargo_shipments)")}
    if "reserved_booking_key" not in columns:
        con.execute("ALTER TABLE cargo_shipments ADD COLUMN reserved_booking_key TEXT")
    if "reserved_previous_status" not in columns:
        con.execute("ALTER TABLE cargo_shipments ADD COLUMN reserved_previous_status TEXT")


def has_route(routes, origin, destination):
    return any((r.get("origin") or {}).get("icao") == origin
               and (r.get("destination") or {}).get("icao") == destination
               and r.get("category") == "Scheduled" for r in routes)


NEAR_NM = 300
_ctx = {"near": None, "routes": None}


def set_context(near=None, routes=None):
    """near(a, b) -> nautical miles between two airports (or None); routes() -> PAC's routes. Set once by the app."""
    _ctx.update(near=near, routes=routes)


def nearby(a, b):
    """Two different airports close enough for the last leg to go by road (road feeder service)."""
    if not a or not b or a == b or not _ctx["near"]:
        return False
    d = _ctx["near"](a, b)
    return d is not None and d <= NEAR_NM


def reachable(routes, destination, final):
    """(ok, by_truck): the shipment can travel on a flight to `destination`: it's going there, PAC flies on from there,
    or its final airport is within 300 nm and the last leg goes by truck."""
    if final == destination or has_route(routes, destination, final):
        return True, False
    return (True, True) if nearby(destination, final) else (False, False)


def transfer_options(con, origin, destination, routes):
    origin, destination = str(origin or "").upper(), str(destination or "").upper()
    rows = con.execute("""SELECT id, awb, origin, destination, current_station, status, shipper, consignee,
        commodity, pieces, gross_weight_lbs, data
        FROM cargo_shipments
        WHERE current_station=? AND status IN ('AT_STATION','HELD_AT_STATION') AND reserved_booking_key IS NULL
        ORDER BY updated_at, awb""", (origin,)).fetchall()
    available = []
    routes = list(routes)
    for row in rows:
        ok, truck = reachable(routes, destination, row["destination"])
        if not ok:
            continue
        item = dict(row)
        item["truck"] = truck
        try:
            item["data"] = json.loads(item["data"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Persistent cargo {item['awb']} has invalid shipment data.") from exc
        available.append(item)
    return available


def selected_transfers(con, shipment_ids, origin, destination, routes, booking_key=None):
    if not isinstance(shipment_ids, list) or len(shipment_ids) > 100:
        raise ValueError("Choose no more than 100 transfer shipments.")
    if any(not isinstance(shipment_id, str) or len(shipment_id) != 32
           or any(char not in "0123456789abcdef" for char in shipment_id) for shipment_id in shipment_ids):
        raise ValueError("A selected transfer shipment is invalid.")
    if len(set(shipment_ids)) != len(shipment_ids):
        raise ValueError("A transfer shipment was selected more than once.")
    if booking_key:
        allowed = {}
        for shipment_id in shipment_ids:
            row = con.execute("""SELECT id, awb, origin, destination, current_station, status, shipper, consignee,
                commodity, pieces, gross_weight_lbs, reserved_booking_key, data
                FROM cargo_shipments WHERE id=?""", (shipment_id,)).fetchone()
            if (not row or row["current_station"] != str(origin or "").upper() or row["status"] != "BOOKED"
                    or row["reserved_booking_key"] != booking_key):
                raise ValueError(f"Transfer shipment {shipment_id} is no longer reserved on this flight.")
            if not reachable(list(routes), str(destination or "").upper(), row["destination"])[0]:
                raise ValueError(f"Transfer shipment {row['awb']} is not routed through {destination}.")
            item = dict(row)
            try:
                item["data"] = json.loads(item["data"])
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Persistent cargo {item['awb']} has invalid shipment data.") from exc
            allowed[shipment_id] = item
    else:
        allowed = {item["id"]: item for item in transfer_options(con, origin, destination, routes)}
    selected = []
    for shipment_id in shipment_ids:
        item = allowed.get(shipment_id)
        if not item:
            raise ValueError("A selected shipment is no longer available for this route. Refresh the load sheet.")
        selected.append(item)
    return selected


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
    released = set(booking.get("cargo_released_ids") or [])     # waiting freight handed back while this booking sat idle
    listed = [s for s in listed if s.get("shipment_id") not in released]
    selected_ids = set(booking.get("cargo_transfer_ids") or []) - released
    listed_transfer_ids = {shipment.get("shipment_id") for shipment in listed if shipment.get("transfer")}
    if selected_ids != listed_transfer_ids:
        raise ValueError("The selected transfer cargo does not match the dispatch manifest.")
    registered = []
    completed_transfers = set()
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
        reserved_previous_status = None
        existing_status = None
        shipment_id = shipment.get("shipment_id")
        if shipment_id:
            row = con.execute("""SELECT id, awb, current_station, status, reserved_booking_key,
                reserved_previous_status FROM cargo_shipments WHERE id=?""",
                              (shipment_id,)).fetchone()
        if row is None:
            row = con.execute("""SELECT id, awb, current_station, status, reserved_booking_key,
                reserved_previous_status FROM cargo_shipments WHERE booking_key=? AND source_awb=?""",
                              (booking_key, source_awb)).fetchone()

        if row:
            shipment_id, permanent_awb = row["id"], row["awb"]
            existing_status = row["status"]
            if shipment_id in selected_ids:
                transfer_event = con.execute("""SELECT 1 FROM cargo_movements WHERE shipment_id=? AND event_key=?""",
                                             (shipment_id, f"transfer-booking:{booking_key}:{shipment_id}")).fetchone()
                completed = bool(transfer_event and row["reserved_booking_key"] is None
                                 and row["current_station"] != origin)
                if completed:
                    completed_transfers.add(shipment_id)
                else:
                    already_reserved = (row["status"] == "BOOKED" and row["reserved_booking_key"] == booking_key)
                    if row["current_station"] != origin or (
                            row["status"] not in ("AT_STATION", "HELD_AT_STATION") and not already_reserved):
                        raise ValueError(f"Transfer shipment {permanent_awb} is no longer at {origin}.")
                    if row["reserved_booking_key"] not in (None, booking_key):
                        raise ValueError(f"Transfer shipment {permanent_awb} is already booked on another flight.")
                    reserved_previous_status = row["reserved_previous_status"] or row["status"]
            elif row["reserved_booking_key"] == booking_key:
                raise ValueError(f"Reserved transfer shipment {permanent_awb} is missing from this dispatch.")
        else:
            if shipment_id in selected_ids:
                raise ValueError(f"Transfer shipment {source_awb} no longer exists.")
            shipment_id = uuid.uuid4().hex
            candidate = str(shipment["awb"])
            collision = con.execute("SELECT 1 FROM cargo_shipments WHERE awb=?", (candidate,)).fetchone()
            permanent_awb = _next_awb(con, reserved_awbs) if collision or candidate in reserved_awbs else candidate

        if permanent_awb in reserved_awbs:
            raise ValueError(f"Air waybill {permanent_awb} was assigned more than once in a booking.")
        reserved_awbs.add(permanent_awb)
        replacements[source_awb] = permanent_awb
        registered.append((shipment, shipment_id, source_awb, permanent_awb, existing_status, reserved_previous_status))

    _rewrite_awbs(dispatch, replacements)
    for shipment, shipment_id, source_awb, permanent_awb, existing_status, reserved_previous_status in registered:
        shipment["shipment_id"] = shipment_id
        shipment["cargo_source_awb"] = source_awb
        shipment["awb"] = permanent_awb
        shipment["unit_details"] = [
            {**p, "dg_entry": next((g for g in dispatch.get("dg") or []
                                    if g.get("pos") == p.get("pos") and g.get("awb") == permanent_awb), None)}
            for p in dispatch.get("positions") or [] if p.get("awb") == permanent_awb
        ]
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
            con.execute("""UPDATE cargo_shipments SET data=?, status=?, reserved_booking_key=?, reserved_previous_status=?,
                updated_at=? WHERE id=?""",
                (payload, "BOOKED" if shipment_id in selected_ids and shipment_id not in completed_transfers else existing_status,
                 booking_key if shipment_id in selected_ids and shipment_id not in completed_transfers else None,
                 reserved_previous_status if shipment_id in selected_ids and shipment_id not in completed_transfers else None,
                 now, shipment_id))
        else:
            awb_doc = shipment.get("awb_doc") or {}
            screening = awb_doc.get("screen") or {}
            final_destination = (shipment.get("destination") or {}).get("icao") or destination
            con.execute("""INSERT INTO cargo_shipments
                (id, awb, booking_key, source_awb, origin, destination, current_station, status, shipper, consignee,
                 commodity, pieces, gross_weight_lbs, chargeable_weight_kg, priority, handling, security_status,
                 reserved_booking_key, reserved_previous_status, data, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (shipment_id, permanent_awb, booking_key, source_awb, origin, final_destination, origin, "BOOKED",
                 (shipment.get("shipper") or {}).get("name") or "",
                 (shipment.get("consignee") or {}).get("name") or "",
                 shipment.get("contents") or "", int(shipment.get("pieces") or 0),
                 float(shipment.get("weight_lbs") or 0), awb_doc.get("chg_kg"),
                 dispatch.get("priority") or shipment.get("service"),
                 json.dumps(shipment.get("handling") or []), screening.get("status"), None, None, payload, now, now))
            con.execute("""INSERT OR IGNORE INTO cargo_movements
                (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number,
                 status, details)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (shipment_id, f"booking:{booking_key}:{source_awb}", "BOOKED", now, None, origin, pilot_id,
                 dispatch.get("flight"), "BOOKED", details))
        if shipment_id in selected_ids:
            con.execute("""INSERT OR IGNORE INTO cargo_movements
                (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number,
                 status, details)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (shipment_id, f"transfer-booking:{booking_key}:{shipment_id}", "TRANSFER_BOOKED", now, origin, destination,
                 pilot_id, dispatch.get("flight"), "BOOKED", details))

    return [shipment_id for _, shipment_id, _, _, _, _ in registered]


def record_flight(con, booking, pirep, pirep_id, pilot_id):
    registered = register_booking(con, booking, pilot_id)
    dispatch = booking.get("dispatch") or {}
    released = set(booking.get("cargo_released_ids") or [])
    shipments = [s for s in dispatch.get("shipments") or [] if s.get("shipment_id") not in released]
    if len(registered) != len(shipments):
        raise RuntimeError("Not every dispatch shipment has a persistent cargo record.")
    actual_station = str(pirep.get("arr") or "").upper()
    flight_status = str(pirep.get("status") or "")
    care_by_awb = {c.get("awb"): {"label": c.get("label"), "status": c.get("status"), "log": c.get("log")}
                   for c in pirep.get("cargo_care") or [] if c.get("awb")}

    now = time.time()
    for shipment, shipment_id in zip(shipments, registered):
        row = con.execute("SELECT current_station, destination FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()
        if not row:
            raise RuntimeError(f"Persistent shipment {shipment_id} was not created.")
        previous_station = row["current_station"]
        trucked = False
        if flight_status in ("Delivered", "Delivered late"):
            if actual_station == row["destination"]:
                status = "DELIVERED_LATE" if flight_status == "Delivered late" else "DELIVERED"
            elif nearby(actual_station, row["destination"]) and not (
                    _ctx["routes"] and has_route(list(_ctx["routes"]()), actual_station, row["destination"])):
                status = "DELIVERED_LATE" if flight_status == "Delivered late" else "DELIVERED"
                trucked = True           # the last leg goes by road from the arrival airport
            else:
                status = "AT_STATION"
        elif flight_status == "Diverted":
            status = "HELD_AT_STATION"
        else:
            status = "EXCEPTION"
        event_key = f"pirep:{pirep_id}:{shipment_id}"
        details = json.dumps({"flight_status": flight_status, "planned_destination": dispatch.get("destination", {}).get("icao"),
                              "final_destination": row["destination"], "cargo_status": status,
                              **({"trucked_from": actual_station} if trucked else {}),
                              **({"care": care_by_awb[shipment.get("awb")]} if shipment.get("awb") in care_by_awb else {})},
                             separators=(",", ":"))
        inserted = con.execute("""INSERT OR IGNORE INTO cargo_movements
            (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number,
             pirep_id, status, details)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (shipment_id, event_key, "FLIGHT_ARRIVAL", now, previous_station, actual_station, pilot_id,
             dispatch.get("flight"), pirep_id, status, details)).rowcount
        if inserted:
            con.execute("""UPDATE cargo_shipments SET current_station=?, status=?, reserved_booking_key=NULL,
                reserved_previous_status=NULL, updated_at=? WHERE id=?""",
                (row["destination"] if trucked else (actual_station or previous_station), status, now, shipment_id))


IDLE_RELEASE_S = 72 * 3600


def release_idle(con, bookings, flying=(), now=None, idle_s=IDLE_RELEASE_S):
    """Waiting freight a pilot picked for a flight they haven't flown in three days goes back on the shelf for
    someone else. The booking itself stays: if the pilot flies it later, it files normally without that freight.
    Returns {pilot_id: [shipment ids released]} so the caller can note it on each booking."""
    now = now or time.time()
    out = {}
    for pilot_id, booking in bookings:
        req = booking.get("requested_at")
        if req is None or pilot_id in flying or now - float(req) < idle_s:
            continue
        key = f"{pilot_id}:{req}"
        rows = con.execute("""SELECT id, current_station, reserved_previous_status FROM cargo_shipments
            WHERE reserved_booking_key=? AND booking_key!=?""", (key, key)).fetchall()
        for row in rows:
            status = row["reserved_previous_status"] or "AT_STATION"
            con.execute("""UPDATE cargo_shipments SET status=?, reserved_booking_key=NULL, reserved_previous_status=NULL,
                updated_at=? WHERE id=? AND reserved_booking_key=?""", (status, now, row["id"], key))
            con.execute("""INSERT OR IGNORE INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station,
                to_station, pilot_id, flight_number, status, details) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (row["id"], f"transfer-idle:{key}:{row['id']}", "TRANSFER_RELEASED", now, row["current_station"],
                 row["current_station"], pilot_id, (booking.get("dispatch") or {}).get("flight"), status,
                 json.dumps({"reason": "The booked flight wasn't flown within three days."})))
            out.setdefault(pilot_id, []).append(row["id"])
    return out


def release_booking(con, booking, pilot_id):
    requested_at = booking.get("requested_at")
    if requested_at is None:
        return
    booking_key = f"{pilot_id}:{requested_at}"
    now = time.time()
    rows = con.execute("""SELECT id, current_station, reserved_previous_status FROM cargo_shipments
        WHERE reserved_booking_key=?""", (booking_key,)).fetchall()
    for row in rows:
        status = row["reserved_previous_status"] or "AT_STATION"
        con.execute("""UPDATE cargo_shipments SET status=?, reserved_booking_key=NULL, reserved_previous_status=NULL,
            updated_at=? WHERE id=?""", (status, now, row["id"]))
        con.execute("""INSERT OR IGNORE INTO cargo_movements
            (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number,
             status, details)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (row["id"], f"transfer-cancelled:{booking_key}:{row['id']}", "TRANSFER_CANCELLED", now,
             row["current_station"], row["current_station"], pilot_id,
             (booking.get("dispatch") or {}).get("flight"), status, "{}"))


def set_flight_outcome(con, pirep_id, accepted):
    """A rejected flight didn't really carry its cargo: each shipment goes back to waiting where it was loaded.
    If staff later accept the flight, the arrival is restored. Only shipments whose latest arrival is this flight
    change (cargo that has since flown on is left alone), and every change is a logged movement, applied once."""
    moved = 0
    arrivals = con.execute("""SELECT shipment_id, from_station, to_station, status, flight_number, pilot_id FROM cargo_movements
        WHERE pirep_id=? AND event_type='FLIGHT_ARRIVAL'""", (pirep_id,)).fetchall()
    now = time.time()
    for a in arrivals:
        latest = con.execute("""SELECT pirep_id FROM cargo_movements WHERE shipment_id=? AND event_type='FLIGHT_ARRIVAL'
            ORDER BY event_time DESC, id DESC LIMIT 1""", (a["shipment_id"],)).fetchone()
        if not latest or latest["pirep_id"] != pirep_id:
            continue
        last = con.execute("""SELECT event_type FROM cargo_movements WHERE shipment_id=? AND pirep_id=?
            AND event_type IN ('FLIGHT_REJECTED','FLIGHT_REINSTATED') ORDER BY id DESC LIMIT 1""",
                           (a["shipment_id"], pirep_id)).fetchone()
        rejected_now = bool(last and last["event_type"] == "FLIGHT_REJECTED")
        if accepted == (not rejected_now):
            continue                       # already in the right state
        n = con.execute("SELECT COUNT(*) FROM cargo_movements WHERE shipment_id=? AND pirep_id=? AND event_type IN ('FLIGHT_REJECTED','FLIGHT_REINSTATED')",
                        (a["shipment_id"], pirep_id)).fetchone()[0]
        if accepted:
            kind, station, status = "FLIGHT_REINSTATED", a["to_station"], a["status"]
        else:
            kind, station, status = "FLIGHT_REJECTED", a["from_station"], "AT_STATION"
        con.execute("""INSERT OR IGNORE INTO cargo_movements
            (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number, pirep_id, status, details)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (a["shipment_id"], f"pirep-outcome:{pirep_id}:{a['shipment_id']}:{n}", kind, now,
             a["to_station"] if not accepted else a["from_station"], station, a["pilot_id"], a["flight_number"], pirep_id, status,
             json.dumps({"reason": "PIREP accepted by staff" if accepted else "PIREP rejected: the flight doesn't count, so the cargo wasn't carried"},
                        separators=(",", ":"))))
        con.execute("UPDATE cargo_shipments SET current_station=?, status=?, updated_at=? WHERE id=?",
                    (station, status, now, a["shipment_id"]))
        moved += 1
    return moved


# ---------------------------------------------------------------- handover notes: pilot to pilot, on the waybill
NOTE_MAX = 280


def _notes_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS cargo_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, shipment_id TEXT NOT NULL,
        pilot_id TEXT NOT NULL, station TEXT, text TEXT NOT NULL, created_at REAL NOT NULL)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_cargo_notes_shipment ON cargo_notes(shipment_id, created_at)")


def notes(con, shipment_ids):
    """{shipment_id: [note, ...]} oldest first, with the pilot's name."""
    _notes_table(con)
    ids = list(shipment_ids)
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    out = {}
    for r in con.execute(f"""SELECT n.id, n.shipment_id, n.pilot_id, p.name AS pilot_name, n.station, n.text, n.created_at
            FROM cargo_notes n LEFT JOIN pilots p ON p.id=n.pilot_id WHERE n.shipment_id IN ({marks})
            ORDER BY n.created_at, n.id""", ids):
        out.setdefault(r["shipment_id"], []).append(dict(r))
    return out


def can_note(con, shipment_id, pilot_id):
    """A pilot can leave a note on freight they were the last to fly, while it waits at a station for its next leg."""
    row = con.execute("SELECT status, current_station FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()
    if not row or row["status"] not in ("AT_STATION", "HELD_AT_STATION"):
        return False
    last = con.execute("""SELECT pilot_id FROM cargo_movements WHERE shipment_id=? AND event_type='FLIGHT_ARRIVAL'
        ORDER BY event_time DESC, id DESC LIMIT 1""", (shipment_id,)).fetchone()
    return bool(last and last["pilot_id"] == pilot_id)


def add_note(con, shipment_id, pilot_id, text, now=None):
    _notes_table(con)
    text = " ".join(str(text or "").split())[:NOTE_MAX]
    if len(text) < 3:
        raise ValueError("Write a short note for the next pilot (at least a few words).")
    if not can_note(con, shipment_id, pilot_id):
        raise PermissionError("You can leave a note on freight you flew in, while it waits for its next flight.")
    if con.execute("SELECT COUNT(*) FROM cargo_notes WHERE shipment_id=? AND pilot_id=?", (shipment_id, pilot_id)).fetchone()[0] >= 3:
        raise ValueError("That's the most notes one pilot can leave on a shipment (3).")
    station = con.execute("SELECT current_station FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()[0]
    con.execute("INSERT INTO cargo_notes (shipment_id, pilot_id, station, text, created_at) VALUES (?,?,?,?,?)",
                (shipment_id, pilot_id, station, text, now or time.time()))
