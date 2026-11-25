"""The CEO desk and the company's people side: hub visits, key-account visits, the shipper complaint inbox, pilot of the
month and the monthly letter from the CEO. Plus the fleet market's staff API.

Visits are flown, not clicked: when a pilot holding the CEO role files a flight that arrives at a PAC hub, that's a hub
visit; arriving at a struggling shipper's home station is an account visit, which lifts the shipper's standing for 90
days (real executives fly out to win back unhappy customers). Complaints come in automatically after late or failed
deliveries; how the company answers changes the shipper's standing."""
from __future__ import annotations

import datetime as dt
import json
import time

import company

HUBS = {"KCVG": "Cincinnati", "LIMC": "Milan Malpensa", "KMIA": "Miami", "OMDW": "Dubai World Central", "VHHH": "Hong Kong", "PANC": "Anchorage"}
VISIT_BONUS, VISIT_DAYS = 15, 90
RESPONSES = {  # key: (label, standing change, cost to PAC)
    "apology": ("Personal apology from management", 3, 0),
    "discount": ("Apology and a 15% credit on their next shipment", 8, 25_000),
    "make_good": ("Fly a free make-up shipment", 12, 60_000),
}


def migrate(con):
    company.migrate(con)
    con.execute("CREATE TABLE IF NOT EXISTS ceo_visits (id INTEGER PRIMARY KEY AUTOINCREMENT, pilot_id TEXT, kind TEXT, place TEXT, shipper TEXT, time REAL, pirep_id INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS account_adjust (id INTEGER PRIMARY KEY AUTOINCREMENT, shipper TEXT, delta INTEGER, until REAL, reason TEXT, time REAL)")
    con.execute("""CREATE TABLE IF NOT EXISTS complaints (id INTEGER PRIMARY KEY AUTOINCREMENT, shipper TEXT, awb TEXT, kind TEXT, station TEXT,
        created REAL, status TEXT DEFAULT 'open', response TEXT, answered_by TEXT, answered REAL)""")
    con.execute("CREATE TABLE IF NOT EXISTS awards (month TEXT PRIMARY KEY, pilot_id TEXT, data TEXT, posted REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS ceo_letters (month TEXT PRIMARY KEY, body TEXT, posted REAL, by_pilot TEXT)")
    con.execute("""CREATE TABLE IF NOT EXISTS fleet_recs (id INTEGER PRIMARY KEY AUTOINCREMENT, by_pilot TEXT, created REAL,
        offer_id TEXT, aircraft TEXT, aircraft_name TEXT, way TEXT, reg TEXT, hub TEXT, weeks INTEGER, note TEXT,
        status TEXT DEFAULT 'pending', decided_by TEXT, decided_at REAL, decide_note TEXT)""")


def adjustments(con, now=None):
    """{shipper: extra standing} from CEO visits and complaint responses that are still in effect."""
    now = now or time.time()
    migrate(con)
    out = {}
    for s, d in con.execute("SELECT shipper, delta FROM account_adjust WHERE until>?", (now,)):
        out[s] = out.get(s, 0) + d
    return out


def home_station(con, shipper):
    r = con.execute("SELECT origin, COUNT(*) n FROM cargo_shipments WHERE shipper=? GROUP BY origin ORDER BY n DESC LIMIT 1", (shipper,)).fetchone()
    return r[0] if r else None


def accounts_needing_visit(con):
    import accounts
    acc = accounts.compute(con)
    out = []
    for a in acc.values():
        if a["tier"] in ("Under review", "At risk"):
            out.append(dict(a, station=home_station(con, a["shipper"])))
    return sorted(out, key=lambda a: a["score"])


def on_filed(con, pid, p, mission, pirep_id=None, now=None):
    """Called after every filed flight: records CEO hub and account visits."""
    if p.get("demo"):
        return []
    return arrive(con, pid, p.get("arr") or ((mission or {}).get("destination") or {}).get("icao"), pirep_id, now)


