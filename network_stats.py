"""The PAC cargo network at a glance (public page /network): what PAC pilots flew in the last 30 days, the busiest
lanes, how much freight was delivered on time, and what is waiting at each station right now.

Everything comes from what PAC already records: filed flights (pireps, demo and rejected flights left out) and the
persistent shipments (cargo_network.py). No pilot names; only totals."""
from __future__ import annotations

import time

DAY = 86400
_cache = {"at": 0, "data": None}


def stats(con, airports, days=30, now=None):
    now = now or time.time()
    since = now - days * DAY
    ok = "demo=0 AND COALESCE(review_status,'')!='Rejected' AND filed_at>?"
    tot = con.execute(f"""SELECT COUNT(*) n, COALESCE(SUM(payload_lbs),0) lbs, COALESCE(SUM(distance_nm),0) nm,
        COALESCE(SUM(block_min),0) mins, COUNT(DISTINCT pilot_id) pilots FROM pireps WHERE {ok}""", (since,)).fetchone()
    lanes = [dict(r) for r in con.execute(f"""SELECT dep, arr, COUNT(*) flights, COALESCE(SUM(payload_lbs),0) lbs
        FROM pireps WHERE {ok} AND dep!=arr AND payload_lbs>0 GROUP BY dep, arr ORDER BY lbs DESC LIMIT 10""", (since,))]
    stations = [dict(r) for r in con.execute(f"""SELECT icao, SUM(n) movements FROM (
        SELECT dep icao, COUNT(*) n FROM pireps WHERE {ok} GROUP BY dep UNION ALL
        SELECT arr icao, COUNT(*) n FROM pireps WHERE {ok} GROUP BY arr) GROUP BY icao ORDER BY movements DESC LIMIT 8""",
        (since, since))]
    types = [dict(r) for r in con.execute(f"""SELECT aircraft, COUNT(*) flights FROM pireps WHERE {ok}
        GROUP BY aircraft ORDER BY flights DESC LIMIT 6""", (since,))]
    try:
        dl = con.execute("""SELECT SUM(status='DELIVERED') on_time, SUM(status='DELIVERED_LATE') late
            FROM cargo_shipments WHERE status IN ('DELIVERED','DELIVERED_LATE') AND updated_at>?""", (since,)).fetchone()
        waiting = [dict(r) for r in con.execute("""SELECT current_station icao, COUNT(*) shipments,
            COALESCE(SUM(gross_weight_lbs),0) lbs FROM cargo_shipments WHERE status IN ('AT_STATION','HELD_AT_STATION')
            GROUP BY current_station ORDER BY lbs DESC LIMIT 8""")]
        goods = [dict(r) for r in con.execute("""SELECT commodity, COUNT(*) shipments, COALESCE(SUM(gross_weight_lbs),0) lbs
            FROM cargo_shipments WHERE status IN ('DELIVERED','DELIVERED_LATE') AND updated_at>?
            GROUP BY commodity ORDER BY lbs DESC LIMIT 6""", (since,))]
    except Exception:              # a fresh site without the cargo tables yet
        dl, waiting, goods = None, [], []
    on_time, late = (dl["on_time"] or 0, dl["late"] or 0) if dl else (0, 0)

    def place(icao):
        a = airports.get(icao or "") or {}
        return {"icao": icao, "city": a.get("city") or a.get("name") or icao, "lat": a.get("lat"), "lon": a.get("lon")}

    for row in lanes:
        row["from"], row["to"] = place(row.pop("dep")), place(row.pop("arr"))
        row["lbs"] = round(row["lbs"])
    for row in stations + waiting:
        row.update(place(row["icao"]))
    for row in waiting + goods:
        row["lbs"] = round(row["lbs"])
    return {"days": days, "updated": now,
            "flights": tot["n"], "freight_lbs": round(tot["lbs"]), "distance_nm": round(tot["nm"]),
            "block_hours": round(tot["mins"] / 60), "pilots": tot["pilots"],
            "delivered": on_time + late, "on_time_pct": round(on_time * 100 / (on_time + late)) if on_time + late else None,
            "waiting_shipments": sum(w["shipments"] for w in waiting), "waiting_lbs": sum(w["lbs"] for w in waiting),
            "lanes": lanes, "stations": stations, "waiting": waiting, "goods": goods, "types": types}


def cached(db, airports, ttl=300):
    """Stats for the public page, worked out at most every five minutes."""
    if _cache["data"] is None or time.time() - _cache["at"] > ttl:
        with db() as con:
            _cache.update(at=time.time(), data=stats(con, airports))
    return _cache["data"]
