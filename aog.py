"""AOG recovery: when a PAC aircraft is grounded away from base, the airline has to get parts and engineers to it.

What happens:
1. A hard landing, structural damage or a tail strike grounds the airframe (va.after_file). PAC opens an AOG case for it.
2. The case gets a recovery kit sized to the event and the aircraft: an inspection team and NDT kit after a hard landing, a
   sheet-metal repair kit after a tail strike, a landing-gear change after structural damage.
3. PAC posts an AOG recovery mission from the nearest PAC hub to the stranded aircraft, flown by any PAC pilot.
4. When the kit is delivered, engineers start work. The repair takes a set time, then the aircraft returns to service by
   itself, with its grounding write-ups closed and the recovery flight named in the log.
5. If nobody books the mission within its window, PAC charters a contractor: the parts arrive later and cost more, but the
   aircraft is never stranded forever.

If the aircraft is grounded at a PAC hub, the parts are already there and repair starts at once.

Kit weights, repair times and costs are PAC simulation estimates, sized by aircraft class, not maintenance-manual figures.
"""
from __future__ import annotations

import json
import time

# Thresholds PAC uses after landing (adjustable here). Descent rate in fpm (negative), vertical load in G.
INSPECT_FPM, DAMAGE_FPM = -600, -1000
INSPECT_G, DAMAGE_G = 2.0, 2.6

AOG_IDS = range(8800, 8900)          # PAC8800-8899: clear of scheduled routes (to PAC7xxx) and the PAC9xxx specials
BOOK_WINDOW_H = 36                    # how long the mission stays open before PAC charters a contractor
CONTRACTOR_DELAY_H = 18               # contractor parts arrive this long after the window closes
CONTRACTOR_COST_MULT = 1.6
HUBS = ["KCVG", "KMIA", "LIMC", "OMDW", "VHHH", "PANC"]
WIDE = {"A306F", "A332F", "B763F", "MD11F", "B77F", "B742F", "B744F", "B748F"}

# kind -> (ATA, title, kit narrowbody, kit widebody); kit = (contents, weight lb, team, repair hours, cost USD)
KITS = {
    "hard_landing": (5, "Hard landing inspection",
                     ("Hard landing inspection kit: NDT (eddy current and ultrasonic) equipment, landing gear and wing-to-body inspection tooling, jacking adapters",
                      1800, "2 structures engineers", 10, 45_000),
                     ("Hard landing inspection kit: NDT (eddy current and ultrasonic) equipment, landing gear and wing-to-body inspection tooling, jacking adapters",
                      3600, "3 structures engineers", 16, 110_000)),
    "tail_strike": (53, "Tail strike repair",
                    ("Tail strike repair kit: aft body skin doublers, tail skid cartridge, fasteners, sealant and riveting tooling",
                     2400, "3 sheet-metal technicians", 30, 180_000),
                    ("Tail strike repair kit: aft body skin doublers and frame repair parts, tail skid cartridge, fasteners, sealant and riveting tooling",
                     5200, "4 sheet-metal technicians", 48, 450_000)),
    "structural": (32, "Landing gear change after a severe hard landing",
                   ("Main landing gear shock strut assemblies, gear change tooling and jacks, structural repair kit",
                    9500, "6-person structures and gear team", 72, 1_200_000),
                   ("Main landing gear shock strut assemblies, gear change tooling and jacks, structural repair kit",
                    26000, "8-person structures and gear team", 120, 3_500_000)),
}


def classify(landing_rate, landing_g, tail_strike):
    """The AOG kind a flight's touchdown and rotation call for, or None."""
    rate, g = landing_rate if landing_rate is not None else 0, landing_g or 0
    if rate < DAMAGE_FPM or g >= DAMAGE_G:
        return "structural"
    if tail_strike:
        return "tail_strike"
    if rate < INSPECT_FPM or g >= INSPECT_G:
        return "hard_landing"
    return None


def kit_for(kind, code):
    ata, title, narrow, wide = KITS[kind]
    contents, lbs, team, hours, cost = wide if code in WIDE else narrow
    return {"ata": ata, "title": title, "contents": contents, "weight_lbs": lbs, "team": team, "repair_hours": hours, "cost_usd": cost}


