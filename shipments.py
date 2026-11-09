"""Who is shipping what, to whom, and how it moves through the airport.

The cargo manifest says what sits in each position. This module groups those units into
shipments (one air waybill each), with a real shipper near the departure airport and a real
consignee near the arrival airport that fit the cargo (companies.py), a short note on why it
is flying, and how to handle it. It also builds the ground handling timeline around the
flight: acceptance, build-up, weighing, loading, doors closed, and offload, customs and
delivery at the other end.

The shipments themselves are invented for flight simulation: the paperwork says so, and
nothing here claims a real business relationship with PAC.

Everything is seeded from the release number, so reprints of the same release match.
"""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

import companies

DATA = Path(__file__).resolve().parent / "data"
_AIRPORTS = None

ME = {"AE", "QA", "SA", "BH", "KW", "OM", "IL", "JO", "TR", "IQ", "IR", "LB", "YE"}
PAC_HUBS = {"KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC"}


def airports():
    global _AIRPORTS
    if _AIRPORTS is None:
        try:
            raw = json.loads((DATA / "airports.json").read_text(encoding="utf-8"))
            f = raw["fields"]
            _AIRPORTS = {r[0]: dict(zip(f, r)) for r in raw["rows"]}
        except Exception:
            _AIRPORTS = {}
    return _AIRPORTS


def region(icao):
    a = airports().get(icao) or {}
    c, cont = a.get("country", ""), a.get("continent", "")
    if c in ME:
        return "ME"
    return cont or "NA"


CITY = {"KCVG": "Cincinnati", "LIMC": "Milan", "OMDW": "Dubai", "EBLG": "Liège", "EGSS": "London", "LFPG": "Paris", "RJAA": "Tokyo",
        "EDDP": "Leipzig", "RCTP": "Taipei", "ZSPD": "Shanghai", "ZGGG": "Guangzhou", "YSSY": "Sydney", "SAEZ": "Buenos Aires",
        "EBBR": "Brussels", "ENGM": "Oslo", "EDDF": "Frankfurt", "KONT": "Ontario, California", "EGLL": "London", "LIRF": "Rome",
        "SKBO": "Bogotá", "KPAE": "Everett", "KBFI": "Seattle", "TNCM": "St. Maarten", "NTGJ": "the Gambier Islands", "EINN": "Shannon",
        "ZULS": "Lhasa"}


def place(icao):
    a = airports().get(icao) or {}
    city = CITY.get(icao) or a.get("city") or a.get("name") or icao
    city = city.split(" (")[0].split("(")[0].split(" / ")[0].strip()
    return city, a.get("country", "")


# ------------------------------------------------------------------ companies
# Each list is (name, regions it fits). "*" fits anywhere.
KEYS = [
    ("plasma", ("plasma",)), ("isotope", ("isotope",)), ("nutrition", ("therapeutic food", "fortified")),
    ("pharma", ("pharma", "vaccine", "insulin", "biologic", "clinical", "medical consumables")),
    ("fire", ("fire retardant", "firefighting")),
    ("automotive", ("automotive", "engine control", "wiring")),
    ("aog", ("aog", "engine", "aircraft spares", "aircraft spare", "landing gear", "avionics", "engine change")),
    ("semis", ("wafer", "semiconductor", "fab")),
    ("electronics", ("consumer electronics", "electronic", "smartphone", "satellite phones")),
    ("ecommerce", ("e-commerce", "online orders", "peak-season")), ("mail", ("mail",)), ("express", ("express", "parcel", "courier", "documents")),
    ("flowers", ("flower", "rose", "carnation")), ("seafood", ("seafood", "salmon", "fish", "lobster", "shrimp")),
    ("wine", ("beaujolais", "wine")), ("produce", ("produce", "fruit", "cherries", "asparagus", "avocado", "blueberr", "vegetable", "meat and dairy")),
    ("energy", ("oil and gas", "wellhead", "drilling", "transformer", "turbine", "power")), ("mining", ("mining", "tyre", "tire")),
    ("helicopter", ("helicopter",)), ("batteries", ("lithium-ion batteries", "lithium ion batteries", "battery packs")),
    ("valuables", ("bullion", "banknote", "gold")), ("livestock", ("cattle", "heifer")), ("zoo", ("rhino", "zoo")),
    ("tour", ("stage, lighting", "touring", "tour's")),
    ("showcars", ("show car",)),
    ("fashion", ("garment", "luxury", "retail", "apparel")), ("racehorses", ("racehorse", "live animals", "thoroughbred")),
    ("art", ("painting", "sculpture", "fine art")), ("space", ("satellite in", "communications satellite")),
    ("polar", ("antarctic", "research station", "science")),
    ("humanitarian", ("relief", "humanitarian", "shelter", "tarpaulin", "water purification", "emergency food", "field hospital",
                      "generator", "oxygen", "surgical", "rescue", "tents")),
    ("resupply", ("resupply", "village", "island", "community")),
]

# the mission board's scenarios (missiongen) and what they carry
SCENARIO = {"hurricane": "humanitarian", "typhoon": "humanitarian", "monsoon": "humanitarian", "earthquake": "humanitarian",
            "food_aid": "humanitarian", "wildfire_north": "fire", "wildfire_south": "fire", "outbreak": "pharma", "vaccines": "pharma",
            "isotopes": "isotope", "plasma": "plasma", "valentine": "flowers", "mothers_day": "flowers", "cherries": "produce",
            "kenya_veg": "produce", "asparagus": "produce", "salmon": "seafood", "lobster": "seafood", "beaujolais": "wine",
            "aog_engine": "aog", "aog_parts": "aog", "semiconductor": "semis", "automotive": "automotive", "satellite": "space",
            "oil_gas": "energy", "power": "energy", "dg_chemicals": "energy", "antarctic": "polar", "racehorses": "racehorses",
            "supercars": "showcars", "art": "art", "ecommerce_peak": "ecommerce", "mail": "mail", "pharma": "pharma",
            "dg_batteries": "batteries", "live_cattle": "livestock", "zoo_transfer": "zoo", "valuables": "valuables", "tour_gear": "tour"}

