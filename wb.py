"""Weight and balance: the real center of gravity (%MAC), load index, envelope check and takeoff trim for PAC freighters.

Only aircraft with documented data in data/wb/<TYPE>.json get a real calculation. Every figure in those files names its
source. Types without a file return None, and the release keeps PAC's estimate, labeled as an estimate.

Simulation paperwork for flight simulation, built from manufacturer and simulator data; not an aircraft's approved
weight-and-balance.
"""
from __future__ import annotations

import json
import os

LB_PER_KG = 2.20462262
JET_A_LB_PER_GAL = 6.7
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wb_data")
_CACHE = {}

# PAC fleet code -> data file, and PAC's position names -> the data file's positions
FILES = {"B738F": "B738"}
POSITION_MAP = {"B738F": {**{f"M{i:02d}": f"M{i}" for i in range(1, 11)}, "M12": "P12",
                          "FWD BULK": "LOWER_FWD", "AFT BULK": "LOWER_AFT"}}


def data(code):
    name = FILES.get(code)
    if not name:
        return None
    if name not in _CACHE:
        with open(os.path.join(_DIR, f"{name}.json")) as f:
            _CACHE[name] = json.load(f)
    return _CACHE[name]


def supported(code):
    return code in FILES


def position_limits_lbs(code):
    """PAC position name -> documented max load (lb), for building manifests within real limits."""
    if not supported(code):
        return None
    m = Model(code)
    return {pac: int(m.max_kg[real] * LB_PER_KG) for pac, real in POSITION_MAP[code].items()}


def _interp(points, x):
    """Linear interpolation over [(x, y), ...] sorted by x; holds the end values outside the range."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0) if x1 != x0 else y1
    return points[-1][1]


class Model:
    """One aircraft type's geometry, positions, basic weight and fuel, in kg and inches (Boeing balance arms)."""

    def __init__(self, code):
        d = data(code)
        if d is None:
            raise KeyError(code)
        self.code, self.d = code, d
        g = d["geometry"]
        self.mac, self.lemac, self.ref, self.c, self.k = g["mac_in"], g["lemac_in"], g["ref_station_in"], g["index_c"], g["index_k"]
        self.arms = {p["pos"]: p["arm"] for p in d["main_deck"]["positions"]}
        self.max_kg = {p["pos"]: p["max_kg"] for p in d["main_deck"]["positions"]}
        sim = d["pmdg_msfs"]
        self.sim_ba = lambda x_ft: sim["ba_offset_in"] - 12 * x_ft          # simulator feet (+forward) -> Boeing inches
        holds = {h["hold"]: h for h in d["lower_holds"]["holds"]}
        for name, parts in (("LOWER_FWD", ("1", "2")), ("LOWER_AFT", ("3", "4"))):
            cap = sum(holds[p]["max_kg"] for p in parts)
            self.arms[name] = sum(holds[p]["max_kg"] * holds[p]["arm"] for p in parts) / cap
            self.max_kg[name] = cap
        # basic aircraft as the simulator loads it: empty weight plus its default crew and galley stations
        items = [(sim["empty_weight_lbs"], sim["empty_cg_ft"])] + [tuple(v) for k, v in sim["stations_lbs_ft"].items()
                                                                      if not k.startswith("lower_")]
        w = sum(i[0] for i in items)
        self.basic_lbs = w
        self.basic_arm = sum(i[0] * self.sim_ba(i[1]) for i in items) / w
        fuel = sim["fuel_gal_ft"]
        self.main_cap_lbs = (fuel["left_main"][0] + fuel["right_main"][0]) * JET_A_LB_PER_GAL
        self.center_cap_lbs = fuel["center"][0] * JET_A_LB_PER_GAL
        self.main_arm, self.center_arm = self.sim_ba(fuel["left_main"][1]), self.sim_ba(fuel["center"][1])
        # measured in the simulator (FMC CG readings) replaces the provisional file-based geometry
        cal = d.get("calibration") or {}
        self.provisional = cal.get("status") != "verified"
        if cal.get("basic_pct_mac") is not None:
            self.basic_arm = self.arm_of(cal["basic_pct_mac"])
        if cal.get("main_tank_arm_in") is not None:
            self.main_arm = cal["main_tank_arm_in"]
        if cal.get("center_tank_arm_in") is not None:
            self.center_arm = cal["center_tank_arm_in"]

    # ---- conversions
    def pct_mac(self, arm):
        return (arm - self.lemac) * 100 / self.mac

    def arm_of(self, pct):
        return self.lemac + self.mac * pct / 100

    def index(self, weight_kg, arm):
        return weight_kg * (arm - self.ref) / self.c + self.k

    # ---- fuel: 737 loads the wing tanks first and burns the center tank first
    def fuel_split(self, fuel_lbs):
        mains = min(fuel_lbs, self.main_cap_lbs)
        return mains, max(0.0, fuel_lbs - mains)

    def fuel_moment(self, fuel_lbs):
        mains, center = self.fuel_split(fuel_lbs)
        return mains * self.main_arm + center * self.center_arm

    # ---- envelope and trim
    def limits(self, phase, weight_kg):
        env = self.d["envelope_pct_mac"][phase]
        return _interp(env["fwd"], weight_kg), _interp(env["aft"], weight_kg)

    def trim(self, weight_kg, pct, flaps="flaps_1_5"):
        t = self.d["trim_units"][flaps]
        cols = t["pct_mac"]
        rows = [(w, _interp(list(zip(cols, vals)), pct)) for w, vals in t["rows"]]
        return _interp(rows, weight_kg)


