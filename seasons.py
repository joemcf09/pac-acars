"""Real air cargo seasons: the times of year when particular freight floods particular lanes.

Each season names where the freight comes from and goes to (ICAO prefixes, so "SK" is Colombia and "K" the
United States), what it is, and when it runs. While a season is on, PAC's forwarders book extra orders of that
freight on matching routes, the Cargo inventory shows it, and a news post announces it once a year.
"""
from __future__ import annotations

import datetime as dt

# window: (month, day) start and end, inclusive; a window may cross the new year
SEASONS = [
    {"id": "valentines", "name": "Valentine's flowers", "window": ((1, 18), (2, 12)),
     "from": ("SK", "SE", "HK"), "to": ("K", "E", "L", "C"), "cargo": "Fresh-cut flowers, roses and carnations",
     "blurb": "Colombia, Ecuador and Kenya ship hundreds of millions of roses in the weeks before February 14. Most fly into Miami and Amsterdam."},
    {"id": "mothers-day", "name": "Mother's Day flowers", "window": ((4, 18), (5, 8)),
     "from": ("SK", "SE", "HK"), "to": ("K", "C"), "cargo": "Fresh-cut flowers, roses and carnations",
     "blurb": "The second flower peak of the year, ahead of US Mother's Day."},
    {"id": "cherries", "name": "Chilean cherry season", "window": ((11, 20), (1, 31)),
     "from": ("SC",), "to": ("Z", "VH", "R", "W", "K"), "cargo": "Fresh cherries, chilled",
     "blurb": "Chile's cherries fly to China for the Lunar New Year, when red fruit is a lucky gift."},
    {"id": "beaujolais", "name": "Beaujolais Nouveau", "window": ((11, 1), (11, 20)),
     "from": ("LF", "ED", "EB"), "to": ("RJ", "RK", "VH", "K", "Z"), "cargo": "Beaujolais Nouveau wine, palletized",
     "blurb": "France releases the new vintage on the third Thursday of November, and Japan expects it on the day."},
    {"id": "peak", "name": "Holiday e-commerce peak", "window": ((11, 10), (12, 22)),
     "from": ("Z", "VH", "RC", "RK"), "to": ("K", "E", "L", "C"), "cargo": "E-commerce parcels",
     "blurb": "Black Friday to Christmas: online orders from Asia push air freight to its busiest weeks of the year."},
    {"id": "salmon", "name": "Christmas salmon", "window": ((11, 15), (12, 23)),
     "from": ("EN", "BI"), "to": ("Z", "VH", "RK", "RJ", "K"), "cargo": "Fresh salmon on ice",
     "blurb": "Norway's salmon exports peak before Christmas, much of it flown to Asia within a day of harvest."},
    {"id": "lunar", "name": "Lunar New Year fresh food", "window": ((1, 2), (2, 8)),
     "from": ("Y", "NZ", "K", "C", "E"), "to": ("Z", "VH", "RC", "W"), "cargo": "Fresh seafood, lobster and fruit",
     "blurb": "Lobster, crab and premium fruit fly into China and Southeast Asia for the New Year feasts."},
    {"id": "berries", "name": "Peruvian blueberries and asparagus", "window": ((9, 1), (12, 15)),
     "from": ("SP",), "to": ("K", "E", "L"), "cargo": "Blueberries and asparagus, chilled",
     "blurb": "Peru's growing season fills freighters north to the United States and Europe every autumn."},
    {"id": "phone-launch", "name": "New smartphone launch", "window": ((9, 8), (10, 5)),
     "from": ("Z", "VH", "VT", "VV"), "to": ("K", "E", "L", "OM", "C"), "cargo": "Consumer electronics, new smartphones",
     "blurb": "Launch day stock is flown, not shipped: whole freighters of new phones leave Asian factories each September."},
    {"id": "hurricane", "name": "Hurricane relief season", "window": ((8, 15), (10, 31)),
     "from": ("K",), "to": ("T", "M", "MY"), "cargo": "Humanitarian relief: water, generators and shelter kits",
     "blurb": "Atlantic storms leave islands cut off; relief freight flies out of Miami and Houston."},
]
BY_ID = {s["id"]: s for s in SEASONS}


def _md(d):
    return (d.month, d.day)


def is_on(season, day):
    (a, b) = season["window"]
    cur = _md(day)
    return a <= cur <= b if a <= b else (cur >= a or cur <= b)


def active(day=None):
    day = day or dt.datetime.utcnow().date()
    return [s for s in SEASONS if is_on(s, day)]


def starts(season, day=None):
    """The date this year's run of the season started (for once-a-year news)."""
    day = day or dt.datetime.utcnow().date()
    (a, b) = season["window"]
    year = day.year - 1 if a > b and _md(day) <= b else day.year
    return dt.date(year, *a)


def _match(icao, prefixes):
    icao = str(icao or "").upper()
    return any(icao.startswith(p) for p in prefixes)


def routes_for(season, routes):
    """PAC's scheduled routes that carry this season's freight."""
    return [r for r in routes if r.get("category") == "Scheduled"
            and _match((r.get("origin") or {}).get("icao"), season["from"])
            and _match((r.get("destination") or {}).get("icao"), season["to"])]
