"""Humanitarian relief missions based on real disasters.

GDACS (the UN and European Commission's Global Disaster Alert and Coordination System) publishes alerts for earthquakes,
tropical cyclones, floods and volcanoes. When an Orange or Red alert appears, PAC drafts a relief mission: supplies from
the nearest UN Humanitarian Response Depot city to the nearest usable airport. Nothing is posted automatically. A staff
member reviews each draft, ticks four checks (facts, tone, help links, timing) and posts it, posts it later, or
dismisses it.

Respect comes first: relief missions carry an "About this mission" notice and the real sources, pay like a normal flight,
earn no bonus points, use calm styling instead of urgent red and countdowns, and are never drafted for events in PAC's
conflict zones (those drafts are held)."""
from __future__ import annotations

import calendar
import json
import time
import urllib.parse
import urllib.request

GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
EVENT_TYPES = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcanic eruption"}
FETCH_EVERY_S = 3600                 # ask GDACS at most once an hour
RECENT_DAYS = 14                     # only events that began in the last two weeks
ENDED_GRACE_DAYS = 3                 # ...and are still current, or ended at most this many days ago
SEARCH_NM = 350                      # how far from the event to look for an airport
MIN_RWY_FT = 7000
OPEN_DAYS = 7                        # a posted mission stays open this long unless staff close it sooner
RELIEF_IDS = range(8900, 9000)       # PAC8900-8999: clear of AOG recoveries (8800-8899) and the PAC9xxx specials
KIND = "Humanitarian relief"
CHECKS = ("facts", "help", "tone", "links", "timing")

# The six UN Humanitarian Response Depot (UNHRD) locations and the airport PAC uses for each.
DEPOTS = [("MPTO", "Panama"), ("GCLP", "Las Palmas"), ("LIBR", "Brindisi"), ("DGAA", "Accra"), ("OMDB", "Dubai"),
          ("WMKK", "Kuala Lumpur")]
# Freighters in order of preference for a relief airlift: a mid-size widebody first.
PREFERRED = ["B763F", "A332F", "A306F", "B752F", "MD11F", "B77F", "B748F", "B744F", "B742F", "B738F", "B722F", "B733F", "B732F"]

# What each kind of disaster needs, as shares of the payload: (item, why it's needed, share, kg per piece, unit, code)
CARGO = {
    "TC": [("Family tents", "Shelter for families who lost their homes", .38, 45, "", "GEN"),
           ("Hygiene kits", "Soap, toothbrushes, sanitary items, water containers", .22, 5, "", "GEN"),
           ("Plastic sheeting and tarpaulins", "Emergency roof repairs", .15, 5, " rolls", "GEN"),
           ("Water purification units", "Portable units for clean drinking water", .13, 800, "", "HEA"),
           ("Emergency health kits", "Basic medicines and supplies for clinics", .12, 210, " modules", "GEN")],
    "FL": [("Water purification units", "Floodwater contaminates drinking water", .22, 800, "", "HEA"),
           ("Hygiene kits", "Soap, water containers and sanitary items to prevent disease", .25, 5, "", "GEN"),
           ("Family tents", "Shelter for displaced families", .25, 45, "", "GEN"),
           ("Inflatable rescue boats", "For reaching cut-off communities", .10, 120, "", "BIG"),
           ("Emergency health kits", "Basic medicines and supplies for clinics", .18, 210, " modules", "GEN")],
    "EQ": [("Family tents", "Shelter for families whose homes are unsafe", .35, 45, "", "GEN"),
           ("Emergency health kits", "Medicines and trauma supplies for clinics", .20, 210, " modules", "GEN"),
           ("Field hospital modules", "Surgical and ward modules for the injured", .20, 1200, "", "BIG"),
           ("Blankets", "Nights outdoors after the quake", .10, 2, "", "GEN"),
           ("Water purification units", "Portable units for clean drinking water", .15, 800, "", "HEA")],
    "VO": [("Respiratory masks", "Protection from volcanic ash", .15, 8, " cartons", "GEN"),
           ("Family tents", "Shelter for evacuated families", .35, 45, "", "GEN"),
           ("Water purification units", "Ash contaminates water supplies", .20, 800, "", "HEA"),
           ("Hygiene kits", "Soap, water containers and sanitary items", .15, 5, "", "GEN"),
           ("Emergency health kits", "Basic medicines and supplies for clinics", .15, 210, " modules", "GEN")],
}

