"""Weekly base pay: a retainer every pilot earns for being on the PAC roster and flying that week.

Real cargo pilots draw a salary, not only per-flight pay. PAC mirrors that with a modest, rank-scaled weekly
base. It is activity-gated: a pilot must have flown at least one accepted leg during the week to collect, so idle
accounts never drain the treasury. Base pay is paid into the pilot wallet (kind 'base_pay') and, like every pilot
cost, shows up in the company profit-and-loss statement and comes out of the company (the CEO's) treasury.

Pay periods are ISO weeks (Monday 00:00 UTC to the next Monday). Each pilot is paid at most once per period; the
payroll_runs table records what was issued, so running the tick repeatedly is safe. The tick pays any complete
week in the recent lookback window that a pilot flew in and has not yet been paid for, so a quiet server that
misses a week still catches up without ever double-paying.

Staff who hold a management role also draw a weekly stipend (ROLE_STIPEND), on top of flight and base pay, for as
long as they hold the role, out of the treasury and rank-independent. It is tracked in role_pay_runs and shows as
its own pay-statement line.
"""
from __future__ import annotations

import datetime as dt
import time

# Rank-scaled weekly retainer, USD. Deliberately modest next to flight pay so flying still clearly pays more.
WEEKLY_BASE = {"Cadet": 500, "Second Officer": 900, "First Officer": 1400,
               "Senior First Officer": 1900, "Captain": 2500, "Senior Captain": 3000}
DEFAULT_BASE = 500
LOOKBACK_WEEKS = 4

# Weekly staff stipend, USD, paid on top of flight and base pay to whoever holds the role, out of the treasury,
# for as long as they hold it (rank-independent: it pays for the job, not the rank). Keys match company.ROLES.
# The owner's CEO role draws nothing. Tune these freely.
ROLE_STIPEND = {"ceo": 0, "chief_pilot": 2500, "dir_ops": 2500, "fleet_mgr": 2500, "commercial": 2500,
                "creative": 1500, "livery_mgr": 1500, "hub_mgr": 1500}


# Wallet transaction kinds, in friendly words for the pay statement. Positive kinds are earnings; negative
# amounts (jumpseat, shop, hotel, training travel, a negative adjustment) are deductions.
LABELS = {"flight_pay": "Flight pay", "profit_share": "Profit share", "skill_bonus": "Skill bonuses",
          "hazard_pay": "Hazard pay", "contract_bonus": "Contract bonus", "ferry_bonus": "Ferry bonus",
          "campaign": "Campaign rewards", "per_diem": "Per diem", "base_pay": "Weekly base pay",
          "gear_bonus": "Crew gear bonus", "mentoring": "Mentoring", "freight_delivered": "Freight delivered",
          "role_stipend": "Staff stipend", "adjustment": "Adjustment", "jumpseat": "Jumpseat travel",
          "shop": "PAC shop", "hotel": "Crew hotel", "training_travel": "Training travel"}
# A pay statement is about pay. These are the pilot's own wallet spending, not payroll, so they stay in the wallet
# ledger and off the paycheck: the statement shows what PAC paid, and net pay never dips because someone went shopping.
SPENDING = {"shop", "jumpseat", "hotel", "training_travel"}


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS payroll_runs (pilot_id TEXT, period TEXT, issued_at REAL, base REAL, rank TEXT,
        PRIMARY KEY (pilot_id, period))""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(payroll_runs)")}
    if "notified" not in cols:
        con.execute("ALTER TABLE payroll_runs ADD COLUMN notified INTEGER DEFAULT 0")
    if "dm_sent" not in cols:
        con.execute("ALTER TABLE payroll_runs ADD COLUMN dm_sent INTEGER DEFAULT 0")
    con.execute("""CREATE TABLE IF NOT EXISTS role_pay_runs (pilot_id TEXT, role TEXT, period TEXT, issued_at REAL, amount REAL,
        PRIMARY KEY (pilot_id, role, period))""")


def _monday(d):
    return d - dt.timedelta(days=d.weekday())


def _epoch(d):
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()


def period_key(start_date):
    return start_date.strftime("%G-W%V")


def period_label(start_date):
    end = start_date + dt.timedelta(days=6)
    return f"{start_date.strftime('%b %d')} to {end.strftime('%b %d, %Y')}"


def recent_periods(now, weeks=LOOKBACK_WEEKS):
    """The most recent completed ISO weeks, oldest first. The current (incomplete) week is excluded."""
    today = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
    this_monday = _monday(today)
    out = []
    for i in range(weeks, 0, -1):
        start = this_monday - dt.timedelta(weeks=i)
        end = start + dt.timedelta(weeks=1)
        out.append((period_key(start), start, end))
    return out


