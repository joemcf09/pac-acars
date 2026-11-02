"""Gives every one-way route in the scheduled network a return leg.

    .venv/bin/python tools/add_return_routes.py --dry-run     see what it would add
    .venv/bin/python tools/add_return_routes.py               write it

Why: a station with arrivals and no departures strands whoever lands there.
PAC's rule is that pilots fly from where they are, so a dead-end station
quietly ends a pilot's evening — and often their membership.

This only ADDS routes. Existing entries are never edited or renumbered, so
flight numbers already in logbooks, bookings and PIREPs keep meaning what
they meant. The file is backed up before anything is written.

The return leg mirrors its outbound: same aircraft, distance, block time,
payload and reward, with origin and destination swapped and a new flight
number. Cargo is re-cut so the return isn't a carbon copy of the outbound.
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "data" / "routes.json"

# What comes back the other way. A return leg carrying the identical freight
# reads as a copy; these are picked by the outbound's cargo so the pairing
# makes sense rather than being random.
RETURN_CARGO = {
    "Overnight express parcels": "Returns, empty ULDs and overnight parcels",
    "E-commerce parcels": "Returns and e-commerce overflow",
    "Express parcels": "Returns and express parcels",
    "Domestic express freight": "Domestic express freight and empty ULDs",
    "Express freight and road-feeder overflow": "Road-feeder overflow and empty ULDs",
    "General cargo": "General cargo and empty containers",
    "Island resupply": "Outbound produce and empty containers",
    "Pharmaceuticals": "Cold-chain returns and general freight",
    "Semiconductors": "Production line parts and general freight",
    "Automotive parts": "Automotive parts and empty racks",
    "Consumer goods": "Consumer goods and empty ULDs",
}
DEFAULT_RETURN_CARGO = "General cargo and empty ULDs"


def icao(place):
    return place.get("icao") if isinstance(place, dict) else place


def city(place):
    if not isinstance(place, dict):
        return str(place)
    return place.get("city") or place.get("name") or place.get("icao")


def next_ids(routes):
    """Flight numbers that don't collide with anything already in use."""
    used = {int(m.group()) for r in routes if (m := re.search(r"\d+", str(r.get("id", ""))))}
    n = max(used) + 1 if used else 1001
    while True:
        while n in used:
            n += 1
        used.add(n)
        yield f"PAC{n}"


def rewrite_briefing(text, a, b):
    """The generated briefing names the sector's distance, load and runway —
    all symmetric — so only the city names need swapping."""
    if not text:
        return text
    return text.replace(city(a), "<<A>>").replace(city(b), city(a)).replace("<<A>>", city(b))


def mirror(r, new_id):
    out = dict(r)
    out["id"] = new_id
    out["origin"], out["destination"] = r["destination"], r["origin"]
    out["title"] = f"{city(r['destination'])} to {city(r['origin'])}"
    out["cargo"] = RETURN_CARGO.get(r.get("cargo", ""), DEFAULT_RETURN_CARGO)
    out["briefing"] = rewrite_briefing(r.get("briefing", ""), r["origin"], r["destination"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", default=str(ROUTES))
    a = ap.parse_args()
    path = Path(a.file)

    routes = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(routes, list):
        sys.exit(f"{path} isn't a list of routes.")

    pairs = {(icao(r["origin"]), icao(r["destination"])) for r in routes}
    oneway = [r for r in routes
              if (icao(r["destination"]), icao(r["origin"])) not in pairs]

    ids = next_ids(routes)
    added = [mirror(r, next(ids)) for r in oneway]

    # what this fixes
    departs = {icao(r["origin"]) for r in routes}
    arrives = {icao(r["destination"]) for r in routes}
    dead_before = arrives - departs
    departs_after = departs | {icao(r["origin"]) for r in added}
    dead_after = (arrives | {icao(r["destination"]) for r in added}) - departs_after

    print(f"routes now            : {len(routes):,}")
    print(f"one-way, no return    : {len(oneway):,}")
    print(f"return legs to add    : {len(added):,}")
    print(f"routes after          : {len(routes) + len(added):,}")
    print(f"dead-end stations     : {len(dead_before)} -> {len(dead_after)}")

    print("\nexamples:")
    for r in added[:5]:
        o, d = icao(r["origin"]), icao(r["destination"])
        print(f"  {r['id']}  {o} -> {d}  {r['distance_nm']:,} nm  {r['cargo']}")

    if a.dry_run:
        print("\nDry run. Nothing was written.")
        return

    backup = path.with_suffix(f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    path.write_text(json.dumps(routes + added, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nBacked up to {backup.name}")
    print(f"Wrote {len(routes) + len(added):,} routes. Restart PAC to pick them up.")


if __name__ == "__main__":
    main()
