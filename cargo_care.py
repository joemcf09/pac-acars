"""Cargo that feels the flight: what happened to sensitive freight, from how the flight was flown.

Three kinds of freight react:
- cold chain (pharmaceuticals, flowers, seafood, produce: PIL, PEF, PES, PER, COL, CRT, ICE, EAT): time on hot or
  freezing ramps, and long delays;
- live animals (AVI): turbulence, steep banks, G-loads, a hard landing and a long taxi;
- fragile and high-value freight (VAL, ELI, wafers, art, medical equipment): G-loads, rough handling and bounces.

Everything comes from the flight record PAC ACARS already keeps. It doesn't change the score or pay: it shows in the
debrief and the shipment history, and customers react to it.
"""
from __future__ import annotations

import math
import time

COLD = {"PIL", "PEF", "PES", "PER", "COL", "CRT", "ICE", "EAT"}
ANIMALS = {"AVI"}
FRAGILE = {"VAL", "ELI"}
FRAGILE_WORDS = ("wafer", "electronic", "glass", "art", "medical equipment", "laboratory", "show car", "smartphone", "instrument")
HANDLING_MIN = 25          # minutes a pallet waits on the ramp around loading, even with a quick turn


def kind(shipment):
    shc = set(shipment.get("shc") or [])
    text = str(shipment.get("contents") or "").lower()
    if shc & ANIMALS:
        return "animals"
    if shc & FRAGILE or any(w in text for w in FRAGILE_WORDS):
        return "fragile"
    if shc & COLD:
        return "cold"
    return None


def estimated_temp(lat, month):
    """A rough ramp temperature from latitude and month when no METAR was recorded (labeled as an estimate)."""
    if lat is None:
        return None
    season = math.cos((month - (7 if lat >= 0 else 1)) / 12 * 2 * math.pi)   # 1 at local midsummer
    return round(31 - 0.008 * lat * lat + season * 0.25 * abs(lat))      # a daytime ramp, not the airport's average


def _temp(wx, apt, month):
    t = (wx or {}).get("temp_c")
    if t is not None:
        return float(t), False
    est = estimated_temp((apt or {}).get("lat"), month)
    return (float(est), True) if est is not None else (None, True)


def assess(shipments, rec, landing, origin_apt, dest_apt, planned_block_min=None, now=None):
    """Returns [{awb, kind, status, label, log: [...]}] for the sensitive shipments on board."""
    o = getattr(rec, "oooi", {}) or {}
    month = time.gmtime(now or time.time()).tm_mon
    ride = getattr(rec, "ride", None) or {}
    taxi_out = ((o.get("off") or 0) - (o.get("out") or 0)) / 60 if o.get("off") and o.get("out") else None
    taxi_in = ((o.get("in") or 0) - (o.get("on") or 0)) / 60 if o.get("in") and o.get("on") else None
    block = ((o.get("in") or 0) - (o.get("out") or 0)) / 60 if o.get("in") and o.get("out") else None
    t_dep, est_dep = _temp(None, origin_apt, month)
    t_arr, est_arr = _temp(getattr(rec, "landing_wx", None), dest_apt, month)
    g_land = (landing or {}).get("g") or 1.0
    g_max, g_min = max(ride.get("max_g") or 1.0, getattr(rec, "max_g", 1.0) or 1.0), ride.get("min_g") or 1.0
    rough, bank, steep = int(ride.get("rough") or 0), float(ride.get("max_bank") or 0), float(ride.get("steep_s") or 0)
    bounces = int(getattr(rec, "bounces", 0) or 0)
    out = []
    for s in shipments:
        k = kind(s)
        if not k:
            continue
        log, status = [], "ok"
        if k == "cold":
            exp_dep = HANDLING_MIN + (taxi_out or 0)
            exp_arr = HANDLING_MIN + (taxi_in or 0)
            for where, t, est, mins in ((origin_apt.get("icao") if origin_apt else "origin", t_dep, est_dep, exp_dep),
                                        (dest_apt.get("icao") if dest_apt else "destination", t_arr, est_arr, exp_arr)):
                if t is None:
                    continue
                tt = f"{t:.0f}°C{' (estimated)' if est else ''}"
                if (t >= 30 and mins > 40) or (t <= -15 and mins > 40):
                    status = "excursion"
                    log.append(f"{where}: {tt} on the ramp for about {mins:.0f} min. Temperature excursion logged; the consignee will inspect it.")
                elif (t >= 27 or t <= -8) and mins > 30:
                    status = "watch" if status == "ok" else status
                    log.append(f"{where}: {tt} on the ramp for about {mins:.0f} min. Stayed in range, but close.")
                else:
                    log.append(f"{where}: {tt}, about {mins:.0f} min on the ramp. In range.")
            if block and planned_block_min and block > planned_block_min + 60:
                status = "watch" if status == "ok" else status
                log.append(f"Arrived {block - planned_block_min:.0f} min later than planned: shorter shelf life left on arrival.")
            label = {"ok": "Cold chain kept", "watch": "Cold chain: close to the limit", "excursion": "Temperature excursion"}[status]
        elif k == "animals":
            score = 100
            if rough:
                score -= 10 * min(rough, 4)
                log.append(f"{rough} rough patch{'es' if rough > 1 else ''} in flight (G outside 0.5–1.5).")
            if bank > 35 or steep > 20:
                score -= 10
                log.append(f"Steep banking (up to {bank:.0f}°).")
            if g_land >= 1.6:
                score -= 15
                log.append(f"Firm landing at {g_land:.2f} G.")
            if bounces:
                score -= 10
                log.append("Bounced on landing.")
            if (taxi_out or 0) + (taxi_in or 0) > 45:
                score -= 5
                log.append(f"Long taxi ({(taxi_out or 0) + (taxi_in or 0):.0f} min).")
            score = max(0, score)
            status = "ok" if score >= 80 else "watch" if score >= 55 else "excursion"
            if not log:
                log.append("Smooth flight: steady ride and a gentle landing.")
            label = {"ok": f"Animals calm ({score}/100)", "watch": f"Animals unsettled ({score}/100)", "excursion": f"Animals distressed ({score}/100)"}[status]
        else:
            if g_land >= 1.8 or g_max >= 2.0 or bounces >= 2 or rough >= 3:
                status = "excursion"
                why = f"landing at {g_land:.2f} G" if g_land >= 1.8 else f"{g_max:.2f} G in flight" if g_max >= 2.0 else \
                      f"{bounces} bounces" if bounces >= 2 else f"{rough} rough patches"
                log.append(f"Damage found on arrival after {why}. A claim has been opened with the customer.")
            elif g_land >= 1.6 or bounces == 1 or g_max >= 1.7 or g_min <= 0.3:
                status = "watch"
                log.append(f"Handled hard (landing {g_land:.2f} G{', a bounce' if bounces else ''}). Inspected on arrival: no damage.")
            else:
                log.append(f"Gentle handling: landing {g_land:.2f} G, peak {g_max:.2f} G.")
            label = {"ok": "Arrived intact", "watch": "Arrived intact after a hard handling", "excursion": "Damaged in transit"}[status]
        out.append({"awb": s.get("awb"), "contents": s.get("contents"), "kind": k, "status": status, "label": label, "log": log})
    return out
