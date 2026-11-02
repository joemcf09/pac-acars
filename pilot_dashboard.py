"""Read-only pilot briefing. No mission generation, booking, or database migration."""
from collections import defaultdict
from contextlib import closing
import json
import sqlite3
import time

from flask import jsonify


def recommendations(routes, fleet, frames, here, hub, eligible, strict=True):
    """Bounded direct/two-sector suggestions using recommended, qualified aircraft."""
    by_origin = defaultdict(list)
    for r in routes:
        types = [t for t in r.get("aircraft", []) if t in eligible and t in fleet
                 and not fleet[t].get("retired")
                 and fleet[t]["max_payload_lbs"] >= r.get("payload_lbs", 0)
                 and fleet[t]["range_nm"] >= r.get("distance_nm", 0) * 1.05
                 and all(not a.get("rwy_ft") or a["rwy_ft"] >= fleet[t]["min_rwy_ft"]
                         for a in (r["origin"], r["destination"]))]
        if not types:
            continue
        available = [f for f in frames if f["type"] in types and f["status"] == "Available"
                     and (not strict or f["location"] == r["origin"]["icao"])]
        item = {"id": r["id"], "origin": r["origin"], "destination": r["destination"],
                "minutes": r.get("target_block_min", 0), "distance": r.get("distance_nm", 0),
                "types": types, "available": bool(available) or not strict,
                "airframe": available[0]["reg"] if available else None,
                "aircraft": available[0]["type"] if available else types[0]}
        by_origin[r["origin"]["icao"]].append(item)
    departures = sorted(by_origin[here], key=lambda r: (not r["available"], r["minutes"], r["id"]))
    home = []
    if here != hub:
        home = [[r] for r in departures if r["destination"]["icao"] == hub]
        if not home:
            for first in departures:
                for second in by_origin[first["destination"]["icao"]]:
                    if second["destination"]["icao"] == hub:
                        home.append([first, second])
        home.sort(key=lambda legs: (not legs[0]["available"], sum(r["minutes"] for r in legs)))
    return departures[:6], home[:3], len(departures)


def register(app, context):
    @app.get("/api/pilot/dashboard")
    def briefing():
        import auth
        import va
        import shop
        who = auth.current()
        if not who:
            return jsonify({"error": "Please sign in."}), 401
        pid = who["id"]  # Identity always comes from the authenticated session.
        with closing(sqlite3.connect(context["DB_PATH"].resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as con:
            con.row_factory = sqlite3.Row
            car = va.career(pid, con)
            pilot = car["pilot"]
            here = pilot.get("location") or va.HOME_BASE
            hub = pilot.get("hub") or va.HOME_BASE
            frames = [dict(r) for r in con.execute("SELECT reg,type,location,status FROM airframes")]
            held = con.execute("SELECT data FROM bookings WHERE pilot_id=?", (pid,)).fetchone()
            booking = json.loads(held[0]) if held else None
            rated = set(va.type_ratings(pid))
            direct_types = set(va.rated_types(pid))
            passes = shop.expiries(pid, con)
            fleet_pass = car["rank_index"] > 0 and any(passes.get(k, 0) > time.time() for k in shop.TIMED)
        settings = context["settings"]()
        fleet = context["FLEET"]
        eligible = {t for t, f in fleet.items() if not f.get("retired")
                    and (not settings.get("enforce_ranks") or ((car["rank_index"] > 0 or t in direct_types) and (t in car["unlocked"] or fleet_pass)))
                    and (not settings.get("require_type_ratings") or fleet_pass or va.rating_family(t) in rated)}
        departures, home, count = recommendations(context["ROUTES"].values(), fleet, frames, here, hub, eligible,
                                                  settings.get("enforce_airframes", True))
        response = jsonify({"pilot": {"id": pid, "name": pilot.get("name", pid), "rank": car["rank"],
                                      "hours": car["hours"], "next": car["next"], "requirements": car["requirements"]},
                            "location": context["airport_obj"](here) or {"icao": here},
                            "hub": context["airport_obj"](hub) or {"icao": hub},
                            "booking": {k: booking.get(k) for k in ("flight_number", "aircraft", "registration", "mission")} if booking else None,
                            "checkride_needed": pilot.get("checkride") not in ("Passed", "Waived") and not direct_types,
                            "checkride_id": va.CHECKRIDE_ID,
                            "eligible_types": sorted(eligible), "departures": departures, "departure_count": count,
                            "home_options": home, "at_home": here == hub})
        response.headers["Cache-Control"] = "private, no-store"
        return response