ONE_CUSTOMER = {"aog", "space", "showcars", "art", "racehorses", "zoo", "helicopter", "tour", "polar"}
COMPATIBLE = [{"express", "ecommerce", "mail"}, {"humanitarian", "pharma", "nutrition"}]

SERVICE = {"aog": "AOG", "isotope": "CRITICAL", "pharma": "TEMP CONTROLLED", "plasma": "TEMP CONTROLLED FROZEN", "humanitarian": "HUMANITARIAN",
           "nutrition": "HUMANITARIAN", "fire": "EMERGENCY", "express": "EXPRESS", "mail": "MAIL", "ecommerce": "DEFERRED EXPRESS",
           "flowers": "PERISHABLE", "seafood": "PERISHABLE", "produce": "PERISHABLE", "wine": "TIME DEFINITE", "semis": "HIGH VALUE",
           "electronics": "HIGH VALUE", "art": "HIGH VALUE ESCORTED", "racehorses": "LIVE ANIMALS", "space": "OUTSIZE / HIGH VALUE",
           "energy": "HEAVY / OUTSIZE", "mining": "PRIORITY", "automotive": "TIME DEFINITE", "showcars": "HIGH VALUE",
           "fashion": "STANDARD", "batteries": "DANGEROUS GOODS", "livestock": "LIVE ANIMALS", "zoo": "LIVE ANIMALS",
           "valuables": "HIGH VALUE ESCORTED", "helicopter": "OUTSIZE", "tour": "TIME DEFINITE", "polar": "PRIORITY", "resupply": "STANDARD", "general": "GENERAL"}

# hours after on-block that the consignee gets the freight
DELIVER_H = {"AOG": 1.5, "CRITICAL": 1.5, "EMERGENCY": 2, "EXPRESS": 2, "TEMP CONTROLLED": 3, "TEMP CONTROLLED FROZEN": 3,
             "PERISHABLE": 3, "LIVE ANIMALS": 1.5, "HUMANITARIAN": 4, "MAIL": 4, "HIGH VALUE ESCORTED": 3}

HANDLING = {
    "PIL": "KEEP +2 TO +8 C. MAX 30 MIN ON RAMP. ACTIVE CONTAINERS: DO NOT SWITCH OFF.",
    "COL": "COOL GOODS. KEEP OUT OF SUN, STORE IN COLD ROOM ON ARRIVAL.",
    "CRT": "CONTROLLED ROOM TEMPERATURE +15 TO +25 C.",
    "ICE": "DRY ICE ON BOARD. VENTILATE HOLD BEFORE ENTRY. SEE NOTOC.",
    "AVI": "LIVE ANIMALS. LOAD LAST, OFFLOAD FIRST. CHECK HOLD TEMPERATURE AND VENTILATION.",
    "VAL": "VALUABLE CARGO. ESCORT FROM ACCEPTANCE TO AIRCRAFT. SEALS CHECKED AT EACH HANDOVER.",
    "HEA": "HEAVY PIECES. USE SPREADER FLOOR. CHECK FLOOR LOADING LIMITS.",
    "BIG": "OUTSIZE. CHECK DOOR CLEARANCE AND CONTOUR BEFORE BUILD-UP.",
    "PER": "PERISHABLE. LOAD LAST, OFFLOAD FIRST.",
    "PEF": "FLOWERS. KEEP COOL, DO NOT STACK.",
    "PES": "FISH AND SEAFOOD. KEEP CHILLED, LEAK-PROOF PACKAGING CHECKED.",
    "AOG": "AOG. HIGHEST HANDLING PRIORITY. COURIER MEETS AIRCRAFT.",
    "HUM": "HUMANITARIAN. RELEASE TO CONSIGNEE TRUCKS AIRSIDE IF PERMITTED.",
    "RLI": "LITHIUM BATTERIES. CARGO AIRCRAFT ONLY. SEE NOTOC.",
    "ELI": "LITHIUM BATTERIES IN EQUIPMENT (SECTION II). HANDLE WITH CARE.",
    "MAL": "MAIL. KEEP IN SECURE AREA. HAND TO POSTAL OPERATOR ONLY.",
    "COU": "COURIER. PRIORITY BREAKDOWN ON ARRIVAL.",
}

FAKE_NAMES = ["A. RAMIREZ", "D. MBEKI", "L. JOHANSSON", "H. TANAKA", "P. O'BRIEN", "M. ROSSI", "S. KAPOOR", "C. NGUYEN", "F. HADDAD",
              "J. SCHMIDT", "R. ALVES", "K. NOWAK", "T. OKAFOR", "E. MARTIN", "Y. CHEN", "B. KOWALCZYK"]


def sector_for(text):
    t = (text or "").lower()
    for key, words in KEYS:
        if any(w in t for w in words):
            return key
    return "general"


def handler(icao, rng):
    return companies.handler(icao, (airports().get(icao) or {}).get("name"))


