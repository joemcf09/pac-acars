"""Who is shipping what, to whom, and how it moves through the airport.

The cargo manifest says what sits in each position. This module groups those units into
shipments (one air waybill each), using a small curated set of real business roles
and explicitly fictional suppliers/receivers, a short note on why it
is flying, and how to handle it. It also builds the ground handling timeline around the
flight: acceptance, build-up, weighing, loading, doors closed, and offload, customs and
delivery at the other end.

Business names are limited to curated roles in add(). The shipments themselves are
invented for flight simulation: the paperwork says so, and nothing here claims a real
business relationship.

Everything is seeded from the release number, so reprints of the same release match.
"""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

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
    return "PAC Simulated Ground Services"


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
        # Only verified business roles are named; no invented local company facilities.
        fwd = "Kuehne+Nagel" if sec in ("pharma", "plasma", "isotope") else "DHL Global Forwarding"
        shipper = "Boeing Distribution" if sec == "aog" else f"PAC Scenario {sec.title()} Supplier"
        consignee = f"PAC Scenario {dcity} Receiving Team"
        story = (f"Fictional shipment of {contents.lower()} via {ocity} to {dcity}. "
                 "Scheduled for the receiving team's next distribution window.")
        if sec == "aog":
            story = f"Fictional aircraft-parts shipment via {ocity} to {dcity} to support a simulated aircraft-on-ground recovery."
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
            "agent": None if shipper.startswith(fwd) else fwd, "notify": rng.choice(FAKE_NAMES),
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
            arr.append((round(s["deliver_h"] * 60), "PLANNED RELEASE " + s["awb"], f"TO {s['consignee']['name']}".upper()))
    arr.sort(key=lambda x: x[0])
    return {"dep": [{"t": a, "what": b, "note": c} for a, b, c in dep], "arr": [{"t": _t(sta, a), "what": b, "note": c} for a, b, c in arr],
            "dep_station": o, "arr_station": de}
