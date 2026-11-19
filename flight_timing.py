"""PAC ACARS 1.2: where the block time went, plan-versus-actual time checks, and the engine start review.

Everything here is informational. Nothing in this module changes a score, a grade, pay or a delivery status:
the existing late-delivery rule in build_pirep() is untouched. The numbers below are PAC's reference values for
the review cards, kept together so they are easy to tune after real flights."""
from __future__ import annotations

import datetime as dt

# Taxi allowance in minutes (typical, generous) by airport size class in data/airports.json (L, M, S).
# Large and small come from the ACARS 1.2 requirements (about 20-30 and 6-10 minutes); medium sits between them.
TAXI_ALLOWANCE_MIN = {"L": (20, 30), "M": (10, 20), "S": (6, 10)}
DEFAULT_SIZE = "M"

DEPARTURE_GRACE_MIN = 10       # early or late departure window around the planned out time
ARRIVAL_GRACE_MIN = 10         # same window for the arrival check
AIRBORNE_TOLERANCE = (5, 0.10)  # minutes, or this share of the planned enroute time, whichever is larger
MAX_PLAN_OFFSET_MIN = 360      # a planned out time further than this from the real one belongs to another day

# Engine start sequences PAC lists as standard, by number of engines. Anything else is reported as "not listed",
# never as an error. Add sequences here as procedures are confirmed.
STANDARD_SEQUENCES = {2: [(1, 2), (2, 1)], 4: [(2, 4, 1, 3)]}
# Longest sensible time from the first engine start to the last one, in seconds, by number of engines.
ENGINE_START_MAX_SPAN_S = {2: 300, 3: 420, 4: 600}


