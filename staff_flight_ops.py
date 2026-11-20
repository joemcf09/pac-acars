"""Founder/admin flight intervention and simulator incident desk."""
import base64
import binascii
import json
import re
import time

from flask import jsonify, request, Response


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS flight_interventions (
        id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL, pilot_id TEXT NOT NULL,
        flight TEXT, action TEXT NOT NULL, reason TEXT NOT NULL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS flight_incidents (
        id INTEGER PRIMARY KEY, created_at REAL NOT NULL, created_by TEXT NOT NULL,
        pilot_id TEXT NOT NULL, flight TEXT, kind TEXT NOT NULL, summary TEXT NOT NULL,
        evidence_note TEXT, evidence_mime TEXT, evidence_image BLOB,
        status TEXT NOT NULL DEFAULT 'Open', goodwill_amount REAL, goodwill_at REAL,
        goodwill_by TEXT, goodwill_note TEXT, closed_at REAL, closed_by TEXT, resolution TEXT)""")


def register(app, C):
    def clean(value, limit):
        return str(value or "").strip()[:limit]

    def pilot_exists(pid):
        with C["db"]() as con:
            return bool(con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone())

    def incident(con, iid):
        return con.execute("SELECT * FROM flight_incidents WHERE id=?", (iid,)).fetchone()

    @app.get("/api/staff/pilot-support/<pid>")
    def staff_pilot_support(pid):
        """Read-only projection of a pilot's site access and current flight state."""
        pid = pid.upper()
        with C["db"]() as con:
            row = con.execute("SELECT id,name,status,hub,location,checkride,staff,password_hash IS NOT NULL AS has_password FROM pilots WHERE id=?", (pid,)).fetchone()
            if not row:
                return jsonify(error="Pilot not found."), 404
            roles = {r[0] for r in con.execute("SELECT role FROM roles WHERE pilot_id=?", (pid,))}
        company = C["company"]
        caps = sorted(cap for cap, spec in company.SCOPE.items() if roles & spec["roles"])
        booking = C["load_booking"](pid)
        # A support lookup must not create an empty flight session or saved-state directory.
        s = C["SESSIONS"].get(pid) or {}
        rec = s.get("recorder")
        remote_seen = s.get("remote_seen") or 0
        remote_live = bool(s.get("remote") and time.time() - remote_seen < 60)
        cp = C["load_json"](C["CHECKPOINT_PATH"], None) if booking else None
        checkpoint = cp if cp and cp.get("requested_at") == booking.get("requested_at") else None
        saved_path = C["DATA"] / "flights" / f"{pid}.pkl"
        signed = bool(booking and C["releases"].valid_signature(booking))
        sign_required = bool(booking and C["signature_required"](booking))
        flight = None
        if booking:
            mission = booking.get("mission") or {}
            flight = {"number": booking.get("flight_number"), "origin": (mission.get("origin") or {}).get("icao"),
                      "destination": (mission.get("destination") or {}).get("icao"),
                      "aircraft": booking.get("aircraft"), "airframe": booking.get("airframe"),
                      "booked_at": booking.get("requested_at"), "release_required": sign_required,
                      "release_signed": signed, "release_amended": bool(booking.get("release_amended"))}
        pilot = {k: row[k] for k in ("id", "name", "status", "hub", "location", "checkride", "staff")}
        pilot["can_sign_in"] = bool(row["has_password"] and row["status"] not in ("Suspended", "Removed"))
        return jsonify({"pilot": pilot, "roles": sorted(roles), "caps": caps,
                        "access": {"staff": bool(row["staff"]), "sections": [cap for cap in company.SCOPE if row["staff"] or cap in caps]},
                        "booking": flight,
                        "acars": {"remote_live": remote_live, "remote_seen": remote_seen or None,
                                  "phase": (s.get("remote_status") or {}).get("phase") or getattr(rec, "phase", None),
                                  "unfiled_draft": bool(rec and getattr(rec, "complete", False)),
                                  "saved_state": saved_path.exists(),
                                  "checkpoint": {k: checkpoint.get(k) for k in ("phase", "saved_at", "source")}
                                      if checkpoint else None}})

    @app.get("/api/staff/flight-ops")
    def staff_flight_ops_list():
        with C["db"]() as con:
            bookings = con.execute("""SELECT b.pilot_id, b.data, p.name FROM bookings b
                LEFT JOIN pilots p ON p.id=b.pilot_id ORDER BY b.requested_at DESC""").fetchall()
            incidents = con.execute("""SELECT i.id,i.created_at,i.created_by,i.pilot_id,p.name AS pilot,
                i.flight,i.kind,i.summary,i.evidence_note,i.evidence_mime,i.status,
                i.goodwill_amount,i.goodwill_at,i.goodwill_by,i.goodwill_note,
                i.closed_at,i.closed_by,i.resolution FROM flight_incidents i
                LEFT JOIN pilots p ON p.id=i.pilot_id ORDER BY (i.status='Open') DESC,i.created_at DESC LIMIT 100""").fetchall()
            actions = con.execute("""SELECT * FROM flight_interventions ORDER BY at DESC LIMIT 30""").fetchall()
        cp = C["load_json"](C["CHECKPOINT_PATH"], None)
        flights = []
        for row in bookings:
            b = json.loads(row["data"])
            pid = row["pilot_id"]
            s = C["session"](pid)
            rec = s.get("recorder")
            remote = s.get("remote") or {}
            status = s.get("remote_status") or {}
            checkpoint = cp if cp and cp.get("requested_at") == b.get("requested_at") else None
            m = b.get("mission") or {}
            flights.append({"pilot_id": pid, "pilot": row["name"] or pid,
                "booking_key": b.get("requested_at"), "flight": b.get("flight_number"),
                "dep": (m.get("origin") or {}).get("icao"), "arr": (m.get("destination") or {}).get("icao"),
                "airframe": b.get("airframe"), "aircraft": b.get("aircraft"),
                "booked_at": b.get("requested_at"), "phase": status.get("phase") or getattr(rec, "phase", None),
                "remote": bool(remote), "remote_seen": s.get("remote_seen"),
                "draft": bool(rec and getattr(rec, "complete", False)),
                "saved_state": C["flight_state_path"](pid).exists(),
                "checkpoint": {k: checkpoint.get(k) for k in ("phase", "saved_at", "source")}
                    if checkpoint else None})
        return jsonify({"flights": flights, "incidents": [dict(r) for r in incidents],
                        "actions": [dict(r) for r in actions]})

    @app.post("/api/staff/flight-ops/<pid>/intervene")
    @C["releases"].serialized
    def staff_flight_intervene(pid):
        pid = pid.upper()
        body = request.get_json(silent=True) or {}
        action = body.get("action")
        reason = clean(body.get("reason"), 500)
        booking = C["load_booking"](pid)
        if action not in ("clear_draft", "release_booking") or len(reason) < 10:
            return jsonify(error="Choose an action and give a reason of at least 10 characters."), 400
        if not booking or body.get("booking_key") != booking.get("requested_at"):
            return jsonify(error="This booking changed. Refresh the desk before intervening."), 409
        s = C["session"](pid)
        if s.get("remote") and time.time() - (s.get("remote_seen") or 0) < 60:
            return jsonify(error="This pilot's ACARS is still live. Have them stop the desktop app first."), 409
        if action == "clear_draft" and booking.pop("release_start", None):
            C["save_booking"](booking, pid, notify=False)
        s.update(recorder=None, remote=None, remote_status=None, remote_seen=0)
        C["clear_flight_state"](pid)
        cp = C["load_json"](C["CHECKPOINT_PATH"], None)
        if cp and cp.get("requested_at") == booking.get("requested_at"):
            C["clear_checkpoint"]()
        if action == "release_booking":
            m = booking.get("mission") or {}
            va = C["va"]
            if m.get("job"):
                va.set_job_status(m["id"], "open")
            if m.get("live"):
                va.set_live_status(m["id"], "open" if time.time() < (m.get("expires") or 0) else "expired")
            if m.get("urgent"):
                urgent, _ = va.urgent_by_id(m["id"])
                va.set_urgent_status(m["id"], "open" if urgent and time.time() < urgent["expires"] else "expired")
            C["clear_booking"](pid)
            va.release_airframe(booking.get("airframe"))
        with C["db"]() as con:
            con.execute("INSERT INTO flight_interventions (at,actor,pilot_id,flight,action,reason) VALUES (?,?,?,?,?,?)",
                (time.time(), C["va"].current_pilot_id(), pid, booking.get("flight_number"), action, reason))
        return jsonify(ok=True, action=action)

    @app.post("/api/staff/flight-incidents")
    def staff_incident_create():
        b = request.get_json(silent=True) or {}
        pid = clean(b.get("pilot_id"), 30).upper()
        kind = clean(b.get("kind"), 40)
        summary = clean(b.get("summary"), 500)
        evidence_note = clean(b.get("evidence_note"), 2000)
        if not re.fullmatch(r"[A-Z0-9-]{3,30}", pid) or not pilot_exists(pid):
            return jsonify(error="Choose a pilot from the roster."), 400
        if kind not in ("simulator_crash", "acars_error", "dispatch_error", "other") or len(summary) < 10:
            return jsonify(error="Choose an incident type and add a summary of at least 10 characters."), 400
        image, mime = None, None
        raw = b.get("screenshot") or ""
        if raw:
            try:
                if not isinstance(raw, str) or len(raw) > 2_800_000:
                    raise ValueError()
                head, encoded = raw.split(",", 1)
                image = base64.b64decode(encoded, validate=True)
                if len(image) > 2 * 1024 * 1024:
                    raise ValueError()
                if head == "data:image/png;base64" and image.startswith(b"\x89PNG\r\n\x1a\n"):
                    mime = "image/png"
                elif head == "data:image/jpeg;base64" and image.startswith(b"\xff\xd8\xff"):
                    mime = "image/jpeg"
                else:
                    raise ValueError()
            except (ValueError, binascii.Error):
                return jsonify(error="Use a PNG or JPEG screenshot under 2 MB."), 400
        booking = C["load_booking"](pid) or {}
        with C["db"]() as con:
            cur = con.execute("""INSERT INTO flight_incidents
                (created_at,created_by,pilot_id,flight,kind,summary,evidence_note,evidence_mime,evidence_image,status)
                VALUES (?,?,?,?,?,?,?,?,?,'Open')""",
                (time.time(), C["va"].current_pilot_id(), pid,
                 clean(b.get("flight"), 20) or booking.get("flight_number"), kind, summary,
                 evidence_note, mime, image))
            iid = cur.lastrowid
        return jsonify(ok=True, id=iid), 201

    @app.get("/api/staff/flight-incidents/<int:iid>/evidence")
    def staff_incident_evidence(iid):
        with C["db"]() as con:
            row = con.execute("SELECT evidence_mime,evidence_image FROM flight_incidents WHERE id=?", (iid,)).fetchone()
        if not row or not row["evidence_image"]:
            return jsonify(error="No screenshot for this incident."), 404
        return Response(row["evidence_image"], mimetype=row["evidence_mime"],
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/api/staff/flight-incidents/<int:iid>/goodwill")
    def staff_incident_goodwill(iid):
        b = request.get_json(silent=True) or {}
        note = clean(b.get("note"), 200)
        try:
            amount = round(float(b.get("amount")), 2)
        except (TypeError, ValueError, OverflowError):
            amount = 0
        if not 0 < amount <= 5000 or len(note) < 10:
            return jsonify(error="Enter $0.01–$5,000 and a reason of at least 10 characters."), 400
        with C["db"]() as con:
            con.execute("BEGIN IMMEDIATE")
            row = incident(con, iid)
            if not row or row["status"] != "Open" or row["goodwill_at"]:
                return jsonify(error="Incident is closed or goodwill was already paid."), 409
            C["va"].add_tx(row["pilot_id"], "adjustment", amount, f"Incident #{iid}: {note}", con=con)
            con.execute("UPDATE flight_incidents SET goodwill_amount=?,goodwill_at=?,goodwill_by=?,goodwill_note=? WHERE id=?",
                (amount, time.time(), C["va"].current_pilot_id(), note, iid))
        return jsonify(ok=True, amount=amount)

    @app.post("/api/staff/flight-incidents/<int:iid>/close")
    def staff_incident_close(iid):
        resolution = clean((request.get_json(silent=True) or {}).get("resolution"), 500)
        if len(resolution) < 10:
            return jsonify(error="Describe the resolution in at least 10 characters."), 400
        with C["db"]() as con:
            cur = con.execute("""UPDATE flight_incidents SET status='Closed',closed_at=?,closed_by=?,resolution=?
                WHERE id=? AND status='Open'""", (time.time(), C["va"].current_pilot_id(), resolution, iid))
            if not cur.rowcount:
                return jsonify(error="Incident is already closed or missing."), 409
        return jsonify(ok=True)