def tick(con, add_tx, rank_of, now=None):
    """Issue base pay for any recent complete week each active pilot has not yet been paid for. Returns the list
    of payments made this run: dicts with pilot_id, period, base, rank, period_start/period_end (epoch), period_label."""
    now = now or time.time()
    migrate(con)
    paid = []
    for key, start, end in recent_periods(now):
        ws, we = _epoch(start), _epoch(end)
        active = [r[0] for r in con.execute(
            "SELECT DISTINCT pilot_id FROM pireps WHERE demo=0 AND review_status='Accepted' AND filed_at>=? AND filed_at<?",
            (ws, we))]
        for pid in active:
            if not pid or con.execute("SELECT 1 FROM payroll_runs WHERE pilot_id=? AND period=?", (pid, key)).fetchone():
                continue
            try:
                rank = rank_of(pid, con) or "Cadet"
            except Exception:
                rank = "Cadet"
            base = WEEKLY_BASE.get(rank, DEFAULT_BASE)
            desc = f"Weekly base pay ({rank}) for {period_label(start)}"
            add_tx(pid, "base_pay", base, desc, None, con)
            con.execute("INSERT OR IGNORE INTO payroll_runs (pilot_id, period, issued_at, base, rank) VALUES (?,?,?,?,?)",
                        (pid, key, now, base, rank))
            paid.append({"pilot_id": pid, "period": key, "base": base, "rank": rank,
                         "period_start": ws, "period_end": we, "period_label": period_label(start)})
    _pay_role_stipends(con, add_tx, rank_of, now)
    coalesce_notices(con)
    return paid


def _pay_role_stipends(con, add_tx, rank_of, now):
    """Pay each staff role-holder their weekly stipend for any recent complete week they held the role, out of the
    treasury, rank-independent. A stipend-only staffer (held the role but didn't fly that week) still gets a pay
    run so the paycheck notice and statement fire. Idempotent per pilot, role and period."""
    import company
    try:
        holders = con.execute("SELECT pilot_id, role, since FROM roles").fetchall()
    except Exception:
        return
    for key, start, end in recent_periods(now):
        we = _epoch(end)
        for h in holders:
            pid, role, since = h[0], h[1], (h[2] or 0)
            amt = ROLE_STIPEND.get(role, 0)
            if not pid or amt <= 0 or since >= we:          # not held by the end of that completed week: no back-pay
                continue
            if con.execute("SELECT 1 FROM role_pay_runs WHERE pilot_id=? AND role=? AND period=?", (pid, role, key)).fetchone():
                continue
            title = company.ROLES.get(role, (role,))[0]
            add_tx(pid, "role_stipend", amt, f"{title} stipend for {period_label(start)}", None, con)
            con.execute("INSERT OR IGNORE INTO role_pay_runs (pilot_id, role, period, issued_at, amount) VALUES (?,?,?,?,?)",
                        (pid, role, key, now, amt))
            if not con.execute("SELECT 1 FROM payroll_runs WHERE pilot_id=? AND period=?", (pid, key)).fetchone():
                try:
                    rank = rank_of(pid, con) or "Cadet"
                except Exception:
                    rank = "Cadet"
                con.execute("INSERT OR IGNORE INTO payroll_runs (pilot_id, period, issued_at, base, rank, notified, dm_sent) VALUES (?,?,?,0,?,0,0)",
                            (pid, key, now, rank))


def coalesce_notices(con):
    """A catch-up should ping a pilot once, for their latest paycheck, not once per backfilled week. Mark every
    run except each pilot's most recent as already notified and DMed, so only the newest paycheck announces itself.
    The pay itself is untouched: all the base payments stay in the wallet and the P&L; this only collapses the
    notifications. Runs each tick, so a quiet server that backfills several weeks still pings only once."""
    migrate(con)
    con.execute("""UPDATE payroll_runs SET notified=1 WHERE notified=0 AND period < (
        SELECT MAX(period) FROM payroll_runs p2 WHERE p2.pilot_id=payroll_runs.pilot_id)""")
    con.execute("""UPDATE payroll_runs SET dm_sent=1 WHERE dm_sent=0 AND period < (
        SELECT MAX(period) FROM payroll_runs p2 WHERE p2.pilot_id=payroll_runs.pilot_id)""")


def _period_bounds(key):
    y, w = key.split("-W")
    start = dt.date.fromisocalendar(int(y), int(w), 1)
    return start, _epoch(start), _epoch(start + dt.timedelta(weeks=1))


def _label(kind):
    return LABELS.get(kind, kind.replace("_", " ").capitalize())


