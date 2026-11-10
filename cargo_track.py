"""Public air waybill tracking: anyone with a PAC air waybill number can follow the shipment.

The movements PAC already records for each shipment (cargo_network.py) are shown the way real cargo
tracking shows them, with Cargo-IMP status codes:
  RCS  received from the shipper     BKD  booked on a flight      DEP  departed on a flight
  ARR  arrived on a flight           RCF  received from a flight  DLV  delivered to the consignee
  DIS  discrepancy (a diversion, an exception, or a flight that didn't count)

Only what a shipper would see is public: the air waybill, the goods, the stations, the flights and their times.
Pilot names, handover notes and holds stay inside the website."""
from __future__ import annotations

import json
import re

AWB_RE = re.compile(r"^(\d{3})-?(\d{8})$")

CODES = {"RCS": "Received from shipper", "BKD": "Booked on flight", "DEP": "Departed", "ARR": "Arrived",
         "RCF": "Received from flight", "DLV": "Delivered", "DIS": "Discrepancy"}

STATUS_TEXT = {"BOOKED": "In transit", "AT_STATION": "Waiting for an onward flight", "HELD_AT_STATION": "Held at a station",
               "DELIVERED": "Delivered", "DELIVERED_LATE": "Delivered late", "EXCEPTION": "Exception: contact PAC",
               "WITHDRAWN": "Withdrawn by the shipper"}


def normalize(text):
    """'90110000123', '901 1000 0123' or '901-10000123' -> '901-10000123', or None."""
    m = AWB_RE.match(re.sub(r"[\s.]", "", str(text or "")))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def _ev(code, t, station, flight=None, note=""):
    return {"code": code, "label": CODES[code], "time": t, "station": station, "flight": flight, "note": note}


def events(shipment, movements, block_min=None):
    """Turn PAC's recorded movements into a tracking history, oldest first."""
    out = []
    final = shipment["destination"]
    for m in movements:
        t, frm, to, fl = m["event_time"], m["from_station"], m["to_station"], m["flight_number"]
        kind, status = m["event_type"], m["status"]
        try:
            details = json.loads(m["details"] or "{}")
        except (TypeError, ValueError):
            details = {}
        if kind == "BOOKED":
            out.append(_ev("RCS", t, to, None, "Accepted at the cargo terminal"))
            out.append(_ev("BKD", t, to, fl, f"Booked for {final}" if to != final else ""))
        elif kind == "TRANSFER_BOOKED":
            out.append(_ev("BKD", t, frm, fl, f"Booked onward to {to}"))
        elif kind in ("TRANSFER_RELEASED", "TRANSFER_CANCELLED"):
            out.append(_ev("RCF", t, frm, None, "Onward booking cancelled; waiting for another flight"))
        elif kind == "FLIGHT_ARRIVAL":
            mins = (block_min or {}).get(m["pirep_id"])
            if frm:
                out.append(_ev("DEP", t - mins * 60 if mins else t, frm, fl, f"To {to}" if to else ""))
            if details.get("trucked_from"):
                out.append(_ev("ARR", t, details["trucked_from"], fl, "Arrived nearby"))
                out.append(_ev("RCF", t, details["trucked_from"], None, f"Trucked to {final}"))
                to = final
            elif to:
                out.append(_ev("ARR", t, to, fl))
            if status in ("DELIVERED", "DELIVERED_LATE"):
                out.append(_ev("DLV", t, to, None, "Delivered late" if status == "DELIVERED_LATE" else "Released to the consignee"))
            elif status == "AT_STATION":
                out.append(_ev("RCF", t, to, None, f"Waiting for an onward flight to {final}"))
            elif status == "HELD_AT_STATION":
                out.append(_ev("DIS", t, to, fl, "Flight diverted; held for an onward flight"))
            elif status == "EXCEPTION":
                out.append(_ev("DIS", t, to or frm, fl, "Exception on arrival"))
        elif kind == "FLIGHT_REJECTED":
            out.append(_ev("DIS", t, to, fl, "Flight record not accepted; shipment returned to " + str(to)))
        elif kind == "FLIGHT_NOT_CREDITED":
            out.append(_ev("RCF", t, to, None, "Offloaded and inspected where the aircraft landed"))
            if status in ("DELIVERED", "DELIVERED_LATE"):
                out.append(_ev("DLV", t, to, None, "Released to the consignee after inspection"))
        elif kind == "FLIGHT_REINSTATED":
            out.append(_ev("ARR", t, to, fl, "Flight record accepted"))
    out.sort(key=lambda e: e["time"])
    return out


def lookup(con, awb):
    """The public tracking record for one air waybill, or None."""
    awb = normalize(awb)
    if not awb:
        return None
    s = con.execute("""SELECT id, awb, origin, destination, current_station, status, commodity, pieces, gross_weight_lbs,
        chargeable_weight_kg, priority, created_at, updated_at, data FROM cargo_shipments WHERE awb=?""", (awb,)).fetchone()
    if not s:
        return None
    moves = con.execute("""SELECT event_type, event_time, from_station, to_station, flight_number, pirep_id, status, details
        FROM cargo_movements WHERE shipment_id=? AND event_type!='CLAIMED' ORDER BY event_time, id""", (s["id"],)).fetchall()
    ids = [m["pirep_id"] for m in moves if m["pirep_id"]]
    block = {}
    if ids:
        try:
            q = ",".join("?" * len(ids))
            block = {r["id"]: r["block_min"] for r in con.execute(f"SELECT id, block_min FROM pireps WHERE id IN ({q})", ids)
                     if r["block_min"]}
        except Exception:
            block = {}
    try:
        data = json.loads(s["data"] or "{}")
    except (TypeError, ValueError):
        data = {}
    codes = [str(c) for c in (data.get("shc") or []) if c]
    return {"awb": s["awb"], "origin": s["origin"], "destination": s["destination"], "station": s["current_station"],
            "status": s["status"], "status_text": STATUS_TEXT.get(s["status"], s["status"].replace("_", " ").title()),
            "goods": s["commodity"], "pieces": s["pieces"], "weight_lbs": round(s["gross_weight_lbs"] or 0),
            "weight_kg": round((s["gross_weight_lbs"] or 0) * 0.45359237),
            "priority": s["priority"], "handling": codes[:8], "deadline": data.get("deadline"),
            "season": data.get("season_name"), "accepted": s["created_at"], "updated": s["updated_at"],
            "events": events(dict(s), [dict(m) for m in moves], block)}
