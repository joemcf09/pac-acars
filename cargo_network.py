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
    if "claimed_by" not in columns:
        con.execute("ALTER TABLE cargo_shipments ADD COLUMN claimed_by TEXT")
    if "claimed_until" not in columns:
        con.execute("ALTER TABLE cargo_shipments ADD COLUMN claimed_until REAL")
    # HUM is the IATA code for human remains. PAC once used it for humanitarian aid: take it off stored relief freight.
    for row in con.execute("SELECT id, handling FROM cargo_shipments WHERE handling LIKE '%\"HUM\"%'").fetchall():
        codes = [c for c in json.loads(row["handling"] or "[]") if c != "HUM"] or ["GEN"]
        con.execute("UPDATE cargo_shipments SET handling=? WHERE id=?", (json.dumps(codes), row["id"]))


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


def transfer_options(con, origin, destination, routes, pilot_id=None, now=None):
    """Freight waiting at `origin` that a flight to `destination` can carry. Freight another pilot has claimed
    (held for their next flight, up to 24 hours) is left out; the pilot's own claims come first."""
    origin, destination = str(origin or "").upper(), str(destination or "").upper()
    now = now or time.time()
    rows = con.execute("""SELECT id, awb, origin, destination, current_station, status, shipper, consignee,
        commodity, pieces, gross_weight_lbs, data, claimed_by, claimed_until
        FROM cargo_shipments
        WHERE current_station=? AND status IN ('AT_STATION','HELD_AT_STATION') AND reserved_booking_key IS NULL
          AND (claimed_by IS NULL OR claimed_until < ? OR claimed_by=?)
        ORDER BY (claimed_by=? AND claimed_until>=?) DESC, updated_at, awb""", (origin, now, pilot_id or "", pilot_id or "", now)).fetchall()
    available = []
    routes = list(routes)
    for row in rows:
        ok, truck = reachable(routes, destination, row["destination"])
        if not ok:
            continue
        item = dict(row)
        item["truck"] = truck
        by, until = item.pop("claimed_by", None), item.pop("claimed_until", None) or 0
        item["claimed_by_me"] = bool(pilot_id and by == pilot_id and until >= now)
        try:
            item["data"] = json.loads(item["data"])
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Persistent cargo {item['awb']} has invalid shipment data.") from exc
        available.append(item)
    return available