def arrive(con, pid, arr, pirep_id=None, now=None):
    """The CEO has arrived somewhere (flown, jumpseated or travelled): records hub and account visits."""
    now = now or time.time()
    migrate(con)
    if "ceo" not in company.roles_of(con, pid):
        return []
    done = []
    if arr in HUBS:
        con.execute("INSERT INTO ceo_visits (pilot_id, kind, place, time, pirep_id) VALUES (?,?,?,?,?)", (pid, "hub", arr, now, pirep_id))
        done.append(("hub", arr, None))
    for a in accounts_needing_visit(con):
        if a["station"] == arr and not con.execute("SELECT 1 FROM account_adjust WHERE shipper=? AND reason LIKE 'CEO visit%' AND until>?", (a["shipper"], now)).fetchone():
            con.execute("INSERT INTO ceo_visits (pilot_id, kind, place, shipper, time, pirep_id) VALUES (?,?,?,?,?,?)", (pid, "account", arr, a["shipper"], now, pirep_id))
            con.execute("INSERT INTO account_adjust (shipper, delta, until, reason, time) VALUES (?,?,?,?,?)",
                        (a["shipper"], VISIT_BONUS, now + VISIT_DAYS * 86400, f"CEO visit to {arr}", now))
            done.append(("account", arr, a["shipper"]))
    return done


def station_report(con, icao, now=None):
    now = now or time.time()
    waiting = con.execute("""SELECT COUNT(*), COALESCE(SUM(gross_weight_lbs),0) FROM cargo_shipments WHERE current_station=?
        AND status NOT IN ('DELIVERED','DELIVERED_LATE','EXCEPTION')""", (icao,)).fetchone()
    frames = con.execute("SELECT status, COUNT(*) FROM airframes WHERE location=? GROUP BY status", (icao,)).fetchall()
    arrivals = con.execute("""SELECT status FROM pireps WHERE arr=? AND demo=0 AND review_status='Accepted' AND filed_at>?""",
                           (icao, now - 30 * 86400)).fetchall()
    on_time = sum(1 for (s,) in arrivals if s == "Delivered")
    last = con.execute("SELECT MAX(time) FROM ceo_visits WHERE kind='hub' AND place=?", (icao,)).fetchone()[0]
    return {"icao": icao, "city": HUBS.get(icao), "waiting": waiting[0], "waiting_lbs": round(waiting[1]),
            "aircraft": {s: n for s, n in frames}, "arrivals_30d": len(arrivals),
            "on_time_pct": round(100 * on_time / len(arrivals)) if arrivals else None, "last_visit": last}


