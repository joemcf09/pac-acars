"""The fleet market: how PAC gets aircraft, the four ways real cargo airlines do.

  * buy new from the manufacturer (only types still in production)
  * buy a used passenger jet and have it converted to a freighter by a conversion specialist
  * lease from an aircraft lessor (a monthly payment, no big up-front cost)
  * wet lease (ACMI): aircraft, crew, maintenance and insurance rented by the week for peaks like Holiday Rush

The companies are real businesses, named for realism only: PAC is a virtual airline with no affiliation to any of them.
Prices and lead times are simplified, approximate figures for the simulation, not quotes. Money comes from and goes
to the company ledger (company.py)."""
from __future__ import annotations

import os
import random
import re
import time
import zlib

import company

DISCLAIMER = ("Pagani Air Cargo is a virtual airline for flight simulation. The manufacturers, lessors, conversion companies and "
              "ACMI operators shown here are real businesses, used for realism only. PAC has no affiliation with or endorsement "
              "from any of them. Logos belong to their owners. Prices and lead times are simplified simulation figures, not quotes.")

COMPANIES = {
    # key: (name, kind, country)
    "boeing": ("Boeing Commercial Airplanes", "Manufacturer", "United States"),
    "airbus": ("Airbus", "Manufacturer", "France"),
    "bcf": ("Boeing Converted Freighters", "Freighter conversion", "United States"),
    "iai": ("Israel Aerospace Industries (IAI)", "Freighter conversion", "Israel"),
    "precision": ("Precision Aircraft Solutions", "Freighter conversion", "United States"),
    "aercap": ("AerCap", "Lessor", "Ireland"),
    "alc": ("Air Lease Corporation", "Lessor", "United States"),
    "avolon": ("Avolon", "Lessor", "Ireland"),
    "bbam": ("BBAM", "Lessor", "United States"),
    "smbc": ("SMBC Aviation Capital", "Lessor", "Ireland"),
    "cam": ("Cargo Aircraft Management (CAM)", "Lessor", "United States"),
    "atlas": ("Atlas Air", "Wet lease (ACMI)", "United States"),
    "abx": ("ABX Air", "Wet lease (ACMI)", "United States"),
    "asl": ("ASL Aviation Holdings", "Wet lease (ACMI)", "Ireland"),
}
NOTES = {"airbus": "The A350F, Airbus's new widebody freighter, isn't delivering yet. No Airbus type in the PAC fleet is still in production."}

# per type: new-build price (None = out of production), used / converted purchase, monthly lease, weekly wet lease (USD, simplified)
PRICES = {
    "B77F":  {"new": 180e6, "used": None,  "lease": 1.20e6, "wet": 1.10e6},
    "B763F": {"new": 100e6, "used": 30e6,  "lease": 0.35e6, "wet": 0.45e6},
    "B748F": {"new": None,  "used": 120e6, "lease": 1.30e6, "wet": 1.30e6},
    "B752F": {"new": None,  "used": 15e6,  "lease": 0.18e6, "wet": 0.30e6},
    "B738F": {"new": None,  "used": 22e6,  "lease": 0.21e6, "wet": 0.28e6},
    "A306F": {"new": None,  "used": 10e6,  "lease": 0.15e6, "wet": 0.30e6},
    "MD11F": {"new": None,  "used": 8e6,   "lease": 0.25e6, "wet": 0.60e6},
    "B733F": {"new": None,  "used": 4e6,   "lease": 0.09e6, "wet": None},
    "B742F": {"new": None,  "used": 2.5e6, "lease": None,   "wet": None},
    "B722F": {"new": None,  "used": 1.5e6, "lease": None,   "wet": None},
    "B732F": {"new": None,  "used": 1.5e6, "lease": None,   "wet": None},
}
NEW_FROM = {"B77F": "boeing", "B763F": "boeing"}
CONVERTERS = {"B763F": ["bcf", "iai"], "B738F": ["bcf", "iai"], "B752F": ["precision"]}
LESSORS = ["aercap", "alc", "avolon", "bbam", "smbc", "cam"]
ACMI = {"B748F": ["atlas"], "B77F": ["atlas"], "B763F": ["atlas", "abx"], "B738F": ["asl"], "B752F": ["asl"], "A306F": ["asl"], "MD11F": ["atlas"]}
LEAD_DAYS = {"new": 60, "conversion": 45, "used": 14, "lease": 7, "wet": 2}
DELIVERY_CENTER = {"boeing": "KPAE"}          # Boeing delivers widebodies from Paine Field (Everett)
HUBS = ("KCVG", "LIMC", "KMIA", "OMDW", "VHHH", "PANC")
ON_ORDER = "On order"


