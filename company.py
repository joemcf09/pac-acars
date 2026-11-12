"""The company itself: management roles, the company ledger and the monthly profit and loss statement.

Roles: management work (the CEO desk today; Chief Pilot, Director of Operations and others later) is tied to a role,
not to an account. The owner holds the CEO role from the start; any role can be handed to another pilot later from the
Staff page, and the work follows the role.

Ledger: money the company spends or earns outside flights (aircraft purchases, lease and wet-lease payments, goodwill
discounts to shippers). Flight revenue and costs stay on each PIREP, as before; the ledger adds the rest so the cash
balance and the monthly statement cover everything."""
from __future__ import annotations

import datetime as dt
import json
import time

OWNER = "PAC0001"
ROLES = {
    "ceo": ("Chief Executive Officer", "Hub visits, key accounts, fleet purchases and leases, the monthly letter"),
    "chief_pilot": ("Chief Pilot", "Checkrides, landing reviews, safety stand-downs"),
    "dir_ops": ("Director of Operations", "Mission boards, events, group flights, campaigns"),
    "fleet_mgr": ("Fleet & Maintenance Manager", "Heavy checks, AOG recovery, aircraft retirements"),
    "commercial": ("Commercial Director", "Shipper accounts, complaints, partner airlines"),
    "creative": ("Creative / Media Director", "Liveries, screenshots, promo graphics, social media"),
    "hub_mgr": ("Hub Manager", "A hub's station report, backlog and regular pilots"),
}
# which roles may do what (the CEO can always do everything)
CAN = {"ceo_desk": {"ceo"}, "fleet_market": {"ceo", "fleet_mgr"}, "complaints": {"ceo", "commercial"}, "roles": {"ceo"}}


def migrate(con):
    con.execute("CREATE TABLE IF NOT EXISTS roles (pilot_id TEXT, role TEXT, note TEXT, since REAL, PRIMARY KEY (pilot_id, role))")
    con.execute("""CREATE TABLE IF NOT EXISTS company_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, kind TEXT, amount REAL,
        description TEXT, ref TEXT, by_pilot TEXT)""")
    if not con.execute("SELECT 1 FROM roles WHERE role='ceo'").fetchone():
        con.execute("INSERT OR IGNORE INTO roles (pilot_id, role, note, since) VALUES (?,?,?,?)", (OWNER, "ceo", "Founder", time.time()))


def roles_of(con, pid):
    migrate(con)
    return {r[0] for r in con.execute("SELECT role FROM roles WHERE pilot_id=?", (pid,))}


def may(con, pid, what):
    mine = roles_of(con, pid)
    return "ceo" in mine or bool(mine & CAN.get(what, set()))


def holders(con):
    migrate(con)
    rows = con.execute("""SELECT r.pilot_id, r.role, r.note, r.since, p.name FROM roles r LEFT JOIN pilots p ON p.id=r.pilot_id
        ORDER BY r.since""").fetchall()
    return [{"pilot_id": r[0], "role": r[1], "title": ROLES.get(r[1], (r[1],))[0], "note": r[2], "since": r[3], "name": r[4]} for r in rows]


def assign(con, pid, role, note=""):
    if role not in ROLES:
        raise ValueError("Unknown role.")
    if not con.execute("SELECT 1 FROM pilots WHERE id=?", (pid,)).fetchone():
        raise ValueError(f"No pilot {pid}.")
    con.execute("INSERT OR REPLACE INTO roles (pilot_id, role, note, since) VALUES (?,?,?,?)", (pid, role, note, time.time()))


def unassign(con, pid, role):
    if role == "ceo" and con.execute("SELECT COUNT(*) FROM roles WHERE role='ceo'").fetchone()[0] <= 1:
        raise ValueError("PAC always needs a CEO. Give the role to someone else first.")
    con.execute("DELETE FROM roles WHERE pilot_id=? AND role=?", (pid, role))


def post(con, kind, amount, description, ref=None, by=None, when=None):
    """amount: positive = money in, negative = money out."""
    migrate(con)
    con.execute("INSERT INTO company_ledger (time, kind, amount, description, ref, by_pilot) VALUES (?,?,?,?,?,?)",
                (when or time.time(), kind, round(float(amount), 2), description, ref, by))