def add(d):
    """Group the manifest into shipments and add the ground handling timeline. Changes d in place and returns it."""
    positions = d.get("positions") or []
    rng = random.Random(f"{d.get('shipment_seed', d.get('release_no', ''))}|shipments")
    o, de = d["origin"]["icao"], d["destination"]["icao"]
    oreg, dreg = region(o), region(de)
    ocity, octry = place(o)
    dcity, dctry = place(de)
    owhere, dwhere = {oreg, "c:" + octry}, {dreg, "c:" + dctry}
    scen = d.get("scenario") or ""
    ms = SCENARIO.get(scen) or sector_for(f"{d.get('cargo', '')} {d.get('mission_title', '')}")
    if scen.startswith("challenge_") and ms not in ("pharma", "humanitarian", "mining", "energy", "polar"):
        ms = "resupply"
    cat = d.get("category") or ""
    if cat == "Humanitarian" and ms not in ("nutrition", "fire", "pharma"):
        ms = "humanitarian"
    elif cat == "Medical" and ms not in ("plasma", "isotope"):
        ms = "pharma"
    if d.get("category") == "Challenge" and ms in ("mail", "express", "produce", "ecommerce", "general"):
        ms = "resupply"      # remote strips: the community's supply run

    # group the units: same contents together, split big groups so a full freighter carries several shippers' freight
    groups = {}
    for p in positions:
        groups.setdefault(p["contents"], []).append(p)
    chunks = []
    for contents, units in groups.items():
        size = rng.randint(2, 6) if len(units) > 6 else len(units)
        for i in range(0, len(units), size):
            chunks.append((contents, units[i:i + size]))
    used_shippers, customer = set(), {}
    shipments = []
    for n, (contents, units) in enumerate(chunks):
        sec = sector_for(contents)
        if sec == "general" and ms in ("humanitarian", "pharma", "resupply", "polar", "energy", "mining"):
            sec = ms                     # a plain description on a relief or supply flight still belongs to that customer
        elif ms in ("humanitarian", "nutrition") and sec in ("electronics", "general", "energy", "resupply"):
            sec = "humanitarian"         # satellite phones, generators and the like on a relief flight are relief stock
        # Real companies that do this business where the flight starts and ends (companies.py); the shipment is fictional.
        if sec in ONE_CUSTOMER and sec in customer:
            shipper, consignee = customer[sec]
        else:
            shipper = companies.pick(companies.SHIPPERS, sec, octry, oreg, rng, used_shippers, ocity, o)
            if sec == "express":         # an express network flies its own freight: the same company receives it
                consignee = companies.express_consignee(shipper, dcity, bool(octry and dctry and octry != dctry))
            else:
                consignee = companies.pick(companies.CONSIGNEES, sec, dctry, dreg, rng, (), dcity, de)
                if consignee == shipper and sec not in ("mail", "ecommerce", "automotive", "semis", "zoo", "valuables"):
                    consignee = companies.pick(companies.CONSIGNEES, sec, dctry, dreg, rng, (shipper,), dcity, de)
            customer[sec] = (shipper, consignee)
        used_shippers.add(shipper)
        fwd = companies.forwarder(sec, rng, (oreg, dreg))
        story = f"{shipper} is shipping {contents[0].lower() + contents[1:]} from {ocity} to {consignee} in {dcity}."
        if sec == "aog":
            story = f"{shipper} is rushing {contents[0].lower() + contents[1:]} to {consignee} in {dcity} to get a grounded aircraft back in service."
        elif sec in ("humanitarian", "nutrition"):
            story = f"{shipper} is moving {contents[0].lower() + contents[1:]} from {ocity} to {consignee} for distribution in and around {dcity}."
        service = SERVICE.get(sec, "GENERAL")
        if sec == "general" and d.get("priority") in ("Urgent", "High"):
            service = "PRIORITY"
        shc = sorted({c for u in units for c in u.get("shc", [])})
        handling = [HANDLING[c] for c in shc if c in HANDLING]
        awb = units[0]["awb"]
        for u in units:            # one air waybill per shipment
            u["awb"] = awb
            u["ship"] = n + 1
        shipments.append({
            "no": n + 1, "awb": awb, "sector": sec, "service": service, "contents": contents,
            "shipper": {"name": shipper, "city": ocity, "country": octry},
            "consignee": {"name": consignee, "city": dcity, "country": dctry},
            "agent": None if (not fwd or shipper.startswith(fwd)) else fwd, "notify": rng.choice(FAKE_NAMES),
            "units": [u["pos"] for u in units], "pieces": sum(u["pieces"] for u in units),
            "weight_lbs": sum(u["weight_lbs"] for u in units), "shc": shc, "handling": handling, "story": story,
            "deliver_h": DELIVER_H.get(service, 6),
        })
    for g in d.get("dg") or []:     # the NOTOC follows the waybill of the unit it sits in
        u = next((p for p in positions if p["pos"] == g.get("pos")), None)
        if u:
            g["awb"] = u["awb"]
    d["shipments"] = shipments
    d["international"] = bool(octry and dctry and octry != dctry)
    d["handling"] = timeline(d, rng)
    d["handlers"] = {"origin": handler(o, rng), "destination": handler(de, rng)}
    d["version"] = max(2, d.get("version", 1))
    return d


