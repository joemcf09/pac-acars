"""Shipper accounts: the customers who remember how PAC handled their freight.

Each shipper's account standing comes from its PAC shipments over the last 90 days: on-time deliveries raise it, late
deliveries and failed shipments lower it. Like lane reputation (lanes.py) it starts at 70. Strong accounts keep
booking with PAC; an account at risk takes much of its freight to other carriers, so its new orders become rarer.

The standings are recomputed by the cargo order tick and cached here, so building a manifest never needs the database."""
from __future__ import annotations

import time

WINDOW_S = 90 * 86400
BASE = 70
TIERS = ((85, "Preferred"), (70, "Good"), (50, "Under review"), (0, "At risk"))
KEEP = {"Preferred": 1.0, "Good": 1.0, "Under review": 0.75, "At risk": 0.4}   # chance a new order still goes to PAC
_cache = {"at": 0, "accounts": {}}


def tier(score):
    return next(name for floor, name in TIERS if score >= floor)


def compute(con, now=None):
    """{shipper name: {...}} for shippers with at least one finished shipment in the window."""
    now = now or time.time()
    rows = con.execute("""SELECT shipper, status, COUNT(*) n, MAX(updated_at) last FROM cargo_shipments
        WHERE status IN ('DELIVERED','DELIVERED_LATE','EXCEPTION','WITHDRAWN') AND updated_at>=? AND COALESCE(shipper,'')!=''
        GROUP BY shipper, status""", (now - WINDOW_S,)).fetchall()
    out = {}
    for r in rows:
        a = out.setdefault(r["shipper"], {"shipper": r["shipper"], "on_time": 0, "late": 0, "failed": 0, "rolled": 0, "last": 0})
        key = {"DELIVERED": "on_time", "DELIVERED_LATE": "late", "EXCEPTION": "failed", "WITHDRAWN": "rolled"}[r["status"]]
        a[key] += r["n"]
        a["last"] = max(a["last"], r["last"] or 0)
    try:
        import ceo
        adj = ceo.adjustments(con, now)
    except Exception:
        adj = {}
    for a in out.values():
        a.setdefault("rolled", 0)
        a["shipments"] = a["on_time"] + a["late"] + a["failed"] + a["rolled"]
        a["adjust"] = adj.get(a["shipper"], 0)
        # a rolled consignment (PAC never uplifted tendered freight) is a serious service failure: between a late
        # delivery and an outright exception. It lowers standing, so the shipper tenders less freight to PAC after.
        a["score"] = int(max(0, min(100, round(BASE + 3 * a["on_time"] - 6 * a["late"] - 10 * a["failed"] - 8 * a["rolled"] + a["adjust"]))))
        a["tier"] = tier(a["score"])
    return out


def refresh(con, now=None):
    _cache.update(at=time.time(), accounts=compute(con, now))
    return _cache["accounts"]


def standing(name):
    return _cache["accounts"].get(name)


def keeps_order(name, rng):
    """Whether this shipper still gives PAC a new order (False: it went to another carrier)."""
    a = standing(name)
    return True if not a else rng.random() < KEEP[a["tier"]]