def migrate(con):
    company.migrate(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(airframes)")}
    for c, t in (("ownership", "TEXT"), ("owner_company", "TEXT"), ("lease_rate", "REAL"), ("lease_until", "REAL"),
                 ("next_payment", "REAL"), ("deliver_at", "REAL"), ("deliver_to", "TEXT")):
        if c not in cols:
            con.execute(f"ALTER TABLE airframes ADD COLUMN {c} {t}")


def logo(key, static_dir):
    for ext in ("svg", "png", "webp"):
        if os.path.exists(os.path.join(static_dir, "partners", "market", f"{key}.{ext}")):
            return f"/static/partners/market/{key}.{ext}"
    return None


def _quote(base, key, ac, month):
    """Lessors price a little differently month to month (fixed per month, so a page refresh doesn't change it)."""
    return round(base * (0.94 + (zlib.crc32(f"{key}|{ac}|{month}".encode()) % 13) / 100) / 1000) * 1000


def offers(fleet, static_dir, now=None):
    month = time.strftime("%Y-%m", time.gmtime(now or time.time()))
    out = []
    for ac, p in PRICES.items():
        if ac not in fleet:
            continue
        name = fleet[ac].get("name", ac)
        if p["new"] and ac in NEW_FROM:
            c = NEW_FROM[ac]
            out.append({"id": f"new|{ac}|{c}", "way": "new", "aircraft": ac, "aircraft_name": name, "company": c,
                        "price": p["new"], "lead_days": LEAD_DAYS["new"],
                        "what": f"Brand-new {name}, delivered from {DELIVERY_CENTER.get(c, 'the factory')}. You fly the delivery flight home."})
        if p["used"]:
            for c in CONVERTERS.get(ac, []):
                out.append({"id": f"conversion|{ac}|{c}", "way": "conversion", "aircraft": ac, "aircraft_name": name, "company": c,
                            "price": _quote(p["used"], c, ac, month), "lead_days": LEAD_DAYS["conversion"],
                            "what": f"A used passenger jet bought and converted to a freighter by {COMPANIES[c][0]}."})
            if ac not in CONVERTERS:
                out.append({"id": f"used|{ac}|market", "way": "used", "aircraft": ac, "aircraft_name": name, "company": None,
                            "price": p["used"], "lead_days": LEAD_DAYS["used"],
                            "what": f"A used {name} already in freighter configuration, bought on the second-hand market."})
        if p["lease"]:
            for c in random.Random(f"{ac}|{month}").sample(LESSORS, 2):
                out.append({"id": f"lease|{ac}|{c}", "way": "lease", "aircraft": ac, "aircraft_name": name, "company": c,
                            "monthly": _quote(p["lease"], c, ac, month), "lead_days": LEAD_DAYS["lease"],
                            "what": f"Leased from {COMPANIES[c][0]}: a monthly payment, return it whenever you like (one month's notice)."})
        if p["wet"]:
            for c in ACMI.get(ac, []):
                out.append({"id": f"wet|{ac}|{c}", "way": "wet", "aircraft": ac, "aircraft_name": name, "company": c,
                            "weekly": _quote(p["wet"], c, ac, month), "lead_days": LEAD_DAYS["wet"],
                            "what": f"Wet lease from {COMPANIES[c][0]}: aircraft, crew, maintenance and insurance by the week. Good for peaks."})
    for o in out:
        if o["company"]:
            n, k, ctry = COMPANIES[o["company"]]
            o["company_name"], o["company_kind"], o["company_country"] = n, k, ctry
            o["logo"] = logo(o["company"], static_dir)
    return out


REG_RE = re.compile(r"^[A-Z0-9]{1,2}-?[A-Z0-9]{2,5}$")


def order(con, offer_id, reg, hub, weeks, cash, fleet, static_dir, by, now=None):
    now = now or time.time()
    migrate(con)
    o = next((x for x in offers(fleet, static_dir, now) if x["id"] == offer_id), None)
    if not o:
        raise ValueError("That offer is no longer available.")
    reg = (reg or "").strip().upper()
    if not REG_RE.match(reg):
        raise ValueError("Enter a registration like N306PC.")
    if con.execute("SELECT 1 FROM airframes WHERE reg=?", (reg,)).fetchone():
        raise ValueError(f"{reg} is already in the fleet.")
    if hub not in HUBS:
        raise ValueError("Choose a PAC hub for the aircraft.")
    way, ac, c = o["way"], o["aircraft"], o["company"]
    who = o.get("company_name") or "the second-hand market"
    up_front = {"new": o.get("price"), "conversion": o.get("price"), "used": o.get("price"),
                "lease": o.get("monthly"), "wet": (o.get("weekly") or 0) * max(1, min(12, int(weeks or 1)))}[way]
    if up_front > cash:
        raise ValueError(f"PAC has ${cash:,.0f} in the bank and this needs ${up_front:,.0f} now. Lease instead, or wait for more cash.")
    deliver_at = now + o["lead_days"] * 86400
    deliver_to = DELIVERY_CENTER.get(c, hub) if way == "new" else hub
    kind = {"new": "aircraft_purchase", "conversion": "conversion", "used": "aircraft_purchase", "lease": "lease", "wet": "wet_lease"}[way]
    label = {"new": f"New {o['aircraft_name']} {reg} from {who}", "conversion": f"{o['aircraft_name']} {reg}: purchase and conversion by {who}",
             "used": f"Used {o['aircraft_name']} {reg}", "lease": f"First month's lease, {o['aircraft_name']} {reg} from {who}",
             "wet": f"Wet lease, {o['aircraft_name']} {reg} from {who}, {max(1, min(12, int(weeks or 1)))} week(s)"}[way]
    company.post(con, kind, -up_front, label, reg, by, now)
    own = {"new": "owned", "conversion": "owned", "used": "owned", "lease": "leased", "wet": "wet_lease"}[way]
    until = deliver_at + max(1, min(12, int(weeks or 1))) * 7 * 86400 if way == "wet" else None
    con.execute("""INSERT INTO airframes (reg, type, location, status, hours, cycles, hours_since_check, updated, note, hours_since_heavy,
        ownership, owner_company, lease_rate, lease_until, next_payment, deliver_at, deliver_to) VALUES (?,?,?,?,0,0,0,?,?,0,?,?,?,?,?,?,?)""",
                (reg, ac, deliver_to, ON_ORDER, now, f"{label}: delivery {time.strftime('%b %d', time.gmtime(deliver_at))}", own, c,
                 o.get("monthly") or o.get("weekly"), until, deliver_at + 30 * 86400 if way == "lease" else None, deliver_at, deliver_to))
    # A used, leased or wet-leased airframe (or a converted ex-passenger jet) arrives already partway through its
    # C-check cycle, so its next heavy check is something the Fleet Manager has to plan for. New-build aircraft start fresh.
    if way in ("used", "lease", "wet", "conversion"):
        import heavy_check
        con.execute("UPDATE airframes SET hours_since_heavy=? WHERE reg=?", (heavy_check.seed_hours(reg), reg))
    return {"reg": reg, "deliver_at": deliver_at, "deliver_to": deliver_to, "paid": up_front, "way": way}


def give_back(con, reg, by, now=None):
    """Return a leased or wet-leased aircraft (or sell an owned one for 60% of its used value)."""
    now = now or time.time()
    migrate(con)
    r = con.execute("SELECT * FROM airframes WHERE reg=?", (reg,)).fetchone()
    if not r:
        raise ValueError("No such aircraft.")
    r = dict(r)
    if r["status"] not in ("Available", ON_ORDER, "Heavy check due", "A-check due"):
        raise ValueError(f"{reg} is {r['status'].lower()}. Wait until it's parked and free.")
    if r.get("ownership") == "owned":
        val = (PRICES.get(r["type"], {}).get("used") or PRICES.get(r["type"], {}).get("new") or 0) * 0.6
        company.post(con, "aircraft_sale", val, f"Sold {r['type']} {reg}", reg, by, now)
        note = f"sold for ${val:,.0f}"
    elif r.get("ownership") in ("leased", "wet_lease"):
        note = "returned to " + (COMPANIES.get(r.get("owner_company") or "", ("the lessor",))[0])
    else:
        raise ValueError(f"{reg} came with the original PAC fleet. It can be sold only once it has a purchase record.")
    con.execute("DELETE FROM airframes WHERE reg=?", (reg,))
    return note


def tick(con, news, now=None):
    """Deliveries, monthly lease payments and wet leases that run out. `news(title, body)` posts to the news feed."""
    now = now or time.time()
    migrate(con)
    for r in con.execute("SELECT * FROM airframes WHERE status=? AND deliver_at<=?", (ON_ORDER, now)).fetchall():
        r = dict(r)
        con.execute("UPDATE airframes SET status='Available', note=NULL, location=?, updated=? WHERE reg=?", (r["deliver_to"], now, r["reg"]))
        how = {"owned": "joins the fleet", "leased": "joins the fleet on lease", "wet_lease": "arrives on a wet lease"}.get(r["ownership"], "joins the fleet")
        who = COMPANIES.get(r.get("owner_company") or "", (None,))[0]
        news(f"{r['reg']} {how}", f"PAC's new {r['type']} {r['reg']}{' from ' + who if who else ''} is ready at {r['deliver_to']}."
             + (" Book the delivery flight home from the mission board." if r["deliver_to"] not in HUBS else ""))
    for r in con.execute("SELECT * FROM airframes WHERE ownership='leased' AND next_payment<=?", (now,)).fetchall():
        r = dict(r)
        company.post(con, "lease", -(r["lease_rate"] or 0), f"Monthly lease, {r['type']} {r['reg']}", r["reg"], None, now)
        con.execute("UPDATE airframes SET next_payment=? WHERE reg=?", ((r["next_payment"] or now) + 30 * 86400, r["reg"]))
    for r in con.execute("SELECT * FROM airframes WHERE ownership='wet_lease' AND lease_until<=? AND status='Available'", (now,)).fetchall():
        con.execute("DELETE FROM airframes WHERE reg=?", (r["reg"],))
        news(f"{r['reg']} wet lease ends", f"The wet-leased {r['type']} {r['reg']} has gone back to its operator.")


def fleet_rows(con):
    migrate(con)
    return [dict(r) for r in con.execute("""SELECT reg, type, location, status, ownership, owner_company, lease_rate, lease_until, deliver_at
        FROM airframes WHERE ownership IS NOT NULL ORDER BY deliver_at DESC""")]