def route_through(d, routes, seed):
    """Give some consignments a scheduled onward destination through this flight's arrival station."""
    if d.get("ferry") or not d.get("shipments"):
        return d
    arrival = (d.get("destination") or {}).get("icao")
    onward = sorted({
        route["destination"]["icao"]: route["destination"]
        for route in routes
        if route.get("category") == "Scheduled"
        and (route.get("origin") or {}).get("icao") == arrival
        and (route.get("destination") or {}).get("icao") != arrival
        and (route.get("destination") or {}).get("icao") != (d.get("origin") or {}).get("icao")   # never back where it came from
    }.values(), key=lambda a: a["icao"])
    if not onward:
        return d
    rng = random.Random(f"{seed}|through")
    used = set()
    through = [shipment for shipment in d["shipments"] if rng.random() < 0.3]
    if not through:
        through = [rng.choice(d["shipments"])]
    for shipment in through:
        dest = rng.choice(onward)
        dcity, dctry = place(dest["icao"])
        shipment["destination"] = {"icao": dest["icao"], "city": dcity, "country": dctry}
        sector = shipment.get("sector") or "general"
        if sector == "express":
            consignee = companies.express_consignee(
                shipment["shipper"]["name"], dcity,
                bool(shipment["shipper"].get("country") and dctry
                     and shipment["shipper"]["country"] != dctry))
        else:
            avoid = used | {shipment["shipper"]["name"]}
            consignee = companies.pick(companies.CONSIGNEES, sector, dctry,
                                       region(dest["icao"]), rng, avoid, dcity, dest["icao"])
        shipment["consignee"] = {"name": consignee, "city": dcity, "country": dctry}
        used.add(consignee)
        shipment["story"] = (f"{shipment['shipper']['name']} is shipping {shipment['contents'][0].lower()}"
                             f"{shipment['contents'][1:]} from {shipment['shipper']['city']} to {consignee} in {dcity}, "
                             f"via {arrival}.")
    return d


def _t(base, minutes):
    return (base + dt.timedelta(minutes=minutes)).strftime("%d%b %H%MZ").upper()


def timeline(d, rng):
    """The ground handling milestones around the flight, from cargo acceptance to delivery."""
    try:
        day = dt.datetime.strptime(d["date"], "%d %b %Y")
        std = day.replace(hour=int(d["std"][:2]), minute=int(d["std"][2:4]), tzinfo=dt.timezone.utc)
    except Exception:
        return []
    sta = std + dt.timedelta(minutes=d.get("block_min") or 60)
    wide = len((d.get("deck") or {}).get("main") or []) >= 20
    ferry = d.get("ferry") or not d.get("positions")
    express = (d.get("category") or "") == "Express" or any(s["service"] in ("EXPRESS", "MAIL") for s in d.get("shipments") or [])
    o, de = d["origin"]["icao"], d["destination"]["icao"]
    dep, arr = [], []
    if not ferry:
        cut = -180 if express else (-240 if wide else -180)
        dep.append((_t(std, cut), "LATEST ACCEPTANCE", "CARGO TERMINAL CLOSES FOR THIS FLIGHT"))
        if d.get("dg"):
            dep.append((_t(std, cut + 30), "DG ACCEPTANCE CHECK", "DANGEROUS GOODS CHECKED AGAINST SHIPPERS DECLARATIONS"))
        if any("AVI" in s["shc"] for s in d["shipments"]):
            dep.append((_t(std, cut + 30), "LIVE ANIMAL CHECK", "ANIMALS INSPECTED, WATER AND DOCUMENTS CHECKED"))
        dep.append((_t(std, -150 if wide else -120), "BUILD-UP COMPLETE", f"{len(d['positions'])} UNITS BUILT, CONTOURED AND NETTED"))
        dep.append((_t(std, -105 if wide else -80), "ULDS WEIGHED", "UNIT WEIGHTS SENT TO LOAD CONTROL"))
        dep.append((_t(std, -90 if wide else -60), "SECURITY SCREENING", "ALL UNITS SCREENED OR FROM A KNOWN CONSIGNOR"))
    dep.append((_t(std, -75 if wide else -60), "CREW REPORT", "CAPTAIN SIGNS THE DISPATCH RELEASE" + (" AND NOTOC" if d.get("dg") else "")))
    if not ferry:
        dep.append((_t(std, -70 if wide else -50), "LOADING STARTS", "SIMULATED LOAD PLAN; AIRCRAFT-SPECIFIC PROCEDURES APPLY"))
        if any(s["service"] in ("PERISHABLE", "LIVE ANIMALS", "AOG", "CRITICAL") for s in d["shipments"]):
            dep.append((_t(std, -30), "LAST-MINUTE LOAD", "PERISHABLES, AOG AND LIVE ANIMALS LOADED LAST"))
        dep.append((_t(std, -20), "FINAL LOADSHEET", "SENT TO THE FLIGHT DECK BY ACARS"))
    dep.append((_t(std, -10), "DOORS CLOSED", ""))
    dep.append((_t(std, 0), "OFF BLOCK", "PUSHBACK"))
    arr.append((0, "ON BLOCK", ""))
    if not ferry:
        arr.append((10, "OFFLOAD STARTS", "PRIORITY UNITS FIRST"))
        arr.append((45 if wide else 30, "OFFLOAD COMPLETE", "UNITS TO THE CARGO TERMINAL"))
        arr.append((75 if wide else 55, "BREAKDOWN", "UNITS BROKEN DOWN AND CHECKED AGAINST THE MANIFEST"))
        if d.get("international"):
            arr.append((60, "CUSTOMS", "PLANNED CUSTOMS PROCESSING; RELEASE SUBJECT TO CLEARANCE"))
        for s in sorted(d["shipments"], key=lambda s: s["deliver_h"])[:6]:
            final = (s.get("destination") or {}).get("icao") or de
            if final != de:
                arr.append((45 if wide else 30, "TRANSFER " + s["awb"], f"SECURE FOR ONWARD FLIGHT TO {final}"))
            else:
                arr.append((round(s["deliver_h"] * 60), "PLANNED RELEASE " + s["awb"], f"TO {s['consignee']['name']}".upper()))
    arr.sort(key=lambda x: x[0])
    return {"dep": [{"t": a, "what": b, "note": c} for a, b, c in dep], "arr": [{"t": _t(sta, a), "what": b, "note": c} for a, b, c in arr],
            "dep_station": o, "arr_station": de}


# ------------------------------------------------------------------ the full air waybill for each shipment
# Everything below fills in what a real air waybill (contract of carriage), the warehouse acceptance record and the
# shipment tracking history carry. The figures follow real practice (IATA volumetric divisor, rate classes, status codes,
# HS headings, security methods); the companies, references and values are fictional and deterministic per release.

