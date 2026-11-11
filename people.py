"""People on board: the supernumeraries who travel with the freight.

Real freighters carry a few passengers who are there because of the cargo: grooms and a vet with racehorses,
an attendant with other live animals, a courier with valuables, and the engineers on an AOG recovery flight.
They appear on the load sheet (standard weights inside the payload) and react in the debrief when the arrival is rough.
"""
from __future__ import annotations

STANDARD_LBS = 200        # a standard adult with carry-on, as many operators use for supernumeraries

HORSE = ("racehorse", "horse", "thoroughbred", "equine", "show-jump", "polo pon")


def aboard(mission, codes=()):
    """Who flies with this cargo, as [{"role", "count", "why"}]. Empty for ordinary freight."""
    m = mission or {}
    text = " ".join(str(m.get(k) or "") for k in ("cargo", "title", "briefing", "urgent_kind")).lower()
    codes = {str(c).upper() for c in codes} | {str(c).upper() for c in (m.get("shc") or [])}
    out = []
    if (m.get("urgent_kind") or "").upper().startswith("AOG") or str(m.get("id", "")).startswith("PAC88") or m.get("aog"):
        out.append({"role": "Maintenance engineers", "count": 2, "why": "flying in with the parts to repair the grounded aircraft"})
    if any(w in text for w in HORSE):
        out.append({"role": "Grooms", "count": 2, "why": "caring for the horses in their stalls"})
        if "vet" in text:
            out.append({"role": "Veterinarian", "count": 1, "why": "travelling with the horses"})
    elif "AVI" in codes:
        out.append({"role": "Animal attendant", "count": 1, "why": "looking after the animals on board"})
    if "VAL" in codes:
        out.append({"role": "Security courier", "count": 1, "why": "escorting the valuable cargo"})
    return out


def total(people):
    return sum(p["count"] for p in people or [])


def summary(people):
    """'2 grooms, 1 veterinarian' for the load sheet."""
    parts = [f"{p['count']} {p['role'].lower()}" if p["count"] > 1 else ("an " if p["role"][0].lower() in "aeiou" else "a ") + p["role"].lower() for p in people or []]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1] if parts else ""


def debrief_note(people, rate=None, g=None, bounces=0):
    """What the people on board said about the ride, or None when nobody flew with the freight."""
    if not people:
        return None
    n = total(people)
    who = (people[0]["role"].lower() if n == 1 else summary(people))
    were = "was" if n == 1 else "were"
    rough = (rate is not None and rate <= -400) or (g or 0) > 1.8 or (bounces or 0) > 0
    hard = (rate is not None and rate <= -600) or (g or 0) >= 2.0
    if hard:
        return {"tone": "bad", "text": f"The {who} on board {were} badly shaken by the arrival"
                + (f" ({rate} fpm" + (f", {g:.2f} G" if g else "") + ")" if rate is not None else "")
                + ". They've asked the company to look into it before flying with PAC again."}
    if rough:
        return {"tone": "warn", "text": f"The {who} on board said the landing was firm"
                + (" and the aircraft bounced" if bounces else "") + ". Nobody was hurt, but they noticed."}
    return {"tone": "good", "text": f"The {who} on board thanked the crew for a smooth flight."}