def init(con):
    con.execute("""CREATE TABLE IF NOT EXISTS aog_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, reg TEXT, type TEXT, station TEXT,
        kind TEXT, title TEXT, kit TEXT, item_ids TEXT, cause_flight TEXT, cause_pirep INTEGER, opened REAL, status TEXT,
        mission_id TEXT, hub TEXT, parts_due REAL, parts_arrived REAL, delivered_by TEXT, delivered_flight TEXT,
        repair_until REAL, closed REAL, cost_usd REAL, contractor INTEGER DEFAULT 0, note TEXT)""")


def open_case_for(con, reg):
    r = con.execute("SELECT * FROM aog_cases WHERE reg=? AND status IN ('awaiting_parts','repairing') ORDER BY id DESC LIMIT 1", (reg,)).fetchone()
    return dict(r) if r else None


def _hub_for(station, code, ctx):
    """Nearest PAC hub that isn't the station itself (or the station, if it is a hub)."""
    if station in HUBS:
        return station
    s = ctx["airport_obj"](station)
    best = None
    for h in HUBS:
        a = ctx["airport_obj"](h)
        if not (s and a):
            continue
        d = ctx["gc_distance_nm"](s["lat"], s["lon"], a["lat"], a["lon"])
        if best is None or d < best[0]:
            best = (d, h)
    return best[1] if best else "KCVG"


def _mission(con, case, kit, hub, ctx, now):
    """The AOG recovery mission (an urgent request flown with the regular booking and filing flow)."""
    o, d = ctx["airport_obj"](hub), ctx["airport_obj"](case["station"])
    if not (o and d):
        return None
    dist = ctx["gc_distance_nm"](o["lat"], o["lon"], d["lat"], d["lon"])
    fleet = ctx["FLEET"]
    types = [c for c, ac in fleet.items() if not ac.get("retired") and (ac.get("max_payload_lbs") or 0) >= kit["weight_lbs"]
             and (ac.get("range_nm") or 0) >= dist * 1.1 and (not d.get("rwy_ft") or d["rwy_ft"] >= (ac.get("min_rwy_ft") or 0))]
    if not types:
        return None
    types.sort(key=lambda c: fleet[c].get("max_payload_lbs") or 0)   # smallest suitable first
    busy = {r[0] for r in con.execute("SELECT id FROM urgent WHERE status IN ('open','booked') OR created > ?", (now - 2 * 86400,))}
    n = next((n for n in AOG_IDS if f"PAC{n}" not in busy), None)
    if n is None:
        return None
    frame = con.execute("SELECT reg, type FROM airframes WHERE status='Available' AND location=? AND type IN (%s) ORDER BY type"
                        % ",".join("?" * len(types)), (hub, *types)).fetchone()
    ac0 = fleet[(frame["type"] if frame else types[0])]
    block = round(45 + dist / (ac0.get("cruise_ktas") or 450) * 60 * 1.05)
    expires = now + BOOK_WINDOW_H * 3600
    city = d.get("city") or d["icao"]
    m = {"id": f"PAC{n}", "title": f"AOG recovery: {case['reg']} at {city}", "category": "Urgent", "priority": "Critical",
         "urgent": True, "urgent_kind": "AOG recovery", "aog_case": case["id"], "origin": o, "destination": d,
         "aircraft": types, "suggested_airframe": frame["reg"] if frame else None,
         "cargo": kit["contents"], "payload_lbs": kit["weight_lbs"], "distance_nm": round(dist), "target_block_min": block,
         "reward": int(round((dist * 0.14 + kit["weight_lbs"] / 1000 * 1.2) * 2.0 / 10) * 10), "yield_mult": 2.0,
         "expires": expires, "deliver_by": expires + block * 60 + 3600,
         "briefing": (f"PAC's own {case['type_name']} {case['reg']} is grounded at {d['icao']} ({case['title'].lower()} after "
                      f"{case['cause_flight'] or 'its last flight'}). Fly the {kit['team']} and their kit from {hub}: "
                      f"{kit['contents'].lower()}. Repair takes about {kit['repair_hours']} hours once the kit arrives. "
                      f"If nobody flies it within {BOOK_WINDOW_H} hours, PAC charters a contractor at a higher cost.")}
    con.execute("DELETE FROM urgent WHERE id=?", (m["id"],))
    con.execute("INSERT INTO urgent (id, data, created, expires, status) VALUES (?,?,?,?, 'open')", (m["id"], json.dumps(m), now, expires))
    return m


