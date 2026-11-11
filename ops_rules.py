"""Real operating rules printed on the dispatch release: night curfews, slot-coordinated airports and ETOPS.
(Deicing is worked out on the release itself from the departure METAR.)

The lists are deliberately short and limited to well-known rules; each line says what it means for the flight."""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

# Airports that close to (or ban scheduled) jet movements at night: (local start, local end, time zone, note)
CURFEWS = {
    "EDDF": ("2300", "0500", "Europe/Berlin", "no scheduled movements"),
    "LSZH": ("2300", "0600", "Europe/Zurich", "no scheduled movements; delayed flights until 2330 only"),
    "YSSY": ("2300", "0600", "Australia/Sydney", "curfew: no jet movements"),
    "LFPO": ("2330", "0600", "Europe/Paris", "curfew: no movements"),
    "RJAA": ("0000", "0600", "Asia/Tokyo", "airport closed"),
    "EDDB": ("0000", "0500", "Europe/Berlin", "core night ban"),
}
# Fully coordinated (IATA Level 3) airports that PAC serves: a slot is required and must be kept.
SLOT_AIRPORTS = {"EGLL", "EGKK", "EHAM", "EDDF", "EDDM", "LFPG", "LFPO", "LSZH", "LEMD", "LIRF", "RJTT", "RJAA", "RKSI", "VHHH",
                 "WSSS", "ZSPD", "ZBAA", "ZGGG", "OMDB", "YSSY", "KJFK", "KLGA"}
# Two-engine freighters. Three- and four-engine all-cargo aircraft are exempt from ETOPS in US rules.
TWINS = {"B732F", "B733F", "B738F", "B752F", "B763F", "A306F", "B77F"}
ONE_ENGINE_KT = 400          # a typical one-engine-inoperative cruise speed for planning
ADEQUATE_RWY_FT = 6500


def _hm(s):
    return int(s[:2]) * 60 + int(s[2:4])


def _inside(local_min, start, end):
    a, b = _hm(start), _hm(end)
    return a <= local_min < b if a < b else (local_min >= a or local_min < b)


def _when(date_str, hhmmz):
    try:
        day = dt.datetime.strptime(date_str, "%d %b %Y")
        return day.replace(hour=int(hhmmz[:2]), minute=int(hhmmz[2:4]), tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def curfew(icao, utc):
    c = CURFEWS.get(icao)
    if not c:
        return None
    start, end, tz, note = c
    out = {"icao": icao, "start": start, "end": end, "note": note, "inside": None, "local": None}
    if utc:
        loc = utc.astimezone(ZoneInfo(tz))
        out["local"] = loc.strftime("%H%M")
        out["inside"] = _inside(loc.hour * 60 + loc.minute, start, end)
    return out


def _dist(a1, o1, a2, o2):
    p1, p2, dl = math.radians(a1), math.radians(a2), math.radians(o2 - o1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.acos(max(-1, min(1, c)))) * 60


def _gc_points(a, b, step_nm=60):
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    d = _dist(a[0], a[1], b[0], b[1])
    n = max(1, int(d // step_nm))
    D = math.radians(d / 60)
    if D == 0:
        return [a]
    pts = []
    for i in range(n + 1):
        f = i / n
        A, B = math.sin((1 - f) * D) / math.sin(D), math.sin(f * D) / math.sin(D)
        x = A * math.cos(la1) * math.cos(lo1) + B * math.cos(la2) * math.cos(lo2)
        y = A * math.cos(la1) * math.sin(lo1) + B * math.cos(la2) * math.sin(lo2)
        z = A * math.sin(la1) + B * math.sin(la2)
        pts.append((math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))))
    return pts


def etops(aircraft, origin, dest, airports):
    """For twins: the farthest the great-circle route gets from an adequate airport, and the ETOPS time that needs."""
    if aircraft not in TWINS or not airports:
        return None
    o, d = airports.get(origin) or {}, airports.get(dest) or {}
    if o.get("lat") is None or d.get("lat") is None:
        return None
    adequate = [(a["lat"], a["lon"]) for a in airports.values() if (a.get("rwy_ft") or 0) >= ADEQUATE_RWY_FT and a.get("lat") is not None]
    worst = 0
    for la, lo in _gc_points((o["lat"], o["lon"]), (d["lat"], d["lon"])):
        best = min((_dist(la, lo, a, b) for a, b in adequate if abs(a - la) < 12), default=None)
        if best is None:
            best = min(_dist(la, lo, a, b) for a, b in adequate)
        worst = max(worst, best)
    minutes = worst / ONE_ENGINE_KT * 60
    if minutes <= 60:
        return {"required": False, "max_nm": round(worst), "minutes": round(minutes)}
    level = next((x for x in (120, 180, 207) if minutes <= x), None)
    return {"required": True, "max_nm": round(worst), "minutes": round(minutes), "level": level}


def rules(d, airports=None):
    """Release lines for this flight: [{"kind", "text"}] in plain release wording."""
    out = []
    dep, arr = (d.get("origin") or {}).get("icao"), (d.get("destination") or {}).get("icao")
    std, sta = _when(d.get("date"), d.get("std")), _when(d.get("date"), d.get("sta"))
    if std and sta and sta < std:
        sta += dt.timedelta(days=1)
    for icao, when, what in ((dep, std, "DEPARTURE"), (arr, sta, "ARRIVAL")):
        c = curfew(icao, when)
        if c:
            txt = f"{icao} NIGHT CURFEW {c['start']}-{c['end']} LOCAL ({c['note'].upper()})."
            if c["inside"]:
                txt += f" PLANNED {what} {c['local']} LOCAL IS INSIDE THE CURFEW: RETIME THE FLIGHT OR EXPECT IT NOT TO OPERATE."
            elif c["local"]:
                txt += f" PLANNED {what} {c['local']} LOCAL. A LATE {what} COULD RUN INTO IT."
            out.append({"kind": "curfew", "text": txt, "warn": bool(c["inside"])})
    for icao in (dep, arr):
        if icao in SLOT_AIRPORTS:
            out.append({"kind": "slot", "text": f"{icao} IS SLOT COORDINATED (IATA LEVEL 3). OPERATE TO YOUR SLOT: BLOCK TIMES WITHIN 15 MIN OF SCHEDULE.", "warn": False})
    e = etops(d.get("aircraft"), dep, arr, airports)
    if e and e["required"]:
        lvl = f"ETOPS {e['level']}" if e["level"] else "BEYOND ETOPS 207"
        out.append({"kind": "etops", "warn": not e["level"],
                    "text": f"{lvl} REQUIRED: ROUTE REACHES {e['max_nm']} NM ({e['minutes']} MIN ONE ENGINE) FROM AN ADEQUATE AIRPORT. "
                            "PLAN ETOPS ALTERNATES AND THE CRITICAL FUEL SCENARIO." + ("" if e["level"] else " NOT APPROVED FOR PAC: REPLAN.")})
    return out