def selected_transfers(con, shipment_ids, origin, destination, routes, booking_key=None, pilot_id=None):
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
        allowed = {item["id"]: item for item in transfer_options(con, origin, destination, routes, pilot_id)}
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
        row = con.execute("SELECT current_station, destination, data FROM cargo_shipments WHERE id=?", (shipment_id,)).fetchone()
        if not row:
            raise RuntimeError(f"Persistent shipment {shipment_id} was not created.")
        previous_station = row["current_station"]
        trucked = False
        # a shipment is late against its own promised delivery time; without one, the flight's on-time result decides
        try:
            deadline = float(json.loads(row["data"] or "{}").get("deadline") or 0)
        except (ValueError, TypeError):
            deadline = 0
        late = (now > deadline) if deadline else flight_status == "Delivered late"
        if flight_status in ("Delivered", "Delivered late"):
            if actual_station == row["destination"]:
                status = "DELIVERED_LATE" if late else "DELIVERED"
            elif nearby(actual_station, row["destination"]) and not (
                    _ctx["routes"] and has_route(list(_ctx["routes"]()), actual_station, row["destination"])):
                status = "DELIVERED_LATE" if late else "DELIVERED"
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
                reserved_previous_status=NULL, claimed_by=NULL, claimed_until=NULL, updated_at=? WHERE id=?""",
                (row["destination"] if trucked else (actual_station or previous_station), status, now, shipment_id))


def create_volume_recovery(con, booking, pirep, pirep_id, pilot_id, fleet, pilot):
    """Tender the unflown part of a volume-limited consignment as waiting freight.

    The booking key makes filing retries idempotent. Each new AWB has a loadable unit
    manifest and a link to the original flight; it is prepaid by that charter.
    """
    cap = (booking.get("mission") or {}).get("volume_cap") or {}
    if (not cap or pirep.get("status") not in ("Delivered", "Delivered late")
            or pirep.get("review_status") == "Rejected" or pirep.get("demo")):
        return []
    dispatched = booking.get("dispatch") or {}
    carried = sum(int(s.get("weight_lbs") or 0) for s in dispatched.get("shipments") or []
                  if not s.get("transfer"))
    remainder = max(0, int(cap.get("from_lbs") or 0) - carried)
    if remainder <= 0:
        return []
    import dispatch as dispatch_module
    import shipments as shipments_module
    mission = booking["mission"]
    origin = mission["origin"]["icao"]
    destination = mission["destination"]["icao"]
    booking_key = f"RECOVERY:{pilot_id}:{booking['requested_at']}"
    source_awbs = [s["awb"] for s in dispatched.get("shipments") or [] if not s.get("transfer")]
    made = []
    batch = 0
    while remainder:
        batch_weight = min(remainder, int(mission.get("payload_lbs") or 0),
                           int(fleet[booking["aircraft"]]["max_payload_lbs"]))
        if batch_weight <= 0:
            raise ValueError("Recovery cargo has no available aircraft payload capacity.")
        fake = {"mission": dict(mission, payload_lbs=batch_weight, volume_cap=None),
                "aircraft": booking["aircraft"], "ofp": None,
                "flight_number": booking["flight_number"], "requested_at": booking["requested_at"],
                "manifest_seed": f"RECOVERY|{booking.get('manifest_seed') or booking_key}|{batch}"}
        manifest = dispatch_module.generate(fake, fleet, pilot)
        shipments_module.enrich(manifest)
        for shipment in manifest.get("shipments") or []:
            source_awb = shipment["awb"]
            old = con.execute("SELECT id, awb FROM cargo_shipments WHERE booking_key=? AND source_awb=?",
                              (booking_key, source_awb)).fetchone()
            if old:
                made.append(old["awb"])
                continue
            sid = uuid.uuid4().hex
            new_awb = _next_awb(con, set())
            unit_details = [{**p, "dg_entry": next((g for g in manifest.get("dg") or []
                              if g.get("pos") == p.get("pos") and g.get("awb") == source_awb), None)}
                            for p in manifest.get("positions") or [] if p.get("awb") == source_awb]
            shipment = _rewrite_awbs(dict(shipment), {source_awb: new_awb})
            unit_details = _rewrite_awbs(unit_details, {source_awb: new_awb})
            shipment.update(shipment_id=sid, cargo_source_awb=source_awb, unit_details=unit_details,
                            recovery=True, recovery_for=booking["flight_number"],
                            recovery_pirep_id=pirep_id, recovery_source_awbs=source_awbs,
                            recovery_prepaid_lbs=int(shipment.get("weight_lbs") or 0))
            doc = shipment.get("awb_doc") or {}
            # The synthetic manifest supplies unit paperwork, not a flight that happened.
            # Keep only origin acceptance until a pilot selects this AWB for a real leg.
            doc["track"] = [event for event in doc.get("track") or []
                            if event.get("code") in ("BKD", "RCS")]
            doc["freight"], doc["others"], doc["total"] = 0, [], 0
            doc["terms"] = "PREPAID ON ORIGINAL CHARTER"
            screen = doc.get("screen") or {}
            now = time.time()
            con.execute("""INSERT INTO cargo_shipments (id, awb, booking_key, source_awb, origin, destination,
                current_station, status, shipper, consignee, commodity, pieces, gross_weight_lbs,
                chargeable_weight_kg, priority, handling, security_status, reserved_booking_key,
                reserved_previous_status, data, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, new_awb, booking_key, source_awb, origin, destination, origin, "AT_STATION",
                 (shipment.get("shipper") or {}).get("name") or "",
                 (shipment.get("consignee") or {}).get("name") or "", shipment.get("contents") or "",
                 int(shipment.get("pieces") or 0), float(shipment.get("weight_lbs") or 0), doc.get("chg_kg"),
                 shipment.get("service"), json.dumps(shipment.get("handling") or []), screen.get("status"),
                 None, None, json.dumps(shipment, separators=(",", ":"), ensure_ascii=False), now, now))
            con.execute("""INSERT INTO cargo_movements (shipment_id, event_key, event_type, event_time,
                from_station, to_station, pilot_id, flight_number, pirep_id, status, details)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, f"recovery:{booking_key}:{source_awb}", "SPLIT_LOAD_WAITING", now, None, origin,
                 pilot_id, booking["flight_number"], pirep_id, "AT_STATION",
                 json.dumps({"source_awbs": source_awbs, "prepaid": True})))
            made.append(new_awb)
        remainder -= batch_weight
        batch += 1
    source_key = f"{pilot_id}:{booking['requested_at']}"
    for row in con.execute("SELECT id, data FROM cargo_shipments WHERE booking_key=?", (source_key,)).fetchall():
        data = json.loads(row["data"])
        if data.get("recovery_awbs") != made:
            data["recovery_awbs"] = made
            con.execute("UPDATE cargo_shipments SET data=? WHERE id=?",
                        (json.dumps(data, separators=(",", ":"), ensure_ascii=False), row["id"]))
    return made


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


def set_flight_outcome(con, pirep_id, accepted, keep_cargo=False):
    """What a staff decision on a flight means for the cargo it carried.

    Accepted: the arrival stands (restored if the flight had been rejected).
    Rejected, keep_cargo=False: the flight didn't really happen (a restricted zone, a bogus report), so each shipment goes
      back to waiting where it was loaded.
    Rejected, keep_cargo=True: the flight happened but doesn't count for the pilot (a deliberate or very hard landing).
      As at a real airline, the freight is offloaded and inspected where the aircraft landed and carries on from there.
    Only shipments whose latest arrival is this flight change (cargo that has since flown on is left alone), and every
    change is a logged movement, applied once."""
    moved = 0
    arrivals = con.execute("""SELECT m.shipment_id, m.from_station, m.to_station, m.status, m.flight_number, m.pilot_id,
        s.destination FROM cargo_movements m JOIN cargo_shipments s ON s.id=m.shipment_id
        WHERE m.pirep_id=? AND m.event_type='FLIGHT_ARRIVAL'""", (pirep_id,)).fetchall()
    now = time.time()
    want = "FLIGHT_REINSTATED" if accepted else ("FLIGHT_NOT_CREDITED" if keep_cargo else "FLIGHT_REJECTED")
    outcomes = ("FLIGHT_REJECTED", "FLIGHT_REINSTATED", "FLIGHT_NOT_CREDITED")
    # A staff rejection that says the flight never happened also withdraws its
    # unflown split-load orders. Reinstating the PIREP puts them back on the shelf.
    if accepted or not keep_cargo:
        recovery_rows = con.execute("""SELECT id, current_station, status FROM cargo_shipments
            WHERE booking_key LIKE 'RECOVERY:%' AND json_extract(data,'$.recovery_pirep_id')=?""",
            (pirep_id,)).fetchall()
        for recovery in recovery_rows:
            current, wanted = recovery["status"], "AT_STATION" if accepted else "WITHDRAWN"
            if current != ("WITHDRAWN" if accepted else "AT_STATION"):
                continue  # already in the target state, or reserved/flown on a later flight
            event = "SPLIT_LOAD_RESTORED" if accepted else "SPLIT_LOAD_REVOKED"
            event_number = con.execute("SELECT COUNT(*) FROM cargo_movements WHERE shipment_id=? AND event_type=?",
                                       (recovery["id"], event)).fetchone()[0]
            con.execute("UPDATE cargo_shipments SET status=?, updated_at=? WHERE id=?",
                        (wanted, now, recovery["id"]))
            con.execute("""INSERT INTO cargo_movements (shipment_id, event_key, event_type, event_time,
                from_station, to_station, pirep_id, status, details) VALUES (?,?,?,?,?,?,?,?,?)""",
                (recovery["id"], f"{event}:{pirep_id}:{recovery['id']}:{event_number}", event, now,
                 recovery["current_station"], recovery["current_station"], pirep_id, wanted, "{}"))
    for a in arrivals:
        latest = con.execute("""SELECT pirep_id FROM cargo_movements WHERE shipment_id=? AND event_type='FLIGHT_ARRIVAL'
            ORDER BY event_time DESC, id DESC LIMIT 1""", (a["shipment_id"],)).fetchone()
        if not latest or latest["pirep_id"] != pirep_id:
            continue
        q = ",".join("?" * len(outcomes))
        last = con.execute(f"""SELECT event_type FROM cargo_movements WHERE shipment_id=? AND pirep_id=?
            AND event_type IN ({q}) ORDER BY id DESC LIMIT 1""", (a["shipment_id"], pirep_id, *outcomes)).fetchone()
        current = last["event_type"] if last else "FLIGHT_REINSTATED"       # a fresh arrival counts as standing
        if current == want:
            continue                       # already in the right state
        n = con.execute(f"SELECT COUNT(*) FROM cargo_movements WHERE shipment_id=? AND pirep_id=? AND event_type IN ({q})",
                        (a["shipment_id"], pirep_id, *outcomes)).fetchone()[0]
        if want == "FLIGHT_REINSTATED":
            station, status, frm = a["to_station"], a["status"], a["from_station"]
            reason = "PIREP accepted by staff"
        elif want == "FLIGHT_REJECTED":
            station, status, frm = a["from_station"], "AT_STATION", a["to_station"]
            reason = "PIREP rejected: the flight doesn't count, so the cargo wasn't carried"
        else:
            station, frm = a["to_station"], a["to_station"]
            status = a["status"]
            if status in ("EXCEPTION", "HELD_AT_STATION", "BOOKED"):
                status = "DELIVERED" if station == a["destination"] else "AT_STATION"
            reason = "Flight not credited to the pilot; the cargo was offloaded and inspected where the aircraft landed"
        con.execute("""INSERT OR IGNORE INTO cargo_movements
            (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id, flight_number, pirep_id, status, details)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (a["shipment_id"], f"pirep-outcome:{pirep_id}:{a['shipment_id']}:{n}", want, now, frm, station, a["pilot_id"],
             a["flight_number"], pirep_id, status, json.dumps({"reason": reason}, separators=(",", ":"))))
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


