"""The Grand Prix flyaway calendar: valid rounds, and the right leg appears in the days after each race.
Mirrors the windowing rule in va._race_flyaway_leg (freight flies 1-4 days after a race to the next circuit).
Run from the PAC folder: python tests/test_race_calendar.py"""
import datetime as dt
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import missiongen as MG  # noqa: E402

failures = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else "  FAIL ") + name + ("" if cond else f" · {detail}"))
    if not cond:
        failures.append(name)


def leg(today):
    """Same rule as va._race_flyaway_leg."""
    cal = MG.RACE_CALENDAR
    for i in range(len(cal) - 1):
        mo, day, oc = cal[i]
        race = dt.date(today.year, mo, day)
        if race < today <= race + dt.timedelta(days=4):
            return oc, cal[i + 1][2]
    return None


cal = MG.RACE_CALENDAR
check("the calendar has a full season of rounds", len(cal) >= 10, len(cal))
check("every round has a valid month, day and 4-letter ICAO",
      all(1 <= mo <= 12 and 1 <= day <= 31 and isinstance(ic, str) and len(ic) == 4 for mo, day, ic in cal))
dates = [dt.date(2026, mo, day) for mo, day, _ in cal]
check("rounds are in calendar order", dates == sorted(dates), dates)
check("no two rounds share a date", len(set(dates)) == len(dates))

# the leg appears in the window after a race, routing to the next round's circuit
check("two days after round 1, the leg runs to round 2",
      leg(dt.date(2026, cal[0][0], cal[0][1]) + dt.timedelta(days=2)) == (cal[0][2], cal[1][2]))
check("on race day there is no leg yet", leg(dt.date(2026, cal[0][0], cal[0][1])) is None)
check("five days after a race the window has closed",
      leg(dt.date(2026, cal[0][0], cal[0][1]) + dt.timedelta(days=5)) is None)
check("after the final round there is no leg (no next circuit)",
      leg(dt.date(2026, cal[-1][0], cal[-1][1]) + dt.timedelta(days=2)) is None)
check("off-season (February) has no leg", leg(dt.date(2026, 2, 1)) is None)

print("\nRACE CALENDAR TEST " + ("PASSED" if not failures else f"FAILED: {failures}"))
sys.exit(1 if failures else 0)
