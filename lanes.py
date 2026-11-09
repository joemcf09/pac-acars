"""Lane reputation: shippers remember how PAC performs on each route.

A lane is an airport pair flown by PAC (origin to destination). Its score starts at 70 and moves with every accepted
flight that carried customer freight on it over the last 90 days: on-time deliveries raise it, late ones, cold-chain
excursions, distressed animals, damaged freight and failed flights lower it. Recent flights count double.

A strong lane brings more customer orders; a weak one fewer. Reputation is the pilots' shared work: nobody is
penalized personally.
"""
from __future__ import annotations

import json
import time

WINDOW_S = 90 * 86400
BASE = 70
TIERS = ((85, "Preferred"), (70, "Good"), (50, "Under review"), (0, "At risk"))
ORDER_WEIGHT = {"Preferred": 2.0, "Good": 1.0, "Under review": 0.7, "At risk": 0.4}


def tier(score):
    return next(name for floor, name in TIERS if score >= floor)


def compute(con, now=None):
    """{(origin, destination): {...}} for lanes with at least one recent accepted cargo flight."""
    now = now or time.time()
    rows = con.execute("""SELECT m.pirep_id, m.from_station, m.to_station, m.status, m.details, m.event_time
        FROM cargo_movements m JOIN pireps p ON p.id=m.pirep_id
        WHERE m.event_type='FLIGHT_ARRIVAL' AND m.event_time>=? AND COALESCE(p.demo,0)=0
          AND COALESCE(p.review_status,'') != 'Rejected'""", (now - WINDOW_S,)).fetchall()
    flights = {}
    for r in rows:
        f = flights.setdefault(r["pirep_id"], {"lane": (r["from_station"], r["to_station"]), "t": r["event_time"],
                                               "late": False, "delivered": False, "exception": False, "bad": 0, "watch": 0})
        st = r["status"] or ""
        f["late"] |= st == "DELIVERED_LATE"
        f["delivered"] |= st.startswith("DELIVERED") or st == "AT_STATION"
        f["exception"] |= st == "EXCEPTION"
        try:
            care = (json.loads(r["details"] or "{}") or {}).get("care") or {}
        except (TypeError, ValueError):
            care = {}
        f["bad"] += care.get("status") == "excursion"
        f["watch"] += care.get("status") == "watch"
    lanes = {}
    for f in flights.values():
        a, b = f["lane"]
        if not a or not b or a == b:
            continue
        L = lanes.setdefault((a, b), {"origin": a, "destination": b, "flights": 0, "on_time": 0, "late": 0, "care_issues": 0,
                                       "failed": 0, "points": 0.0, "last": 0})
        w = 2.0 if now - f["t"] < 30 * 86400 else 1.0
        L["flights"] += 1
        L["last"] = max(L["last"], f["t"])
        if f["exception"]:
            L["failed"] += 1
            L["points"] -= 10 * w
        elif f["late"]:
            L["late"] += 1
            L["points"] -= 6 * w
        elif f["delivered"]:
            L["on_time"] += 1
            L["points"] += 4 * w
        if f["bad"]:
            L["care_issues"] += 1
            L["points"] -= 8 * w
        elif f["watch"]:
            L["points"] -= 2 * w
    for L in lanes.values():
        L["score"] = int(max(0, min(100, round(BASE + L.pop("points")))))
        L["tier"] = tier(L["score"])
    return lanes


def weight(lanes, origin, destination):
    L = lanes.get((origin, destination))
    return ORDER_WEIGHT[L["tier"]] if L else 1.0
