"""Conflict zones: airspace a US cargo carrier like PAC wouldn't fly into or over.

Two levels, set per zone by staff (Staff > Site and rules > Conflict zones):
  restricted  the flight stays visible and bookable, but it isn't authorized: a flight that departs from, lands in or
              is planned to a restricted country is rejected automatically (no pay, points or hours). A flight whose
              track crosses a restricted country is flagged for staff review instead, because the outlines are
              approximate near borders and coasts.
  caution     flights to, from or across the zone are allowed and earn hazard pay (a % of flight pay).

The whole feature sits behind one switch (conflict_zones_enabled, off by default). The defaults follow the FAA's
prohibitions and advisories for US operators, and Russia, which is closed to US carriers. Real-world rules change,
so staff can move any zone between restricted, caution and off.

Country outlines (data/conflict_zones_shapes.json) are Natural Earth 1:50m, public domain, rounded to 0.05 degrees.
They cover land only, so airspace over the sea next to a country isn't checked.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# id: (name, ICAO airport prefixes, default level, default hazard pay %, note)
DEFAULT_ZONES = {
    "russia": ("Russia", ("UU", "UL", "UR", "US", "UW", "UN", "UI", "UH", "UE", "UO"), "restricted", 15,
               "Closed to US airlines since 2022: the US banned Russian aircraft, and Russia closed its airspace to US carriers in return. Includes Kaliningrad and occupied Crimea."),
    "ukraine": ("Ukraine", ("UK",), "restricted", 15, "Active war zone since 2022. Civil flights are banned over the whole country, with risk from missiles, drones and air defense."),
    "belarus": ("Belarus", ("UM",), "restricted", 15, "US carriers are banned from Belarusian airspace, partly over its support for the war in Ukraine."),
    "syria": ("Syria", ("OS",), "restricted", 15, "Ongoing conflict and military activity, with a risk of misidentification by air defense. US carriers are prohibited."),
    "libya": ("Libya", ("HL",), "restricted", 15, "Unstable, with armed groups and anti-aircraft weapons. US carriers are prohibited."),
    "yemen": ("Yemen", ("OY",), "restricted", 15, "Civil war, with missiles and drones launched across the region. US carriers are prohibited."),
    "iran": ("Iran", ("OI",), "restricted", 15, "US carriers are prohibited after regional military escalation and the risk of misidentification, as in the 2020 shoot-down of a passenger jet near Tehran."),
    "afghanistan": ("Afghanistan", ("OA",), "restricted", 15, "Taliban control, no reliable air traffic services and anti-aircraft weapons. US carriers are prohibited."),
    "north_korea": ("North Korea", ("ZK",), "restricted", 15, "Unannounced missile launches with no warning to aircraft. US carriers are prohibited."),
    "sudan": ("Sudan", ("HS",), "restricted", 15, "Civil war since 2023. Khartoum airport was heavily damaged in the fighting. US carriers are prohibited."),
    "somalia": ("Somalia", ("HC",), "caution", 15, "Armed groups with weapons that can reach low-flying aircraft. US carriers are restricted at lower levels."),
    "iraq": ("Iraq", ("OR",), "restricted", 15, "Regional conflict advisories warn of missile and drone activity and the risk of misidentification. PAC treats it as restricted."),
    "israel": ("Israel and the Palestinian territories", ("LL", "LV"), "caution", 15, "Rockets and drones in the area. Flights operate, but airlines regularly suspend service at short notice."),
    "lebanon": ("Lebanon", ("OL",), "restricted", 15, "Rocket, drone and air-strike activity near the Israel border. PAC treats it as restricted."),
    "persian_gulf": ("Persian Gulf waters", (), "caution", 10, "Gulf and Strait of Hormuz. Our Dubai hub stays fully open."),
    "saudi_south": ("Southern Saudi Arabia", (), "caution", 10, "Near the Yemen border (missile and drone activity)."),
    "mali": ("Mali", ("GA",), "caution", 10, "Armed groups with weapons that can reach low-flying aircraft. US carriers are restricted at lower levels."),
    "south_sudan": ("South Sudan", ("HJ",), "caution", 10, "Armed conflict and unreliable air traffic services. US carriers are restricted at lower levels."),
    "pakistan": ("Pakistan", ("OP",), "caution", 10, "Security advisory for US carriers: tension and military activity can close airspace at short notice."),
    "venezuela": ("Venezuela", ("SV",), "caution", 10, "Security advisory for US carriers: tension and military activity can close airspace at short notice."),
    "haiti": ("Haiti", ("MT",), "caution", 15, "Gang violence: aircraft have been hit by gunfire at Port-au-Prince. Relief flights still operate with care."),
}
LEVELS = ("restricted", "caution", "off")
SAMPLE_NM = 25            # how often a planned great-circle route is checked

_shapes = None


# areas that aren't a whole country, drawn by hand as [lon, lat] rings
CUSTOM_SHAPES = {
    # the Persian Gulf and the Strait of Hormuz, over water (Dubai, Doha and Bahrain airports sit just outside)
    "persian_gulf": [[[48.0, 30.0], [49.6, 30.1], [50.6, 29.4], [51.4, 27.9], [53.6, 26.8], [55.2, 26.6], [56.3, 27.2],
                      [56.9, 26.6], [56.5, 26.1], [56.2, 25.7], [55.9, 25.6], [55.3, 25.3], [54.4, 24.6], [53.0, 24.3],
                      [51.9, 25.0], [51.75, 26.2], [51.0, 26.35], [50.2, 26.45], [49.4, 27.3], [48.6, 28.2], [48.0, 30.0]]],
    # southern Saudi Arabia along the Yemen border
    "saudi_south": [[[41.6, 19.5], [52.0, 19.5], [55.0, 19.9], [55.6, 18.9], [52.0, 18.9], [47.0, 17.2], [44.0, 17.3],
                     [42.8, 16.4], [41.6, 19.5]]],
}


def _prep(ring):
    """Precompute a ring for point-in-polygon tests, as (bbox, ring, wrapped). A ring that straddles the
    antimeridian (eastern Russia's Chukotka) is unwrapped to a continuous span east of 0 degrees, so the test
    isn't smeared back across the Pacific and over Alaska. Rings that don't cross the date line are left alone."""
    xs = [p[0] for p in ring]
    wrapped = max(xs) - min(xs) > 180
    r = _unwrap(ring) if wrapped else ring
    return (_bbox(r), r, wrapped)


def load_shapes(data_dir):
    global _shapes
    if _shapes is None:
        try:
            raw = json.loads((Path(data_dir) / "conflict_zones_shapes.json").read_text(encoding="utf-8"))
            _shapes = {k: [_prep(r) for r in rings] for k, rings in raw["shapes"].items()}
        except (OSError, ValueError, KeyError):
            _shapes = {}
        for k, rings in CUSTOM_SHAPES.items():
            _shapes[k] = [_prep(r) for r in rings]
    return _shapes


def _bbox(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _inside(lon, lat, ring):
    hit, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def zone_at(lat, lon, shapes, ids):
    """The zone (one of ids) a position is over, or None."""
    if lat is None or lon is None:
        return None
    lon = ((lon + 180) % 360) - 180
    lon_w = lon + 360 if lon < 0 else lon   # same frame as an unwrapped, antimeridian-crossing ring
    for zid in ids:
        for (x0, y0, x1, y1), ring, wrapped in shapes.get(zid, ()):
            x = lon_w if wrapped else lon
            if x0 <= x <= x1 and y0 <= lat <= y1 and _inside(x, lat, ring):
                return zid
    return None


def zones(settings):
    """Every zone with its current level and hazard pay, after staff changes."""
    over = (settings or {}).get("conflict_zone_overrides") or {}
    out = []
    for zid, (name, pref, level, pct, note) in DEFAULT_ZONES.items():
        o = over.get(zid) or {}
        lv = o.get("level") if o.get("level") in LEVELS else level
        try:
            p = max(0, min(50, int(o.get("pct", pct))))
        except (TypeError, ValueError):
            p = pct
        out.append({"id": zid, "name": name, "prefixes": list(pref), "level": lv, "pct": p, "note": note,
                    "default_level": level, "default_pct": pct})
    return out


def enabled(settings):
    return bool((settings or {}).get("conflict_zones_enabled"))


def airport_zone(icao, zlist):
    icao = (icao or "").upper()
    for z in zlist:
        if z["level"] != "off" and any(icao.startswith(p) for p in z["prefixes"]):
            return z
    return None


def restricted_airport(icao, settings):
    """True when the feature is on and this airport sits in a restricted zone, so a flight that departs from or lands
    at it is auto-rejected. Used to keep generated work (checkrides, jobs) out of airspace nobody could legally fly."""
    if not enabled(settings):
        return False
    z = airport_zone(str(icao or "").upper(), zones(settings))
    return bool(z and z["level"] == "restricted")


def _gc_points(lat1, lon1, lat2, lon2, step_nm=SAMPLE_NM):
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    n = max(1, int(d * 3440.065 / step_nm))
    for i in range(n + 1):
        f = i / n
        if d < 1e-9:
            yield lat1, lon1
            continue
        a, b = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
        y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
        z = a * math.sin(p1) + b * math.sin(p2)
        yield math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def _path(points, step_nm=SAMPLE_NM):
    """A list of [lat, lon] waypoints, filled in along great circles."""
    pts = [(p[0], p[1]) for p in points if p and p[0] is not None and p[1] is not None]
    for a, b in zip(pts, pts[1:]):
        yield from _gc_points(a[0], a[1], b[0], b[1], step_nm)
    if len(pts) == 1:
        yield pts[0]


def crossed(points, zlist, shapes, step_nm=SAMPLE_NM):
    """Zones a route crosses (in order, each once). points are [lat, lon, ...]."""
    active = {z["id"]: z for z in zlist if z["level"] != "off"}
    seen = []
    for lat, lon in _path(points, step_nm):
        zid = zone_at(lat, lon, shapes, active)
        if zid and zid not in seen:
            seen.append(zid)
    return [active[z] for z in seen]


def assess(dep, arr, points, settings, data_dir, step_nm=SAMPLE_NM):
    """What a flight means under the conflict-zone rules.

    dep and arr are {icao, lat, lon}; points are the route (OFP waypoints or the flown track) as [lat, lon, ...].
    Returns None when nothing applies (or the feature is off), else:
      level      restricted or caution (the worst that applies)
      airports   zones of the departure/arrival airports
      crossings  zones the route crosses
      pct        hazard pay % (the highest caution zone involved), for caution only
      text       one line for pilots and staff
    """
    if not enabled(settings):
        return None
    zl, shapes = zones(settings), load_shapes(data_dir)
    ends = [z for z in (airport_zone((dep or {}).get("icao"), zl), airport_zone((arr or {}).get("icao"), zl)) if z]
    route = list(points or [])
    if not route and dep and arr and dep.get("lat") is not None and arr.get("lat") is not None:
        route = [[dep["lat"], dep["lon"]], [arr["lat"], arr["lon"]]]
    over = [z for z in crossed(route, zl, shapes, step_nm) if z["id"] not in {e["id"] for e in ends}]
    involved = ends + over
    if not involved:
        return None
    restricted_end = [z for z in ends if z["level"] == "restricted"]
    restricted_over = [z for z in over if z["level"] == "restricted"]
    caution = [z for z in involved if z["level"] == "caution"]
    level = "restricted" if (restricted_end or restricted_over) else "caution"
    names = lambda zs: ", ".join(dict.fromkeys(z["name"] for z in zs))  # noqa: E731
    if restricted_end:
        text = f"Not authorized: {names(restricted_end)} is restricted airspace for PAC."
    elif restricted_over:
        text = f"Route crosses restricted airspace ({names(restricted_over)}). Plan around it."
    else:
        text = f"Caution area ({names(caution)}): hazard pay applies."
    return {"level": level, "airports": [z["id"] for z in ends], "crossings": [z["id"] for z in over],
            "restricted_airport": bool(restricted_end), "restricted_crossing": bool(restricted_over),
            "zones": [{"id": z["id"], "name": z["name"], "level": z["level"]} for z in involved],
            "pct": max((z["pct"] for z in caution), default=0) if level == "caution" else 0, "text": text}


def public(settings):
    """What the website needs to tag flights: the switch and each active zone's prefixes."""
    return {"enabled": enabled(settings),
            "zones": [{k: z[k] for k in ("id", "name", "prefixes", "level", "pct", "note")} for z in zones(settings) if z["level"] != "off"]}


def _unwrap(ring):
    """A ring that crosses the date line (eastern Russia) is drawn as one piece east of 180 degrees, not as a band
    across the whole map."""
    xs = [p[0] for p in ring]
    if max(xs) - min(xs) <= 180:
        return ring
    return [[x + 360 if x < 0 else x, y] for x, y in ring]


def geojson(settings, data_dir):
    """Active zones as GeoJSON for the maps (outlines approximate, rounded to 0.05 degrees)."""
    if not enabled(settings):
        return {"type": "FeatureCollection", "features": []}
    shapes = load_shapes(data_dir)
    feats = []
    for z in zones(settings):
        if z["level"] == "off" or not shapes.get(z["id"]):
            continue
        feats.append({"type": "Feature",
                      "properties": {"id": z["id"], "name": z["name"], "level": z["level"], "pct": z["pct"], "note": z["note"]},
                      "geometry": {"type": "MultiPolygon", "coordinates": [[ring] for _bb, ring, _w in shapes[z["id"]]]}})
    return {"type": "FeatureCollection", "features": feats}
