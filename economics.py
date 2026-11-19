"""Pagani Air Cargo airline economics.

Every flight is a contract. The customer pays a fixed price for the job, set
from the cost of the most expensive recommended aircraft that can carry the load
over the planned block time, plus a markup for the kind of work. The airline's
costs come from what was actually flown: fuel burned, block hours, fees and
handling, plus any incidents.

So flying a recommended aircraft makes money; a right-sized, efficient one makes
more; flying well (fuel on plan, on time) adds to it; and incidents, diversions,
lateness or an oversized aircraft eat into it.
"""
from __future__ import annotations

import math

DEFAULT_FUEL_PRICE = 2.85        # USD per US gallon of Jet-A
DEFAULT_START_CAPITAL = 100_000_000
LB_PER_GAL = 6.7
WIDEBODIES = {"A306F", "A332F", "B763F", "MD11F", "B77F", "B742F", "B744F", "B748F"}
THREE_CREW = {"B722F", "B742F"}

# Contract markup over the planned cost of the job, by kind of work
MARKUP = {"Humanitarian": 1.06, "Scheduled": 1.12, "Express": 1.16, "Medical": 1.18, "Heavy lift": 1.20, "Premium": 1.24, "Sports & events": 1.22,
          "Urgent": 1.35, "Charter": 1.15, "Tour": 1.10, "Checkride": 1.03, "Ferry": 0.0}
URGENT_KIND_MARKUP = {"Relief": 1.12, "Humanitarian relief": 1.12}


def markup(mission):
    cat = mission.get("category")
    if cat == "Urgent":
        return URGENT_KIND_MARKUP.get(mission.get("urgent_kind"), MARKUP["Urgent"])
    m = MARKUP.get(cat, 1.2)
    if cat == "Scheduled" and mission.get("priority") == "High":
        m += 0.04  # express, perishable and pharma lanes
    return m


def is_wide(code, ac):
    return code in WIDEBODIES or ac.get("max_payload_lbs", 0) >= 90000


def planned_block(ac, distance_nm):
    return 45 + distance_nm / max(250, ac.get("cruise_ktas", 450)) * 60 * 1.05


def planned_fuel(ac, block_min):
    burn = ac.get("fuel_burn_pph", 8000)
    return burn * max(0.25, (block_min - 25) / 60) * 1.05 + burn * 0.12


def cost_lines(code, ac, distance_nm, block_min, fuel_lbs, payload_kg, fuel_price):
    bh = max(0.25, block_min / 60)
    mtow = ac.get("mtow_lbs", 150000)
    return {
        "fuel": fuel_lbs / LB_PER_GAL * fuel_price,
        "crew": bh * (1700 if code in THREE_CREW else 1200) * (1.3 if is_wide(code, ac) else 1.0),
        "maintenance": bh * ac.get("maint_per_bh", 1500),
        "ownership": bh * ac.get("ownership_per_bh", 2000),
        "landing_fees": 5.0 * mtow / 1000,
        "navigation": 0.65 * distance_nm * math.sqrt(mtow / 100000),
        "handling": payload_kg * 0.06 * 2,
    }


def contract(mission, fleet, settings, distance_nm):
    """The price the customer pays for the whole job, and the aircraft it was priced on."""
    fuel_price = float(settings.get("fuel_price_gal") or DEFAULT_FUEL_PRICE)
    payload = mission.get("payload_lbs") or 0
    live = {k: v for k, v in fleet.items() if not v.get("retired")}
    cands = [c for c in mission.get("aircraft", []) if c in live]
    fits = [c for c in cands if live[c].get("max_payload_lbs", 0) >= payload * 0.95]
    cands = fits or cands or list(live)[:1]
    best = None
    for c in cands:
        ac = live[c]
        blk = planned_block(ac, distance_nm)
        carried = min(payload, ac.get("max_payload_lbs", payload))
        cost = sum(cost_lines(c, ac, distance_nm, blk, planned_fuel(ac, blk), carried / 2.20462, fuel_price).values())
        if best is None or cost > best[1]:
            best = (c, cost)
    price = best[1] * markup(mission) if mission.get("category") != "Ferry" else 0.0
    return round(price), best[0]


def _result(revenue, costs, notes, payload_kg, extra=None):
    costs = {k: round(v) for k, v in costs.items() if round(v)}
    total = sum(costs.values())
    revenue = round(revenue)
    out = {"revenue": revenue, "costs": costs, "total_cost": total, "profit": revenue - total,
           "margin": round((revenue - total) / revenue * 100, 1) if revenue else None,
           "yield_per_kg": round(revenue / payload_kg, 2) if payload_kg else None, "notes": notes}
    out.update(extra or {})
    return out


