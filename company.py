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
    "creative": ("Creative / Media Director", "Screenshots, promo graphics and social media; site announcements and company NOTAMs; promoting PAC on forums and social channels"),
    "livery_mgr": ("Livery Manager", "The PAC livery library and paint kits, across MSFS and X-Plane"),
    "hub_mgr": ("Hub Manager", "A hub's station report, backlog and regular pilots"),
    "academy_director": ("Academy Director", "Build and publish PAC Academy courses, lessons and training resources"),
}
# which roles may do what (the CEO can always do everything)
CAN = {"ceo_desk": {"ceo"}, "fleet_market": {"ceo", "fleet_mgr"}, "complaints": {"ceo", "commercial"}, "roles": {"ceo"}}

# ---------------------------------------------------------------------------
# Scoped staff access.
#
# The staff area is otherwise all-or-nothing: an account is either full admin
# (pilots.staff = 1, the owner) or a pilot with no staff access at all. SCOPE
# carves out a few narrow, non-sensitive sections a role-holder may reach
# WITHOUT being made a full admin. Each capability lists the roles that grant
# it and the first path segment(s) under /api/staff/ that it covers.
#
# DEFAULT-DENY: anything not named here stays full-admin only — Settings, every
# key (mail/Discord/Hoppie), backups, pilot records, wallets, finances, the CEO
# desk, role assignment and the monolithic /api/staff/overview feed. A scoped
# role never receives that feed, so pilot records and money cannot leak through
# it. Add a capability here only once its section has been carved out and
# tested. Built incrementally, one clean role at a time.
SCOPE = {
    "liveries": {"roles": {"livery_mgr"}, "paths": ("liveries",)},
    "creative": {"roles": {"creative"}, "paths": ("partner-photos", "news")},
    "commercial": {"roles": {"commercial"}, "paths": ("complaints", "accounts", "lanes", "featured-shipments")},
    "fleet": {"roles": {"fleet_mgr"}, "paths": ("fleet-types", "airframes", "maintenance", "fleet-recs", "fleet-catalog")},
    "operations": {"roles": {"dir_ops"}, "paths": ("cargo-campaigns", "events", "relief")},
    "academy": {"roles": {"academy_director"}, "paths": ("academy",)},
    # The fleet MARKET itself (buying/leasing, which spends company cash) stays full-admin only, so a
    # Fleet Manager can browse the catalog (fleet-catalog, no cash shown) and file recommendations
    # (fleet-recs), but only the owner approves them, which executes the order under /api/staff/market/rec.
}


def _staff_tail(path):
    """'/api/staff/liveries/ab12' -> 'liveries/ab12'; '' for any non-staff path."""
    marker = "/api/staff/"
    return path[len(marker):] if path.startswith(marker) else ""


def capability_for(path):
    """Which scoped capability, if any, guards this /api/staff/ path.
    None means the path is not scoped and stays full-admin only (default-deny)."""
    tail = _staff_tail(path)
    if not tail:
        return None
    head = tail.split("/", 1)[0].split("?", 1)[0]
    for cap, spec in SCOPE.items():
        if head in spec["paths"]:
            return cap
    return None


def caps_of(con, pid):
    """The scoped capabilities a pilot's roles grant (empty for a plain pilot)."""
    mine = roles_of(con, pid)
    return sorted(cap for cap, spec in SCOPE.items() if mine & spec["roles"])


def may_path(con, pid, path):
    """True only if this pilot's roles grant scoped access to this /api/staff/ path.
    Full admins are handled by the gatekeeper before this is ever consulted."""
    cap = capability_for(path)
    return bool(cap) and cap in caps_of(con, pid)


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
               "wet_lease": "Wet leases (ACMI)", "goodwill": "Customer goodwill", "insurance": "Insurance premiums", "insurance_settlement": "Insurance settlements", "hotel": "Crew hotels", "exec_travel": "Executive travel", "hub_opening": "New hub setup", "hub_station": "Hub station costs", "aircraft_sale": "Aircraft sales", "other": "Other"}
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
    for r in con.execute("SELECT time, kind, amount FROM wallet WHERE kind IN ('per_diem','profit_share','campaign','base_pay','role_stipend')"):
        lbl = {"per_diem": "Per diem", "profit_share": "Pilot profit share", "campaign": "Campaign rewards", "base_pay": "Pilot base pay", "role_stipend": "Staff stipends"}[r[1]]
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
        import payroll
        with g["db"]() as con:
            return jsonify({"roles": [{"key": k, "title": v[0], "does": v[1], "pay": payroll.ROLE_STIPEND.get(k, 0)} for k, v in ROLES.items()],
                            "holders": holders(con), "mine": sorted(roles_of(con, pid())), "can_assign": may(con, pid(), "roles")})

    @app.post("/api/staff/roles")
    def roles_change():
        b = request.get_json(silent=True)
        b = b if isinstance(b, dict) else {}
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