NOTICE = ("This flight is based on a real disaster: {event}. Real people have lost their lives, homes and livelihoods, and many "
          "are still suffering. PAC creates this mission as a tribute to the aid workers, flight crews and volunteers carrying "
          "out the real relief effort, not as entertainment. It earns no bonus points or rewards.")


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS relief_drafts (
        id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
        post_after REAL, mission_id TEXT)""")
    con.execute("CREATE TABLE IF NOT EXISTS relief_meta (k TEXT PRIMARY KEY, v TEXT)")


# ---------------------------------------------------------------- GDACS
def fetch_gdacs(now=None, opener=None):
    """Recent Orange and Red alerts from GDACS, as plain dicts. `opener` lets tests supply the JSON."""
    now = now or time.time()
    q = {"eventlist": ";".join(EVENT_TYPES), "alertlevel": "Orange;Red",
         "fromdate": time.strftime("%Y-%m-%d", time.gmtime(now - RECENT_DAYS * 86400)),
         "todate": time.strftime("%Y-%m-%d", time.gmtime(now + 86400))}
    if opener:
        raw = opener(q)
    else:
        req = urllib.request.Request(GDACS_URL + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "PAC-VA relief drafts (pac-va.com)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            # GDACS answers an empty search with HTTP 204 and no JSON body.
            if r.status == 204:
                return []
            raw = json.loads(r.read().decode("utf-8"))
    return parse_gdacs(raw, now)


def parse_gdacs(raw, now):
    out = []
    for f in (raw or {}).get("features", []):
        p = f.get("properties") or {}
        kind = p.get("eventtype")
        if kind not in EVENT_TYPES or p.get("alertlevel") not in ("Orange", "Red"):
            continue
        try:
            lon, lat = (f.get("geometry") or {}).get("coordinates")[:2]
            start = calendar.timegm(time.strptime(p.get("fromdate", "")[:19], "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError):
            continue
        if start < now - RECENT_DAYS * 86400:
            continue
        try:
            end = calendar.timegm(time.strptime(p.get("todate", "")[:19], "%Y-%m-%dT%H:%M:%S"))
        except (TypeError, ValueError):
            end = None
        if str(p.get("iscurrent")).lower() != "true" and end and end < now - ENDED_GRACE_DAYS * 86400:
            continue   # over for days already: too late for a relief airlift
        countries = [c.get("countryname") for c in p.get("affectedcountries") or [] if c.get("countryname")]
        out.append({"key": f"gdacs:{kind}:{p.get('eventid')}", "type": kind, "type_name": EVENT_TYPES[kind],
                    "name": p.get("eventname") or "", "title": p.get("name") or "", "alert": p.get("alertlevel"),
                    "country": countries[0] if countries else (p.get("country") or ""), "countries": countries,
                    "iso2": [c.get("iso2") for c in p.get("affectedcountries") or [] if c.get("iso2")],
                    "lat": float(lat), "lon": float(lon), "start": start,
                    "severity": (p.get("severitydata") or {}).get("severitytext") or "",
                    "report_url": (p.get("url") or {}).get("report") or "https://www.gdacs.org/"})
    return out


# ---------------------------------------------------------------- drafting
def _event_label(e):
    when = time.strftime("%B %Y", time.gmtime(e["start"]))
    name = e["name"] if e["type"] == "TC" and e["name"] else e["type_name"]
    return f"{name}, {e['country'] or 'the affected area'}, {when}"


def plan(e, ctx):
    """The draft for one event: route, aircraft, cargo and links, or a held draft with the reason."""
    dist = ctx["gc_distance_nm"]
    zones = ctx["zones"]
    near = []
    for a in ctx["airports"].values():
        if (a.get("rwy_ft") or 0) < MIN_RWY_FT or a.get("lat") is None:
            continue
        nm = dist(e["lat"], e["lon"], a["lat"], a["lon"])
        if nm <= SEARCH_NM:
            near.append((nm, a))
    near.sort(key=lambda x: x[0])
    d = dict(e)
    d["label"] = _event_label(e)
    d["help"] = [["International Federation of Red Cross and Red Crescent Societies (IFRC) appeals", "https://www.ifrc.org/appeals"],
                 ["UN OCHA and partners on ReliefWeb", "https://reliefweb.int/disasters"]]
    if any(ctx["airport_zone"](a["icao"], zones) for _, a in near[:3]):
        d.update(held=True, reason="The area is in one of PAC's conflict zones. Relief missions are never drafted for these.")
        return d
    in_country = [x for x in near if not e["iso2"] or x[1].get("country") in e["iso2"]]
    if not in_country:
        d.update(held=True, reason=f"No airport with a runway of {MIN_RWY_FT:,} ft or more within {SEARCH_NM} nm of the event.")
        return d
    dnm, dest = in_country[0]
    depots = sorted(((dist(dest["lat"], dest["lon"], ctx["airports"][i]["lat"], ctx["airports"][i]["lon"]), i, city)
                     for i, city in DEPOTS if i in ctx["airports"] and i != dest["icao"]), key=lambda x: x[0])
    for leg, origin, depot_city in depots:
        types = [t for t in PREFERRED if t in ctx["fleet"] and not ctx["fleet"][t].get("retired")
                 and (ctx["fleet"][t].get("range_nm") or 0) >= leg * 1.15
                 and (ctx["fleet"][t].get("min_rwy_ft") or 0) <= (dest.get("rwy_ft") or 0)]
        if types:
            break
    else:
        d.update(held=True, reason="No PAC freighter can reach the nearest airport from a humanitarian depot.")
        return d
    ac = ctx["fleet"][types[0]]
    payload_kg = int(min(ac.get("max_payload_lbs", 0) * 0.7 / 2.20462, 50000) // 500 * 500)
    items = []
    for name, why, share, per, unit, code in CARGO[e["type"]]:
        kg = int(payload_kg * share // 100 * 100)
        items.append({"item": name, "why": why, "pieces": f"{max(1, round(kg / per)):,}{unit}", "kg": kg, "code": code})
    d.update(held=False, origin=origin, depot_city=depot_city, destination=dest["icao"], dest_city=dest.get("city") or dest["icao"],
             dest_name=dest.get("name") or "", event_to_airport_nm=round(dnm), distance_nm=round(leg), aircraft=types[0],
             aircraft_options=types[:4], payload_kg=sum(i["kg"] for i in items), cargo=items)
    return d


def refresh(con, ctx, now=None, events=None):
    """Fetches GDACS at most once an hour and drafts any new events. Returns how many drafts were added."""
    now = now or time.time()
    migrate(con)
    if events is None:
        last = con.execute("SELECT v FROM relief_meta WHERE k='fetched'").fetchone()
        if last and now - float(last[0]) < FETCH_EVERY_S:
            return 0
        con.execute("INSERT OR REPLACE INTO relief_meta (k, v) VALUES ('fetched', ?)", (str(now),))
        try:
            events = fetch_gdacs(now)
        except (OSError, ValueError) as exc:
            con.execute("INSERT OR REPLACE INTO relief_meta (k, v) VALUES ('error', ?)", (f"{type(exc).__name__}: {exc}"[:300],))
            return 0
        con.execute("DELETE FROM relief_meta WHERE k='error'")
    added = 0
    for e in events:
        if con.execute("SELECT 1 FROM relief_drafts WHERE id=?", (e["key"],)).fetchone():
            continue   # one draft per event, ever: a dismissed draft never comes back
        d = plan(e, ctx)
        con.execute("INSERT INTO relief_drafts (id, data, status, created, updated) VALUES (?,?,?,?,?)",
                    (e["key"], json.dumps(d), "held" if d.get("held") else "draft", now, now))
        added += 1
    return added


def listing(con, now=None):
    now = now or time.time()
    migrate(con)
    rows = con.execute("SELECT * FROM relief_drafts ORDER BY CASE status WHEN 'draft' THEN 0 WHEN 'later' THEN 1 WHEN 'posted' THEN 2 "
                       "WHEN 'held' THEN 3 ELSE 4 END, created DESC LIMIT 60").fetchall()
    meta = dict(con.execute("SELECT k, v FROM relief_meta").fetchall())
    out = []
    for r in rows:
        d = json.loads(r["data"])
        d.update(id=r["id"], status=r["status"], created=r["created"], post_after=r["post_after"], mission_id=r["mission_id"])
        out.append(d)
    return {"drafts": out, "fetched": float(meta["fetched"]) if meta.get("fetched") else None, "error": meta.get("error"),
            "waiting": sum(1 for d in out if d["status"] == "draft")}


def edit(con, did, body):
    r = con.execute("SELECT data, status FROM relief_drafts WHERE id=?", (did,)).fetchone()
    if not r or r["status"] not in ("draft", "later"):
        raise ValueError("Only drafts waiting for review can be edited.")
    d = json.loads(r["data"])
    if "help" in body:
        links = [[str(t).strip()[:140], str(u).strip()[:400]] for t, u in body["help"] if str(t).strip() and str(u).strip().startswith("https://")]
        if not links:
            raise ValueError("Give at least one help link, starting with https://.")
        d["help"] = links[:5]
    if body.get("aircraft") in (d.get("aircraft_options") or []):
        d["aircraft"] = body["aircraft"]
    if "note" in body:
        d["note"] = str(body["note"]).strip()[:600]
    con.execute("UPDATE relief_drafts SET data=?, updated=? WHERE id=?", (json.dumps(d), time.time(), did))
    return d


def dismiss(con, did):
    con.execute("UPDATE relief_drafts SET status='dismissed', updated=? WHERE id=? AND status IN ('draft','later','held')", (time.time(), did))


def later(con, did, hours):
    hours = max(1, min(int(hours), 7 * 24))
    con.execute("UPDATE relief_drafts SET status='later', post_after=?, updated=? WHERE id=? AND status IN ('draft','later')",
                (time.time() + hours * 3600, time.time(), did))


def post(con, did, checks, ctx, now=None):
    """Posts a reviewed draft as a relief mission. All five checks must be ticked."""
    now = now or time.time()
    if not all((checks or {}).get(c) for c in CHECKS):
        raise ValueError("Tick all five checks before posting.")
    r = con.execute("SELECT data, status FROM relief_drafts WHERE id=?", (did,)).fetchone()
    if not r or r["status"] not in ("draft", "later"):
        raise ValueError("This draft can't be posted.")
    d = json.loads(r["data"])
    o, dest = ctx["airport_obj"](d["origin"]), ctx["airport_obj"](d["destination"])
    ac = ctx["fleet"][d["aircraft"]]
    busy = {x[0] for x in con.execute("SELECT id FROM urgent WHERE status IN ('open','booked') OR created > ?", (now - 2 * 86400,))}
    n = next((n for n in RELIEF_IDS if f"PAC{n}" not in busy), None)
    if n is None:
        raise ValueError("No free relief flight number. Close an older relief mission first.")
    block = round(45 + d["distance_nm"] / (ac.get("cruise_ktas") or 450) * 60 * 1.05)
    expires = now + OPEN_DAYS * 86400
    payload_lbs = int(round(d["payload_kg"] * 2.20462 / 100) * 100)
    cargo = "; ".join(f"{i['item']} ({i['pieces']})" for i in d["cargo"])
    m = {"id": f"PAC{n}", "title": f"Relief supplies to {d['dest_city']}", "category": "Urgent", "priority": "High",
         "urgent": True, "urgent_kind": KIND, "origin": o, "destination": dest, "aircraft": [d["aircraft"]], "suggested_airframe": None,
         "cargo": cargo, "payload_lbs": payload_lbs, "distance_nm": d["distance_nm"], "target_block_min": block,
         "reward": int(round((d["distance_nm"] * 0.14 + payload_lbs / 1000 * 1.2) / 10) * 10), "yield_mult": 1.0,
         "expires": expires, "deliver_by": expires + 2 * 86400,
         "briefing": (f"Relief supplies from the humanitarian depot at {d['depot_city']} to {d['dest_city']}, after the "
                      f"{d['label']}. " + (d.get("note") or "")).strip(),
         "relief": {"draft": did, "event": d["label"], "type": d["type_name"], "alert": d["alert"], "start": d["start"],
                    "country": d["country"], "severity": d["severity"], "source": d["report_url"], "help": d["help"],
                    "items": d["cargo"], "depot_city": d["depot_city"], "notice": NOTICE.format(event=d["label"]),
                    "ops": [["Fuel", f"Fuel at {d['destination']} may be limited. Carry enough to return to {d['origin']} or reach an alternate without refueling."],
                            ["Arrival", "The relief apron may be busy. Expect delays, and keep ground time short."],
                            ["Weather", "Check the latest METAR and forecast before departure."],
                            ["Online", "Flying on VATSIM or IVAO? File with your PGI callsign and fly normally. Relief flights get no special priority."]]}}
    con.execute("DELETE FROM urgent WHERE id=?", (m["id"],))
    con.execute("INSERT INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, 'open')", (m["id"], json.dumps(m), now, expires))
    con.execute("UPDATE relief_drafts SET status='posted', mission_id=?, updated=? WHERE id=?", (m["id"], now, did))
    return m


def close(con, did):
    r = con.execute("SELECT mission_id FROM relief_drafts WHERE id=? AND status='posted'", (did,)).fetchone()
    if r and r["mission_id"]:
        con.execute("UPDATE urgent SET status='expired' WHERE id=? AND status='open'", (r["mission_id"],))
    con.execute("UPDATE relief_drafts SET status='closed', updated=? WHERE id=? AND status='posted'", (time.time(), did))


def register(app, g):
    """Staff API. Everything under /api/staff/ is staff-only (auth.py)."""
    from flask import jsonify, request

    def ctx():
        s = g["settings"]()
        import conflict_zones
        return {"airports": g["AIRPORTS"], "fleet": g["FLEET"], "gc_distance_nm": g["gc_distance_nm"], "airport_obj": g["airport_obj"],
                "zones": conflict_zones.zones(s), "airport_zone": conflict_zones.airport_zone}

    @app.get("/api/staff/relief")
    def relief_list():
        with g["db"]() as con:
            migrate(con)
            refresh(con, ctx())
            return jsonify(listing(con))

    @app.post("/api/staff/relief/<path:did>/<action>")
    def relief_action(did, action):
        b = request.get_json(silent=True) or {}
        try:
            with g["db"]() as con:
                migrate(con)
                if action == "post":
                    return jsonify({"mission": post(con, did, b.get("checks"), ctx())})
                if action == "edit":
                    return jsonify({"draft": edit(con, did, b)})
                if action == "later":
                    later(con, did, b.get("hours", 24))
                elif action == "dismiss":
                    dismiss(con, did)
                elif action == "close":
                    close(con, did)
                else:
                    return jsonify({"error": "Unknown action."}), 404
                return jsonify({"ok": True})
        except (ValueError, KeyError) as e:
            return jsonify({"error": str(e)}), 400