# (keywords in the contents, HS code, customs description, packaging, density kg/m3)
GOODS = [
    (("pharmaceutical", "vaccine"), "3002.41", "VACCINES FOR HUMAN MEDICINE", "ACTIVE TEMPERATURE-CONTROLLED CONTAINERS (ENVIROTAINER TYPE)", 180),
    (("medical consumables",), "9018.39", "MEDICAL CONSUMABLES: CATHETERS, CANNULAE AND SIMILAR", "CARTONS ON SHRINK-WRAPPED PALLETS", 160),
    (("field hospital",), "9402.90", "MEDICAL FURNITURE AND FIELD HOSPITAL MODULES", "FLAT-PACKED MODULES ON SKIDS", 140),
    (("surgical",), "9018.90", "SURGICAL INSTRUMENTS AND APPLIANCES", "STERILE-PACKED CARTONS", 200),
    (("oxygen",), "2804.40", "OXYGEN, COMPRESSED IN CYLINDERS", "CYLINDERS IN STEEL CRADLES, VALVES CAPPED", 400),
    (("tarpaulin", "shelter"), "6306.12", "TARPAULINS AND SHELTER KITS", "BALES AND CARTONS, PALLETIZED", 220),
    (("water purification",), "8421.21", "WATER FILTERING AND PURIFYING MACHINERY", "WOODEN CRATES", 250),
    (("food ration",), "2106.90", "FOOD PREPARATIONS, EMERGENCY RATIONS", "CARTONS ON PALLETS", 350),
    (("generator",), "8502.11", "GENERATING SETS, DIESEL, FUEL DRAINED", "SKID-MOUNTED, STRAPPED", 380),
    (("satellite phone", "radios"), "8517.14", "SATELLITE TELEPHONES AND RADIO SETS", "FIBERBOARD CARTONS", 150),
    (("spare engine",), "8411.12", "TURBOFAN ENGINE ON TRANSPORT STAND", "ENGINE STAND WITH COVER, BOLTED TO PALLET", 300),
    (("aircraft spares", "engine change tooling"), "8803.30", "PARTS OF AIRPLANES", "WOODEN CRATES AND ATA 300 CASES", 220),
    (("consumer electronics",), "8517.13", "SMARTPHONES AND CONSUMER ELECTRONICS", "RETAIL CARTONS ON SHRINK-WRAPPED PALLETS", 170),
    (("semiconductor",), "8542.31", "ELECTRONIC INTEGRATED CIRCUITS AND WAFERS", "SEALED FOUPS IN SHOCK-ISOLATED CRATES, NITROGEN-PURGED", 150),
    (("electronic components",), "8541.49", "SEMICONDUCTOR DEVICES AND COMPONENTS", "ANTI-STATIC CARTONS", 180),
    (("express parcel",), "9999.00", "CONSOLIDATION AS PER ATTACHED MANIFEST", "PARCELS IN AKE CONTAINERS AND NETTED PALLETS", 160),
    (("e-commerce",), "9999.00", "CONSOLIDATION AS PER ATTACHED MANIFEST", "POLY BAGS AND CARTONS, BULK-LOADED IN CONTAINERS", 140),
    (("mail",), "", "POSTAL ITEMS (UPU CN 38 DELIVERY BILL)", "MAIL BAGS, SEALED BY THE POSTAL OPERATOR", 150),
    (("flowers",), "0603.11", "FRESH-CUT ROSES AND FLOWERS", "VENTILATED FLOWER BOXES, PRE-COOLED", 120),
    (("seafood",), "0302.14", "FRESH ATLANTIC SALMON AND SEAFOOD, CHILLED", "INSULATED POLYSTYRENE BOXES WITH GEL ICE / DRY ICE", 320),
    (("fresh produce",), "0809.29", "FRESH FRUIT AND VEGETABLES", "VENTILATED CARTONS, PRE-COOLED, ON PALLETS", 280),
    (("meat and dairy",), "0201.30", "CHILLED BEEF AND DAIRY PRODUCTS", "VACUUM-PACKED IN INSULATED CARTONS", 450),
    (("industrial machinery",), "8479.89", "INDUSTRIAL MACHINERY", "SEAWORTHY WOODEN CRATES, SKIDDED", 380),
    (("oil and gas",), "8481.80", "VALVES AND WELLHEAD EQUIPMENT", "STEEL FRAMES AND CRATES", 600),
    (("spare parts",), "8487.90", "MACHINERY SPARE PARTS", "CARTONS AND CRATES", 300),
    (("automotive",), "8708.99", "PARTS AND ACCESSORIES OF MOTOR VEHICLES", "RETURNABLE STEEL STILLAGES", 300),
    (("show car",), "8703.80", "MOTOR CARS, ELECTRIC, FOR EXHIBITION", "CLIMATE-CONTROLLED CAR CRATES, BATTERY ISOLATED", 120),
    (("garments",), "6204.43", "GARMENTS, WOMEN'S DRESSES", "GARMENTS ON HANGERS IN WARDROBE BOXES", 80),
    (("luxury",), "4202.21", "HANDBAGS AND LEATHER GOODS", "SEALED CARTONS, TAMPER TAPE", 150),
    (("retail stock",), "6109.10", "COTTON T-SHIRTS AND RETAIL STOCK", "CARTONS ON PALLETS", 200),
    (("live animals",), "0102.29", "LIVE ANIMALS", "IATA LAR-COMPLIANT CONTAINERS / STALLS", 250),
    (("lithium ion batteries",), "8507.60", "LITHIUM-ION ACCUMULATORS", "UN-SPECIFICATION FIBERBOARD BOXES", 450),
    (("chemicals",), "3824.99", "CHEMICAL PREPARATIONS FOR OIL-FIELD USE", "UN-SPECIFICATION DRUMS ON PALLETS", 700),
    (("gas cylinder",), "2804.30", "NITROGEN, COMPRESSED", "CYLINDERS IN STEEL CRADLES", 420),
    (("valuable",), "7108.13", "GOLD, SEMI-MANUFACTURED", "SEALED STEEL CASES UNDER ESCORT", 900),
    (("helicopter",), "8802.12", "HELICOPTER, UNLADEN WEIGHT OVER 2,000 KG", "ON SKID FRAME, BLADES REMOVED AND CRATED", 90),
    (("rotor blades",), "8803.20", "PARTS OF HELICOPTERS: ROTOR BLADES", "LONG WOODEN BLADE BOXES", 80),
    (("tires",), "4011.80", "NEW TIRES FOR CONSTRUCTION AND MINING VEHICLES", "UNPACKED, STRAPPED TO PALLETS", 500),
    (("touring production",), "9405.42", "STAGE LIGHTING AND TOURING EQUIPMENT", "ROAD CASES ON WHEELS", 220),
    (("relief",), "6306.22", "RELIEF SUPPLIES: TENTS AND SHELTER", "BALES AND CARTONS", 220),
]
GENERAL_GOODS = ("9999.00", "GENERAL CARGO AS PER ATTACHED INVOICE", "CARTONS ON SHRINK-WRAPPED PALLETS", 167)