def statement(con, pid, period=None, now=None):
    """The pilot's pay statement for a pay period: earnings by category, deductions, net, and the week's flying.
    Base pay is read from payroll_runs (it is issued after the week closes); everything else is summed from the
    wallet entries dated inside the week."""
    now = now or time.time()
    migrate(con)
    if not period:
        row = con.execute("SELECT period FROM payroll_runs WHERE pilot_id=? ORDER BY period DESC LIMIT 1", (pid,)).fetchone()
        period = row[0] if row else recent_periods(now)[-1][0]
    start, ws, we = _period_bounds(period)
    run = con.execute("SELECT base, rank, issued_at FROM payroll_runs WHERE pilot_id=? AND period=?", (pid, period)).fetchone()
    base = (run["base"] if run else 0) or 0
    earn, ded = {}, {}
    for r in con.execute("""SELECT kind, COALESCE(SUM(amount),0) a FROM wallet WHERE pilot_id=? AND time>=? AND time<?
            AND kind NOT IN ('base_pay','role_stipend') GROUP BY kind""", (pid, ws, we)):
        if r["kind"] in SPENDING:          # the pilot's own wallet spending is not pay: keep it off the paycheck
            continue
        amt = round(r["a"], 2)
        if amt:
            (earn if amt > 0 else ded)[r["kind"]] = amt
    if base:
        earn["base_pay"] = round(earn.get("base_pay", 0) + base, 2)
    stip = con.execute("SELECT COALESCE(SUM(amount),0) FROM role_pay_runs WHERE pilot_id=? AND period=?", (pid, period)).fetchone()[0] or 0
    if stip:            # staff stipend is issued after the week closes, like base pay, so read it from its run table
        earn["role_stipend"] = round(earn.get("role_stipend", 0) + stip, 2)
    lines = [{"kind": k, "label": _label(k), "amount": v} for k, v in sorted(earn.items(), key=lambda kv: -kv[1])]
    deductions = [{"kind": k, "label": _label(k), "amount": v} for k, v in sorted(ded.items(), key=lambda kv: kv[1])]
    gross = round(sum(earn.values()), 2)
    ded_total = round(sum(ded.values()), 2)
    fl = con.execute("""SELECT COUNT(*) c, COALESCE(SUM(block_min),0) b FROM pireps WHERE pilot_id=? AND demo=0
            AND review_status='Accepted' AND filed_at>=? AND filed_at<?""", (pid, ws, we)).fetchone()
    bal = con.execute("SELECT COALESCE(SUM(amount),0) FROM wallet WHERE pilot_id=?", (pid,)).fetchone()[0]
    return {"period": period, "period_label": period_label(start), "period_start": ws, "period_end": we,
            "rank": run["rank"] if run else None, "base": round(base, 2), "issued_at": run["issued_at"] if run else None,
            "lines": lines, "deductions": deductions, "gross": gross, "deductions_total": ded_total,
            "net": round(gross + ded_total, 2), "flights": fl["c"], "block_hours": round((fl["b"] or 0) / 60, 1),
            "balance": round(bal, 2)}


def periods_for(con, pid, limit=26):
    """The pilot's recent pay periods, newest first, each a full statement summary."""
    migrate(con)
    keys = [r[0] for r in con.execute(
        "SELECT period FROM payroll_runs WHERE pilot_id=? ORDER BY period DESC LIMIT ?", (pid, limit))]
    return [statement(con, pid, k) for k in keys]


def pending_site(con, pid, now=None):
    """The most recent pay period this pilot has not yet seen a site notification for, or None."""
    migrate(con)
    row = con.execute("SELECT period FROM payroll_runs WHERE pilot_id=? AND notified=0 ORDER BY period DESC LIMIT 1",
                      (pid,)).fetchone()
    if not row:
        return None
    s = statement(con, pid, row[0], now)
    return {"period": s["period"], "period_label": s["period_label"], "net": s["net"], "gross": s["gross"]}


def mark_notified(con, pid, period):
    migrate(con)
    con.execute("UPDATE payroll_runs SET notified=1 WHERE pilot_id=? AND period=?", (pid, period))


def dm_due(con, site, now=None):
    """Pay statements to announce by Discord DM (one per pilot per period), for pilots who have linked Discord."""
    migrate(con)
    out = []
    for r in con.execute("""SELECT pr.pilot_id, pr.period, p.discord_id, p.name FROM payroll_runs pr
            JOIN pilots p ON p.id=pr.pilot_id
            WHERE pr.dm_sent=0 AND p.discord_id IS NOT NULL AND p.discord_id!='' ORDER BY pr.period"""):
        s = statement(con, r["pilot_id"], r["period"], now)
        who = (r["name"] or r["pilot_id"]).split()[0]
        text = (f"\U0001F4B0 You've been paid, {who}! Your PAC pay statement for {s['period_label']} is ready: "
                f"${s['net']:,.0f} net from {s['flights']} flight(s) this period. "
                f"See the full breakdown on the PAC site: {site}/#career/wallet")
        out.append({"src": "paystub", "discord_id": r["discord_id"], "pilot_id": r["pilot_id"], "period": r["period"],
                    "period_label": s["period_label"], "amount": s["net"], "text": text})
    return out


def mark_dmed(con, items):
    migrate(con)
    for it in items or []:
        if it.get("src") == "paystub" and it.get("pilot_id") and it.get("period"):
            con.execute("UPDATE payroll_runs SET dm_sent=1 WHERE pilot_id=? AND period=?",
                        (it["pilot_id"], it["period"]))
