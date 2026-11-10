"""Runway wind analysis for the briefing: for each runway at an airport, the headwind (or tailwind) and crosswind
from the current METAR wind, gusts included, and which runway the wind favors.

METAR winds and the runway headings in runways.json are both true, so no magnetic variation is needed.
The limits flagged are common planning figures, not any one aircraft's: a tailwind over 10 kt and a crosswind over
30 kt (gusts included) say "check your aircraft's limits"; they never block a flight."""
from __future__ import annotations

import math

TAILWIND_LIMIT_KT = 10
CROSSWIND_LIMIT_KT = 30


def components(wind_dir, speed, runway_hdg):
    """(headwind, crosswind) in knots for one runway direction. Headwind < 0 is a tailwind; crosswind > 0 is from the right."""
    a = math.radians((wind_dir - runway_hdg + 540) % 360 - 180)
    return speed * math.cos(a), speed * math.sin(a)


def analyse(runways, wind, min_length_ft=0):
    """Every runway end, best first. `runways` is the airport's list from runways.json; `wind` the decoded METAR wind
    ({dir, spd, gust, vrb}). Returns {"calm": bool, "variable": bool, "ends": [...]} or None without wind or runways."""
    if not wind or not runways:
        return None
    spd, gust = wind.get("spd") or 0, wind.get("gust")
    ends = []
    for r in runways:
        length = r[10] or 0
        for ident, hdg in ((r[0], r[3]), (r[5], r[8])):
            if not ident or hdg is None:
                continue
            row = {"runway": str(ident), "heading": round(hdg), "length_ft": length, "short": bool(min_length_ft and length < min_length_ft)}
            if wind.get("vrb") or wind.get("dir") is None:
                row.update(head=None, cross=None, cross_side=None, gust_cross=None, gust_head=None)
            else:
                h, x = components(wind["dir"], spd, hdg)
                gh, gx = components(wind["dir"], gust, hdg) if gust else (h, x)
                row.update(head=round(h), cross=round(abs(x)), cross_side=("R" if x > 0 else "L") if round(abs(x)) else "",
                           gust_head=round(gh), gust_cross=round(abs(gx)))
            notes = []
            if row["head"] is not None and min(row["head"], row["gust_head"]) < -TAILWIND_LIMIT_KT:
                notes.append(f"tailwind over {TAILWIND_LIMIT_KT} kt")
            if row["gust_cross"] is not None and row["gust_cross"] > CROSSWIND_LIMIT_KT:
                notes.append(f"crosswind over {CROSSWIND_LIMIT_KT} kt")
            if row["short"]:
                notes.append("shorter than the aircraft needs")
            row["notes"] = notes
            ends.append(row)
    if not ends:
        return None
    calm = spd < 3 and not gust
    ends.sort(key=lambda e: (e["short"], bool(e["notes"]), -(e["head"] if e["head"] is not None else 0), -(e["length_ft"] or 0)))
    if not calm and not wind.get("vrb") and wind.get("dir") is not None and not ends[0]["notes"]:
        ends[0]["favored"] = True
    return {"calm": calm, "variable": bool(wind.get("vrb")), "wind": wind, "ends": ends}