# typical declared value for customs, USD per kg, by sector
VALUE_KG = {"semis": (900, 2600), "electronics": (120, 320), "pharma": (300, 1400), "plasma": (400, 900), "isotope": (2000, 6000),
            "aog": (600, 3500), "space": (8000, 20000), "showcars": (300, 900), "art": (5000, 40000), "valuables": (110000, 130000),
            "fashion": (40, 180), "flowers": (6, 12), "seafood": (12, 28), "produce": (3, 7), "wine": (18, 45), "automotive": (25, 80),
            "energy": (40, 160), "mining": (15, 40), "batteries": (30, 70), "helicopter": (900, 2500), "tour": (60, 200),
            "racehorses": (2000, 15000), "livestock": (6, 12), "zoo": (500, 3000), "polar": (60, 250)}
# rate per chargeable kg, USD, and the IATA rate class (Q quantity, C specific commodity, S surcharged class, R reduced)
RATE = {"AOG": (9.5, 16.0, "S"), "CRITICAL": (11.0, 18.0, "S"), "EMERGENCY": (3.0, 5.0, "R"), "EXPRESS": (5.5, 8.5, "Q"),
        "DEFERRED EXPRESS": (3.6, 5.2, "Q"), "MAIL": (2.2, 3.4, "C"), "TEMP CONTROLLED": (6.5, 10.5, "C"),
        "TEMP CONTROLLED FROZEN": (7.0, 11.0, "C"), "PERISHABLE": (2.8, 4.6, "C"), "HUMANITARIAN": (1.4, 2.4, "R"),
        "TIME DEFINITE": (3.8, 5.6, "Q"), "HIGH VALUE": (6.0, 9.5, "S"), "HIGH VALUE ESCORTED": (9.0, 15.0, "S"),
        "LIVE ANIMALS": (7.5, 12.0, "S"), "OUTSIZE / HIGH VALUE": (8.0, 13.0, "S"), "HEAVY / OUTSIZE": (4.2, 6.8, "Q"),
        "OUTSIZE": (4.5, 7.2, "Q"), "DANGEROUS GOODS": (5.0, 7.8, "S"), "PRIORITY": (3.6, 5.4, "Q")}
DEFAULT_RATE = (2.6, 4.2, "Q")

TEMPS = [("PIL", "+2 C TO +8 C (ACTIVE CONTROL)"), ("PES", "0 C TO +4 C (CHILLED)"),
         ("PEF", "+1 C TO +4 C (PRE-COOLED)"), ("COL", "+2 C TO +8 C"), ("CRT", "+15 C TO +25 C"), ("AVI", "+10 C TO +24 C HOLD, VENTILATED")]

# who screens what: real methods in the electronic consignment security declaration (e-CSD)
SCREEN = [("AVI", "VCK", "VISUAL CHECK OF CONTAINERS (LIVE ANIMALS EXEMPT FROM X-RAY)"),
          ("VAL", "PHS", "PHYSICAL SEARCH UNDER ESCORT, SEALS APPLIED"),
          ("BIG", "ETD", "EXPLOSIVE TRACE DETECTION (TOO LARGE FOR X-RAY)"),
          ("HEA", "ETD", "EXPLOSIVE TRACE DETECTION (TOO LARGE FOR X-RAY)"),
          ("PIL", "KC", "SECURED BY KNOWN CONSIGNOR, SEALED AT SOURCE"),
          ("AOG", "XRY", "X-RAY SCREENING")]


def _goods(contents):
    t = (contents or "").lower()
    for keys, hs, desc, pack, dens in GOODS:
        if any(k in t for k in keys):
            return hs, desc, pack, dens
    return GENERAL_GOODS