def _quarter_start(now):
    d = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    return dt.datetime(d.year, 3 * ((d.month - 1) // 3) + 1, 1, tzinfo=dt.timezone.utc).timestamp()


# ------------------------------------------------------------------------------------------------------- complaints
def fix_false_late(con):
    """Shipments marked late although they arrived before their own deadline (an earlier rule took the flight's on-time
    result): set them to delivered and withdraw the complaints they caused. Safe to run any number of times."""
    fixed = 0
    for sid, awb, data, upd in con.execute("SELECT id, awb, data, updated_at FROM cargo_shipments WHERE status='DELIVERED_LATE'").fetchall():
        try:
            dl = float(json.loads(data or "{}").get("deadline") or 0)
        except (ValueError, TypeError):
            dl = 0
        if dl and upd and upd <= dl:
            con.execute("UPDATE cargo_shipments SET status='DELIVERED' WHERE id=?", (sid,))
            con.execute("UPDATE complaints SET status='withdrawn' WHERE awb=? AND status='open'", (awb,))
            fixed += 1
    return fixed


def scan_complaints(con, now=None):
    """A late or failed delivery in the last week gets a complaint from its shipper (at most one open per shipper)."""
    now = now or time.time()
    migrate(con)
    made = 0
    for r in con.execute("""SELECT shipper, awb, status, destination FROM cargo_shipments WHERE status IN ('DELIVERED_LATE','EXCEPTION')
            AND updated_at>? ORDER BY updated_at""", (now - 7 * 86400,)).fetchall():
        if con.execute("SELECT 1 FROM complaints WHERE awb=?", (r[1],)).fetchone():
            continue
        if con.execute("SELECT 1 FROM complaints WHERE shipper=? AND status='open'", (r[0],)).fetchone():
            continue
        con.execute("INSERT INTO complaints (shipper, awb, kind, station, created) VALUES (?,?,?,?,?)",
                    (r[0], r[1], "late" if r[2] == "DELIVERED_LATE" else "failed", r[3], now))
        made += 1
    return made


def answer(con, cid, key, by, now=None):
    now = now or time.time()
    if key not in RESPONSES:
        raise ValueError("Pick a response.")
    c = con.execute("SELECT * FROM complaints WHERE id=? AND status='open'", (cid,)).fetchone()
    if not c:
        raise ValueError("That complaint has already been answered.")
    label, delta, cost = RESPONSES[key]
    con.execute("UPDATE complaints SET status='answered', response=?, answered_by=?, answered=? WHERE id=?", (key, by, now, cid))
    con.execute("INSERT INTO account_adjust (shipper, delta, until, reason, time) VALUES (?,?,?,?,?)",
                (c["shipper"], delta, now + VISIT_DAYS * 86400, f"Complaint answered: {label}", now))
    if cost:
        company.post(con, "goodwill", -cost, f"{label} for {c['shipper']} (AWB {c['awb']})", c["awb"], by, now)
    return {"shipper": c["shipper"], "delta": delta, "cost": cost}


# ------------------------------------------------------------------------------------------------- pilot of the month
def _month_bounds(month):
    y, m = map(int, month.split("-"))
    a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    b = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc)
    return a.timestamp(), b.timestamp()


def pilot_of_month(con, month):
    """The month's standout pilot: hours flown, flights, smooth landings and on-time deliveries (at least 3 flights)."""
    a, b = _month_bounds(month)
    rows = con.execute("""SELECT p.pilot_id, n.name, COUNT(*) flights, SUM(p.block_min)/60.0 hours,
            SUM(CASE WHEN p.landing_rate >= -300 AND p.landing_rate < 0 THEN 1 ELSE 0 END) smooth,
            SUM(CASE WHEN p.status='Delivered' THEN 1 ELSE 0 END) on_time, AVG(p.landing_rate) avg_rate
        FROM pireps p LEFT JOIN pilots n ON n.id=p.pilot_id WHERE p.demo=0 AND p.review_status='Accepted' AND p.filed_at>=? AND p.filed_at<?
        GROUP BY p.pilot_id HAVING flights>=3""", (a, b)).fetchall()
    best = None
    for r in rows:
        score = (r[3] or 0) + 2 * r[2] + 3 * (r[4] or 0) + 2 * (r[5] or 0)
        if not best or score > best["score"]:
            best = {"pilot_id": r[0], "name": r[1] or r[0], "flights": r[2], "hours": round(r[3] or 0, 1), "smooth": r[4] or 0,
                    "on_time": r[5] or 0, "avg_rate": round(r[6]) if r[6] is not None else None, "score": round(score, 1)}
    return best


def tick(con, news, now=None):
    """Runs with the maintenance tick: complaints, and on the first days of a month, last month's pilot of the month."""
    now = now or time.time()
    migrate(con)
    fix_false_late(con)
    scan_complaints(con, now)
    d = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    if d.day <= 3:
        prev = (d.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
        if not con.execute("SELECT 1 FROM awards WHERE month=?", (prev,)).fetchone():
            best = pilot_of_month(con, prev)
            con.execute("INSERT INTO awards (month, pilot_id, data, posted) VALUES (?,?,?,?)", (prev, best and best["pilot_id"], json.dumps(best), now))
            if best:
                label = dt.datetime.strptime(prev, "%Y-%m").strftime("%B %Y")
                news(f"Pilot of the month: {best['name']}",
                     f"{best['name']} is PAC's pilot of the month for {label}: {best['flights']} flights, {best['hours']} hours, "
                     f"{best['smooth']} smooth landings and {best['on_time']} on-time deliveries. Congratulations!")


# ----------------------------------------------------------------------------------------------- letter from the CEO
def letter_draft(con, month, ceo_name):
    a, b = _month_bounds(month)
    label = dt.datetime.strptime(month, "%Y-%m").strftime("%B")
    f = con.execute("""SELECT COUNT(*), COALESCE(SUM(payload_lbs),0), COALESCE(SUM(block_min),0)/60.0,
            SUM(CASE WHEN status='Delivered' THEN 1 ELSE 0 END), COUNT(DISTINCT pilot_id)
        FROM pireps WHERE demo=0 AND review_status='Accepted' AND filed_at>=? AND filed_at<?""", (a, b)).fetchone()
    flights, lbs, hours, on_time, pilots = f[0], f[1], f[2], f[3] or 0, f[4]
    st = next((s for s in company.statements(con, 24) if s["month"] == month), None)
    aw = con.execute("SELECT data FROM awards WHERE month=?", (month,)).fetchone()
    pom = json.loads(aw[0]) if aw and aw[0] else pilot_of_month(con, month)
    new_ac = [r[0] for r in con.execute("""SELECT description FROM company_ledger WHERE kind IN ('aircraft_purchase','conversion','lease','wet_lease')
        AND time>=? AND time<? AND description NOT LIKE 'Monthly lease%'""", (a, b))]
    hubs = sorted({r[0] for r in con.execute("SELECT place FROM ceo_visits WHERE kind='hub' AND time>=? AND time<?", (a, b))})
    lines = [f"Team,", "",
             f"{label} is in the books. {pilots} pilot{'s' if pilots != 1 else ''} flew {flights} flight{'s' if flights != 1 else ''} for PAC, "
             f"moving {lbs / 2204.62:,.0f} tonnes of freight in {hours:,.0f} block hours"
             + (f", with {round(100 * on_time / flights)}% delivered on time." if flights else ".")]
    if st:
        lines.append(f"Revenue came to ${st['revenue']:,.0f} and the company {'made' if st['net'] >= 0 else 'lost'} ${abs(st['net']):,.0f} after all costs.")
    if pom:
        lines += ["", f"Pilot of the month is {pom['name']}: {pom['flights']} flights, {pom['hours']} hours and {pom['smooth']} smooth landings. Thank you."]
    if new_ac:
        lines += ["", "Fleet news: " + "; ".join(new_ac) + "."]
    if hubs:
        lines += ["", "I visited " + ", ".join(f"{HUBS[h]} ({h})" for h in hubs) + " this month. Thank you to everyone who keeps those stations moving."]
    lines += ["", "Fly safe and keep the freight moving.", "", f"{ceo_name}", "Chief Executive Officer, Pagani Air Cargo"]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------------- the API
# ---------------------------------------------------------------- executive travel
# How a real airline CEO gets to a hub: a seat on the airline's own freighter (free), a commercial ticket (economy on
# short trips, business class on long haul, as company travel policies allow), or a business jet charter.
CHARTER_MID, CHARTER_LARGE = 5500, 9500          # dollars per flight hour: midsize jet, large-cabin jet


def travel_options(frm, to, dist, pac_seat):
    long = dist >= 3000          # business class only on long-haul international trips
    fare = round(600 + 1.1 * dist, -1) if long else round(180 + 0.25 * dist, -1)
    jet_rate = CHARTER_LARGE if dist > 2500 else CHARTER_MID
    jet_h = round(dist / 430 + 0.5, 1)
    opts = []
    if pac_seat:
        opts.append({"kind": "pac", "label": "Ride along on a PAC freighter", "cost": 0,
                     "note": "Jumpseat or courier seat on our own flight. Free, and the crews get to meet the boss."})
    opts.append({"kind": "commercial", "label": f"Commercial ticket ({'business class' if long else 'economy'})", "cost": int(fare),
                 "note": "Booked by the company as executive travel." + (" Business class on long haul, per company travel policy." if long else "")})
    opts.append({"kind": "charter", "label": f"Business jet charter ({'large-cabin' if dist > 2500 else 'midsize'} jet)", "cost": int(round(jet_rate * jet_h, -2)),
                 "note": f"About {jet_h} h at ${jet_rate:,}/h. Fastest, and the board will see the bill."})
    return opts


def register(app, g):
    from flask import jsonify, request
    import fleet_market

    def pid():
        return g["va"].current_pilot_id()

    def cash(con):
        import economics
        s = g["settings"]()
        start = float(s.get("starting_capital") or economics.DEFAULT_START_CAPITAL)
        prof = con.execute("SELECT COALESCE(SUM(profit),0) FROM pireps WHERE demo=0 AND review_status='Accepted' AND revenue IS NOT NULL").fetchone()[0]
        shares = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE kind IN ('profit_share','base_pay','role_stipend')").fetchone()[0]
        return round(start + prof - shares + company.ledger_total(con))

    def deny(con, what):
        if not company.may(con, pid(), what):
            return jsonify({"error": "This is for the CEO (or the role it's been handed to)."}), 403

    def _quote(con, to):
        va = g["va"]
        frm = va.pilot_location(pid())
        q = va.jumpseat_options(frm, to)
        return frm, q, travel_options(frm, q["to"]["icao"], q["distance_nm"], any(o["kind"] == "pac" for o in q["options"]))

    def _hub_network(con):
        import hubs as H
        import growth
        H.migrate(con)
        opened = [dict(zip(("icao", "city", "opened_at"), r)) for r in
                  con.execute("SELECT icao, city, opened_at FROM hubs_opened WHERE closed_at IS NULL ORDER BY opened_at")]
        ap = g["AIRPORTS"]
        cands = [dict(c, city=(ap.get(c["icao"]) or {}).get("city") or c["icao"]) for c in growth.hub_candidates(con, n=6)]
        return {"core": list(H.CORE), "opened": opened, "candidates": cands, "open_cost": H.OPEN_COST,
                "monthly_cost": H.MONTHLY_COST, "max": H.MAX_HUBS, "count": len(H.names())}

    @app.post("/api/staff/ceo/hub")
    def ceo_hub():
        import hubs as H
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        try:
            with g["db"]() as con:
                if (r := deny(con, "ceo_desk")):
                    return r
                if b.get("action") == "close":
                    H.close_hub(con, b.get("icao"), pid())
                    return jsonify({"ok": True, "hub_network": _hub_network(con)})
                city = H.open_hub(con, b.get("icao"), (b.get("city") or "").strip()[:40], pid(), g["AIRPORTS"])
                icao = str(b.get("icao")).upper()
                con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                            (time.time(), "news", f"PAC opens a new hub in {city}",
                             f"Pagani Air Cargo has opened its newest hub at {city} ({icao}). Missions, trips and cargo orders now start "
                             f"from {icao}, and pilots can choose it as their home base.", 1, time.time() + 21 * 86400, "PAC Operations"))
                return jsonify({"ok": True, "city": city, "hub_network": _hub_network(con)})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.get("/api/staff/ceo/travel")
    def ceo_travel_quote():
        try:
            with g["db"]() as con:
                if (r := deny(con, "ceo_desk")):
                    return r
                frm, q, opts = _quote(con, request.args.get("to", ""))
                return jsonify({"from": frm, "to": q["to"]["icao"], "city": q["to"].get("city"), "distance_nm": q["distance_nm"], "options": opts})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/staff/ceo/travel")
    def ceo_travel_go():
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        try:
            with g["db"]() as con:
                if (r := deny(con, "ceo_desk")):
                    return r
                frm, q, opts = _quote(con, b.get("to", ""))
                o = next((x for x in opts if x["kind"] == b.get("how")), None)
                if not o:
                    return jsonify({"error": "That way of travelling isn't available for this trip."}), 400
                to = q["to"]["icao"]
                if o["cost"]:
                    company.post(con, "exec_travel", -o["cost"], f"{o['label']}: {frm} to {to} ({q['distance_nm']:,} nm)", None, pid())
                con.execute("UPDATE pilots SET location=? WHERE id=?", (to, pid()))
                done = arrive(con, pid(), to)
                return jsonify({"location": to, "cost": o["cost"], "how": o["label"],
                                "visits": [{"kind": k, "place": pl, "shipper": sh} for k, pl, sh in done]})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.get("/api/staff/ceo")
    def ceo_desk():
        with g["db"]() as con:
            migrate(con)
            if (r := deny(con, "ceo_desk")):
                return r
            now = time.time()
            q0 = _quarter_start(now)
            visited = {r[0] for r in con.execute("SELECT DISTINCT place FROM ceo_visits WHERE kind='hub' AND time>=?", (q0,))}
            month = (dt.datetime.now(dt.timezone.utc).replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
            me = con.execute("SELECT name FROM pilots WHERE id=?", (pid(),)).fetchone()
            letter = con.execute("SELECT posted FROM ceo_letters WHERE month=?", (month,)).fetchone()
            return jsonify({"hubs": [dict(station_report(con, h, now), visited_this_quarter=h in visited) for h in HUBS],
                            "accounts": accounts_needing_visit(con), "visit_bonus": VISIT_BONUS, "visit_days": VISIT_DAYS,
                            "visits": [dict(zip(("kind", "place", "shipper", "time"), r)) for r in
                                       con.execute("SELECT kind, place, shipper, time FROM ceo_visits ORDER BY time DESC LIMIT 12")],
                            "letter": {"month": month, "posted": letter[0] if letter else None,
                                       "draft": letter_draft(con, month, (me[0] if me else "The CEO"))},
                            "awards": [dict(month=r[0], **(json.loads(r[1]) if r[1] and r[1] != "null" else {})) for r in
                                       con.execute("SELECT month, data FROM awards ORDER BY month DESC LIMIT 6")],
                            "cash": cash(con), "location": g["va"].pilot_location(pid()),
                            "hub_network": _hub_network(con)})

    @app.post("/api/staff/ceo/letter")
    def ceo_letter():
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        with g["db"]() as con:
            migrate(con)
            if (r := deny(con, "ceo_desk")):
                return r
            body = (b.get("body") or "").strip()
            month = b.get("month")
            if len(body) < 40 or not month:
                return jsonify({"error": "The letter is empty."}), 400
            me = con.execute("SELECT name FROM pilots WHERE id=?", (pid(),)).fetchone()
            label = dt.datetime.strptime(month, "%Y-%m").strftime("%B %Y")
            con.execute("INSERT INTO news (time, kind, title, body, important, expires, author) VALUES (?,?,?,?,?,?,?)",
                        (time.time(), "news", f"A letter from the CEO: {label}", body, 0, None, (me[0] if me else "PAC") + ", CEO"))
            con.execute("INSERT OR REPLACE INTO ceo_letters (month, body, posted, by_pilot) VALUES (?,?,?,?)", (month, body, time.time(), pid()))
            return jsonify({"ok": True})

    @app.get("/api/staff/complaints")
    def complaint_list():
        with g["db"]() as con:
            migrate(con)
            if (r := deny(con, "complaints")):
                return r
            fix_false_late(con)
            scan_complaints(con)
            import accounts
            acc = accounts.compute(con)
            rows = [dict(r) for r in con.execute("SELECT * FROM complaints ORDER BY status='answered', created DESC LIMIT 40")]
            for c in rows:
                c["standing"] = acc.get(c["shipper"])
            return jsonify({"complaints": rows, "responses": [{"key": k, "label": v[0], "delta": v[1], "cost": v[2]} for k, v in RESPONSES.items()]})

    @app.post("/api/staff/complaints/<int:cid>")
    def complaint_answer(cid):
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        try:
            with g["db"]() as con:
                migrate(con)
                if (r := deny(con, "complaints")):
                    return r
                return jsonify(answer(con, cid, b.get("response"), pid()))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.get("/api/staff/accounts")
    def shipper_accounts():
        """Commercial: every shipper's 90-day account standing, worst first, with at-risk ones flagged."""
        with g["db"]() as con:
            if (r := deny(con, "complaints")):
                return r
            import accounts
            acc = accounts.compute(con)
            rows = sorted(acc.values(), key=lambda a: (a["score"], -a.get("shipments", 0)))
            needs = [a for a in rows if a["tier"] in ("Under review", "At risk")]
            return jsonify({"accounts": rows, "needs_attention": needs, "tiers": [t[1] for t in accounts.TIERS]})

    @app.get("/api/staff/lanes")
    def lane_reputation():
        """Commercial: route-level customer reputation, weakest lanes first."""
        with g["db"]() as con:
            if (r := deny(con, "complaints")):
                return r
            import lanes
            L = lanes.compute(con)
            rows = sorted(L.values(), key=lambda x: (x["score"], -x.get("flights", 0)))
            return jsonify({"lanes": rows})

    # --- Fleet acquisitions: the Fleet Manager recommends, the owner approves ---
    def _is_admin():
        with g["db"]() as con:
            row = con.execute("SELECT staff FROM pilots WHERE id=?", (pid(),)).fetchone()
        return bool(row and row[0])

    @app.get("/api/staff/fleet-catalog")
    def fleet_catalog():
        """Aircraft offers for the Fleet Manager to recommend from. No company cash is exposed here."""
        with g["db"]() as con:
            fleet_market.migrate(con)
            if (r := deny(con, "fleet_recs")):
                return r
            return jsonify({"offers": fleet_market.offers(g["FLEET"], app.static_folder), "hubs": list(fleet_market.HUBS)})

    @app.get("/api/staff/fleet-recs")
    def fleet_recs_list():
        with g["db"]() as con:
            migrate(con)
            if (r := deny(con, "fleet_recs")):
                return r
            rows = [dict(x) for x in con.execute(
                """SELECT fr.*, p.name by_name, d.name decided_name FROM fleet_recs fr
                   LEFT JOIN pilots p ON p.id=fr.by_pilot LEFT JOIN pilots d ON d.id=fr.decided_by
                   ORDER BY fr.status='pending' DESC, fr.created DESC LIMIT 80""")]
            can_decide = company.may(con, pid(), "fleet_market")
        return jsonify({"recs": rows, "can_decide": can_decide})

    @app.post("/api/staff/fleet-recs")
    def fleet_rec_create():
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        with g["db"]() as con:
            migrate(con); fleet_market.migrate(con)
            if (r := deny(con, "fleet_recs")):
                return r
            o = next((x for x in fleet_market.offers(g["FLEET"], app.static_folder) if x["id"] == str(b.get("offer") or "")), None)
            if not o:
                return jsonify({"error": "Pick an aircraft offer."}), 400
            hub = str(b.get("hub") or "").upper()
            if hub not in fleet_market.HUBS:
                return jsonify({"error": "Choose a PAC hub for the aircraft."}), 400
            reg = str(b.get("reg") or "").strip().upper()
            if not fleet_market.REG_RE.match(reg):
                return jsonify({"error": "Suggest a registration like N306PC."}), 400
            weeks = max(1, min(12, int(b.get("weeks") or 1))) if o["way"] == "wet" else None
            note = (str(b.get("note") or "")).strip()[:500]
            con.execute("""INSERT INTO fleet_recs (by_pilot, created, offer_id, aircraft, aircraft_name, way, reg, hub, weeks, note, status)
                VALUES (?,?,?,?,?,?,?,?,?,?, 'pending')""",
                        (pid(), time.time(), o["id"], o["aircraft"], o["aircraft_name"], o["way"], reg, hub, weeks, note))
            con.commit()
        return jsonify({"ok": True})

    @app.post("/api/staff/market/rec/<int:rid>")
    def fleet_rec_decide(rid):
        """Owner-only (under /api/staff/market, which is admin-gated): approve executes the order, decline closes it."""
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        action, note = b.get("action"), (str(b.get("note") or "")).strip()[:500]
        try:
            with g["db"]() as con:
                migrate(con); fleet_market.migrate(con)
                if (r := deny(con, "fleet_market")):   # only the CEO spends company money
                    return r
                row = con.execute("SELECT * FROM fleet_recs WHERE id=?", (rid,)).fetchone()
                if not row:
                    return jsonify({"error": "That recommendation is gone."}), 404
                if row["status"] != "pending":
                    return jsonify({"error": "That recommendation was already decided."}), 409
                if action == "approve":
                    res = fleet_market.order(con, row["offer_id"], row["reg"], row["hub"], row["weeks"], cash(con),
                                             g["FLEET"], app.static_folder, pid())
                    con.execute("UPDATE fleet_recs SET status='approved', decided_by=?, decided_at=?, decide_note=? WHERE id=?",
                                (pid(), time.time(), note, rid))
                    con.commit()
                    _unretire(row["offer_id"])
                    return jsonify({"ok": True, "ordered": res})
                if action == "decline":
                    con.execute("UPDATE fleet_recs SET status='declined', decided_by=?, decided_at=?, decide_note=? WHERE id=?",
                                (pid(), time.time(), note, rid))
                    con.commit()
                    return jsonify({"ok": True})
                return jsonify({"error": "Choose approve or decline."}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.get("/api/staff/market")
    def market():
        with g["db"]() as con:
            fleet_market.migrate(con)
            if (r := deny(con, "fleet_market")):
                return r
            companies = {k: {"name": v[0], "kind": v[1], "country": v[2], "logo": fleet_market.logo(k, app.static_folder),
                             "note": fleet_market.NOTES.get(k)} for k, v in fleet_market.COMPANIES.items()}
            return jsonify({"offers": fleet_market.offers(g["FLEET"], app.static_folder), "companies": companies, "cash": cash(con),
                            "fleet": fleet_market.fleet_rows(con, g["FLEET"]), "hubs": list(fleet_market.HUBS), "disclaimer": fleet_market.DISCLAIMER})

    def _unretire(offer_id):
        """Buying or leasing a type PAC had sold off brings the type back into the fleet."""
        o = next((x for x in fleet_market.offers(g["FLEET"], app.static_folder) if x["id"] == offer_id), None)
        if o and g["FLEET"].get(o["aircraft"], {}).get("retired"):
            g["save_fleet_custom"](o["aircraft"], {"retired": False})

    @app.post("/api/staff/market/order")
    def market_order():
        b = request.get_json(silent=True); b = b if isinstance(b, dict) else {}
        try:
            with g["db"]() as con:
                fleet_market.migrate(con)
                if (r := deny(con, "fleet_market")):
                    return r
                out = fleet_market.order(con, b.get("offer"), b.get("reg"), b.get("hub"), b.get("weeks"), cash(con),
                                         g["FLEET"], app.static_folder, pid())
            _unretire(str(b.get("offer") or ""))
            return jsonify(out)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.post("/api/staff/market/return/<reg>")
    def market_return(reg):
        try:
            with g["db"]() as con:
                fleet_market.migrate(con)
                if (r := deny(con, "fleet_market")):
                    return r
                reg = reg.upper()
                row = con.execute("SELECT type FROM airframes WHERE reg=?", (reg,)).fetchone()
                note = fleet_market.give_back(con, reg, pid(), fleet=g["FLEET"])
                typ = row[0] if row else None
                gone = bool(typ) and not con.execute("SELECT 1 FROM airframes WHERE type=?", (typ,)).fetchone()
            if gone:   # that was the last one: the type leaves PAC's fleet (missions, booking, the fleet page)
                g["save_fleet_custom"](typ, {"retired": True})
                note += f". That was PAC's last {g['FLEET'].get(typ, {}).get('name', typ)}, so the type has left the fleet"
            return jsonify({"note": note, "type_retired": typ if gone else None})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