def ledger_total(con):
    migrate(con)
    return con.execute("SELECT COALESCE(SUM(amount),0) FROM company_ledger").fetchone()[0]


LEDGER_LINE = {"aircraft_purchase": "Aircraft purchases", "conversion": "Freighter conversions", "lease": "Aircraft leases",
               "wet_lease": "Wet leases (ACMI)", "goodwill": "Customer goodwill", "aircraft_sale": "Aircraft sales", "other": "Other"}
COST_LINE = {"fuel": "Fuel", "crew": "Crew", "maintenance": "Maintenance", "ownership": "Aircraft ownership", "landing_fees": "Landing fees",
             "navigation": "Navigation", "handling": "Handling", "incidents": "Incidents"}


def _month(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m")


def statements(con, months=6):
    """The monthly profit and loss statement for the last `months` months, newest first."""
    migrate(con)
    out = {}
    def m(key):
        return out.setdefault(key, {"month": key, "revenue": 0.0, "flights": 0, "operating": {}, "people": {}, "other": {}})
    for r in con.execute("""SELECT filed_at, revenue, cost, detail FROM pireps WHERE demo=0 AND review_status='Accepted'
            AND revenue IS NOT NULL"""):
        s = m(_month(r[0])); s["revenue"] += r[1] or 0; s["flights"] += 1
        costs = ((json.loads(r[3] or "{}").get("economics") or {}).get("costs") or {})
        if not costs and r[2]:
            costs = {"other": r[2]}
        for k, v in costs.items():
            lbl = COST_LINE.get(k, k.replace("_", " ").capitalize())
            s["operating"][lbl] = s["operating"].get(lbl, 0) + v
    for r in con.execute("SELECT time, kind, amount FROM wallet WHERE kind IN ('per_diem','profit_share','campaign')"):
        lbl = {"per_diem": "Per diem", "profit_share": "Pilot profit share", "campaign": "Campaign rewards"}[r[1]]
        s = m(_month(r[0])); s["people"][lbl] = s["people"].get(lbl, 0) + (r[2] or 0)
    for r in con.execute("SELECT time, kind, amount FROM company_ledger"):
        lbl = LEDGER_LINE.get(r[1], r[1])
        s = m(_month(r[0])); s["other"][lbl] = s["other"].get(lbl, 0) + (r[2] or 0)
    res = []
    for k in sorted(out, reverse=True)[:months]:
        s = out[k]
        op = sum(s["operating"].values()); ppl = sum(s["people"].values()); oth = sum(s["other"].values())
        s["operating_profit"] = round(s["revenue"] - op)
        s["net"] = round(s["revenue"] - op - ppl + oth)
        for grp in ("operating", "people", "other"):
            s[grp] = {a: round(b) for a, b in sorted(s[grp].items(), key=lambda kv: -abs(kv[1]))}
        s["revenue"] = round(s["revenue"])
        res.append(s)
    return res


def register(app, g):
    from flask import jsonify, request

    def pid():
        return g["va"].current_pilot_id()

    @app.get("/api/staff/roles")
    def roles_list():
        with g["db"]() as con:
            return jsonify({"roles": [{"key": k, "title": v[0], "does": v[1]} for k, v in ROLES.items()], "holders": holders(con),
                            "mine": sorted(roles_of(con, pid())), "can_assign": may(con, pid(), "roles")})

    @app.post("/api/staff/roles")
    def roles_change():
        b = request.get_json(silent=True) or {}
        try:
            with g["db"]() as con:
                if not may(con, pid(), "roles"):
                    return jsonify({"error": "Only the CEO can hand out roles."}), 403
                if b.get("remove"):
                    unassign(con, str(b.get("pilot_id", "")).upper(), b.get("role"))
                else:
                    assign(con, str(b.get("pilot_id", "")).upper(), b.get("role"), b.get("note", ""))
                return jsonify({"holders": holders(con)})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.get("/api/staff/statements")
    def statement_list():
        with g["db"]() as con:
            return jsonify({"months": statements(con, int(request.args.get("months", 6)))})
