"""Aviation insurance, the way real airlines carry it.

PAC pays a monthly premium for hull and liability cover on every aircraft in the fleet. After an incident (a heavy
landing that damages the aircraft, a tail strike) the flight pays only the deductible; the insurer pays the rest of
the repair. Claims make the next premiums dearer: each claim in the last 12 months adds 10% (up to +50%).

Figures are simplified for the simulation: the yearly premium is about 0.12% of each aircraft's value (a fleet already in service is insured at about two thirds of its new price), and the
deductible per incident is $750,000 for a widebody and $250,000 for a narrowbody."""
from __future__ import annotations

import datetime as dt
import time

ANNUAL_RATE = 0.0012
DEDUCTIBLE = {"wide": 750_000, "narrow": 250_000}
CLAIM_LOADING, MAX_LOADING = 0.10, 0.50
INSURED_COSTS = ("damage_repairs", "tail_strike_repairs")
CLAIM_NOTE = "Insurance claim"


def deductible(wide):
    return DEDUCTIBLE["wide" if wide else "narrow"]


def apply(costs, wide, notes):
    """Caps insured repair costs at the deductible. Returns what the insurer pays."""
    insured = sum(costs.get(k, 0) for k in INSURED_COSTS)
    if not insured:
        return 0
    ded = deductible(wide)
    if insured <= ded:
        notes.append(f"Repairs (${insured:,.0f}) are below the ${ded:,.0f} insurance deductible: PAC pays them in full")
        return 0
    scale = ded / insured
    for k in INSURED_COSTS:
        if k in costs:
            costs[k] = round(costs[k] * scale)
    notes.append(f"{CLAIM_NOTE}: the insurer pays ${insured - ded:,.0f} of the ${insured:,.0f} repair; PAC pays the ${ded:,.0f} deductible")
    return insured - ded


def hull_value(code):
    import fleet_market
    p = fleet_market.PRICES.get(code) or {}
    return p.get("used") or (p.get("new") or 0) * 0.67 or 5_000_000


def claims(con, now=None):
    now = now or time.time()
    return con.execute("SELECT COUNT(*) FROM pireps WHERE demo=0 AND filed_at>? AND detail LIKE ?", (now - 365 * 86400, f"%{CLAIM_NOTE}%")).fetchone()[0]


def policy(con, fleet, now=None):
    """The current policy: per-type premiums for the fleet, loading from claims, and the monthly total."""
    now = now or time.time()
    import fleet_market
    fleet_market.migrate(con)
    rows = con.execute("SELECT type, COUNT(*) FROM airframes WHERE COALESCE(ownership,'') != 'wet_lease' GROUP BY type").fetchall()
    n = claims(con, now)
    loading = min(MAX_LOADING, n * CLAIM_LOADING)
    lines = []
    for code, count in rows:
        monthly = hull_value(code) * ANNUAL_RATE / 12 * (1 + loading)
        lines.append({"type": code, "name": (fleet.get(code) or {}).get("name", code), "aircraft": count,
                      "value": hull_value(code), "monthly": round(monthly * count)})
    lines.sort(key=lambda x: -x["monthly"])
    return {"lines": lines, "monthly": sum(x["monthly"] for x in lines), "claims_12m": n, "loading_pct": round(loading * 100),
            "deductible": DEDUCTIBLE, "annual_rate_pct": ANNUAL_RATE * 100,
            "note": "Wet-leased aircraft are insured by their operator, as in a real ACMI deal."}


def tick(con, fleet, now=None):
    """Bills the month's premium once, on the first tick of each month."""
    import company
    now = now or time.time()
    con.execute("CREATE TABLE IF NOT EXISTS insurance_bills (month TEXT PRIMARY KEY, amount REAL, time REAL)")
    month = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y-%m")
    if con.execute("SELECT 1 FROM insurance_bills WHERE month=?", (month,)).fetchone():
        return None
    pol = policy(con, fleet, now)
    con.execute("INSERT INTO insurance_bills (month, amount, time) VALUES (?,?,?)", (month, pol["monthly"], now))
    if pol["monthly"]:
        company.post(con, "insurance", -pol["monthly"], f"Hull and liability insurance, {month}"
                     + (f" (+{pol['loading_pct']}% for {pol['claims_12m']} claim{'s' if pol['claims_12m'] != 1 else ''})" if pol["loading_pct"] else ""), month, None, now)
    return pol["monthly"]