def _dims(rng, pieces, vol_m3, big):
    """Piece dimensions in cm: up to three size groups that add up to the shipment's volume."""
    pieces = max(1, pieces)
    groups = [pieces] if pieces < 4 else [pieces - pieces // 3 - pieces // 6, pieces // 3, pieces // 6]
    groups = [g for g in groups if g > 0]
    shares = [1.0] if len(groups) == 1 else [g / pieces for g in groups]
    out = []
    for g, share in zip(groups, shares):
        v = max(0.004, vol_m3 * share / g)          # volume of one piece, m3
        if big:                                       # long, flat or tall single items
            l, w = rng.uniform(1.8, 3.2), rng.uniform(0.8, 1.2)
        else:
            l, w = rng.uniform(0.9, 1.5), rng.uniform(0.7, 1.1)
        h = v / (l * w)
        if h < 0.12:                                  # small parcels: scale every side down together
            k = (v / (l * w * 0.5)) ** (1 / 3)
            l, w, h = l * k, w * k, 0.5 * k
        h = min(h, 2.95 if big else 1.6)
        out.append({"n": g, "l": max(15, round(l * 100)), "w": max(10, round(w * 100)), "h": max(8, round(h * 100))})
    return out


def _ref(rng, kind, octry, day):
    if kind == "US":
        return "AES ITN X" + day.strftime("%Y%m%d") + f"{rng.randrange(0, 999999):06d}"
    if kind == "EU":
        return "MRN " + day.strftime("%y") + octry + "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(14))
    return f"EXPORT DECL {octry}{rng.randrange(10**9, 10**10)}"


EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL",
      "PT", "RO", "SK", "SI", "ES", "SE"}


