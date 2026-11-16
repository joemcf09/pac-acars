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


def migrate(con):
    con.execute("""CREATE TABLE IF NOT EXISTS payroll_runs (pilot_id TEXT, period TEXT, issued_at REAL, base REAL, rank TEXT,
        PRIMARY KEY (pilot_id, period))""")


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