def _z(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H%MZ") if t else None


def _min(a, b):
    """Minutes from a to b, or None if either is missing."""
    return None if a is None or b is None else (b - a) / 60.0


def _hm(minutes):
    m = int(round(abs(minutes)))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def _signed(minutes):
    m = int(round(minutes))
    return f"{m:+d} min"


def _planned_out(ofp):
    """The SimBrief scheduled out time as epoch seconds, or None."""
    try:
        v = float((ofp or {}).get("departure_time_utc") or 0)
    except (TypeError, ValueError):
        return None
    return v or None


def taxi_allowance(size):
    return TAXI_ALLOWANCE_MIN.get(size) or TAXI_ALLOWANCE_MIN[DEFAULT_SIZE]


def block_segments(oooi):
    """OUT, OFF, ON, IN as zulu strings, and the four segments in minutes. Missing times stay None."""
    o = oooi or {}
    seg = {"taxi_out_min": _min(o.get("out"), o.get("off")), "airborne_min": _min(o.get("off"), o.get("on")),
           "taxi_in_min": _min(o.get("on"), o.get("in")), "block_min": _min(o.get("out"), o.get("in"))}
    return {"times": {k: o.get(k) for k in ("out", "off", "on", "in")},
            "zulu": {k: _z(o.get(k)) for k in ("out", "off", "on", "in")},
            **{k: (round(v, 1) if v is not None else None) for k, v in seg.items()}}


def _check(cid, label, status, text, actual=None, plan=None, diff=None):
    return {"id": cid, "label": label, "status": status, "text": text, "actual": actual, "plan": plan,
            "diff_min": round(diff, 1) if diff is not None else None}


def time_checks(oooi, ofp, dep_size=None, arr_size=None):
    """Separate checks for departure, taxi out, airborne time, taxi in, arrival and total block.
    Returns None when the flight has no recorded out time at all."""
    o = oooi or {}
    if not o.get("out"):
        return None
    seg = block_segments(o)
    ofp = ofp or {}
    plan_out = _planned_out(ofp)
    enroute, est_block = ofp.get("est_enroute_min") or None, ofp.get("est_block_min") or None
    out_lo, out_hi = taxi_allowance(dep_size)
    in_lo, in_hi = taxi_allowance(arr_size)
    checks = []

    # departure against the planned out time
    if plan_out is None:
        checks.append(_check("departure", "Departure", "na", "No planned departure time (import a SimBrief plan to compare)."))
    else:
        d = _min(plan_out, o["out"])
        if abs(d) > MAX_PLAN_OFFSET_MIN:
            checks.append(_check("departure", "Departure", "na", "The planned departure time is for another day, so it was not compared."))
        elif abs(d) <= DEPARTURE_GRACE_MIN:
            checks.append(_check("departure", "Departure", "ok",
                                 f"Off the gate {_signed(d)} against the plan, inside the {DEPARTURE_GRACE_MIN} minute window.",
                                 _z(o["out"]), _z(plan_out), d))
        else:
            checks.append(_check("departure", "Departure", "late" if d > 0 else "early",
                                 f"Off the gate {_hm(d)} {'late' if d > 0 else 'early'} against the plan "
                                 f"(window is {DEPARTURE_GRACE_MIN} minutes either side).", _z(o["out"]), _z(plan_out), d))

    # taxi out and taxi in against the allowance for the airport size
    for cid, label, actual, lo, hi in (("taxi_out", "Taxi out", seg["taxi_out_min"], out_lo, out_hi),
                                       ("taxi_in", "Taxi in", seg["taxi_in_min"], in_lo, in_hi)):
        if actual is None:
            checks.append(_check(cid, label, "na", f"{label} was not completed."))
        elif actual < lo:
            checks.append(_check(cid, label, "ok", f"{_hm(actual)}, well under the {hi} minute allowance.", _hm(actual), f"{lo}-{hi} min", actual - hi))
        elif actual <= hi:
            checks.append(_check(cid, label, "ok", f"{_hm(actual)}, inside the {lo}-{hi} minute allowance.", _hm(actual), f"{lo}-{hi} min", actual - hi))
        else:
            checks.append(_check(cid, label, "over", f"{_hm(actual)}, {_hm(actual - hi)} over the {lo}-{hi} minute allowance.",
                                 _hm(actual), f"{lo}-{hi} min", actual - hi))

    # airborne time against the planned enroute time
    if seg["airborne_min"] is None:
        checks.append(_check("airborne", "Airborne", "na", "Airborne time was not recorded."))
    elif not enroute:
        checks.append(_check("airborne", "Airborne", "na", f"{_hm(seg['airborne_min'])} airborne; no planned enroute time to compare.", _hm(seg["airborne_min"])))
    else:
        d = seg["airborne_min"] - enroute
        tol = max(AIRBORNE_TOLERANCE[0], enroute * AIRBORNE_TOLERANCE[1])
        checks.append(_check("airborne", "Airborne", "ok" if abs(d) <= tol else ("over" if d > 0 else "under"),
                             f"{_hm(seg['airborne_min'])} airborne against {_hm(enroute)} planned ({_signed(d)}).",
                             _hm(seg["airborne_min"]), _hm(enroute), d))

    # arrival, measured from takeoff: airborne plan plus the taxi-in allowance, so a late departure doesn't hide or cause it
    if o.get("in") and o.get("off") and enroute:
        expected = o["off"] + enroute * 60 + in_hi * 60
        d = _min(expected, o["in"])
        basis = f"takeoff plus the planned enroute time and the {in_hi} minute taxi-in allowance gives {_z(expected)}"
        if d <= ARRIVAL_GRACE_MIN:
            checks.append(_check("arrival", "Arrival", "ok", f"On the stand at {_z(o['in'])}; {basis}.", _z(o["in"]), _z(expected), d))
        else:
            checks.append(_check("arrival", "Arrival", "late", f"On the stand at {_z(o['in'])}, {_hm(d)} after {_z(expected)} "
                                 f"({basis.replace(' gives ' + _z(expected), '')}).", _z(o["in"]), _z(expected), d))
    else:
        checks.append(_check("arrival", "Arrival", "na", "Needs a takeoff time, an on-block time and a planned enroute time."))

    # the whole block against the plan, and where the difference came from
    if seg["block_min"] is None:
        checks.append(_check("block", "Block", "na", "The flight did not go on block."))
    elif not est_block:
        checks.append(_check("block", "Block", "na", f"Block {_hm(seg['block_min'])}; no planned block time to compare.", _hm(seg["block_min"])))
    else:
        d = seg["block_min"] - est_block
        why = ""
        if enroute and seg["airborne_min"] is not None and seg["taxi_out_min"] is not None and seg["taxi_in_min"] is not None:
            plan_taxi = max(0, est_block - enroute)
            air_d = seg["airborne_min"] - enroute
            taxi_d = seg["taxi_out_min"] + seg["taxi_in_min"] - plan_taxi
            why = f" Airborne {_signed(air_d)}, taxi {_signed(taxi_d)} against the plan."
        status = "ok" if d <= ARRIVAL_GRACE_MIN else "late"
        checks.append(_check("block", "Block", status, f"Block {_hm(seg['block_min'])} against {_hm(est_block)} planned ({_signed(d)}).{why}",
                             _hm(seg["block_min"]), _hm(est_block), d))

    return {"informational": True, "segments": seg,
            "planned": {"out": _z(plan_out), "enroute_min": enroute, "block_min": est_block,
                        "taxi_out_allowance": [out_lo, out_hi], "taxi_in_allowance": [in_lo, in_hi]},
            "checks": checks}


def engine_review(eng_starts, expected=None):
    """Start order, gaps, total time to all engines running, and the sequence against PAC's standard list.
    Returns None when no engine starts were recorded (older clients, or a simulator that hides engine state)."""
    starts = sorted(eng_starts or [], key=lambda e: e.get("seq", e.get("t", 0)))
    if not starts:
        return None
    order = tuple(int(e["n"]) for e in starts)
    count = int(expected or len(order))
    order_text = " → ".join(str(n) for n in order)
    times = [e.get("t") for e in starts]
    timed = all(t is not None for t in times)   # a start with no timestamp still counts for the order
    gaps = [round(b - a, 1) for a, b in zip(times, times[1:])] if timed else []
    span = (round(times[-1] - times[0], 1) if len(times) > 1 else 0.0) if timed else None
    notes = []

    listed = STANDARD_SEQUENCES.get(count)
    if len(order) < count:
        sequence = {"status": "incomplete", "text": f"{len(order)} of {count} engines were seen starting."}
        notes.append("Engines already running when the flight tracker started are not counted.")
    elif listed is None:
        sequence = {"status": "none_defined", "text": f"PAC has no standard start sequence for {count}-engine aircraft yet."}
    elif order in listed:
        sequence = {"status": "listed", "text": f"{order_text} is one of PAC's standard sequences for {count} engines."}
    else:
        sequence = {"status": "unlisted", "text": f"{order_text} is not one of PAC's listed sequences for {count} engines "
                                                  f"({', '.join(' → '.join(map(str, s)) for s in listed)}). Informational only."}

    limit = ENGINE_START_MAX_SPAN_S.get(count)
    if len(order) < 2 or limit is None or span is None:
        timing = None
    elif span <= limit:
        timing = {"status": "ok", "limit_s": limit, "text": f"All engines running {int(span)} seconds after the first start (target {limit})."}
    else:
        timing = {"status": "slow", "limit_s": limit, "text": f"All engines running {int(span)} seconds after the first start (target {limit})."}

    return {"informational": True, "order": list(order), "order_text": order_text, "started": len(order), "expected": count,
            "first_z": starts[0].get("z"), "last_z": starts[-1].get("z"), "gaps_s": gaps, "span_s": span,
            "sequence": sequence, "timing": timing, "notes": notes}