# ---------------------------------------------------------------- claims: hold waiting freight for your next flight
CLAIM_S = 24 * 3600
CLAIM_MAX = 3


def claim(con, shipment_id, pilot_id, now=None):
    """Hold waiting freight for this pilot's next flight for 24 hours (website or Discord /claim)."""
    now = now or time.time()
    row = con.execute("""SELECT id, awb, status, current_station, reserved_booking_key, claimed_by, claimed_until FROM cargo_shipments
        WHERE id=?""", (shipment_id,)).fetchone()
    if not row or row["status"] not in ("AT_STATION", "HELD_AT_STATION") or row["reserved_booking_key"]:
        raise ValueError("That freight isn't waiting at a station right now.")
    if row["claimed_by"] and row["claimed_by"] != pilot_id and (row["claimed_until"] or 0) >= now:
        raise ValueError("Another pilot is already holding that freight.")
    mine = con.execute("SELECT COUNT(*) FROM cargo_shipments WHERE claimed_by=? AND claimed_until>=? AND id!=?",
                       (pilot_id, now, shipment_id)).fetchone()[0]
    if mine >= CLAIM_MAX:
        raise ValueError(f"You're already holding {CLAIM_MAX} shipments. Fly or release one first.")
    until = now + CLAIM_S
    con.execute("UPDATE cargo_shipments SET claimed_by=?, claimed_until=? WHERE id=?", (pilot_id, until, shipment_id))
    con.execute("""INSERT OR IGNORE INTO cargo_movements (shipment_id, event_key, event_type, event_time, from_station, to_station, pilot_id,
        status, details) VALUES (?,?,?,?,?,?,?,?,?)""", (shipment_id, f"claim:{shipment_id}:{pilot_id}:{int(now // 60)}", "CLAIMED", now,
        row["current_station"], row["current_station"], pilot_id, row["status"], json.dumps({"until": until})))
    return {"awb": row["awb"], "station": row["current_station"], "until": until}


def release_claim(con, shipment_id, pilot_id):
    con.execute("UPDATE cargo_shipments SET claimed_by=NULL, claimed_until=NULL WHERE id=? AND claimed_by=?", (shipment_id, pilot_id))
