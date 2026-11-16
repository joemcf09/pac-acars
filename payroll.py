"""Weekly base pay: a retainer every pilot earns for being on the PAC roster and flying that week.

Real cargo pilots draw a salary, not only per-flight pay. PAC mirrors that with a modest, rank-scaled weekly
base. It is activity-gated: a pilot must have flown at least one accepted leg during the week to collect, so idle
accounts never drain the treasury. Base pay is paid into the pilot wallet (kind 'base_pay') and, like every pilot
cost, shows up in the company profit-and-loss statement and comes out of the company (the CEO's) treasury.

Pay periods are ISO weeks (Monday 00:00 UTC to the next Monday). Each pilot is paid at most once per period; the
payroll_runs table records what was issued, so running the tick repeatedly is safe. The tick pays any complete
week in the recent lookback window that a pilot flew in and has not yet been paid for, so a quiet server that
misses a week still catches up without ever double-paying.
"""
from __future__ import annotations

import datetime as dt
import time

# Rank-scaled weekly retainer, USD. Deliberately modest next to flight pay so flying still clearly pays more.
WEEKLY_BASE = {"Cadet": 500, "Second Officer": 900, "First Officer": 1400,
               "Senior First Officer": 1900, "Captain": 2500, "Senior Captain": 3000}
DEFAULT_BASE = 500
LOOKBACK_WEEKS = 4


# Wallet transaction kinds, in friendly words for the pay statement. Positive kinds are earnings; negative
# amounts (jumpseat, shop, hotel, training travel, a negative adjustment) are deductions.
LABELS = {"flight_pay": "Flight pay", "profit_share": "Profit share", "skill_bonus": "Skill bonuses",
          "hazard_pay": "Hazard pay", "contract_bonus": "Contract bonus", "ferry_bonus": "Ferry bonus",
          "campaign": "Campaign rewards", "per_diem": "Per diem", "base_pay": "Weekly base pay",
          "gear_bonus": "Crew gear bonus", "mentoring": "Mentoring", "freight_delivered": "Freight delivered",
          "adjustment": "Adjustment", "jumpseat": "Jumpseat travel", "shop": "PAC shop", "hotel": "Crew hotel",
          "training_travel": "Training travel"}


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS payroll_runs (pilot_id TEXT, period TEXT, issued_at REAL, base REAL, rank TEXT,
        PRIMARY KEY (pilot_id, period))""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(payroll_runs)")}
    if "notified" not in cols:
        con.execute("ALTER TABLE payroll_runs ADD COLUMN notified INTEGER DEFAULT 0")
    if "dm_sent" not in cols:
        con.execute("ALTER TABLE payroll_runs ADD COLUMN dm_sent INTEGER DEFAULT 0")


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
    return paid


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
            AND kind!='base_pay' GROUP BY kind""", (pid, ws, we)):
        amt = round(r["a"], 2)
        if amt:
            (earn if amt > 0 else ded)[r["kind"]] = amt
    if base:
        earn["base_pay"] = round(earn.get("base_pay", 0) + base, 2)
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
