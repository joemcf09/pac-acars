"""Dispatch release, cargo manifest and NOTOC for Pagani Air Cargo flights.

The manifest is generated once when a flight is booked (seeded from the flight
number and booking time) so the paperwork never changes between prints.
"""
from __future__ import annotations

import datetime as dt
import random

AWB_PREFIX = "901"

# Deck layouts: main-deck positions, unit type, max weight per unit (lb), lower-deck positions and unit
DECKS = {
    "B732F": {"main": 7, "uld": "PAG", "cap": 7000, "lower": 2, "luld": "BULK", "lcap": 3000},
    "B733F": {"main": 9, "uld": "AAY", "cap": 7000, "lower": 2, "luld": "BULK", "lcap": 3500},
    "B738F": {"main": 12, "uld": "AAY", "cap": 7500, "lower": 2, "luld": "BULK", "lcap": 4500},
    "B722F": {"main": 12, "uld": "PAG", "cap": 7500, "lower": 2, "luld": "BULK", "lcap": 4000},
    "B752F": {"main": 15, "uld": "PAG", "cap": 8000, "lower": 2, "luld": "BULK", "lcap": 5000},
    "A306F": {"main": 20, "uld": "PMC", "cap": 11000, "lower": 8, "luld": "AKE", "lcap": 3500},
    "B763F": {"main": 24, "uld": "PMC", "cap": 12000, "lower": 8, "luld": "AKE", "lcap": 3500},
    "MD11F": {"main": 26, "uld": "PMC", "cap": 13000, "lower": 10, "luld": "AKE", "lcap": 3500},
    "B77F": {"main": 27, "uld": "PMC", "cap": 15000, "lower": 10, "luld": "AKE", "lcap": 3500},
    "B742F": {"main": 29, "uld": "PMC", "cap": 15000, "lower": 9, "luld": "AKE", "lcap": 3500},
    "B748F": {"main": 34, "uld": "PMC", "cap": 15000, "lower": 10, "luld": "AKE", "lcap": 3500},
}

SHC_NAMES = {
    "GEN": "General cargo", "PER": "Perishable", "PIL": "Pharmaceuticals", "COL": "Cool goods", "CRT": "Controlled room temperature",
    "ICE": "Dry ice", "ELI": "Lithium ion batteries (Section II)", "RLI": "Lithium ion batteries (fully regulated)", "HEA": "Heavy cargo",
    "VAL": "Valuable cargo", "AVI": "Live animals", "EAT": "Foodstuffs", "MAL": "Mail", "COU": "Courier / express", "RMD": "Miscellaneous dangerous goods",
    "RNG": "Non-flammable gas", "RCM": "Corrosive", "AOG": "Aircraft on ground spares", "HUM": "Humanitarian aid", "PEF": "Flowers",
    "PES": "Fish and seafood", "BIG": "Outsized", "ECC": "E-commerce", "RFL": "Flammable liquid",
}

# (keywords, contents, SHC codes, dangerous goods entry or None)
DG = {
    "ice": {"un": "UN1845", "name": "Carbon dioxide, solid (dry ice)", "cls": "9", "imp": "ICE", "unit": "kg", "qty": (40, 220)},
    "rli": {"un": "UN3481", "name": "Lithium ion batteries contained in equipment", "cls": "9", "imp": "RLI", "unit": "kg", "qty": (5, 60)},
    "eng": {"un": "UN3530", "name": "Engine, internal combustion", "cls": "9", "imp": "RMD", "unit": "pc", "qty": (1, 1)},
    "oxy": {"un": "UN1072", "name": "Oxygen, compressed", "cls": "2.2", "sub": "5.1", "imp": "RNG", "unit": "L", "qty": (400, 1500)},
    "acid": {"un": "UN2794", "name": "Batteries, wet, filled with acid", "cls": "8", "imp": "RCM", "unit": "kg", "qty": (60, 400)},
    "paint": {"un": "UN1263", "name": "Paint", "cls": "3", "imp": "RFL", "unit": "L", "qty": (20, 120)},
    "rli0": {"un": "UN3480", "name": "Lithium ion batteries", "cls": "9", "imp": "RLI", "unit": "kg", "qty": (200, 2400)},
    "gas": {"un": "UN1066", "name": "Nitrogen, compressed", "cls": "2.2", "imp": "RNG", "unit": "L", "qty": (600, 2400)},
    "corr": {"un": "UN1760", "name": "Corrosive liquid, n.o.s.", "cls": "8", "imp": "RCM", "unit": "L", "qty": (60, 400)},
    "id8000": {"un": "ID8000", "name": "Consumer commodity", "cls": "9", "imp": "RMD", "unit": "kg", "qty": (5, 40)},
}

