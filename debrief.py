"""The after-action debrief for a flight: planned versus actual, the customers' and dispatcher's comments,
and how each air waybill on the flight turned out.

It only reads what the flight recorded and what the release planned. Nothing here changes the score,
the grade or the pay: it explains them.
"""
from __future__ import annotations

import copy
import datetime as dt
import random

import shipments

FRAGILE = {"VAL", "AVI", "PIL", "AOG", "ELI", "ELM", "RLI"}       # customers notice a hard arrival with these on board
PERISH = {"PER", "PES", "PEF", "PIL", "COL", "ICE", "EAT", "PEM", "FRO"}


def _hm(mins):
    if mins is None:
        return None
    m = int(round(abs(mins)))
    return f"{'-' if mins < 0 else ''}{m // 60}:{m % 60:02d}"


def _row(what, planned, actual, unit, kind="num", limit=False, good=None):
    """One planned-versus-actual line. kind 'time' shows h:mm. limit=True means 'actual must stay at or under planned'."""
    if planned is None and actual is None:
        return None
    var = (actual - planned) if (planned is not None and actual is not None) else None
    fmt = (lambda v: _hm(v)) if kind == "time" else (lambda v: f"{round(v):,}")
    out = {"what": what, "unit": unit, "planned": None if planned is None else fmt(planned), "actual": None if actual is None else fmt(actual),
           "variance": None if var is None else (("+" if var > 0 else "") + fmt(var)), "limit": limit}
    if var is not None:
        out["pct"] = round(var / planned * 100, 1) if planned else None
        out["ok"] = (actual <= planned) if limit else (good(var, planned) if good else True)
    return out


def _can_carry(p, m, booking, fleet):
    """The planned payload: the consignment, capped by what this aircraft type can lift."""
    want = p.get("mission_payload_lbs") or m.get("payload_lbs")
    cap = ((fleet or {}).get(booking.get("aircraft")) or {}).get("max_payload_lbs")
    return min(want, cap) if (want and cap) else want


def _shipments(booking):
    """The release's shipments with their waybills. Old releases without shipments give an empty list."""
    d = copy.deepcopy(booking.get("dispatch") or {})
    if not d.get("shipments"):
        return [], d
    d.setdefault("requested_at", booking.get("requested_at"))
    try:
        shipments.enrich(d)
    except Exception:
        pass
    return d["shipments"], d


