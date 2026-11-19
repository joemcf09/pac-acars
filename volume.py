"""Volumetric loading, stage 1: how full the aircraft is by weight AND by volume.

Freighters usually fill their holds before they reach their weight limit ("cube out"), above all with light, bulky
freight such as e-commerce parcels. This module only measures that. It does not change the payload, pay, scores or
PAC's economics: the load is still planned by weight, and these figures are shown beside it on the loadsheet and
in the debrief.

Each fleet type carries its usable cargo volume in data/fleet.json ("cargo_volume_ft3", main deck plus lower holds).
The consignment's volume comes from the air waybills (shipments.py works each one out from the commodity's typical
density), or from the same densities when the waybills have not been written yet."""
from __future__ import annotations

FT3_PER_M3 = 35.3147
LB_PER_KG = 2.20462


def capacity_m3(ac):
    ft3 = (ac or {}).get("cargo_volume_ft3")
    try:
        return float(ft3) / FT3_PER_M3 if ft3 and float(ft3) > 0 else None
    except (TypeError, ValueError):
        return None


def consignment(d):
    """(weight_lbs, volume_m3) of everything manifested on a dispatch, or (0, 0) when nothing is."""
    import shipments
    sh = (d or {}).get("shipments") or []
    vols = [((s.get("awb_doc") or {}).get("vol_m3")) for s in sh]
    if sh and all(v for v in vols):
        return sum(int(s.get("weight_lbs") or 0) for s in sh), float(sum(vols))
    weight = vol = 0.0
    for p in (d or {}).get("positions") or []:   # before the waybills exist: the commodity's typical density
        kg = (p.get("weight_lbs") or 0) / LB_PER_KG
        dens = shipments._goods(p.get("contents"))[3] or 167
        weight += p.get("weight_lbs") or 0
        vol += kg / dens
    return weight, vol


def load_factors(d, ac):
    """Weight and volume load factor for a dispatch on aircraft data `ac`, or None when either can't be worked out.
    Percentages are not capped: a volume factor over 100% means the load as planned would not physically fit."""
    cap = capacity_m3(ac)
    max_lbs = (ac or {}).get("max_payload_lbs")
    if not cap or not max_lbs:
        return None
    weight, vol = consignment(d)
    if not weight or not vol:
        return None
    wlf, vlf = weight / max_lbs, vol / cap
    return {"informational": True,
            "weight_pct": round(wlf * 100, 1), "volume_pct": round(vlf * 100, 1),
            "limited_by": "volume" if vlf > wlf else "weight",
            "over_volume": vlf > 1.0,
            "payload_lbs": int(weight), "max_payload_lbs": int(max_lbs),
            "volume_ft3": round(vol * FT3_PER_M3), "capacity_ft3": round(cap * FT3_PER_M3),
            # kg per cubic metre: how dense this load is, and the density at which the aircraft fills by weight and
            # volume at the same moment (lighter freight than that cubes out first)
            "load_density": round(weight / LB_PER_KG / vol), "design_density": round(max_lbs / LB_PER_KG / cap),
            "provisional": bool((ac or {}).get("volume_provisional"))}


# ---------------------------------------------------------------------------------------------- stage 2
# With the "volumetric_loading" setting on, a booking carries only what physically fits in the hold: the mission's
# freight has a typical density, and the aircraft's usable volume times that density is the most it can load. Light,
# bulky freight then "cubes out" below the weight limit, as real freighters do. PAC's contract price is then worked out
# on chargeable weight (the higher of actual and volumetric weight), so a full hold of light freight still pays.
UTILISATION = 0.90             # share of the rated volume a real load fills (pallet build-up and contour losses)
CHARGEABLE_KG_PER_M3 = 166.67  # IATA volumetric divisor, 6,000 cm3 per kg


def enabled(settings):
    return bool((settings or {}).get("volumetric_loading"))


def mission_density(m):
    """Typical density of a mission's freight, kg per m3, from the same commodity pool the load sheet draws from.
    The leading commodity weighs most (the load sheet picks it about six times in ten)."""
    import dispatch, shipments
    pool = dispatch.pool_for(m.get("cargo", ""), m.get("category", ""))
    if not pool:
        return CHARGEABLE_KG_PER_M3
    words = set(str(m.get("cargo", "")).lower().replace(",", " ").split())
    pool = sorted(pool, key=lambda it: -len(words & set(it[0].lower().replace(",", " ").split())))
    dens = [shipments._goods(it[0])[3] or CHARGEABLE_KG_PER_M3 for it in pool]
    inv = 0.6 / dens[0] + 0.4 * sum(1 / d for d in dens) / len(dens)   # volume per kg, mixed by weight
    return round(1 / inv)


def volume_cap_lbs(ac, density):
    cap = capacity_m3(ac)
    return int(cap * UTILISATION * density * LB_PER_KG // 500 * 500) if cap and density else None


def chargeable_factor(density):
    """Chargeable weight over actual weight for freight of this density: 1.0 for dense freight, more for bulky."""
    return max(1.0, CHARGEABLE_KG_PER_M3 / density) if density else 1.0


def booking_mission(m, code, fleet, settings):
    """The mission as this aircraft can carry it. Returns `m` itself when nothing changes (setting off, no volume for the
    type, a positioning or training flight, or freight dense enough to weigh out first); otherwise a copy with the
    payload cut to what fits and the reason under "volume_cap"."""
    if not enabled(settings) or not m or m.get("training") or m.get("contract") or m.get("category") in ("Ferry", "Checkride"):
        return m
    ac = (fleet or {}).get(code) or {}
    want = min(int(m.get("payload_lbs") or 0), int(ac.get("max_payload_lbs") or 0))
    if want <= 0 or m.get("volume_cap"):
        return m
    density = mission_density(m)
    cap = volume_cap_lbs(ac, density)
    if not cap or cap >= want:
        return m
    out = dict(m)
    out["payload_lbs"] = cap
    out["volume_cap"] = {"from_lbs": int(m.get("payload_lbs") or 0), "lbs": cap, "aircraft": code, "density_kg_m3": density,
                         "volume_ft3": round((capacity_m3(ac) or 0) * UTILISATION * FT3_PER_M3),
                         "chargeable_factor": round(chargeable_factor(density), 3)}
    return out