def _phase(model, name, weight_lbs, moment_lbin, phase):
    kg = weight_lbs / LB_PER_KG
    arm = moment_lbin / weight_lbs
    pct = model.pct_mac(arm)
    fwd, aft = model.limits(phase, kg)
    return {"name": name, "weight_lbs": round(weight_lbs), "arm_in": round(arm, 1), "pct_mac": round(pct, 1),
            "index": round(model.index(kg, arm), 1), "fwd_limit": round(fwd, 1), "aft_limit": round(aft, 1),
            "ok": fwd - 0.05 <= pct <= aft + 0.05,
            "margin": round(min(pct - fwd, aft - pct), 1)}


def balance(code, positions, dow_lbs, takeoff_fuel_lbs, trip_fuel_lbs, flaps="flaps_1_5"):
    """The loadsheet's balance block for a release: CG and index at zero fuel, takeoff and landing, the envelope check,
    unit and deck limits, and the takeoff stabilizer trim. `positions` are the release units ({pos, weight_lbs})."""
    if not supported(code):
        return None
    m = Model(code)
    pmap = POSITION_MAP[code]
    unknown = sorted({p["pos"] for p in positions if p["pos"] not in pmap})
    if unknown:
        return {"available": False, "reason": f"This release uses positions the {code} layout doesn't have ({', '.join(unknown)}). "
                                              "Re-import your OFP to rebuild the manifest on the current deck layout."}
    warnings = []
    payload = sum(p["weight_lbs"] for p in positions)
    pay_moment = 0.0
    main_kg = 0.0
    for p in positions:
        pos = pmap[p["pos"]]
        pay_moment += p["weight_lbs"] * m.arms[pos]
        kg = p["weight_lbs"] / LB_PER_KG
        if not pos.startswith("LOWER"):
            main_kg += kg
        if kg > m.max_kg[pos] + 0.5:
            warnings.append(f"{p['pos']} holds {p['weight_lbs']:,} lb; its limit is {m.max_kg[pos] * LB_PER_KG:,.0f} lb.")
    deck_max = m.d["main_deck"]["combined_max_kg"]
    if main_kg > deck_max + 0.5:
        warnings.append(f"Main deck carries {main_kg * LB_PER_KG:,.0f} lb; its combined limit is {deck_max * LB_PER_KG:,.0f} lb.")
    # the basic aircraft sits at the simulator's basic CG, scaled to the release's dry operating weight
    dow_moment = dow_lbs * m.basic_arm
    zfw = dow_lbs + payload
    zf_moment = dow_moment + pay_moment
    tow = zfw + takeoff_fuel_lbs
    ldw_fuel = max(0.0, takeoff_fuel_lbs - trip_fuel_lbs)
    lw = zfw + ldw_fuel
    phases = [_phase(m, "ZFW", zfw, zf_moment, "zero_fuel"),
              _phase(m, "TOW", tow, zf_moment + m.fuel_moment(takeoff_fuel_lbs), "takeoff"),
              _phase(m, "LW", lw, zf_moment + m.fuel_moment(ldw_fuel), "landing")]
    dow_kg = dow_lbs / LB_PER_KG
    to = phases[1]
    min_tow_kg = 50802
    if tow / LB_PER_KG < min_tow_kg and any(not pmap[p["pos"]].startswith("LOWER") and pmap[p["pos"]] not in ("M5", "M6", "M7")
                                              for p in positions):
        warnings.append("Takeoff weight is under 50,802 kg (112,000 lb): main-deck cargo may only be in M05 to M07.")
    advice = None
    bad = next((ph for ph in phases if not ph["ok"]), None)
    if bad:
        target = bad["fwd_limit"] + 1.0 if bad["pct_mac"] < bad["fwd_limit"] else bad["aft_limit"] - 1.0
        shift = (m.arm_of(target) - bad["arm_in"]) * bad["weight_lbs"]       # lb-in the cargo must move
        span = 4 * 97.0                                                        # about four positions fore/aft
        lbs = abs(shift) / span
        advice = (f"CG {bad['pct_mac']}% MAC at {bad['name']} is {'forward' if bad['pct_mac'] < bad['fwd_limit'] else 'aft'} of the "
                  f"{bad['fwd_limit' if bad['pct_mac'] < bad['fwd_limit'] else 'aft_limit']}% limit. Move about {lbs:,.0f} lb "
                  f"{'aft' if shift > 0 else 'forward'} by four positions, or use Auto-load.")
    return {
        "available": True, "aircraft": code, "model": m.d["name"], "provisional": m.provisional,
        "dow_lbs": round(dow_lbs), "doi": round(m.index(dow_kg, m.basic_arm), 1),
        "phases": phases, "ok": all(ph["ok"] for ph in phases) and not warnings, "within_envelope": all(ph["ok"] for ph in phases),
        "warnings": warnings, "advice": advice,
        "trim_units": round(m.trim(tow / LB_PER_KG, to["pct_mac"], flaps), 2), "trim_flaps": "1 or 5" if flaps == "flaps_1_5" else "10, 15 or 25",
        "envelope": {ph: m.d["envelope_pct_mac"][ph] for ph in ("zero_fuel", "takeoff", "landing")},
        "arms": {k: round(v, 2) for k, v in m.arms.items()}, "position_map": pmap,
        "max_lbs": {k: round(v * LB_PER_KG) for k, v in m.max_kg.items()},
        "mac": {"length_in": m.mac, "lemac_in": m.lemac},
        "sources": [m.d["sources"]["wb_report"], m.d["sources"]["tcds"], m.d["pmdg_msfs"]["source"]],
        "provisional_note": ("Provisional: the empty aircraft and fuel tank figures are awaiting the simulator calibration, "
                             "so CG values may be off by several percent. Envelope, positions and trim tables are final.") if m.provisional else None,
        "note": "Simulation paperwork: envelope, positions and trim from the AEI 737-800SF weight-and-balance data; basic aircraft "
                "and fuel tanks from the PMDG 737-800BCF. Not an aircraft's approved weight-and-balance.",
    }