def build(p, booking, rec=None, fleet=None):
    """The debrief block stored with the PIREP (detail.debrief)."""
    m = booking.get("mission") or {}
    ofp = booking.get("ofp") or {}
    if m.get("training"):
        return None
    o = p.get("oooi") or {}
    fuel = getattr(rec, "fuel", None) or {}
    status = p.get("status") or ""
    delivered = status in ("Delivered", "Delivered late")
    late = status == "Delivered late"
    rate = p.get("landing_rate")
    hard = rate is not None and rate <= -600
    firm = rate is not None and -600 < rate <= -400
    target = p.get("target_block_min")

    # ---- planned versus actual
    rows = [
        _row("Block time", target, p.get("block_min"), "h:mm", "time",
             good=lambda v, pl: v <= pl * (0.25 if m.get("priority") in ("Critical", "High") else 0.35)),
        _row("Trip fuel", p.get("planned_trip_lbs"), p.get("trip_burn_lbs"), "lb", good=lambda v, pl: v <= pl * 0.05),
        _row("Payload", _can_carry(p, m, booking, fleet), p.get("payload_lbs"), "lb", good=lambda v, pl: v >= -max(500, pl * 0.02)),
        _row("Landing weight (limit MLW)", p.get("mlw_lbs"), p.get("landing_weight_lbs"), "lb", limit=True),
    ]
    if fuel.get("on") is not None and ofp.get("reserve_fuel_lbs"):
        r = _row("Fuel at touchdown (min. final reserve)", ofp["reserve_fuel_lbs"], fuel["on"], "lb")
        r["ok"] = fuel["on"] >= ofp["reserve_fuel_lbs"]
        r["limit"] = "min"
        rows.append(r)
    if p.get("planned_arr") and p.get("arr") and p["planned_arr"] != p["arr"]:
        rows.append({"what": "Arrival airport", "planned": p["planned_arr"], "actual": p["arr"], "variance": "Diverted", "unit": "", "ok": False})
    rows = [r for r in rows if r]

    # ---- the cargo, waybill by waybill
    ships, d = _shipments(booking)
    in_t = o.get("in")
    cargo = []
    for s in ships:
        a = s.get("awb_doc") or {}
        final = (s.get("destination") or {}).get("icao") or (d.get("destination") or {}).get("icao")
        if delivered and final and final != p.get("arr"):
            state, when = "TRANSFERRED AT STATION", None
        elif delivered and in_t:
            dlv = dt.datetime.fromtimestamp(in_t, dt.timezone.utc) + dt.timedelta(minutes=60 if len((d.get("deck") or {}).get("main") or []) >= 20 else 40)
            state, when = ("DELIVERED LATE" if late else "DELIVERED"), dlv.strftime("%d%b %H%MZ").upper()
        elif status == "Diverted":
            state, when = "HELD AT DIVERSION AIRPORT", None
        else:
            state, when = "NOT DELIVERED", None
        care = next((c for c in p.get("cargo_care") or [] if c.get("awb") == s["awb"]), None)
        cargo.append({"awb": s["awb"], "shipper": s["shipper"]["name"], "consignee": s["consignee"]["name"], "contents": s["contents"],
                      "pieces": s.get("pieces"), "weight_lbs": s.get("weight_lbs"), "shc": s.get("shc") or [], "status": state, "delivered": when,
                      "charges": a.get("total"), "care": care})

    # ---- what the customers said
    rng = random.Random(f"{booking.get('requested_at')}|{booking.get('flight_number')}|cust")
    names = list(dict.fromkeys(c["consignee"] for c in cargo))[:3]
    who = ", ".join(names) if names else "The consignee"
    shc = {c for x in cargo for c in x["shc"]} or set(m.get("shc") or [])
    hurt = [c for c in cargo if c.get("care") and c["care"]["status"] == "excursion"]
    close = [c for c in cargo if c.get("care") and c["care"]["status"] == "watch"]
    if delivered and hurt:
        x = hurt[0]
        names = [x["consignee"]]
        who = x["consignee"]
        tone = "bad"
        text = {"cold": f"Our {x['contents'].lower()} arrived with a temperature excursion. {x['care']['log'][0]} We're inspecting it before acceptance.",
                "animals": f"The animals arrived distressed ({x['care']['label'].split('(')[-1].rstrip(')')}). Our handler noted: {' '.join(x['care']['log'][:2])}",
                "fragile": f"Our {x['contents'].lower()} arrived damaged. {x['care']['log'][0]}"}[x["care"]["kind"]]
    elif not delivered:
        tone = "bad"
        text = (f"The cargo didn't reach {p.get('planned_arr') or 'its destination'}. " +
                ("It is being held at the diversion airport while PAC arranges onward carriage. " if status == "Diverted" else "") +
                "The customer has asked for a recovery plan and an updated arrival time.")
    elif hard and shc & FRAGILE:
        tone = "bad"
        text = (f"Consignments received, but the receiving team logged a hard arrival ({rate} fpm) with sensitive cargo on board "
                f"({', '.join(sorted(shc & FRAGILE))}). Units are being inspected before release. Please land gently with this kind of load.")
    elif late and shc & PERISH:
        tone = "bad"
        text = "Received, but late against a temperature-sensitive delivery window. Part of the load needed checking for cold-chain exposure."
    elif late:
        tone = "mixed"
        text = "Consignments received, but the delivery commitment was missed. Please improve connection and handling reliability."
    elif close:
        x = close[0]
        who = x["consignee"]
        tone = "mixed"
        text = f"Received, and {x['care']['label'][0].lower() + x['care']['label'][1:]}. {x['care']['log'][-1]}"
    elif hard or firm:
        tone = "mixed"
        text = f"All consignments received on time. The ground team noted a firm arrival ({rate} fpm); no damage was reported."
    else:
        tone = "good"
        text = rng.choice([
            "All consignments received on time and in good order. Thank you, PAC.",
            "Delivered within the promised window, documents complete. We'll book PAC again for this lane.",
            "Received on schedule with no exceptions. The handover was smooth.",
        ])
    customer = {"from": who, "tone": tone, "text": text}

    # ---- the dispatcher's summary
    bits = [f"{p.get('flight_number')} operated {p.get('dep')}–{p.get('arr')} in {round(p.get('block_min') or 0)} minutes"]
    if target:
        dv = round((p.get("block_min") or 0) - target)
        bits[-1] += f" ({abs(dv)} min {'over' if dv > 0 else 'under'} the planned {target})" if dv else " (exactly as planned)"
    if cargo:
        bits.append(f"{len(cargo)} customer air waybill{'s' if len(cargo) != 1 else ''}, {sum(c['pieces'] or 0 for c in cargo):,} pieces, "
                    f"{round(p.get('payload_lbs') or 0):,} lb delivered" if delivered else f"{len(cargo)} air waybills not delivered")
    elif p.get("payload_lbs"):
        bits.append(f"{round(p['payload_lbs']):,} lb of cargo")
    if p.get("loaded_lbs") and p.get("mission_payload_lbs") and abs(p["loaded_lbs"] - p["mission_payload_lbs"]) > 500:
        bits.append(f"SimBrief payload {round(p['loaded_lbs']):,} lb against a {round(p['mission_payload_lbs']):,} lb consignment")
    if p.get("trip_burn_lbs") is not None and p.get("planned_trip_lbs"):
        pct = (p["trip_burn_lbs"] / p["planned_trip_lbs"] - 1) * 100
        bits.append(f"trip fuel {pct:+.1f}% against the OFP")
    elif not ofp:
        bits.append("no SimBrief OFP was attached, so fuel wasn't compared")
    if rate is not None:
        bits.append(f"touchdown {rate} fpm" + (f" at {p['landing_g']:.2f} G" if p.get("landing_g") else ""))
    if fuel.get("on") is not None and ofp.get("reserve_fuel_lbs"):
        bits.append("landed above final reserve" if fuel["on"] >= ofp["reserve_fuel_lbs"] else "LANDED BELOW FINAL RESERVE")
    dispatcher = "; ".join(bits) + "."
    take = []
    for r in rows:
        if r.get("ok") is False:
            take.append({"Block time": "Plan the departure and routing to protect the delivery time.",
                         "Trip fuel": "Trip fuel ran over plan: check the cruise level, speed and routing against the OFP.",
                         "Payload": "The aircraft carried less than the consignment: check the SimBrief payload before you depart.",
                         "Arrival airport": "Diverted: file the reason with dispatch so the customer can be told."}.get(r["what"].split(" (")[0],
                         f"{r['what']}: outside the plan."))
    if hard:
        take.append("Hard landing: review the flare on the touchdown trace before your next flight.")
    for c in cargo:
        if c.get("care") and c["care"]["status"] == "excursion":
            take.append({"cold": "Cold chain: keep ramp time short on hot or freezing days; a quick turn protects temperature-sensitive freight.",
                         "animals": "Live animals: a smooth ride matters: gentle turns, avoid turbulence where you can, and a soft landing.",
                         "fragile": "Fragile freight: fly it gently and land softly; G-loads and bounces damage it."}[c["care"]["kind"]])
            break
    if not take:
        take.append("Everything ran to plan. Keep this standard for the next one.")
    import people
    who = people.aboard(m, {c for x in cargo for c in x.get("shc") or []})
    return {"v": 1, "planned_actual": rows, "customer": customer, "dispatcher": dispatcher, "takeaways": take, "cargo": cargo,
            "people": people.debrief_note(who, rate, p.get("landing_g"), p.get("bounces")),
            "on_time": None if not cargo else _on_time_label(cargo)}


def _on_time_label(cargo):
    """'5 delivered, 2 transferred at station, all on time' instead of a bare '5 / 7'."""
    n = len(cargo)
    dl = sum(c["status"] == "DELIVERED" for c in cargo)
    tr = sum("TRANSFER" in str(c["status"]) for c in cargo)
    if dl + tr == n:
        return f"{dl} delivered, {tr} transferred at station, all on time" if tr else f"{n} / {n} delivered, all on time"
    return f"{dl + tr} / {n} on time" + (f" ({tr} transferred at station)" if tr else "")