POOLS = [
    (("vaccine", "pharma", "plasma", "blood"),
     [("Pharmaceuticals, +2/+8 °C active containers", ["PIL", "COL"], "ice"), ("Medical consumables", ["GEN"], None)]),
    (("hospital", "surgical", "oxygen"),
     [("Field hospital modules", ["HUM", "BIG"], None), ("Surgical instruments", ["GEN"], None),
      ("Oxygen cylinders", ["GEN"], "oxy", 2)]),
    (("relief", "humanitarian", "tent", "tarp", "shelter", "rescue", "water", "generator", "roofing", "resupply", "food"),
     [("Relief supplies: tarpaulins and shelter kits", ["HUM"], None), ("Water purification units", ["HUM"], None),
      ("Emergency food rations", ["HUM", "EAT"], None), ("Portable generators, fuel drained", ["HUM"], None),
      ("Satellite phones and radios", ["HUM", "RLI"], "rli")]),
    (("engine", "aog", "aircraft parts", "aerospace", "spares"),
     [("Spare engine on transport stand", ["AOG", "HEA"], "eng", 1), ("Aircraft spares", ["AOG"], None), ("Engine change tooling", ["AOG"], None)]),
    (("electronic", "semiconductor", "smartphone", "wafer", "hard drive", "components"),
     [("Consumer electronics", ["ELI", "VAL"], "rli"), ("Semiconductor wafers", ["VAL", "CRT"], None), ("Electronic components", ["GEN"], None)]),
    (("e-commerce", "parcel", "express", "mail", "documents", "courier"),
     [("Express parcels", ["COU"], None), ("E-commerce parcels", ["ECC"], "id8000"), ("Mail bags", ["MAL"], None)]),
    (("flower", "rose", "carnation", "bulb"),
     [("Fresh-cut flowers", ["PEF", "PER", "COL"], None)]),
    (("seafood", "salmon", "fish", "shrimp", "perch", "crayfish"),
     [("Fresh seafood on ice", ["PES", "PER", "COL"], "ice")]),
    (("fruit", "cherries", "asparagus", "blueberries", "avocados", "kiwifruit", "produce", "perishable", "citrus", "grapes", "meat", "beef", "dairy", "vegetables"),
     [("Fresh produce", ["PER", "EAT", "COL"], None), ("Chilled meat and dairy", ["PER", "EAT", "COL"], "ice")]),
    (("transformer", "machinery", "heavy", "oil", "mining", "equipment", "construction", "energy", "industrial"),
     [("Industrial machinery", ["HEA"], None), ("Oil and gas equipment", ["HEA"], None), ("Spare parts", ["GEN"], "paint")]),
    (("automotive", "auto parts", "show car", "car parts"),
     [("Automotive components", ["GEN"], "acid"), ("Show cars in climate-controlled crates", ["VAL", "BIG"], None, 3)]),
    (("fashion", "garment", "apparel", "textile", "luxury", "retail"),
     [("Garments on hangers", ["GEN"], None), ("Luxury goods", ["VAL"], None), ("Retail stock", ["GEN"], None)]),
    (("livestock", "cattle", "heifer", "rhino", "zoo"), [("Live animals", ["AVI"], None)]),
    (("lithium", "battery packs", "un3480"), [("Lithium ion batteries", ["RLI"], "rli0", 99)]),
    (("corrosive", "chemicals"), [("Oil-field chemicals", ["RCM"], "corr", 99)]),
    (("industrial gases", "cylinders"), [("Industrial gas cylinders", ["RNG"], "gas", 99)]),
    (("bullion", "banknote"), [("Valuable cargo, escorted", ["VAL"], None)]),
    (("helicopter",), [("Helicopter on skid frame, blades removed", ["BIG", "HEA"], None, 1), ("Rotor blades and spares", ["BIG"], None)]),
    (("tyre", "tire"), [("Mining-truck tires", ["BIG", "HEA"], None)]),
    (("stage", "lighting", "touring", "motorsport"), [("Touring production equipment", ["GEN"], None)]),
]
GENERAL = [("General cargo", ["GEN"], None), ("Consolidated freight", ["GEN"], None), ("Machinery spares", ["GEN"], None)]