def _plain(t):
    """Capitals without accents, as cargo messaging and printed waybills carry them."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if not unicodedata.combining(c)).upper()


def enrich(d):
    """Add the air waybill, acceptance record and tracking history to every shipment. Safe to call again."""
    sh = d.get("shipments") or []
    if not sh or all(s.get("awb_doc") for s in sh):
        return d
    try:
        day = dt.datetime.strptime(d["date"], "%d %b %Y").replace(tzinfo=dt.timezone.utc)
        std = day.replace(hour=int(d["std"][:2]), minute=int(d["std"][2:4]))
    except Exception:
        day = std = dt.datetime.now(dt.timezone.utc)
    sta = std + dt.timedelta(minutes=d.get("block_min") or 60)
    booked = dt.datetime.fromtimestamp(d["requested_at"], dt.timezone.utc) if d.get("requested_at") else std - dt.timedelta(minutes=45)
    booked = min(booked, std - dt.timedelta(minutes=45))
    wide = len((d.get("deck") or {}).get("main") or []) >= 20
    o, de = d["origin"]["icao"], d["destination"]["icao"]
    ocity, octry = place(o)
    hd = d.get("handlers") or {}
    op = d.get("operator") or {}
    carrier = (op.get("name") or "Pagani Air Cargo").upper()
    code = (op.get("code") or "PAC").upper()
    stamp = lambda t: t.strftime("%d%b %H%MZ").upper()  # noqa: E731
    for s in sh:
        if s.get("awb_doc"):
            continue
        final = (s.get("destination") or {}).get("icao") or de
        dcity, dctry = place(final)
        intl = bool(octry and dctry and octry != dctry)
        rng = random.Random(f"{d.get('shipment_seed', d.get('release_no', ''))}|awb|{s['awb']}")
        hs, desc, pack, dens = _goods(s["contents"])
        kg = round(s["weight_lbs"] * 0.45359237, 1)
        big = bool({"BIG", "HEA"} & set(s.get("shc") or []))
        vol = round(kg / dens * rng.uniform(0.9, 1.15), 3)
        dims = _dims(rng, s["pieces"], vol, big)
        vol = round(sum(g["n"] * g["l"] * g["w"] * g["h"] for g in dims) / 1e6, 3)
        vol_kg = round(vol * 1e6 / 6000, 1)                         # IATA volumetric divisor 6,000 cm3 per kg
        chg = max(kg, vol_kg)
        chg = float(int(chg * 2 + (1 if (chg * 2) % 1 else 0))) / 2  # rounded up to the next half kilo
        lo, hi, rclass = RATE.get(s["service"], DEFAULT_RATE)
        rate = round(rng.uniform(lo, hi), 2)
        freight = round(rate * chg, 2)
        fuel = round(rng.uniform(0.85, 1.25), 2)
        others = [("MYC", "FUEL SURCHARGE", round(fuel * chg, 2)), ("SCC", "SECURITY SURCHARGE", round(0.15 * chg, 2)), ("AWC", "AWB FEE", 50.0)]
        if "PIL" in (s.get("shc") or []) or "ICE" in (s.get("shc") or []):
            others.append(("TCC", "TEMPERATURE CONTROL", round(0.65 * chg, 2)))
        if set(s.get("shc") or []) & {"RLI", "RCM", "RNG", "RFL", "RMD", "ICE"}:
            others.append(("RAC", "DANGEROUS GOODS CHECK", 175.0))
        sec = s.get("sector", "general")
        vlo, vhi = VALUE_KG.get(sec, (10, 45))
        value = round(kg * rng.uniform(vlo, vhi), 2)
        humanitarian = s["service"] in ("HUMANITARIAN",) or sec in ("humanitarian", "nutrition", "resupply")
        temp = next((t for c, t in TEMPS if c in (s.get("shc") or [])), "AMBIENT")
        if s["service"] == "TEMP CONTROLLED FROZEN" or ("ICE" in (s.get("shc") or []) and temp == "AMBIENT"):
            temp = "FROZEN -20 C OR BELOW"
        method = next(((m, why) for c, m, why in SCREEN if c in (s.get("shc") or [])), None)
        if not method:
            method = ("XRY", "X-RAY SCREENING") if not big else ("ETD", "EXPLOSIVE TRACE DETECTION (TOO LARGE FOR X-RAY)")
        handling_info = "; ".join(h.strip().rstrip(".;") for h in (s.get("handling") or []) if h.strip())
        handling_info = (handling_info + ".") if handling_info else "NO SPECIAL HANDLING. STACKABLE."
        if big and "NO STACKING" not in handling_info:
            handling_info += " DO NOT STACK."
        accept_t = std - dt.timedelta(minutes=(240 if wide else 180) + rng.randint(15, 140))
        # the warehouse acceptance checks, in the order a cargo agent does them
        checks = [
            ("AIR WAYBILL AND PARTIES", f"AWB {s['awb']} MATCHES SHIPPER, CONSIGNEE AND ROUTING {o}-{final}."),
            ("PIECE COUNT", f"{s['pieces']} PIECES COUNTED AGAINST THE AIR WAYBILL AND DELIVERY RECEIPT."),
            ("SCALE WEIGHT", f"GROSS {kg:,.1f} KG ON CERTIFIED SCALE. CHARGEABLE {chg:,.1f} KG."),
            ("PACKAGING AND DIMENSIONS", f"{pack}. NO DAMAGE OR LEAKS."),
            ("SECURITY SCREENING", f"{method[0]}: {method[1]}. STATUS SCO (SECURE FOR CARGO AIRCRAFT ONLY)."),
        ]
        if intl:
            checks.append(("COMMERCIAL INVOICE", f"HS {hs or 'N/A'}, DECLARED VALUE USD {value:,.2f}." if not humanitarian else "PRO FORMA INVOICE, NO COMMERCIAL VALUE (HUMANITARIAN)."))
            checks.append(("EXPORT CUSTOMS", f"EXPORT DECLARATION FILED. ROUTING {o}-{de} TO {s['consignee']['name'].upper()}."))
        else:
            checks.append(("DOMESTIC MOVEMENT", "NO EXPORT DECLARATION REQUIRED."))
        if set(s.get("shc") or []) & {"RLI", "RCM", "RNG", "RFL", "RMD", "ICE"}:
            checks.append(("DANGEROUS GOODS ACCEPTANCE", "SHIPPER'S DECLARATION CHECKED, MARKS AND LABELS VERIFIED. SEE NOTOC."))
        if "AVI" in (s.get("shc") or []):
            checks.append(("LIVE ANIMAL CHECK", "ANIMALS HEALTHY, WATER AVAILABLE, VETERINARY CERTIFICATE ATTACHED."))
        step = max(4, (std - dt.timedelta(minutes=95 if wide else 70) - accept_t).seconds // 60 // (len(checks) + 1))
        deliver = sta + dt.timedelta(hours=s.get("deliver_h") or 6)
        track = [
            {"code": "BKD", "what": "BOOKED", "at": stamp(booked), "where": o},
            {"code": "RCS", "what": "RECEIVED FROM SHIPPER", "at": stamp(accept_t), "where": o},
            {"code": "MAN", "what": f"MANIFESTED ON {d.get('flight', '')}", "at": stamp(std - dt.timedelta(minutes=20)), "where": o},
            {"code": "DEP", "what": "DEPARTED", "at": stamp(std), "where": o},
            {"code": "ARR", "what": "ARRIVED", "at": stamp(sta), "where": de},
            {"code": "RCF", "what": "RECEIVED FROM FLIGHT", "at": stamp(sta + dt.timedelta(minutes=55 if wide else 35)), "where": de},
        ]
        if final != de:
            track.append({"code": "TRS", "what": f"TRANSFER TO {final}", "at": stamp(sta + dt.timedelta(minutes=70 if wide else 50)), "where": de})
        else:
            track.extend([
                {"code": "NFD", "what": "CONSIGNEE NOTIFIED", "at": stamp(sta + dt.timedelta(minutes=70 if wide else 50)), "where": de},
                {"code": "DLV", "what": "DELIVERED TO CONSIGNEE", "at": stamp(deliver), "where": de},
            ])
        s["awb_doc"] = {
            "carrier": carrier, "code": code, "issued": stamp(booked), "issued_at": _plain(ocity),
            "charter_customer": _plain(d.get("charter_customer")),
            "shipper_addr": _plain(f"CARGO TERMINAL, {ocity}, {octry}"), "consignee_addr": _plain(f"IMPORT CENTER, {dcity}, {dctry}"),
            "kg": kg, "vol_m3": vol, "vol_kg": vol_kg, "chg_kg": chg, "dims": dims, "rate_class": rclass, "rate": rate,
            "freight": freight, "others": [{"code": c, "what": w, "amt": a} for c, w, a in others],
            "total": round(freight + sum(a for _, _, a in others), 2), "currency": "USD", "terms": "PP",
            "dv_carriage": f"USD {value:,.0f}" if "VAL" in (s.get("shc") or []) else "NVD",
            "dv_customs": ("NCV" if humanitarian else f"USD {value:,.2f}") if intl else "NOT REQUIRED (DOMESTIC)",
            "value": value, "insurance": "XXX", "hs": hs, "hs_desc": desc, "packaging": pack, "temp": temp, "handling_info": handling_info,
            "origin_handler": (hd.get("origin") or "").upper(), "dest_handler": (hd.get("destination") or "").upper(),
            "screen": {"method": method[0], "why": method[1], "status": "SCO", "by": (hd.get("origin") or "").upper(),
                       "at": stamp(accept_t + dt.timedelta(minutes=step * 5)), "ecsd": f"{code}-RA-{rng.randrange(10000, 99999)}"},
            "export": _ref(rng, "US" if octry == "US" else "EU" if octry in EU else "OTHER", octry, day) if intl and not humanitarian else ("HUMANITARIAN EXEMPTION" if intl else ""),
            "checks": [{"what": a, "note": b, "at": stamp(accept_t + dt.timedelta(minutes=step * i))} for i, (a, b) in enumerate(checks)],
            "release_at": stamp(accept_t + dt.timedelta(minutes=step * len(checks))),
            # IATA Cargo-IMP status codes, planned against the schedule; the debrief shows what happened
            "track": track,
        }
    return d