def flight_economics(p, booking, fleet, settings, distance_nm):
    """Actual economics for a flown PIREP."""
    m = booking["mission"]
    code = booking["aircraft"]
    ac = fleet.get(code, {})
    fuel_price = float(settings.get("fuel_price_gal") or DEFAULT_FUEL_PRICE)
    if m.get("contract"):
        fee = crew_fee(code, ac, p.get("block_min") or 0)
        return _result(fee, {}, [f"Crew contract for {m['operator']['name']}: they pay for the aircraft, fuel and fees. PAC earns a crew placement fee."],
                       0, {"contract_price": fee, "priced_on": code})
    price, basis = contract(m, fleet, settings, distance_nm)
    ferry = m.get("category") == "Ferry"
    delivered = 0 if ferry else (p.get("payload_lbs") or 0)
    wanted = m.get("payload_lbs") or delivered or 1
    notes = [f"Contract priced on the {fleet.get(basis, {}).get('icao', basis)}"] if not ferry else ["Positioning flight: no revenue"]
    revenue = price * min(1.0, delivered / wanted) if not ferry else 0.0
    if delivered < wanted * 0.98 and not ferry:
        notes.append(f"Carried {delivered / wanted:.0%} of the contracted load")
    status = p.get("status")
    if status == "Failed":
        revenue, notes = 0.0, ["Cargo not delivered: no revenue"]
    elif status == "Diverted":
        revenue *= 0.6
        notes.append("Diverted: cargo trucked on, 40% of revenue lost")
    elif status == "Delivered late" and m.get("priority") in ("Critical", "High"):
        revenue *= 0.85
        notes.append("Late delivery: 15% service credit to the customer")
    if m.get("urgent") and p.get("urgent_on_time") is False:
        revenue *= 0.5
        notes.append("Urgent deadline missed: 50% of revenue refunded")
    kg = delivered / 2.20462
    costs = cost_lines(code, ac, distance_nm, p.get("block_min") or 0, p.get("fuel_used_lbs") or 0, kg, fuel_price)
    rate = p.get("landing_rate")
    wide = is_wide(code, ac)
    if rate is not None and rate < -1000:
        costs["damage_repairs"] = 2_500_000 if wide else 900_000
    elif rate is not None and rate < -600:
        costs["hard_landing_inspection"] = 60_000 if wide else 25_000
    if (p.get("takeoff_analysis") or {}).get("tail_strike"):
        costs["tail_strike_repairs"] = 450_000 if wide else 180_000
    if status == "Diverted":
        costs["diversion"] = 45_000 if wide else 18_000
    import insurance
    insurance.apply(costs, wide, notes)          # repairs above the deductible go to the insurer
    return _result(revenue, costs, notes, kg, {"contract_price": price, "priced_on": basis, "fuel_price": fuel_price,
                                                "distance_nm": round(distance_nm)})


def crew_fee(code, ac, block_min):
    """What a partner pays PAC for lending a captain."""
    return round(max(0.5, block_min / 60) * (1400 if is_wide(code, ac) else 900))


def estimate(mission, code, fleet, settings, distance_nm, payload_lbs=None, block_min=None, trip_fuel_lbs=None):
    """Planned economics before the flight, for the aircraft the pilot has chosen."""
    ac = fleet.get(code, {})
    if mission.get("contract"):
        blk = block_min or round(planned_block(ac, distance_nm))
        fee = crew_fee(code, ac, blk)
        return _result(fee, {}, [f"Crew contract for {mission['operator']['name']}: they pay for the aircraft, fuel and fees."], 0,
                       {"contract_price": fee, "priced_on": code, "block_min": blk})
    fuel_price = float(settings.get("fuel_price_gal") or DEFAULT_FUEL_PRICE)
    price, basis = contract(mission, fleet, settings, distance_nm)
    ferry = mission.get("category") == "Ferry"
    wanted = mission.get("payload_lbs") or 0
    carried = 0 if ferry else min(payload_lbs if payload_lbs is not None else wanted, ac.get("max_payload_lbs", wanted), wanted or 10 ** 9)
    block = block_min or round(planned_block(ac, distance_nm))
    fuel = trip_fuel_lbs or planned_fuel(ac, block)
    revenue = 0.0 if ferry else price * (min(1.0, carried / wanted) if wanted else 1.0)
    notes = ["Positioning flight: no revenue"] if ferry else [f"Contract priced on the {fleet.get(basis, {}).get('icao', basis)}"]
    if not ferry and wanted and carried < wanted * 0.98:
        notes.append(f"This aircraft carries {carried / wanted:.0%} of the contracted load")
    costs = cost_lines(code, ac, distance_nm, block, fuel, carried / 2.20462, fuel_price)
    return _result(revenue, costs, notes, carried / 2.20462, {"contract_price": price, "priced_on": basis, "fuel_lbs": round(fuel),
                                                               "block_min": block, "payload_lbs": round(carried)})
