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