def awb(rng):
    serial = rng.randrange(1_000_000, 9_999_999)
    return f"{AWB_PREFIX}-{serial}{serial % 7}"


def pool_for(cargo, category):
    text = f"{cargo} {category}".lower()
    pool = []
    for keys, items in POOLS:
        if any(k in text for k in keys):
            pool += items
    return pool or GENERAL


def generate(booking, fleet, pilot, now=None):
    m, ofp = booking["mission"], booking.get("ofp") or {}
    code = booking["aircraft"]
    ac = fleet.get(code, {})
    pl_max = ac.get("max_payload_lbs", 50000)
    deck = DECKS.get(code) or ({"main": max(8, min(40, round(pl_max / 9000))), "uld": "PMC", "cap": 13000, "lower": 8, "luld": "AKE", "lcap": 3500}
                               if pl_max >= 90000 else
                               {"main": max(4, min(16, round(pl_max / 4500))), "uld": "PAG", "cap": 7500, "lower": 2, "luld": "BULK", "lcap": 4000})
    # a preliminary load sheet hands its seed to the booking, so the release keeps the same units, positions and waybills
    seed = booking.get("manifest_seed") or f"{booking['flight_number']}|{booking.get('requested_at')}"
    rng = random.Random(seed)
    ferry = m.get("category") == "Ferry" or str(m.get("cargo", "")).startswith("Ferry")
    payload_target = int(ofp.get("payload_lbs") or min(m["payload_lbs"], ac.get("max_payload_lbs", m["payload_lbs"])))
    if booking.get("cargo_transfer_ids"):
        payload_target = min(payload_target, int(m.get("payload_lbs") or 0), int(ac.get("max_payload_lbs") or 0))
    payload = 0 if ferry else max(0, payload_target - int(booking.get("cargo_transfer_weight_lbs") or 0))

    # positions
    main = [f"M{i + 1:02d}" for i in range(deck["main"])]
    lower = ([f"L{i + 1}" for i in range(deck["lower"])] if deck["luld"] != "BULK" else ["FWD BULK", "AFT BULK"][:deck["lower"]])
    positions, dgs = [], []
    if payload > 0:
        pool = pool_for(m.get("cargo", ""), m.get("category", ""))
        words = set(str(m.get("cargo", "")).lower().replace(",", " ").split())
        pool.sort(key=lambda it: -len(words & set(it[0].lower().replace(",", " ").split())))
        cap_total = deck["main"] * deck["cap"] + len(lower) * deck["lcap"]
        fill = min(1.0, payload / max(1, cap_total) * 1.6 + 0.12)
        n_main = max(1, min(deck["main"], round(deck["main"] * fill)))
        n_low = min(len(lower), round(len(lower) * fill * 0.8))
        slots = [(p, deck["uld"], deck["cap"]) for p in main[:n_main]] + [(p, deck["luld"], deck["lcap"]) for p in lower[:n_low]]
        # spread weight, then keep every unit under its limit
        raw = [rng.uniform(0.65, 1.35) * cap for _, _, cap in slots]
        scale = payload / sum(raw)
        wts = [min(cap, round(r * scale / 10) * 10) for r, (_, _, cap) in zip(raw, slots)]
        short = payload - sum(wts)
        for i in range(len(wts)):
            if short <= 0:
                break
            room = slots[i][2] - wts[i]
            add = min(room, short)
            wts[i] += add
            short -= add
        drift = payload - sum(wts)
        if drift and wts[-1] + drift <= slots[-1][2]:
            wts[-1] += drift
        used = {}
        def pick(first):
            order = ([pool[0]] if first or rng.random() < 0.6 else []) + rng.sample(pool, len(pool)) + [p for p in pool if len(p) < 4]
            for it in order:
                limit = it[3] if len(it) > 3 else None
                if limit is None or used.get(it[0], 0) < limit:
                    used[it[0]] = used.get(it[0], 0) + 1
                    return it
            return GENERAL[0]
        for n, ((pos, uld, cap), w) in enumerate(zip(slots, wts)):
            item = pick(n == 0)
            desc, shc, dgkey = item[0], item[1], item[2]
            pcs = max(1, round(w / rng.uniform(60, 420)))
            if uld == "BULK":
                unit_id = "BULK"
            else:
                unit_id = f"{uld}{rng.randrange(10000, 99999)}PC"
            positions.append({"pos": pos, "uld": uld, "unit": unit_id, "awb": awb(rng), "contents": desc, "shc": list(shc),
                              "pieces": pcs, "weight_lbs": int(w), "dg": None})
            if dgkey:
                spec = DG[dgkey]
                qty = spec["qty"][0] if spec["qty"][0] == spec["qty"][1] else rng.randint(*spec["qty"])
                entry = {"un": spec["un"], "name": spec["name"], "cls": spec["cls"], "sub": spec.get("sub", ""), "imp": spec["imp"],
                         "pieces": 1 if spec["unit"] == "pc" else rng.randint(1, 12), "net": f"{qty} {spec['unit']}",
                         "pos": pos, "awb": positions[-1]["awb"], "cao": spec["cls"] in ("2.2",) or dgkey in ("rli", "rli0")}
                dgs.append(entry)
                positions[-1]["dg"] = spec["imp"]
                if spec["imp"] not in positions[-1]["shc"]:
                    positions[-1]["shc"].append(spec["imp"])

    # times
    req = booking.get("requested_at") or (now or dt.datetime.now(dt.timezone.utc).timestamp())
    std = dt.datetime.fromtimestamp(req, dt.timezone.utc) + dt.timedelta(minutes=45)
    std = std.replace(minute=(std.minute // 5) * 5, second=0, microsecond=0)
    block = ofp.get("est_block_min") or m.get("target_block_min") or 60
    sta = std + dt.timedelta(minutes=block)

    shc_used = sorted({c for p in positions for c in p["shc"]})
    fuel = {k: ofp.get(k) for k in ("block_fuel_lbs", "taxi_fuel_lbs", "trip_fuel_lbs", "reserve_fuel_lbs")}
    weights = {"payload_lbs": payload, "zfw_lbs": ofp.get("zfw_lbs"), "tow_lbs": ofp.get("tow_lbs"), "ldw_lbs": ofp.get("ldw_lbs"),
               "mtow_lbs": ac.get("mtow_lbs"), "max_payload_lbs": ac.get("max_payload_lbs")}
    d = {
        "version": 1, "ferry": ferry,
        "flight": booking["flight_number"], "mission_id": m["id"], "mission_title": m["title"], "category": m.get("category"),
        "priority": m.get("priority"), "briefing": m.get("briefing", ""), "cargo": m.get("cargo", ""), "scenario": m.get("scenario"),
        "date": std.strftime("%d %b %Y").upper(), "std": std.strftime("%H%MZ"), "sta": sta.strftime("%H%MZ"), "block_min": block,
        "aircraft": code, "aircraft_name": ac.get("name", code), "icao": ac.get("icao", ""), "tail": booking.get("airframe") or booking.get("partner_reg") or ofp.get("registration") or ("Partner aircraft" if m.get("contract") else "—"),
        "origin": m["origin"], "destination": m["destination"], "alternate": ofp.get("alternate"),
        "route": ofp.get("route") or "", "cruise": f"FL{round((ofp.get('cruise_ft') or 0) / 100):03d}" if ofp.get("cruise_ft") else "",
        "distance_nm": ofp.get("distance_nm") or m.get("distance_nm"), "ofp_id": ofp.get("request_id") or "",
        "captain": pilot, "fuel": fuel, "weights": weights,
        "deck": {"main": main, "lower": lower, "uld": deck["uld"], "luld": deck["luld"], "cap": deck["cap"], "lcap": deck["lcap"]},
        "positions": positions, "dg": dgs, "shc": [{"code": c, "name": SHC_NAMES.get(c, c)} for c in shc_used],
        "totals": {"units": len(positions), "pieces": sum(p["pieces"] for p in positions), "weight_lbs": sum(p["weight_lbs"] for p in positions),
                   "main_lbs": sum(p["weight_lbs"] for p in positions if p["pos"].startswith("M")),
                   "lower_lbs": sum(p["weight_lbs"] for p in positions if not p["pos"].startswith("M"))},
        "release_no": f"{(m.get('operator') or {}).get('code', 'PAC')}-{std.strftime('%y%m%d')}-{rng.randrange(1000, 9999)}",
        "operator": m.get("operator"),
        "charter_customer": (m.get("customer") or {}).get("name", ""),
    }
    import shipments  # shippers, consignees and the ground handling timeline
    d["shipment_seed"] = seed
    shipments.add(d)
    import group  # village freight for Pagani Remote Aviation on flights into Anchorage
    return group.add_onward(d, booking)


def attach_transfers(d, shipments, booking):
    """Put previously manifested warehouse shipments into free positions on this flight."""
    if not shipments:
        return d
    occupied = {p["pos"] for p in d.get("positions") or []}
    deck = d["deck"]
    slots = []
    for pos in deck["main"]:
        if pos not in occupied:
            slots.append((pos, deck["uld"], int(deck["cap"])))
    for pos in deck["lower"]:
        if pos not in occupied:
            cap = int(deck["lcap"])
            slots.append((pos, deck["luld"], cap))

    for item in shipments:
        shipment = dict(item["data"])
        shipment["shipment_id"] = item["id"]
        shipment["transfer"] = True
        shipment["cargo_source_awb"] = shipment.get("cargo_source_awb") or item["awb"]
        shipment["awb"] = item["awb"]
        shipment.setdefault("destination", {"icao": item["destination"]})
        source_units = shipment.get("unit_details") or []
        if not source_units:
            raise ValueError(f"Transfer shipment {item['awb']} has no stored unit manifest and cannot be loaded.")
        loaded_units = []
        for source in source_units:
            weight = int(source.get("weight_lbs") or 0)
            pieces = int(source.get("pieces") or 0)
            if weight <= 0 or pieces <= 0:
                raise ValueError(f"Transfer shipment {item['awb']} has an invalid unit manifest.")
            chunks = []
            while weight:
                cap = max((slot[2] for slot in slots), default=0)
                if cap <= 0:
                    raise ValueError(f"The {d['aircraft_name']} has no free positions for all selected transfer cargo.")
                chunk = min(weight, cap)
                chunks.append(chunk)
                weight -= chunk
            if len(chunks) > pieces:
                raise ValueError(f"AWB {item['awb']} has a unit too heavy for this aircraft's ULD limits.")
            remaining_pieces = pieces
            remaining_weight = sum(chunks)
            for index, chunk in enumerate(chunks):
                compatible = next((i for i, slot in enumerate(slots) if slot[2] >= chunk), None)
                if compatible is None:
                    raise ValueError(f"The {d['aircraft_name']} has no compatible free ULD position for AWB {item['awb']}.")
                pos, uld, _ = slots.pop(compatible)
                unit_pieces = (remaining_pieces if index == len(chunks) - 1 else
                               max(1, min(remaining_pieces - len(chunks[index + 1:]),
                                          round(pieces * chunk / remaining_weight))))
                remaining_pieces -= unit_pieces
                remaining_weight -= chunk
                unit_rng = random.Random("{}|{}|{}".format(booking.get("manifest_seed"), item["awb"], pos))
                unit_id = "BULK" if uld == "BULK" else f"{uld}{unit_rng.randrange(10000, 99999)}PC"
                position = {
                    "pos": pos, "uld": uld, "unit": unit_id, "awb": item["awb"],
                    "contents": source.get("contents") or shipment.get("contents") or "Transfer cargo",
                    "shc": list(source.get("shc") or shipment.get("shc") or ["GEN"]),
                    "pieces": unit_pieces, "weight_lbs": chunk, "dg": source.get("dg"),
                }
                d["positions"].append(position)
                dg_entry = source.get("dg_entry")
                if dg_entry and index == 0:
                    entry = dict(dg_entry)
                    entry.update({"pos": pos, "awb": item["awb"]})
                    d["dg"].append(entry)
                loaded_units.append(position)
        shipment["units"] = [p["pos"] for p in loaded_units]
        shipment["unit_details"] = loaded_units
        shipment["pieces"] = sum(p["pieces"] for p in loaded_units)
        shipment["weight_lbs"] = sum(p["weight_lbs"] for p in loaded_units)
        shipment["no"] = len(d["shipments"]) + 1
        awb_doc = shipment.get("awb_doc") or {}
        track = awb_doc.get("track") or []
        manifest_event = f"MANIFESTED ON {d.get('flight', '')}"
        if not any(event.get("what") == manifest_event for event in track):
            try:
                day = dt.datetime.strptime(d["date"], "%d %b %Y").replace(tzinfo=dt.timezone.utc)
                std = day.replace(hour=int(d["std"][:2]), minute=int(d["std"][2:4]))
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"Transfer shipment {item['awb']} has invalid dispatch times.")
            sta = std + dt.timedelta(minutes=d.get("block_min") or 60)
            stamp = lambda value: value.strftime("%d%b %H%MZ").upper()
            track.extend([
                {"code": "MAN", "what": manifest_event, "at": stamp(std - dt.timedelta(minutes=20)), "where": d["origin"]["icao"]},
                {"code": "DEP", "what": "DEPARTED", "at": stamp(std), "where": d["origin"]["icao"]},
                {"code": "ARR", "what": "ARRIVED", "at": stamp(sta), "where": d["destination"]["icao"]},
                {"code": "RCF", "what": "RECEIVED FROM FLIGHT", "at": stamp(sta + dt.timedelta(minutes=35)),
                 "where": d["destination"]["icao"]},
            ])
            final = (shipment.get("destination") or {}).get("icao") or item["destination"]
            if final == d["destination"]["icao"]:
                track.append({"code": "DLV", "what": "DELIVERED TO CONSIGNEE", "at": stamp(sta + dt.timedelta(hours=6)),
                              "where": d["destination"]["icao"]})
            else:
                track.append({"code": "TRS", "what": f"TRANSFER TO {final}", "at": stamp(sta + dt.timedelta(minutes=50)),
                              "where": d["destination"]["icao"]})
            awb_doc["track"] = track
            shipment["awb_doc"] = awb_doc
        d["shipments"].append(shipment)

    positions = d["positions"]
    d["weights"]["payload_lbs"] = sum(p["weight_lbs"] for p in positions)
    d["totals"] = {
        "units": len(positions),
        "pieces": sum(p["pieces"] for p in positions),
        "weight_lbs": sum(p["weight_lbs"] for p in positions),
        "main_lbs": sum(p["weight_lbs"] for p in positions if p["pos"].startswith("M")),
        "lower_lbs": sum(p["weight_lbs"] for p in positions if not p["pos"].startswith("M")),
    }
    used = sorted({code for p in positions for code in p.get("shc") or []})
    d["shc"] = [{"code": code, "name": SHC_NAMES.get(code, code)} for code in used]
    return d


# ---------------------------------------------------------------- the paperwork around the release (authentic figures)
# published structural limits (lb): max zero fuel weight and max landing weight; MTOW comes from the fleet data
LIMITS = {"B732F": (95000, 107000), "B733F": (106500, 114000), "B738F": (138300, 146300), "B722F": (147000, 161000),
          "A306F": (286600, 308600), "MD11F": (461300, 491500), "B752F": (200000, 210000), "B763F": (309000, 326000),
          "B77F": (547000, 575000), "B742F": (590000, 660000), "B748F": (721000, 757000)}
# ICAO emergency response drill codes and packing groups for the dangerous goods PAC carries
ERG = {"UN3480": ("12FZ", "—"), "UN1066": ("2L", "—"), "UN1760": ("8L", "II"), "UN1845": ("9A", "—"), "UN3481": ("12FZ", "—"), "UN3530": ("9L", "—"), "UN1072": ("2X", "—"), "UN2794": ("8L", "III"),
       "UN1263": ("3L", "II"), "ID8000": ("9L", "—")}
DISPATCHERS = ["R. MORALES", "K. OYELARAN", "T. BRANDT", "M. CASTELLANO", "J. WHITFIELD", "S. NAKAMURA", "A. DELACROIX", "P. SINGH"]


def paperwork(d, fleet, booking=None, notams=None, captain_rank=None, airports=None, dow_override=None):
    """Everything a real release package carries beyond the cargo: limits, the loadsheet figures, dispatcher, SELCAL,
    release validity, minimum fuel and company NOTAMs. Deterministic for a given release, so reprints match."""
    rng = random.Random(d.get("release_no", "") + "|paperwork")
    ac = fleet.get(d["aircraft"], {})
    mtow = ac.get("mtow_lbs") or 150000
    mzfw, mlw = LIMITS.get(d["aircraft"], (round(mtow * .75, -2), round(mtow * .8, -2)))
    max_pl = ac.get("max_payload_lbs") or round(mzfw * .4)
    # dry operating weight: max payload is MZFW less DOW, so a full legal load always fits under the MZFW
    dow = round(mzfw - max_pl, -2) if d["aircraft"] in LIMITS and ac.get("max_payload_lbs") else max(round(mzfw - max_pl, -2), round(mtow * .45, -2))
    if dow_override:   # the dry operating weight PAC has seen in pilots' SimBrief plans for this type
        dow = round(dow_override, -2)
    w, f = d.get("weights") or {}, d.get("fuel") or {}
    payload = int(w.get("payload_lbs") or 0)
    zfw = int(w.get("zfw_lbs") or (dow + payload))
    dow = zfw - payload if w.get("zfw_lbs") else dow  # the OFP's dry operating weight when there is one
    burn = ac.get("fuel_burn_pph") or 5000
    block_min = d.get("block_min") or 60
    trip = int(f.get("trip_fuel_lbs") or round(burn * max(.3, (block_min - 25) / 60) * 1.05, -1))
    taxi = int(f.get("taxi_fuel_lbs") or round(burn * .08, -1))
    reserve = int(f.get("reserve_fuel_lbs") or round(burn * .75, -1))
    contingency = round(trip * .05, -1)
    block = int(f.get("block_fuel_lbs") or (trip + taxi + reserve + contingency + round(burn * .5, -1)))
    tof = block - taxi
    tow = int(w.get("tow_lbs") or (zfw + tof))
    law = int(w.get("ldw_lbs") or (tow - trip))
    min_release = trip + reserve + contingency + round(burn * .25, -1)  # trip, final reserve, contingency, alternate allowance
    # balance: where the cargo sits along the hold sets the center of gravity (%MAC) and the stabilizer trim
    main = d.get("deck", {}).get("main") or []
    pos_ix = {p: (i + .5) / max(1, len(main)) for i, p in enumerate(main)}
    moment = sum(p["weight_lbs"] * pos_ix.get(p["pos"], .55) for p in d.get("positions", []))
    pcg = moment / payload if payload else .5
    mac_dow = 22.0 + rng.uniform(-1.5, 1.5)
    mac_zfw = round((dow * mac_dow + payload * (14 + pcg * 22)) / max(1, zfw), 1)
    mac_tow = round(mac_zfw - (tof / max(1, tow)) * 4.5, 1)
    doi = round(45 + (mac_dow - 22) * 2.4, 1)
    dli = round(doi + (mac_zfw - mac_dow) * 3.1, 1)
    lizfw, litow = dli, round(dli + (mac_tow - mac_zfw) * 3.1, 1)
    airbus = ac.get("icao", "").startswith("A")
    trim = f"{round((26 - mac_tow) * .2, 1):+.1f} THS" if airbus else f"{round(9.6 - .2 * mac_tow, 1):.1f} UNITS"
    underload = min(mzfw - zfw, mtow - tow, mlw + trip - tow)
    issued = (booking or {}).get("requested_at") or 0
    reg = str(d.get("tail") or "")
    sel = "".join(rng.sample("ABCDEFGHJKLMPQRS", 4))
    crew = "3/0" if d["aircraft"] in ("B722F", "B742F") else "2/0"
    dow, zfw, tof, tow, trip, law, taxi, block, underload, min_release, contingency, mzfw, mlw, mtow, max_pl = (
        int(round(v)) for v in (dow, zfw, tof, tow, trip, law, taxi, block, underload, min_release, contingency, mzfw, mlw, mtow, max_pl))
    return {
        "limits": {"mzfw": mzfw, "mtow": mtow, "mlw": mlw, "max_payload": max_pl},
        "loadsheet": {"dow": dow, "payload": payload, "zfw": zfw, "tof": tof, "tow": tow, "trip": trip, "law": law, "taxi": taxi, "block": block,
                      "underload": underload, "doi": doi, "dli": dli, "lizfw": lizfw, "litow": litow, "mac_zfw": mac_zfw, "mac_tow": mac_tow,
                      "trim": trim, "crew": crew, "edno": "01"},
        "min_release_fuel": min_release, "contingency": contingency,
        "dispatcher": {"name": rng.choice(DISPATCHERS), "cert": f"ADX {rng.randrange(2000000, 3999999)}"},
        "pic_cert": f"ATP {rng.randrange(2000000, 3999999)}", "captain_rank": captain_rank,
        "selcal": f"{sel[:2]}-{sel[2:]}", "callsign": "PAGANI " + "".join(ch for ch in d["flight"] if ch.isdigit()),
        "issued_at": issued, "fltplan_filed": "YES" if d.get("ofp_id") else "NO",
        "cost_index": ((booking or {}).get("ofp") or {}).get("cost_index"),
        "erg": {k: {"erg": v[0], "pg": v[1]} for k, v in ERG.items()},
        "briefing": __import__("copy").deepcopy(((booking or {}).get("ofp") or {}).get("briefing")),
        "notams": [{"title": n.get("title"), "body": n.get("body"), "id": n.get("id")} for n in (notams or [])],
        "form": {"release": "OCC-121-1 REV 07/26", "loadsheet": "LDS-517 REV 03/26", "manifest": "CGO-210 REV 05/26",
                 "notoc": "DGR-1001 REV 01/26", "weather": "OCC-WX-4 REV 07/26", "awb": "CGO-AWB REV 11/26"},
        "reg_hash": reg,
        "iata": {k: (airports or {}).get(k, {}).get("iata") or k[-3:] for k in
                 [d["origin"]["icao"], d["destination"]["icao"]] + ([d["alternate"]["icao"]] if d.get("alternate") else [])},
    }