def open_case(con, reg, code, station, kind, item_ids, cause_flight, cause_pirep, ctx, now=None):
    """Opens the AOG case for a grounded airframe and posts its recovery mission. Returns (case, event for the bot)."""
    now = now or time.time()
    init(con)
    if open_case_for(con, reg):
        return None, None
    kit = kit_for(kind, code)
    hub = _hub_for(station, code, ctx)
    at_hub = hub == station
    cur = con.execute("""INSERT INTO aog_cases (reg, type, station, kind, title, kit, item_ids, cause_flight, cause_pirep, opened, status, hub,
        parts_due, parts_arrived, repair_until, cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (reg, code, station, kind, kit["title"], json.dumps(kit), json.dumps(item_ids), cause_flight, cause_pirep, now,
                       "repairing" if at_hub else "awaiting_parts", hub, None if at_hub else now + BOOK_WINDOW_H * 3600,
                       now if at_hub else None, now + kit["repair_hours"] * 3600 if at_hub else None, kit["cost_usd"]))
    case = {"id": cur.lastrowid, "reg": reg, "type": code, "type_name": ctx["FLEET"].get(code, {}).get("name", code), "station": station,
            "kind": kind, "title": kit["title"], "cause_flight": cause_flight}
    mission = None
    if not at_hub:
        mission = _mission(con, case, kit, hub, ctx, now)
        if mission:
            con.execute("UPDATE aog_cases SET mission_id=? WHERE id=?", (mission["id"], case["id"]))
        else:   # nothing in the fleet can fly it there: contractor straight away
            con.execute("UPDATE aog_cases SET contractor=1, cost_usd=?, parts_due=? WHERE id=?",
                        (kit["cost_usd"] * CONTRACTOR_COST_MULT, now + CONTRACTOR_DELAY_H * 3600, case["id"]))
    body = (f"{reg} ({case['type_name']}) is AOG at {station}: {kit['title'].lower()} after {cause_flight or 'its last flight'}. "
            + (f"The parts are at the {station} hub; engineers expect it back in about {kit['repair_hours']} hours." if at_hub else
               f"Recovery flight {mission['id']} from {hub} carries the {kit['team']} and {kit['weight_lbs']:,} lb of parts. Any PAC pilot can fly it."
               if mission else f"A contractor is flying the parts in; about {CONTRACTOR_DELAY_H + kit['repair_hours']} hours to return to service."))
    con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                (now, "event", f"AOG: {reg} grounded at {station}", body, 0, now + 7 * 86400, "PAC Maintenance Control"))
    event = {"reg": reg, "type": case["type_name"], "station": station, "title": kit["title"], "cause": cause_flight,
             "mission": mission["id"] if mission else None, "hub": hub, "weight_lbs": kit["weight_lbs"], "repair_hours": kit["repair_hours"],
             "at_hub": at_hub}
    event["staff_discord"] = notify_staff(con, case, mission, now)
    return case, event


def notify_staff(con, case, mission, now):
    """One direct alert per active role holder; the public dispatch post is not a staff handoff."""
    import messaging
    messaging.migrate(con)
    roles = {
        "fleet_mgr": "Fleet: inspect the linked flight and grounding write-up in Fleet & maintenance → Maintenance. Keep the tail grounded until the inspection or repair is complete; record rectification before clearing it.",
        "dir_ops": "Operations: review this AOG in Ops desk → Exceptions. Record the hold or recovery decision and send a dispatch instruction to the pilot. Confirm any cargo disposition from shipment records.",
        "chief_pilot": "Chief Pilot: review the landing circumstances with the pilot and coordinate any safety follow-up with Maintenance. Do not clear the aircraft yourself.",
        "ceo": "CEO: monitor the Fleet and Operations handoff; resolve staffing or spending decisions they escalate.",
    }
    try:
        rows = con.execute("""SELECT r.pilot_id,r.role,p.discord_id FROM roles r JOIN pilots p ON p.id=r.pilot_id
            WHERE r.role IN ('fleet_mgr','dir_ops','chief_pilot','ceo')
              AND COALESCE(p.status,'Active')='Active'""").fetchall()
    except Exception:
        return []
    by_pilot = {}
    for row in rows:
        entry = by_pilot.setdefault(row["pilot_id"], {"steps": [], "discord_id": row["discord_id"]})
        entry["steps"].append(roles[row["role"]])
    subject = f"AOG action · {case['reg']} · case {case['id']}"
    newly_notified = set()
    for pid, entry in by_pilot.items():
        if con.execute("SELECT 1 FROM messages WHERE recipient=? AND subject=? LIMIT 1", (pid, subject)).fetchone():
            continue
        body = (f"{case['reg']} is grounded at {case['station']} after {case['cause_flight'] or 'a flight'}: {case['title']}.\n"
                f"{('Recovery mission ' + mission['id'] + ' is open.') if mission else 'The repair or contractor path is underway.'}\n\n"
                + "\n".join(entry["steps"]) + "\n\nThis automated alert does not release the aircraft or deliver cargo. Reply to the CEO if you need help.")
        con.execute("INSERT INTO messages (sender,recipient,subject,body,time) VALUES (?,?,?,?,?)",
                    ("SYSTEM", pid, subject, body, now))
        if entry["discord_id"]:
            newly_notified.add(str(entry["discord_id"]))
    return sorted(newly_notified)


def reconcile_staff_alerts(con, now=None):
    """Catch up role holders on active cases opened before direct staff alerts existed."""
    init(con)
    events = []
    for row in con.execute("""SELECT id,reg,type,station,title,cause_flight,mission_id,status
        FROM aog_cases WHERE status IN ('awaiting_parts','repairing') ORDER BY id"""):
        case = dict(row)
        mission = {"id": row["mission_id"]} if row["mission_id"] and row["status"] == "awaiting_parts" else None
        recipients = notify_staff(con, case, mission, now or time.time())
        if recipients:
            events.append({"reg": row["reg"], "station": row["station"], "cause": row["cause_flight"],
                           "staff_discord": recipients})
    return events


def parts_delivered(con, case_id, flight, pilot_id, now=None):
    """The recovery flight arrived: engineers start the repair."""
    now = now or time.time()
    init(con)
    r = con.execute("SELECT * FROM aog_cases WHERE id=? AND status='awaiting_parts'", (case_id,)).fetchone()
    if not r:
        return None
    kit = json.loads(r["kit"])
    con.execute("UPDATE aog_cases SET status='repairing', parts_arrived=?, delivered_by=?, delivered_flight=?, repair_until=? WHERE id=?",
                (now, pilot_id, flight, now + kit["repair_hours"] * 3600, case_id))
    return {"reg": r["reg"], "station": r["station"], "flight": flight, "pilot_id": pilot_id, "repair_hours": kit["repair_hours"]}


def tick(con, now=None):
    """Moves cases along: contractor fallback when the mission window closes, and return to service when the repair is done.
    Returns events for the bot."""
    now = now or time.time()
    init(con)
    events = []
    for r in con.execute("SELECT * FROM aog_cases WHERE status='awaiting_parts'").fetchall():
        kit = json.loads(r["kit"])
        st = con.execute("SELECT status, expires FROM urgent WHERE id=?", (r["mission_id"],)).fetchone() if r["mission_id"] else None
        booked = st is not None and st["status"] == "booked"
        if booked:   # a booking that is never flown doesn't strand the aircraft: contractor a day after the delivery deadline
            data = con.execute("SELECT data FROM urgent WHERE id=?", (r["mission_id"],)).fetchone()
            booked = now < (json.loads(data["data"]).get("deliver_by") or now) + 86400
        if not r["contractor"] and not booked and (st is None or st["status"] in ("expired",) or (st["expires"] or 0) < now):
            if r["mission_id"]:
                con.execute("UPDATE urgent SET status='expired' WHERE id=? AND status='open'", (r["mission_id"],))
            con.execute("UPDATE aog_cases SET contractor=1, cost_usd=?, parts_due=? WHERE id=?",
                        (kit["cost_usd"] * CONTRACTOR_COST_MULT, now + CONTRACTOR_DELAY_H * 3600, r["id"]))
        elif r["contractor"] and (r["parts_due"] or 0) <= now:
            con.execute("UPDATE aog_cases SET status='repairing', parts_arrived=?, delivered_flight='Contractor', repair_until=? WHERE id=?",
                        (now, now + kit["repair_hours"] * 3600, r["id"]))
    for r in con.execute("SELECT * FROM aog_cases WHERE status='repairing' AND repair_until <= ?", (now,)).fetchall():
        events.append(_return_to_service(con, dict(r), now))
    return events


def _charge(con, r, now):
    """The repair is paid when the aircraft returns to service: the parts and labour as an AOG repair, and, when a
    contractor had to fly the parts in, the contractor's extra as its own line, so the finance page shows what an
    unflown recovery mission cost. Once per case. Returns the contractor premium in USD (0 when PAC flew the parts)."""
    import company
    cost = float(r.get("cost_usd") or 0)
    if cost <= 0:
        return 0
    company.migrate(con)
    ref = f"aog-{r['id']}"
    if con.execute("SELECT 1 FROM company_ledger WHERE ref=? OR ref=?", (ref, ref + "-contractor")).fetchone():
        return 0
    base = round(cost / CONTRACTOR_COST_MULT, 2) if r.get("contractor") else cost
    premium = round(cost - base, 2)
    company.post(con, "aog_repair", -base, f"AOG repair, {r['reg']} at {r['station']}", ref=ref, when=now)
    if premium > 0:
        company.post(con, "aog_contractor", -premium, f"AOG contractor charter, {r['reg']} at {r['station']} (recovery mission not flown)",
                     ref=ref + "-contractor", when=now)
    return premium


def _return_to_service(con, r, now):
    who = r["delivered_flight"] or "parts on site"
    note = f"Returned to service after AOG recovery ({who})."
    for iid in json.loads(r["item_ids"] or "[]"):
        con.execute("UPDATE maint SET status='cleared', cleared_time=?, cleared_by=?, note=? WHERE id=? AND status='open'",
                    (now, "PAC Maintenance Control", note, iid))
    still = con.execute("SELECT COUNT(*) FROM maint WHERE reg=? AND status='open' AND (severity='grounding' OR (severity='deferred' AND due < ?))",
                        (r["reg"], now)).fetchone()[0]
    if not still:
        con.execute("UPDATE airframes SET status='Available', note=NULL, updated=? WHERE reg=? AND status IN ('Maintenance','Inspection','Damaged')",
                    (now, r["reg"]))
    con.execute("UPDATE aog_cases SET status='closed', closed=? WHERE id=?", (now, r["id"]))
    premium = _charge(con, r, now)
    hours = (now - r["opened"]) / 3600
    con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                (now, "event", f"{r['reg']} back in service at {r['station']}",
                 f"{r['reg']} is back in service after {hours:.0f} hours AOG. {note} Repair cost ${r['cost_usd']:,.0f}"
                 + (f", including ${premium:,.0f} for the contractor because nobody flew the recovery mission." if premium else "."),
                 0, now + 5 * 86400, "PAC Maintenance Control"))
    return {"kind": "aog_resolved", "reg": r["reg"], "station": r["station"], "hours": round(hours), "by": who,
            "pilot_id": r["delivered_by"], "cost": r["cost_usd"]}


def staff_cleared(con, reg, now=None):
    """Staff cleared the write-ups by hand: close the case and withdraw an unbooked mission."""
    now = now or time.time()
    init(con)
    r = open_case_for(con, reg)
    if not r:
        return
    if r["mission_id"]:
        con.execute("UPDATE urgent SET status='expired' WHERE id=? AND status='open'", (r["mission_id"],))
    con.execute("UPDATE aog_cases SET status='closed', closed=?, note='Cleared by staff' WHERE id=?", (now, r["id"]))


def cases(con, limit=50):
    init(con)
    out = []
    for r in con.execute("SELECT * FROM aog_cases ORDER BY CASE WHEN status='closed' THEN 1 ELSE 0 END, id DESC LIMIT ?", (limit,)):
        c = dict(r)
        c["kit"] = json.loads(c["kit"] or "{}")
        c["item_ids"] = json.loads(c["item_ids"] or "[]")
        out.append(c)
    return out
