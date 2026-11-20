"""Staff flight-following desk for diverted freight and grounded aircraft.

Decisions are dispatch instructions. Shipment location and reservation stay under
the existing booking/PIREP workflow; a desk action never claims delivery.
"""
import json
import time

from flask import jsonify, request


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS ops_exception_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, case_key TEXT NOT NULL, at REAL NOT NULL,
        actor TEXT NOT NULL, choice TEXT NOT NULL, target_pilot TEXT,
        target_flight TEXT, note TEXT NOT NULL)""")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ops_exception_case ON ops_exception_actions(case_key, id)")


def _cases(con):
    """Project current exceptions from cargo and AOG records, not a second status store."""
    cases = {}
    rows = con.execute("""SELECT m.pirep_id, m.flight_number, m.pilot_id, m.to_station,
        m.event_time, s.id, s.awb, s.destination, s.commodity, s.pieces,
        s.gross_weight_lbs, s.priority, s.data
        FROM cargo_movements m JOIN cargo_shipments s ON s.id=m.shipment_id
        WHERE m.event_type='FLIGHT_ARRIVAL' AND m.status='HELD_AT_STATION'
          AND m.pirep_id IS NOT NULL AND s.status='HELD_AT_STATION'
          AND s.current_station=m.to_station
          AND m.id=(SELECT MAX(last.id) FROM cargo_movements last
                    WHERE last.shipment_id=s.id AND last.event_type='FLIGHT_ARRIVAL')
        ORDER BY m.event_time DESC, s.awb""").fetchall()
    for row in rows:
        key = f"DIVERSION:{row['pirep_id']}"
        case = cases.setdefault(key, {"key": key, "kind": "diversion", "station": row["to_station"],
            "flight": row["flight_number"], "pilot_id": row["pilot_id"], "opened": row["event_time"],
            "shipments": [], "mission_id": None, "airframe": None})
        try:
            detail = json.loads(row["data"] or "{}")
        except (TypeError, ValueError):
            detail = {}
        case["shipments"].append({"id": row["id"], "awb": row["awb"],
            "destination": row["destination"], "commodity": row["commodity"],
            "pieces": row["pieces"], "weight_lbs": row["gross_weight_lbs"],
            "priority": row["priority"], "deadline": detail.get("deadline")})
    import aog
    aog.init(con)
    for row in con.execute("""SELECT a.id,a.reg,a.station,a.title,a.cause_flight,a.cause_pirep,
        a.opened,a.status,a.mission_id,p.pilot_id FROM aog_cases a
        LEFT JOIN pireps p ON p.id=a.cause_pirep
        WHERE a.status IN ('awaiting_parts','repairing') ORDER BY a.opened DESC"""):
        key = f"AOG:{row['id']}"
        cases[key] = {"key": key, "kind": "aog", "station": row["station"],
            "flight": row["cause_flight"], "pilot_id": row["pilot_id"], "opened": row["opened"],
            "shipments": [], "mission_id": row["mission_id"], "airframe": row["reg"],
            "title": row["title"], "status": row["status"]}
    if cases:
        for row in con.execute("""SELECT * FROM ops_exception_actions WHERE id IN
            (SELECT MAX(id) FROM ops_exception_actions GROUP BY case_key)"""):
            if row["case_key"] in cases:
                cases[row["case_key"]]["decision"] = dict(row)
    return sorted(cases.values(), key=lambda c: c["opened"] or 0, reverse=True)


def register(app, C):
    @app.get("/api/staff/ops-exceptions")
    def staff_ops_exceptions():
        with C["db"]() as con:
            cases = _cases(con)
            bookings = []
            for row in con.execute("SELECT pilot_id,data FROM bookings"):
                try:
                    b = json.loads(row["data"])
                    m = b.get("mission") or {}
                    if b.get("release_start") or C["releases"].valid_signature(b):
                        continue
                    bookings.append({"pilot_id": row["pilot_id"], "flight": b.get("flight_number"),
                        "origin": (m.get("origin") or {}).get("icao"),
                        "destination": (m.get("destination") or {}).get("icao")})
                except (TypeError, ValueError, KeyError):
                    continue
            pilots = [dict(r) for r in con.execute("""SELECT id,name FROM pilots
                WHERE COALESCE(status,'Active')='Active' ORDER BY name""")]
            recent = [dict(r) for r in con.execute("""SELECT * FROM ops_exception_actions
                ORDER BY id DESC LIMIT 20""")]
        return jsonify(cases=cases, bookings=bookings, pilots=pilots, recent=recent)

    @app.post("/api/staff/ops-exceptions/<case_key>/decision")
    def staff_ops_exception_decision(case_key):
        body = request.get_json(silent=True) or {}
        choice = body.get("choice")
        target = str(body.get("target_pilot") or "").strip().upper()
        flight = str(body.get("target_flight") or "").strip().upper()[:20]
        note = str(body.get("note") or "").strip()[:500]
        if choice not in ("hold", "onward", "recovery") or len(note) < 10:
            return jsonify(error="Choose a decision and give a reason of at least 10 characters."), 400
        if choice in ("onward", "recovery") and not target:
            return jsonify(error="Choose a pilot to receive the dispatch instruction."), 400
        with C["db"]() as con:
            con.execute("BEGIN IMMEDIATE")
            case = next((c for c in _cases(con) if c["key"] == case_key), None)
            if not case:
                return jsonify(error="This exception has changed or cleared. Refresh the desk."), 409
            if target and not con.execute("""SELECT 1 FROM pilots WHERE id=?
                AND COALESCE(status,'Active')='Active'""", (target,)).fetchone():
                return jsonify(error="Choose an active PAC pilot."), 400
            if choice == "onward":
                if case["kind"] != "diversion" or not case["shipments"] or not flight:
                    return jsonify(error="Choose a booked onward flight for diverted freight."), 400
                row = con.execute("SELECT data FROM bookings WHERE pilot_id=?", (target,)).fetchone()
                booking = json.loads(row["data"]) if row else {}
                mission = booking.get("mission") or {}
                dep = (mission.get("origin") or {}).get("icao")
                arr = (mission.get("destination") or {}).get("icao")
                if booking.get("flight_number") != flight or dep != case["station"] or booking.get("release_start") or C["releases"].valid_signature(booking):
                    return jsonify(error="That pilot needs an unsigned, unstarted booking from the cargo station."), 409
                import cargo_network
                routes = C["ROUTES"].values()
                if not arr or any(not cargo_network.reachable(routes, arr, s["destination"])[0]
                                  for s in case["shipments"]):
                    return jsonify(error="That flight cannot carry all affected shipments toward their destinations."), 409
            elif choice == "recovery" and case["kind"] == "aog" and case["status"] != "awaiting_parts":
                return jsonify(error="Parts are already at this aircraft; a recovery flight is no longer needed."), 409
            elif flight:
                return jsonify(error="A flight number is only used for an onward booking."), 400
            previous = case.get("decision") or {}
            if (previous.get("choice"), previous.get("target_pilot") or "", previous.get("target_flight") or "", previous.get("note")) == (choice, target, flight, note):
                return jsonify(ok=True, id=previous["id"], duplicate=True)
            actor = C["va"].current_pilot_id()
            now = time.time()
            cur = con.execute("""INSERT INTO ops_exception_actions
                (case_key,at,actor,choice,target_pilot,target_flight,note)
                VALUES (?,?,?,?,?,?,?)""", (case_key, now, actor, choice, target or None, flight or None, note))
            awbs = ", ".join(s["awb"] for s in case["shipments"])
            subject = f"PAC OCC · {case['flight'] or case['airframe'] or case['station']} · {choice.title()}"
            if choice == "hold":
                instruction = (f"Keep {case['airframe']} grounded at {case['station']} pending maintenance clearance."
                    if case["kind"] == "aog" else
                    f"Hold the affected freight at {case['station']} pending further instructions.")
            elif choice == "onward":
                instruction = (f"Plan onward carriage from {case['station']} on {flight}. "
                    "Select the listed freight in Cargo inventory and confirm it is on your dispatch release before departure.")
            elif case["mission_id"]:
                instruction = f"Recovery requested for {case['airframe']} at {case['station']}. Review mission {case['mission_id']} on the mission board."
            else:
                instruction = f"Plan a recovery flight from {case['station']} for the held freight. Coordinate the booking with OCC before departure."
            message = f"{instruction}\nAffected AWBs: {awbs or 'none (aircraft recovery)'}\nOCC note: {note}\nNo cargo is marked delivered by this instruction."
            import messaging
            messaging.migrate(con)
            recipients = {p for p in (case["pilot_id"], target) if p}
            for recipient in recipients:
                con.execute("INSERT INTO messages (sender,recipient,subject,body,time) VALUES (?,?,?,?,?)",
                    (actor, recipient, subject, message, now))
            return jsonify(ok=True, id=cur.lastrowid, sent=len(recipients))
